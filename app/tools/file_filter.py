import os
from app.utils.source import detect_language

IGNORED_DIRECTORIES = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "egg-info",
    ".pytest_cache",
    ".mypy_cache",
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo", ".pyd",
    ".min.js", ".min.css", ".map",
    ".lock", ".sum",
}


class RepositoryFileFilter:
    """Filters repository files to exclude non-analyzable, binary, or vendor files."""

    def __init__(self, max_file_size_bytes: int = 500_000):
        self.max_file_size_bytes = max_file_size_bytes

    def is_ignored_path(self, path: str) -> bool:
        """Check if file path belongs to an ignored directory or has an ignored extension."""
        normalized_path = path.replace("\\", "/").strip("/")
        parts = normalized_path.split("/")

        # Check directory names
        for part in parts[:-1]:
            if part in IGNORED_DIRECTORIES or part.startswith("."):
                return True

        filename = parts[-1]
        if filename.startswith("."):
            return True

        filename_lower = filename.lower()
        for ext in IGNORED_EXTENSIONS:
            if filename_lower.endswith(ext):
                return True

        return False

    def is_analyzable(self, path: str, size: int | None = None) -> tuple[bool, str]:
        """Determine if a file should be retrieved and analyzed.

        Returns (is_analyzable: bool, reason: str).
        """
        if self.is_ignored_path(path):
            return False, "ignored_path_or_extension"

        if size is not None and size > self.max_file_size_bytes:
            return False, f"file_size_exceeds_limit ({size} > {self.max_file_size_bytes})"

        language = detect_language(path)
        if language == "unknown":
            return False, "unsupported_language"

        return True, "analyzable"
