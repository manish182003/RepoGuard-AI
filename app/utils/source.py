from app.schemas.github import FileContent,SourceFile
from app.utils.encoding import decode_base64_content

def file_content_to_source_file(file_content:FileContent)->SourceFile:
    """
    Convert Github Base64 encoded file content 
    into a decoded SourceFile
    """

    content=decode_base64_content(content=file_content.content)
    language=detect_language(path=file_content.path)

    return SourceFile(
        path=file_content.path,
        sha=file_content.sha,
        size=file_content.size,
        content=content,
        language=language
    )


def detect_language(path: str) -> str:
    """
    Detect Programming language from file extensions.
    """
    if path.endswith(".py"):
        return "python"
    if path.endswith(".js"):
        return "javascript"
    if path.endswith(".ts"):
        return "typescript"
    if path.endswith(".tsx"):
        return "typescript"
    if path.endswith(".jsx"):
        return "javascript"
    return "unknown"


def is_test_file(path: str) -> bool:
    """
    Determine if a file path belongs to a test suite (e.g., tests/, test_*.py).
    Test files should not be analyzed by defect rules or targeted for bugfix patches in OSS.
    """
    normalized = path.replace("\\", "/").lower().strip("/")
    parts = normalized.split("/")
    filename = parts[-1]

    # Directories dedicated to tests
    for dir_part in parts[:-1]:
        if dir_part in ("test", "tests", "testing", "__tests__", "spec", "specs"):
            return True

    # File naming patterns for tests
    if filename.startswith("test_") or filename.startswith("tests_"):
        return True
    if filename.endswith("_test.py") or filename.endswith("_tests.py"):
        return True
    if filename.endswith(".test.js") or filename.endswith(".spec.js") or filename.endswith(".test.ts") or filename.endswith(".spec.ts"):
        return True

    return False