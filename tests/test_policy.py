from app.core.policy import PolicyEngine, SecurityPolicy


def test_policy_read_only_action():
    engine = PolicyEngine()
    decision = engine.evaluate_action("read_code")
    assert decision.allowed is True
    assert decision.risk_level == "low"
    assert decision.requires_approval is False


def test_policy_open_pr_unapproved():
    engine = PolicyEngine()
    decision = engine.evaluate_action("open_pr", human_approved=False)
    assert decision.allowed is False
    assert decision.risk_level == "high"
    assert decision.requires_approval is True
    assert "requires explicit human approval" in decision.reason


def test_policy_open_pr_approved():
    engine = PolicyEngine()
    decision = engine.evaluate_action("open_pr", human_approved=True)
    assert decision.allowed is True
    assert decision.risk_level == "high"


def test_policy_secret_redaction():
    engine = PolicyEngine()
    raw = "My key is ghp_123456789012345678901234567890123456 and gsk_abcdef1234567890abcdef1234567890abcdef12345678"
    sanitized = engine.redact_secrets(raw)

    assert "ghp_" not in sanitized
    assert "gsk_" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
