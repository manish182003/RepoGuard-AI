from app.schemas.github import SourceFile
from app.tools.code_analysis import CodeAnalysisService


def test_analyze_python_file():
    source_file = SourceFile(
        path="example.py",
        sha="abc123",
        size=100,
        content="""
import requests

def fetch(url):
    return requests.get(url)
""",
        language="python",
    )

    service = CodeAnalysisService()

    result = service.analyze_file(source_file)

    assert result.path == "example.py"
    assert result.language == "python"
    assert result.status == "analyzed"

    assert result.imports == ["requests"]

    assert result.functions == [
        {
            "name": "fetch",
            "line": 4,
            "end_line": 5,
        }
    ]

    assert result.function_calls == [
        {
            "name": "requests.get",
            "line": 5,
        }
    ]


def test_analyze_invalid_python_file():
    source_file = SourceFile(
        path="broken.py",
        sha="abc123",
        size=20,
        content="""
def broken(
""",
        language="python",
    )

    service = CodeAnalysisService()

    result = service.analyze_file(source_file)

    assert result.path == "broken.py"
    assert result.status == "syntax_error"
    assert result.error is not None