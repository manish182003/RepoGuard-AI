import pytest
import httpx
from app.services.jev_client import JevDecisionService, JevIssueEvaluation, JevPatchEvaluation
from app.core.policy import PolicyEngine


@pytest.mark.asyncio
async def test_jev_triage_issue_success(monkeypatch):
    service = JevDecisionService(api_key="fake-key")

    mock_answers = {
        "is_actionable_bug": {"type": "noul", "noul": 0.88},
        "category": {
            "type": "choice",
            "choice": "logic_defect",
            "confidence": 0.95,
            "probabilities": {"logic_defect": 0.95, "crash": 0.05, "feature_request": 0.0},
        },
    }

    async def mock_post(*args, **kwargs):
        class MockResp:
            status_code = 200
            def json(self):
                return {"answers": mock_answers}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    triage = await service.triage_issue(
        title="Negative timestamp raises ValueError",
        body="Dates before 1970 fail in from_timestamp",
    )

    assert triage.is_actionable_bug is True
    assert triage.bug_probability == 0.88
    assert triage.category == "logic_defect"
    assert triage.confidence == 0.95


@pytest.mark.asyncio
async def test_jev_patch_risk_evaluation(monkeypatch):
    service = JevDecisionService(api_key="fake-key")

    mock_answers = {
        "is_safe_remediation": {"type": "noul", "noul": 0.92},
        "risk_tier": {
            "type": "choice",
            "choice": "low",
            "confidence": 0.85,
            "probabilities": {"low": 0.85, "medium": 0.15, "high": 0.0},
        },
    }

    async def mock_post(*args, **kwargs):
        class MockResp:
            status_code = 200
            def json(self):
                return {"answers": mock_answers}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    eval_res = await service.evaluate_patch_risk(
        patch_summary="Remove negative timestamp check",
        target_file="src/marshmallow/utils.py",
        diff="- if value < 0: raise ValueError()",
    )

    assert eval_res.is_safe is True
    assert eval_res.safety_probability == 0.92
    assert eval_res.risk_tier == "low"


@pytest.mark.asyncio
async def test_jev_fallback_when_api_fails(monkeypatch):
    service = JevDecisionService(api_key="fake-key")

    async def mock_post_err(*args, **kwargs):
        raise httpx.RequestError("Network error")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_err)

    triage = await service.triage_issue(
        title="Crash bug in parser",
        body="Unexpected KeyError thrown",
    )
    assert triage.is_actionable_bug is True
    assert triage.category == "logic_defect"


@pytest.mark.asyncio
async def test_policy_engine_with_jev(monkeypatch):
    engine = PolicyEngine()

    mock_answers = {
        "is_safe_remediation": {"type": "noul", "noul": 0.75},
        "risk_tier": {
            "type": "choice",
            "choice": "medium",
            "confidence": 0.70,
            "probabilities": {"low": 0.20, "medium": 0.70, "high": 0.10},
        },
    }

    async def mock_post(*args, **kwargs):
        class MockResp:
            status_code = 200
            def json(self):
                return {"answers": mock_answers}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    decision = await engine.evaluate_action_with_jev(
        action="open_pr",
        human_approved=False,
        patch_summary="Fix learning rate scheduler floor",
        target_file="ignite/handlers/param_scheduler.py",
    )

    assert decision.allowed is False  # requires human approval
    assert decision.requires_approval is True
    assert decision.risk_level == "medium"
    assert decision.jev_safety_score == 0.75
    assert decision.jev_confidence == 0.70
