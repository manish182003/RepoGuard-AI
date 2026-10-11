import subprocess
from pathlib import Path

from app.tools.workspace import RepositoryWorkspaceService

def run_git(cwd:Path,*args:str)->None:
    subprocess.run(
        ["git",*args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True
    )

def test_create_workspace(tmp_path):
    source_repo=tmp_path / "source"

    source_repo.mkdir()

    run_git(source_repo,"init")

    run_git(source_repo,"config","user.email","test@example.com")
    run_git(source_repo,"config","user.name","RepoGuard Test")
    (source_repo / "example.py").write_text(
        "print('hello')\n",
        encoding='utf-8'
    )

    run_git(source_repo,"add",".")
    run_git(source_repo,"commit","-m","initial commit")

    service=RepositoryWorkspaceService()

    workspace=service.create_workspace(str(source_repo))

    workspace_path=Path(workspace.path)

    try:
        assert workspace_path.exists()
        assert (
            workspace_path / "example.py"
        ).exists()

        assert workspace.branch in {
            "main",
            "master",
            "detached"
        }

        assert len(workspace.commit_sha)==40

    finally:
        import shutil

        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )

    

