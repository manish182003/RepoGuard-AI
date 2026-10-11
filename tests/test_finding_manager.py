import pytest
from app.schemas.finding import Finding
from app.tools.finding_manager import FindingLifecycleManager


def test_finding_creation_defaults():
    finding = Finding(
        rule="requests_timeout",
        path="app/main.py",
        line=10,
        title="Missing timeout parameter",
        description="Call to requests.get() lacks timeout",
        severity="medium",
        confidence=0.8,
    )

    assert finding.id is not None
    assert finding.status == "candidate"
    assert finding.repro_status == "untested"
    assert finding.fix_status == "unfixed"


def test_finding_dedup_key():
    key1 = FindingLifecycleManager.generate_dedup_key("app/main.py", 10, "requests_timeout")
    key2 = FindingLifecycleManager.generate_dedup_key("app/main.py", 10, "requests_timeout")
    key3 = FindingLifecycleManager.generate_dedup_key("app/main.py", 11, "requests_timeout")

    assert key1 == key2
    assert key1 != key3


def test_valid_finding_transitions():
    finding = Finding(
        rule="requests_timeout",
        path="app/main.py",
        line=10,
        title="Missing timeout parameter",
        description="Call to requests.get() lacks timeout",
    )

    # candidate -> investigating
    finding = FindingLifecycleManager.transition(finding, "investigating", "Starting analysis")
    assert finding.status == "investigating"
    assert finding.status_reason == "Starting analysis"

    # investigating -> supported
    finding = FindingLifecycleManager.transition(finding, "supported", "AST evidence confirmed")
    assert finding.status == "supported"

    # supported -> rejected
    finding = FindingLifecycleManager.transition(finding, "rejected", "Found default timeout config")
    assert finding.status == "rejected"


def test_invalid_finding_transitions():
    finding = Finding(
        rule="requests_timeout",
        path="app/main.py",
        line=10,
        title="Missing timeout parameter",
        description="Call to requests.get() lacks timeout",
        status="candidate",
    )

    # candidate -> validated is invalid (cannot skip investigating/supported/fixed)
    with pytest.raises(ValueError) as exc_info:
        FindingLifecycleManager.transition(finding, "validated", "Skip steps")

    assert "Invalid status transition" in str(exc_info.value)
