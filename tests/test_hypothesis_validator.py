import pytest
from app.schemas.context import RepositoryContext
from app.schemas.github import IssueInfo, RepositoryInfo, RepositorySnapshot, SourceFile
from app.schemas.investigation import InvestigationHypothesis
from app.tools.hypothesis_validator import HypothesisValidator


@pytest.fixture
def sample_context():
    repo = RepositoryInfo(
        owner="testowner",
        name="testrepo",
        full_name="testowner/testrepo",
        default_branch="main",
        stars=10,
        forks=2,
        is_private=False,
    )

    valid_py = SourceFile(
        path="app/main.py",
        sha="abc1",
        content="def hello():\n    return 'world'\n",
        language="python",
        size=35,
    )

    invalid_py = SourceFile(
        path="app/broken.py",
        sha="abc2",
        content="def hello(\n",
        language="python",
        size=12,
    )

    snapshot = RepositorySnapshot(
        repository=repo,
        files=[valid_py, invalid_py],
    )

    issues = [
        IssueInfo(
            number=42,
            title="Broken syntax in main.py",
            body="Syntax error reported in main.py",
            state="open",
            labels=[],
            html_url="https://github.com/testowner/testrepo/issues/42",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    ]

    return RepositoryContext(snapshot=snapshot, existing_issues=issues)


def test_validator_rejects_missing_file(sample_context):
    validator = HypothesisValidator()
    hypothesis = InvestigationHypothesis(
        title="Missing file bug",
        description="Bug in nonexistent file",
        path="app/nonexistent.py",
        line=1,
        severity="low",
        evidence=["none"],
        confidence=0.5,
    )

    res = validator.validate(hypothesis, sample_context)
    assert res["status"] == "rejected"
    assert "not found" in res["reason"]


def test_validator_rejects_out_of_bounds_line(sample_context):
    validator = HypothesisValidator()
    hypothesis = InvestigationHypothesis(
        title="Out of bounds line",
        description="Line 999 does not exist",
        path="app/main.py",
        line=999,
        severity="low",
        evidence=["none"],
        confidence=0.5,
    )

    res = validator.validate(hypothesis, sample_context)
    assert res["status"] == "rejected"
    assert "exceeds" in res["reason"]


def test_validator_rejects_false_syntax_defect_on_valid_python(sample_context):
    validator = HypothesisValidator()
    hypothesis = InvestigationHypothesis(
        title="Syntax error in hello function",
        description="Missing closing parenthesis syntax error",
        path="app/main.py",
        line=1,
        severity="high",
        evidence=["def hello():"],
        confidence=0.9,
    )

    res = validator.validate(hypothesis, sample_context)
    assert res["status"] == "rejected"
    assert res["syntax_check"] == "passed"
    assert "parses successfully" in res["reason"]
