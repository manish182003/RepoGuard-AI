import pytest
from app.tools.github import GitHubTool
from app.schemas.github import FileEntry,FileContent

def test_parse_repository_url():
    tool=GitHubTool()

    owner,repository=tool.parse_repository_url("https://github.com/facebook/react")

    assert owner=="facebook"
    assert repository=="react"

def test_invalid_repository_url():
    tool=GitHubTool()

    with pytest.raises(ValueError):
        tool.parse_repository_url("https://example.com/something")


def test_file_entry():
    file_entry = FileEntry(
        path="src/main.py",
        sha="abc123",
        size=100,
        url="https://api.github.com/example",
        html_url="https://github.com/example/example/blob/main/src/main.py",
        git_url="https://api.github.com/example",
        download_url=None,
        type="blob",
    )

    assert file_entry.path == "src/main.py"
    assert file_entry.type == "blob"
    assert file_entry.size == 100

def test_file_content():
    file_content=FileContent(
        path="README",
        sha="abc123",
        size=13,
        content="SGVsbG8gV29ybGQhCg==",
        encoding="base64",
    )

    assert file_content.path=="README"
    assert file_content.size==13
    assert file_content.encoding=="base64"


@pytest.mark.asyncio
async def test_find_existing_pull_request_for_issue(monkeypatch):
    import httpx
    tool = GitHubTool()

    async def mock_get(self, url, headers=None, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "total_count": 1,
                    "items": [
                        {
                            "number": 13202,
                            "title": "fix: reject datetime numeric ordering filters (fixes #13201)",
                            "body": "Resolves issue #13201 with FilterError",
                            "state": "open",
                            "html_url": "https://github.com/deepset-ai/haystack/pull/13202",
                            "user": {"login": "contributor123"},
                        }
                    ],
                }
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await tool.find_existing_pull_request_for_issue("https://github.com/deepset-ai/haystack", 13201)
    assert res is not None
    assert res["pr_number"] == 13202
    assert res["author"] == "contributor123"
    assert "https://github.com/deepset-ai/haystack/pull/13202" == res["html_url"]


@pytest.mark.asyncio
async def test_find_existing_pull_request_for_issue_none(monkeypatch):
    import httpx
    tool = GitHubTool()

    async def mock_get(self, url, headers=None, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {"total_count": 0, "items": []}
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await tool.find_existing_pull_request_for_issue("https://github.com/deepset-ai/haystack", 99999)
    assert res is None