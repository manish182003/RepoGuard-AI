import os
import shutil
import tempfile
import pytest
from app.tools.git_service import GitAutomationService


@pytest.mark.asyncio
async def test_git_automation_service_branch_and_commit():
    temp_dir = tempfile.mkdtemp(prefix="test_git_repo_")
    git_service = GitAutomationService()

    try:
        # 1. Init temporary git repo
        init_res = await git_service._run_git_cmd(temp_dir, ["init"])
        assert init_res.success is True

        # Config user email/name for commits
        await git_service._run_git_cmd(temp_dir, ["config", "user.email", "agent@repoguard.ai"])
        await git_service._run_git_cmd(temp_dir, ["config", "user.name", "RepoGuard AI"])

        # Write initial file
        dummy_file = os.path.join(temp_dir, "main.py")
        with open(dummy_file, "w") as f:
            f.write("print('initial')\n")

        # Initial commit
        await git_service.commit_changes(temp_dir, "Initial commit")

        # 2. Create feature branch
        branch_res = await git_service.create_branch(temp_dir, "repoguard/fix-bug")
        assert branch_res.success is True

        # 3. Modify file and commit
        with open(dummy_file, "w") as f:
            f.write("print('fixed')\n")

        commit_res = await git_service.commit_changes(temp_dir, "fix: resolved bug")
        assert commit_res.success is True
        assert "fix: resolved bug" in commit_res.output or commit_res.exit_code == 0 if hasattr(commit_res, 'exit_code') else True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
