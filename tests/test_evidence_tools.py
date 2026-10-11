import pytest
from app.schemas.context import RepositoryContext
from app.schemas.github import RepositoryInfo, RepositorySnapshot, SourceFile
from app.tools.evidence_tools import EvidenceTools
from app.tools.registry import ToolRegistry


@pytest.fixture
def mock_context():
    repo = RepositoryInfo(
        owner="owner",
        name="repo",
        full_name="owner/repo",
        default_branch="main",
        stars=1,
        forks=0,
        is_private=False,
    )

    f1 = SourceFile(
        path="app/main.py",
        sha="1",
        content="import os\n\ndef run():\n    print('running')\n",
        language="python",
        size=40,
    )

    f2 = SourceFile(
        path="app/config.py",
        sha="2",
        content="DEBUG = True\nTIMEOUT = 30\n",
        language="python",
        size=25,
    )

    snapshot = RepositorySnapshot(repository=repo, files=[f1, f2])
    return RepositoryContext(snapshot=snapshot, existing_issues=[])


def test_read_source_file_lines(mock_context):
    tools = EvidenceTools(mock_context)
    res = tools.read_source_file_lines("app/main.py", start_line=1, end_line=3)

    assert res["path"] == "app/main.py"
    assert len(res["lines"]) == 3
    assert res["lines"][0]["content"] == "import os"
    assert res["lines"][2]["content"] == "def run():"


def test_grep_search_code(mock_context):
    tools = EvidenceTools(mock_context)
    res = tools.grep_search_code("TIMEOUT")

    assert res["total_matches"] == 1
    assert res["matches"][0]["path"] == "app/config.py"
    assert res["matches"][0]["line"] == 2


def test_get_file_ast_symbols(mock_context):
    tools = EvidenceTools(mock_context)
    res = tools.get_file_ast_symbols("app/main.py")

    assert res["path"] == "app/main.py"
    assert "run" in res["functions"]
    assert "os" in res["imports"]


@pytest.mark.asyncio
async def test_evidence_tools_registration(mock_context):
    registry = ToolRegistry()
    tools = EvidenceTools(mock_context)
    tools.register_all(registry)

    defs = registry.get_tool_definitions()
    tool_names = [d["name"] for d in defs]
    assert "read_source_file_lines" in tool_names
    assert "grep_search_code" in tool_names
    assert "get_file_ast_symbols" in tool_names
    assert "list_repository_issues" in tool_names
    assert "get_issue_details" in tool_names

    res = await registry.execute_tool("read_source_file_lines", {"path": "app/config.py", "start_line": 1, "end_line": 1})
    assert res.success is True
    assert "DEBUG = True" in res.output


def test_issue_tools(mock_context):
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
    tools = EvidenceTools(mock_context)

    issue_list = tools.list_repository_issues()
    assert issue_list["total_issues"] == 1
    assert issue_list["issues"][0]["number"] == 1470

    details = tools.get_issue_details(1470)
    assert details["number"] == 1470
    assert "MultipartParser" in details["title"]
    assert "MEMFILE_MAX" in details["body"]

    not_found = tools.get_issue_details(9999)
    assert "error" in not_found


def test_grep_search_code_with_directory_and_find_files(mock_context):
    tools = EvidenceTools(mock_context)
    # Test directory filter
    res = tools.grep_search_code("DEBUG", directory="app")
    assert res["total_matches"] >= 1
    assert res["matches"][0]["path"] == "app/config.py"

    # Test unknown kwarg tolerance
    res_kwargs = tools.grep_search_code("DEBUG", unexpected_kwarg="some_val")
    assert res_kwargs["total_matches"] >= 1

    # Test find_repository_files
    files = tools.find_repository_files("config")
    assert files["total_matches"] == 1
    assert "app/config.py" in files["files"]

