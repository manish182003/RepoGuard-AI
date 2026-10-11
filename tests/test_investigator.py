import pytest
from app.agents.investigator import GroqInvestigator
from app.llm import FakeLLMProvider
from app.schemas.context import RepositoryContext
from app.schemas.github import FileEntry, IssueInfo, RepositoryInfo, RepositorySnapshot, SourceFile


@pytest.fixture
def mock_repository_context():
    repo = RepositoryInfo(
        owner="psf",
        name="requests",
        full_name="psf/requests",
        default_branch="main",
        description="Python HTTP for Humans.",
        stars=50000,
        forks=10000,
        is_private=False,
    )

    tree = [
        FileEntry(
            path="src/requests/api.py",
            sha="12345",
            size=100,
            url="https://api.github.com/repos/psf/requests/contents/src/requests/api.py",
            html_url="https://github.com/psf/requests/blob/main/src/requests/api.py",
            type="file",
        )
    ]

    files = [
        SourceFile(
            path="src/requests/api.py",
            sha="12345",
            content="def get(url, **kwargs):\n    return request('get', url, **kwargs)\n",
            language="python",
            size=70,
        )
    ]

    snapshot = RepositorySnapshot(
        repository=repo,
        tree=tree,
        files=files,
    )

    issues = [
        IssueInfo(
            number=1,
            title="Missing timeout setting",
            body="Requests without explicit timeout may hang indefinitely.",
            state="open",
            labels=["bug"],
            html_url="https://github.com/psf/requests/issues/1",
            user_login="testuser",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    ]

    return RepositoryContext(snapshot=snapshot, existing_issues=issues)


@pytest.mark.asyncio
async def test_investigator_with_fake_provider(mock_repository_context):
    fake_payload = {
        "summary": "Found request call without timeout",
        "hypotheses": [
            {
                "title": "Missing timeout parameter in get()",
                "description": "get function forwards kwargs to request without enforcing a default timeout.",
                "path": "src/requests/api.py",
                "line": 2,
                "severity": "medium",
                "evidence": ["return request('get', url, **kwargs)"],
                "confidence": 0.8,
            }
        ],
    }

    provider = FakeLLMProvider(response_content=fake_payload)
    investigator = GroqInvestigator(provider=provider)

    result = await investigator.investigate(mock_repository_context)

    assert result.summary == "Found request call without timeout"
    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].path == "src/requests/api.py"
    assert result.hypotheses[0].confidence == 0.8
