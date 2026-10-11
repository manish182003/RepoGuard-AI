import asyncio
import logging
from typing import Callable, Awaitable
from app.schemas.github import RepositorySnapshot, SourceFile
from app.tools.github import GitHubTool
from app.utils.source import file_content_to_source_file

logger = logging.getLogger(__name__)

class RepositoryIngestionService:
    """
    Build a source level snapshot of a Github Repository with concurrency and event streaming.
    """

    def __init__(self, github_tool: GitHubTool | None = None):
        self.github_tool = github_tool or GitHubTool()

    async def build_snapshot(
        self,
        url: str,
        on_event: Callable[[str, dict], Awaitable[None]] | None = None,
        priority_keywords: list[str] | None = None,
    ) -> RepositorySnapshot:
        repository = await self.github_tool.get_repository(url)
        if on_event:
            await on_event("metadata_fetched", {
                "owner": repository.owner,
                "name": repository.name,
                "full_name": repository.full_name,
                "stars": repository.stars,
                "default_branch": repository.default_branch,
            })

        file_entries = await self.github_tool.get_file_tree(url)
        if on_event:
            await on_event("tree_fetched", {
                "total_files": len(file_entries),
                "default_branch": repository.default_branch,
            })

        candidates = [fe for fe in file_entries if self._should_include(fe.path)]

        # Score and prioritize candidates using issue keywords and core paths
        def score_candidate(fe) -> int:
            path_lower = fe.path.lower()
            score = 0
            if priority_keywords:
                for kw in priority_keywords:
                    if len(kw) > 2 and kw.lower() in path_lower:
                        score += 150

            core_patterns = ["providers/", "engine/", "core/", "src/", "api/", "lib/"]
            if any(cp in path_lower for cp in core_patterns):
                score += 50

            aux_patterns = ["scripts/", "benchmarks/", "tests/", "testing/", "docs/", "examples/", "dify/", "zapier/"]
            if any(ap in path_lower for ap in aux_patterns):
                score -= 30

            return score

        candidates.sort(key=score_candidate, reverse=True)
        if len(candidates) > 150:
            candidates = candidates[:150]

        if on_event:
            await on_event("files_selected", {
                "count": len(candidates),
                "total_tree": len(file_entries),
            })

        source_files: list[SourceFile] = []
        sem = asyncio.Semaphore(12)
        completed = 0
        total_cand = len(candidates)

        async def fetch_file(fe):
            nonlocal completed
            async with sem:
                try:
                    file_content = await self.github_tool.get_file_content(url, fe.path)
                    source_file = file_content_to_source_file(file_content=file_content)
                    completed += 1
                    if on_event and (completed % 10 == 0 or completed == total_cand):
                        await on_event("files_fetching_progress", {
                            "completed": completed,
                            "total": total_cand,
                            "percent": int((completed / total_cand) * 100),
                            "current_file": fe.path,
                        })
                    if source_file.language != "unknown":
                        return source_file
                except Exception as err:
                    completed += 1
                    logger.debug(f"Failed to fetch content for {fe.path}: {err}")
                return None

        tasks = [fetch_file(fe) for fe in candidates]
        results = await asyncio.gather(*tasks)
        source_files = [sf for sf in results if sf is not None]

        return RepositorySnapshot(
            repository=repository,
            files=source_files,
        )


    def _should_include(self,path:str)->bool:
        excluded_directories={
            ".git/",
            "__pycache__",
            "node_modules/",
            ".venv/",
            "venv/",
            "dist/",
            "build/"
        }

        supported_extensions={
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx"
        }

        normalized_path=path.replace("\\","/")

        for directory in excluded_directories:
            if directory in normalized_path:
                return False

        return any(
            normalized_path.endswith(extension)
            for extension in supported_extensions
        )

