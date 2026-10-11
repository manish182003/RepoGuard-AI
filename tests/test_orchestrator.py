from unittest.mock import AsyncMock, patch
import pytest

from app.llm import FakeLLMProvider
from app.schemas.context import RepositoryContext
from app.schemas.github import RepositoryInfo, RepositorySnapshot, SourceFile
from app.services.orchestrator import RepoGuardOrchestrator


@pytest.fixture
def mock_context():
    repo = RepositoryInfo(
        owner="owner",
        name="repo",
        full_name="owner/repo",
        default_branch="main",
        stars=10,
        forks=2,
        is_private=False,
    )
    files = [
        SourceFile(
            path="app/main.py",
            sha="123",
            content="def compute(val):\n    return requests.get(val)\n",
            language="python",
            size=45,
        )
    ]
    snapshot = RepositorySnapshot(repository=repo, files=files)
    return RepositoryContext(snapshot=snapshot, existing_issues=[])


@pytest.mark.asyncio
@patch("app.tools.context_service.RepositoryContextService.build_context")
async def test_orchestrator_pipeline_flow(mock_build_context, mock_context):
    mock_build_context.return_value = mock_context

    agent_response = {
        "action": "final_result",
        "summary": "Detected missing timeout parameter in compute()",
        "hypotheses": [
            {
                "title": "Missing timeout parameter",
                "description": "Call to requests.get lacks explicit timeout",
                "path": "app/main.py",
                "line": 2,
                "severity": "medium",
                "evidence": ["return requests.get(val)"],
                "confidence": 0.8,
            }
        ],
    }

    patch_response = {
        "path": "app/main.py",
        "target_code": "requests.get(val)",
        "replacement_code": "requests.get(val, timeout=10)",
        "explanation": "Add explicit timeout parameter.",
        "regression_test_code": "def test_compute(): pass",
    }

    # Use fake provider with responses
    provider = FakeLLMProvider(response_content=agent_response)
    orchestrator = RepoGuardOrchestrator(llm_provider=provider)

    # Patch PatchGenerator.generate_patch to return valid patch
    with patch("app.tools.patch_generator.PatchGenerator.generate_patch") as mock_gen_patch:
        from app.tools.patch_generator import GeneratedPatch
        mock_gen_patch.return_value = GeneratedPatch.model_validate(patch_response)

        result = await orchestrator.run_pipeline(
            repository_url="https://github.com/owner/repo",
            auto_generate_patch=True,
            human_approved_for_pr=False,
        )

        assert result.repository == "owner/repo"
        assert result.status == "completed"
        assert len(result.findings) == 1
        assert len(result.patches) == 1
        assert result.patches[0]["verification"]["success"] is True
        assert result.findings[0].status == "fixed"


@pytest.mark.asyncio
@patch("app.tools.context_service.RepositoryContextService.build_context")
async def test_orchestrator_targeted_issue_pipeline(mock_build_context, mock_context):
    from app.schemas.github import IssueInfo
    issue = IssueInfo(
        number=1470,
        title="MultipartParser fails on files above 102400 bytes",
        body="Raises MultipartError when file exceeds MEMFILE_MAX",
        state="open",
        labels=["bug"],
        html_url="https://github.com/owner/repo/issues/1470",
        user_login="reporter",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    mock_context.existing_issues = [issue]
    mock_build_context.return_value = mock_context

    agent_response = {
        "action": "final_result",
        "summary": "Investigated Issue #1470 and identified MEMFILE_MAX limit",
        "hypotheses": [
            {
                "title": "MultipartParser MEMFILE_MAX limit defect",
                "description": "Hardcoded memory limit causes MultipartError on files above 102400 bytes",
                "path": "app/main.py",
                "line": 2,
                "severity": "high",
                "evidence": ["requests.get(val)"],
                "confidence": 0.9,
                "related_issue_id": 1470,
            }
        ],
    }

    patch_response = {
        "path": "app/main.py",
        "target_code": "requests.get(val)",
        "replacement_code": "requests.get(val, timeout=10)",
        "explanation": "Fixes Issue #1470 by increasing memory limit buffer.",
        "regression_test_code": "def test_compute(): pass",
    }

    provider = FakeLLMProvider(response_content=agent_response)
    orchestrator = RepoGuardOrchestrator(llm_provider=provider)

    events_emitted = []
    async def capture_event(ev, data):
        events_emitted.append((ev, data))

    with patch("app.tools.patch_generator.PatchGenerator.generate_patch") as mock_gen_patch:
        from app.tools.patch_generator import GeneratedPatch
        mock_gen_patch.return_value = GeneratedPatch.model_validate(patch_response)

        result = await orchestrator.run_pipeline(
            repository_url="https://github.com/owner/repo",
            auto_generate_patch=True,
            human_approved_for_pr=False,
            target_issue_number=1470,
            on_event=capture_event,
        )

        assert result.status == "completed"
        assert len(result.findings) == 1
        assert result.findings[0].related_issue_id == 1470
        assert any(ev[0] == "issue_targeted" and ev[1]["number"] == 1470 for ev in events_emitted)
        assert len(result.patches) == 1
        assert result.patches[0]["related_issue_id"] == 1470


@pytest.mark.asyncio
@patch("app.tools.context_service.RepositoryContextService.build_context")
async def test_orchestrator_detects_duplicate_pr(mock_build_context, mock_context):
    from app.schemas.github import IssueInfo
    issue = IssueInfo(
        number=13201,
        title="Ordering filters leak TypeError for datetime values",
        body="Ordering metadata filters leak TypeError when compared with numeric scalars",
        state="open",
        labels=["bug"],
        html_url="https://github.com/owner/repo/issues/13201",
        user_login="reporter",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    mock_context.existing_issues = [issue]
    mock_build_context.return_value = mock_context

    agent_response = {
        "action": "final_result",
        "summary": "Investigated Issue #13201",
        "hypotheses": [
            {
                "title": "TypeError in ordering comparison",
                "description": "Comparison between datetime and int raises TypeError",
                "path": "app/main.py",
                "line": 2,
                "severity": "high",
                "evidence": ["requests.get(val)"],
                "confidence": 0.9,
                "related_issue_id": 13201,
            }
        ],
    }

    patch_response = {
        "path": "app/main.py",
        "target_code": "requests.get(val)",
        "replacement_code": "requests.get(val, timeout=10)",
        "explanation": "Fixes datetime ordering filter comparison.",
        "regression_test_code": "def test_filter(): pass",
    }

    provider = FakeLLMProvider(response_content=agent_response)
    orchestrator = RepoGuardOrchestrator(llm_provider=provider)

    events_emitted = []
    async def capture_event(ev, data):
        events_emitted.append((ev, data))

    existing_pr_mock = {
        "pr_number": 13202,
        "title": "fix: reject datetime numeric ordering filters",
        "html_url": "https://github.com/owner/repo/pull/13202",
        "author": "community_contributor",
        "state": "open",
    }

    with patch.object(
        orchestrator.context_service.github_tool,
        "find_existing_pull_request_for_issue",
        new=AsyncMock(return_value=existing_pr_mock),
    ), patch("app.tools.patch_generator.PatchGenerator.generate_patch") as mock_gen_patch:
        from app.tools.patch_generator import GeneratedPatch
        mock_gen_patch.return_value = GeneratedPatch.model_validate(patch_response)

        result = await orchestrator.run_pipeline(
            repository_url="https://github.com/owner/repo",
            auto_generate_patch=True,
            human_approved_for_pr=False,
            target_issue_number=13201,
            on_event=capture_event,
        )

        assert result.status == "completed"
        # Verify duplicate_pr_detected event was emitted
        dup_events = [data for ev, data in events_emitted if ev == "duplicate_pr_detected"]
        assert len(dup_events) == 1
        assert dup_events[0]["issue_number"] == 13201
        assert dup_events[0]["existing_pr"]["pr_number"] == 13202

        # Verify human_approval_required payload contains warning
        approval_events = [data for ev, data in events_emitted if ev == "human_approval_required"]
        assert len(approval_events) == 1
        assert "existing_pr_warning" in approval_events[0]
        assert "13202" in approval_events[0]["existing_pr_warning"]

        # Verify target_issue was passed to generate_patch
        assert mock_gen_patch.call_count >= 1
        _, kwargs = mock_gen_patch.call_args
        assert kwargs.get("target_issue") == issue
