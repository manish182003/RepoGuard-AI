import asyncio
import logging
import os
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GitOperationResult(BaseModel):
    success: bool
    command: str
    output: str
    error: str | None = None


class GitAutomationService:
    """Automates local git repository operations: branching, committing, and pushing."""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    async def _run_git_cmd(self, cwd: str, args: list[str]) -> GitOperationResult:
        cmd_str = f"git {' '.join(args)}"
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=float(self.timeout_seconds),
            )
            exit_code = process.returncode or 0
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            output_text = (stdout_str + "\n" + stderr_str).strip()

            if exit_code != 0:
                return GitOperationResult(
                    success=False,
                    command=cmd_str,
                    output=output_text,
                    error=f"Git command failed with exit code {exit_code}: {stderr_str}",
                )

            return GitOperationResult(
                success=True,
                command=cmd_str,
                output=output_text,
            )

        except asyncio.TimeoutError:
            return GitOperationResult(
                success=False,
                command=cmd_str,
                output="",
                error=f"Git command timed out after {self.timeout_seconds}s",
            )
        except Exception as exc:
            return GitOperationResult(
                success=False,
                command=cmd_str,
                output="",
                error=f"Git execution error: {exc}",
            )

    async def create_branch(self, cwd: str, branch_name: str) -> GitOperationResult:
        """Create and checkout a new git branch."""
        return await self._run_git_cmd(cwd, ["checkout", "-b", branch_name])

    async def commit_changes(self, cwd: str, commit_message: str) -> GitOperationResult:
        """Stage all modified files and create a git commit."""
        add_res = await self._run_git_cmd(cwd, ["add", "."])
        if not add_res.success:
            return add_res
        return await self._run_git_cmd(cwd, ["commit", "-m", commit_message])

    async def push_branch(self, cwd: str, remote_name_or_url: str, branch_name: str) -> GitOperationResult:
        """Push branch to remote repository."""
        return await self._run_git_cmd(cwd, ["push", remote_name_or_url, branch_name])
