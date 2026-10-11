import re
import httpx
from typing import Any
from app.core.config import settings
from app.schemas.github import RepositoryInfo,FileEntry,FileContent,IssueInfo
GITHUB_API="https://api.github.com"

class GitHubTool:
    """Tool for interacting with the Github API."""

    def __init__(self):
        self.headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if settings.github_token:
            self.headers["Authorization"]=(
                f"Bearer {settings.github_token}"
            )

    def parse_repository_url(self,url:str)->tuple[str,str]:
        pattern = r"^https?://github\.com/([^/]+)/([^/#]+?)/?$"

        match=re.match(pattern,url)

        if not match:
            raise ValueError("Invalid GitHub repository URL")

        owner=match.group(1)
        repository=match.group(2)

        return owner,repository

    async def get_repository(self,url:str)->RepositoryInfo:
        owner,repository=self.parse_repository_url(url)

        api_url=f"{GITHUB_API}/repos/{owner}/{repository}"

        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
            response=await client.get(api_url,headers=self.headers)


        if response.status_code in (301,302,307,308):
            redirect_url=response.headers.get("Location")


            if not redirect_url:
                raise RuntimeError("Github returned an redirect without a location")

            raise RuntimeError(
                f"Github redirected the requested repository to: {redirect_url}"
            )

        response.raise_for_status()

        data=response.json()

        returned_owner=data["owner"]["login"]
        returned_repository=data["name"]

        if (returned_owner.lower()!=owner.lower() or returned_repository.lower()!=repository.lower()):
            raise RuntimeError(
                f"Github returned a different repository than requested: {returned_owner}/{returned_repository}"
            )


        return RepositoryInfo(
            owner=data["owner"]["login"],
            name=data["name"],
            full_name=data["full_name"],
            default_branch=data["default_branch"],
            description=data["description"],
            stars=data["stargazers_count"],
            forks=data["forks_count"],
            is_private=data["private"]
        )

    async def get_file_tree(self,url:str)->list[FileEntry]:
        owner,repository=self.parse_repository_url(url)

        repository_info=await self.get_repository(url)

        api_url=(
            f"{GITHUB_API}/repos/"
            f"{owner}/{repository}/git/trees/"
            f"{repository_info.default_branch}"
        )

        params={
            "recursive":"1"
        }

        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.get(api_url,headers=self.headers,params=params)

        response.raise_for_status()
        data=response.json()

        entries:list[FileEntry]=[]

        for item in data.get("tree",[]):
            if item.get("type")!="blob":
                continue

            entries.append(
                FileEntry(
                    path=item["path"],
                    sha=item["sha"],
                    size=item.get("size"),
                    url=item["url"],
                    html_url=(
                        f"https://github.com/"
                        f"{owner}/{repository}/blob/"
                        f"{repository_info.default_branch}/"
                        f"{item["path"]}"
                    ),
                    git_url=item.get("url"),
                    download_url=None,
                    type=item["type"]
                )
            )

        return entries

    async def get_file_content(self,url:str,path:str)->FileContent:
        owner,repository=self.parse_repository_url(url)

        api_url=(
            f"{GITHUB_API}/repos/"
            f"{owner}/{repository}/contents/{path}"
        )

        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response= await client.get(api_url,headers=self.headers)

        if response.status_code in (301,302,307,308):
            redirect_url=response.headers.get("Location")

            if not redirect_url:
                raise RuntimeError(
                    "Github return a redirect without Location"
                )

            raise RuntimeError(
                f"Github redirected the requested repository to: {redirect_url}"
            )

        response.raise_for_status()

        data=response.json()

        if data.get("type")!="file":
            raise ValueError(
                f"Requested path is not a file: {path}"
            )

        return FileContent(
            path=data["path"],
            sha=data["sha"],
            size=data["size"],
            content=data["content"],
            encoding=data["encoding"]
        )

    async def get_issues(self,url:str,state:str="open")->list[IssueInfo]:
        owner,repository=self.parse_repository_url(url)

        api_url=(
            f"{GITHUB_API}/repos/"
            f"{owner}/{repository}/issues"
        )

        params={
            "state":state,
            "per_page":100
        }

        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.get(
                api_url,
                headers=self.headers,
                params=params
            )

        if response.status_code in (301,302,307,308):
            redirect_url=response.headers.get("Location")

            if not redirect_url:
                raise RuntimeError(
                    "Github retruned a redirect without a location."
                )

            raise RuntimeError(
                    "Github redirected the requested repository to: "
                    f"{redirect_url}"
                )

        response.raise_for_status()

        data=response.json()

        issues=[]

        for item in data:
            if "pull_request" in item:
                continue

            issues.append(
                IssueInfo(
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body"),
                    state=item["state"],
                    labels=[
                        label["name"]
                        for label in item.get("labels",[])
                    ],
                    html_url=item["html_url"],
                    user_login=(
                        item.get("user",{}) or {}
                    ).get("login"),
                    created_at=item["created_at"],
                    updated_at=item["updated_at"]
                )
            )

        return issues

    async def get_issue(self, url: str, issue_number: int) -> IssueInfo:
        """Fetch a specific issue by number directly from GitHub API."""
        owner, repository = self.parse_repository_url(url)
        api_url = f"{GITHUB_API}/repos/{owner}/{repository}/issues/{issue_number}"

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(api_url, headers=self.headers)

        resp.raise_for_status()
        item = resp.json()

        return IssueInfo(
            number=item["number"],
            title=item["title"],
            body=item.get("body"),
            state=item["state"],
            labels=[label["name"] for label in item.get("labels", [])],
            html_url=item["html_url"],
            user_login=(item.get("user", {}) or {}).get("login"),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )

    async def find_existing_pull_request_for_issue(self, url: str, issue_number: int) -> dict[str, Any] | None:
        """Check if an open pull request already references or attempts to resolve this issue."""
        try:
            owner, repository = self.parse_repository_url(url)
            search_query = f"repo:{owner}/{repository} is:pr is:open {issue_number}"
            api_url = f"{GITHUB_API}/search/issues?q={search_query}"

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(api_url, headers=self.headers)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        text = f"{item.get('title', '')} {item.get('body', '')}".lower()
                        if (
                            f"#{issue_number}" in text
                            or f"/{issue_number}" in text
                            or f"fixes {issue_number}" in text
                            or f"fix #{issue_number}" in text
                            or str(issue_number) in item.get("title", "")
                        ):
                            return {
                                "pr_number": item["number"],
                                "title": item["title"],
                                "html_url": item["html_url"],
                                "author": (item.get("user") or {}).get("login"),
                                "state": item.get("state"),
                            }
        except Exception:
            pass
        return None


        



