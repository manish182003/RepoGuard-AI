import shutil
import subprocess
import tempfile
from pathlib import Path

from app.schemas.workspace import RepositoryWorkspace

class RepositoryWorkspaceService:
    """Create and Manage local Git repository workspaces"""

    def create_workspace(self,repository_url:str,branch:str | None=None)->RepositoryWorkspace:
        workspace_path=Path(
            tempfile.mkdtemp(prefix="repoguard-")
        )

        command=[
            "git",
            "clone"
        ]

        if branch:
            command.extend(
                [
                    "--branch",
                    branch
                ]
            )

        command.extend(
            [
                repository_url,
                str(workspace_path)
            ]
        )

        result=subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode!=0:
            shutil.rmtree(
                workspace_path,
                ignore_errors=True
            )
            raise RuntimeError(
                "Failed to clone the repository: ",
                f"{result.stderr.strip()}" 
            )

        commit_sha=self._get_commit_sha(workspace_path)
        current_branch=self._get_current_branch(workspace_path)

        return RepositoryWorkspace(
            repository_url=repository_url,
            path=str(workspace_path),
            branch=current_branch,
            commit_sha=commit_sha
        )

    def _get_commit_sha(self,workspace_path:Path)->str:
        result=subprocess.run(
            ["git","-C",str(workspace_path),"rev-parse","HEAD"],
            capture_output=True,
            text=True,
            check=True
        )

        return result.stdout.strip()

    def _get_current_branch(self,workspace_path:Path)->str:
        result=subprocess.run(
            ["git","-C",str(workspace_path),"branch","--show-current"],
            capture_output=True,
            text=True,
            check=True
        )

        branch=result.stdout.strip()

        if branch:
            return branch

        return "detached"