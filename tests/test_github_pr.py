import pytest
import httpx
from app.core.policy import PolicyEngine, SecurityPolicy
from app.tools.github_pr import GitHubPRAutomation, PRCreationRequest


@pytest.mark.asyncio
async def test_github_pr_blocked_without_human_approval():
    policy = PolicyEngine(SecurityPolicy(require_human_approval_for_prs=True))
    automation = GitHubPRAutomation(github_token="fake_token", policy_engine=policy)

    req = PRCreationRequest(
        repository_owner="owner",
        repository_name="repo",
        branch_name="fix-branch",
        title="Fix bug",
        body="Fix description",
        head_branch="fix-branch",
        human_approved=False,
    )

    res = await automation.create_pull_request(req)
    assert res.success is False
    assert "blocked by policy" in res.error


@pytest.mark.asyncio
async def test_github_pr_success_mock_transport():
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url == "https://api.github.com/repos/owner/repo/pulls":
            return httpx.Response(
                status_code=201,
                json={
                    "number": 101,
                    "html_url": "https://github.com/owner/repo/pull/101",
                },
            )
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handle_request)
    policy = PolicyEngine(SecurityPolicy(require_human_approval_for_prs=True))

    async with httpx.AsyncClient(transport=transport) as client:
        automation = GitHubPRAutomation(
            github_token="fake_token",
            policy_engine=policy,
            http_client=client,
        )

        req = PRCreationRequest(
            repository_owner="owner",
            repository_name="repo",
            branch_name="fix-branch",
            title="Fix bug",
            body="Fix description",
            head_branch="fix-branch",
            human_approved=True,
        )

        res = await automation.create_pull_request(req)

        assert res.success is True
        assert res.pr_number == 101
        assert res.html_url == "https://github.com/owner/repo/pull/101"


@pytest.mark.asyncio
async def test_github_pr_create_remote_branch_and_commit():
    def handle_request(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/git/ref/heads/feature-branch" in url_str:
            return httpx.Response(404)
        if "/git/ref/heads/main" in url_str:
            return httpx.Response(200, json={"object": {"sha": "base123"}})
        if "/git/refs" in url_str and request.method == "POST":
            return httpx.Response(201, json={"ref": "refs/heads/feature-branch"})
        if "/contents/test.py" in url_str and request.method == "GET":
            return httpx.Response(200, json={"sha": "file123"})
        if "/contents/test.py" in url_str and request.method == "PUT":
            return httpx.Response(200, json={"commit": {"sha": "commit123"}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        automation = GitHubPRAutomation(github_token="fake_token", http_client=client)

        success = await automation.prepare_branch_and_commit(
            owner="owner",
            repo="repo",
            branch_name="feature-branch",
            base_branch="main",
            file_path="test.py",
            modified_content="# updated",
            commit_message="fix test",
        )
        assert success is True
