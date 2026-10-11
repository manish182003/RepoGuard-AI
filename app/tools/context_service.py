from typing import Callable, Awaitable
from app.schemas.context import RepositoryContext
from app.tools.repository import RepositoryIngestionService
from app.tools.github import GitHubTool


class RepositoryContextService:
    def __init__(
        self,
        repository_service: RepositoryIngestionService | None = None,
        github_tool: GitHubTool | None = None,
    ):
        self.repository_service = repository_service or RepositoryIngestionService()
        self.github_tool = github_tool or self.repository_service.github_tool

    async def build_context(
        self,
        url: str,
        issue_state: str = "open",
        on_event: Callable[[str, dict], Awaitable[None]] | None = None,
        priority_keywords: list[str] | None = None,
    ) -> RepositoryContext:
        snapshot = await self.repository_service.build_snapshot(
            url, on_event=on_event, priority_keywords=priority_keywords
        )

        issues = await self.github_tool.get_issues(url, issue_state)
        if on_event:
            await on_event("issues_fetched", {
                "count": len(issues),
                "state": issue_state,
                "sample_titles": [i.title for i in issues[:3]],
            })

        return RepositoryContext(
            snapshot=snapshot,
            existing_issues=issues,
        )
