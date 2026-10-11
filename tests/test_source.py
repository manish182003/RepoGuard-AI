from app.schemas.github import FileContent
from app.utils.source import (
    detect_language,
    file_content_to_source_file,
)


def test_detect_python():
    assert detect_language("src/main.py") == "python"


def test_detect_javascript():
    assert detect_language("src/app.js") == "javascript"


def test_detect_typescript():
    assert detect_language("src/app.ts") == "typescript"


def test_detect_tsx():
    assert detect_language("src/App.tsx") == "typescript"


def test_unknown_language():
    assert detect_language("README.md") == "unknown"


def test_file_content_to_source_file():
    file_content = FileContent(
        path="src/main.py",
        sha="abc123",
        size=13,
        content="cHJpbnQoIkhlbGxvIik=",
        encoding="base64",
    )

    source_file = file_content_to_source_file(file_content)

    assert source_file.path == "src/main.py"
    assert source_file.sha == "abc123"
    assert source_file.size == 13
    assert source_file.content == 'print("Hello")'
    assert source_file.language == "python"