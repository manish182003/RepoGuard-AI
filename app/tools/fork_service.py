import logging
from typing import Any
import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class ForkDetails(BaseModel):
    is_fork: bool
    owner: str
    name: str
    full_name: str
    clone_url: str
    parent_owner: str
    parent_name: str
    parent_full_name: str
    default_branch: str = "main"


class GitHubForkService:
    """Automates checking repository write permissions and creating GitHub forks when required."""

    def __init__(
        self,
        github_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.github_token = github_token or settings.github_token
        self.http_client = http_client

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "RepoGuard-AI",
        }
        if self.github_token:
            auth_prefix = "Bearer" if self.github_token.startswith("ghp_") or self.github_token.startswith("github_pat_") else "token"
            headers["Authorization"] = f"{auth_prefix} {self.github_token}"
        return headers

    async def get_authenticated_user(self, client: httpx.AsyncClient) -> str:
        """Fetch current authenticated user login handle."""
        headers = self._get_headers()
        res = await client.get("https://api.github.com/user", headers=headers, timeout=10.0)
        res.raise_for_status()
        data = res.json()
        return data["login"]

    async def check_write_permission(self, owner: str, repo: str) -> tuple[bool, str, str]:
        """Check if authenticated user has write/push permission on repository.

        Returns (has_permission: bool, user_login: str, default_branch: str).
        """
        if not self.github_token:
            return False, "", "main"

        client = self.http_client or httpx.AsyncClient()
        headers = self._get_headers()

        try:
            user_login = await self.get_authenticated_user(client)
            res = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers,
                timeout=10.0,
            )
            res.raise_for_status()
            data = res.json()
            permissions = data.get("permissions", {})
            has_push = permissions.get("push", False) or permissions.get("admin", False)
            default_branch = data.get("default_branch", "main")

            return has_push, user_login, default_branch
        except Exception as exc:
            logger.warning(f"Permission check failed for {owner}/{repo}: {exc}")
            return False, "", "main"
        finally:
            if self.http_client is None:
                await client.aclose()

    async def ensure_fork(self, owner: str, repo: str) -> ForkDetails:
        """Ensure a fork exists for non-writable target repositories."""
        if not self.github_token:
            raise ValueError("GitHub API token is not configured.")

        client = self.http_client or httpx.AsyncClient()
        headers = self._get_headers()

        try:
            has_push, user_login, parent_default_branch = await self.check_write_permission(owner, repo)

            if has_push:
                return ForkDetails(
                    is_fork=False,
                    owner=owner,
                    name=repo,
                    full_name=f"{owner}/{repo}",
                    clone_url=f"https://github.com/{owner}/{repo}.git",
                    parent_owner=owner,
                    parent_name=repo,
                    parent_full_name=f"{owner}/{repo}",
                    default_branch=parent_default_branch,
                )

            # Otherwise, check if fork already exists under user's account
            fork_res = await client.get(
                f"https://api.github.com/repos/{user_login}/{repo}",
                headers=headers,
                timeout=10.0,
            )

            if fork_res.status_code == 200:
                fork_data = fork_res.json()
                return ForkDetails(
                    is_fork=True,
                    owner=user_login,
                    name=repo,
                    full_name=f"{user_login}/{repo}",
                    clone_url=f"https://github.com/{user_login}/{repo}.git",
                    parent_owner=owner,
                    parent_name=repo,
                    parent_full_name=f"{owner}/{repo}",
                    default_branch=fork_data.get("default_branch") or parent_default_branch,
                )

            # Fork does not exist yet; send POST /repos/{owner}/{repo}/forks request
            create_res = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/forks",
                headers=headers,
                timeout=15.0,
            )
            if create_res.status_code in (403, 404):
                raise PermissionError(
                    f"GitHub API returned {create_res.status_code} when attempting to fork '{owner}/{repo}'. "
                    f"Your GitHub token (@{user_login}) is missing write permissions. "
                    f"Please ensure your GitHub Personal Access Token includes the 'public_repo' or 'repo' scope."
                )
            create_res.raise_for_status()
            created_data = create_res.json()

            return ForkDetails(
                is_fork=True,
                owner=user_login,
                name=repo,
                full_name=f"{user_login}/{repo}",
                clone_url=created_data.get("clone_url", f"https://github.com/{user_login}/{repo}.git"),
                parent_owner=owner,
                parent_name=repo,
                parent_full_name=f"{owner}/{repo}",
                default_branch=created_data.get("default_branch") or parent_default_branch,
            )
        finally:
            if self.http_client is None:
                await client.aclose()
