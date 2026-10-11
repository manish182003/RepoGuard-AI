import pytest
import httpx
from app.tools.fork_service import GitHubForkService


@pytest.mark.asyncio
async def test_fork_service_writable_repository():
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url == "https://api.github.com/user":
            return httpx.Response(200, json={"login": "myuser"})
        if request.url == "https://api.github.com/repos/owner/repo":
            return httpx.Response(200, json={"permissions": {"push": True}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubForkService(github_token="fake_token", http_client=client)
        details = await service.ensure_fork("owner", "repo")

        assert details.is_fork is False
        assert details.owner == "owner"
        assert details.full_name == "owner/repo"


@pytest.mark.asyncio
async def test_fork_service_creates_fork_when_non_writable():
    def handle_request(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://api.github.com/user":
            return httpx.Response(200, json={"login": "myuser"})
        if url_str == "https://api.github.com/repos/upstream/repo":
            return httpx.Response(200, json={"permissions": {"push": False}})
        if url_str == "https://api.github.com/repos/myuser/repo":
            return httpx.Response(404)
        if url_str == "https://api.github.com/repos/upstream/repo/forks":
            return httpx.Response(202, json={
                "full_name": "myuser/repo",
                "clone_url": "https://github.com/myuser/repo.git",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubForkService(github_token="fake_token", http_client=client)
        details = await service.ensure_fork("upstream", "repo")

        assert details.is_fork is True
        assert details.owner == "myuser"
        assert details.full_name == "myuser/repo"
        assert details.parent_full_name == "upstream/repo"


@pytest.mark.asyncio
async def test_fork_service_missing_token_scope_raises_permission_error():
    def handle_request(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://api.github.com/user":
            return httpx.Response(200, json={"login": "myuser"})
        if url_str == "https://api.github.com/repos/upstream/repo":
            return httpx.Response(200, json={"permissions": {"push": False}})
        if url_str == "https://api.github.com/repos/myuser/repo":
            return httpx.Response(404)
        if url_str == "https://api.github.com/repos/upstream/repo/forks":
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubForkService(github_token="fake_token", http_client=client)
        with pytest.raises(PermissionError) as exc_info:
            await service.ensure_fork("upstream", "repo")
        assert "missing write permissions" in str(exc_info.value)
