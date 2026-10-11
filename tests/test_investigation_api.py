from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.context import RepositoryContext
from app.schemas.github import RepositoryInfo, RepositorySnapshot, SourceFile
from app.schemas.finding import Finding
from app.services.orchestrator import PipelineExecutionResult

client = TestClient(app)


@pytest.fixture
def mock_context():
    repo = RepositoryInfo(
        owner="testowner",
        name="testrepo",
        full_name="testowner/testrepo",
        default_branch="main",
        stars=10,
        forks=2,
        is_private=False,
    )
    files = [
        SourceFile(
            path="main.py",
            sha="123",
            content="print('hello')\n",
            language="python",
            size=15,
        )
    ]
    snapshot = RepositorySnapshot(repository=repo, files=[files[0]])
    return RepositoryContext(snapshot=snapshot, existing_issues=[])


def test_investigation_endpoint_invalid_url():
    response = client.post("/investigation", json={"repository_url": "invalid-url"})
    assert response.status_code == 400
    assert "Invalid GitHub repository URL" in response.json()["detail"]


@patch("app.api.routes.investigation.RepoGuardOrchestrator.run_pipeline")
def test_investigation_endpoint_success(mock_run_pipeline):
    mock_run_pipeline.return_value = PipelineExecutionResult(
        repository="testowner/testrepo",
        status="completed",
        summary="Found candidate defect",
        findings=[
            Finding(
                rule="missing_timeout",
                path="main.py",
                line=1,
                title="Potential missing timeout",
                description="Call without explicit timeout parameter",
                severity="low",
                confidence=0.5,
                evidence=["print('hello')"],
                status="supported",
            )
        ],
        patches=[],
        iterations_used=2,
    )

    response = client.post(
        "/investigation",
        json={"repository_url": "https://github.com/testowner/testrepo"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["repository"] == "testowner/testrepo"
    assert data["summary"] == "Found candidate defect"
    assert len(data["findings"]) == 1
    assert data["findings"][0]["status"] == "supported"


@patch("app.api.routes.investigation.RepoGuardOrchestrator.run_pipeline")
def test_stream_investigation_endpoint(mock_run_pipeline):
    async def mock_run_impl(repository_url, issue_state="open", auto_generate_patch=True, human_approved_for_pr=False, target_issue_number=None, on_event=None, **kwargs):
        if on_event:
            await on_event("pipeline_started", {"repository_url": repository_url})
            await on_event("pipeline_completed", {"repository": "testowner/testrepo", "status": "completed"})
        return PipelineExecutionResult(
            repository="testowner/testrepo",
            status="completed",
            summary="Stream test completed",
            findings=[],
            patches=[],
            iterations_used=1,
        )

    mock_run_pipeline.side_effect = mock_run_impl

    response = client.post(
        "/investigation/stream",
        json={"repository_url": "https://github.com/testowner/testrepo"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    assert "data: {" in body
    assert "pipeline_started" in body
    assert "pipeline_completed" in body
