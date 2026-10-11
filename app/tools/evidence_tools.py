import os
import re
from typing import Any
import httpx
from app.schemas.context import RepositoryContext
from app.schemas.github import SourceFile
from app.tools.ast_analyzer import PythonASTAnalyzer
from app.tools.registry import ToolRegistry
from app.utils.source import detect_language


class EvidenceTools:
    """Provides evidence-gathering tools operating on a RepositoryContext."""

    def __init__(self, context: RepositoryContext):
        self.context = context
        self.files_by_path = {
            f.path: f for f in context.snapshot.files
        }

    def _get_or_fetch_file(self, path: str) -> SourceFile | None:
        """Find source file in snapshot via exact match, suffix match, or on-demand GitHub fetch."""
        source_file = self.files_by_path.get(path)
        if source_file:
            return source_file

        normalized_req = path.replace("\\", "/").lower().lstrip("/")
        for stored_path, f_obj in self.files_by_path.items():
            stored_norm = stored_path.replace("\\", "/").lower().lstrip("/")
            if stored_norm.endswith(normalized_req) or normalized_req.endswith(stored_norm):
                return f_obj

        # On-demand remote fetch if not present in pre-downloaded snapshot
        try:
            repo = getattr(self.context.snapshot, "repository", None)
            if repo and getattr(repo, "full_name", None):
                token = os.getenv("GITHUB_TOKEN")
                headers = {"Authorization": f"token {token}"} if token else {}
                branch = getattr(repo, "default_branch", "main") or "main"
                clean_path = path.replace("\\", "/").lstrip("/")
                url = f"https://raw.githubusercontent.com/{repo.full_name}/{branch}/{clean_path}"
                resp = httpx.get(url, headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    content = resp.text
                    sf = SourceFile(
                        path=clean_path,
                        sha="",
                        size=len(content.encode("utf-8")),
                        content=content,
                        language=detect_language(clean_path),
                    )
                    self.files_by_path[clean_path] = sf
                    self.context.snapshot.files.append(sf)
                    return sf
        except Exception:
            pass

        return None

    def read_source_file_lines(self, path: str, start_line: int, end_line: int, **kwargs: Any) -> dict[str, Any]:
        """Read a specified range of lines from a source file."""
        source_file = self._get_or_fetch_file(path)
        if not source_file:
            return {"error": f"File '{path}' not found in repository snapshot or remote repository."}

        lines = source_file.content.splitlines()
        total_lines = len(lines)

        start = max(1, start_line)
        end = min(total_lines, end_line)

        if start > total_lines:
            return {"error": f"start_line {start} exceeds total file lines ({total_lines})."}

        selected_lines = [
            {"line": idx + 1, "content": lines[idx]}
            for idx in range(start - 1, end)
        ]

        return {
            "path": source_file.path,
            "total_lines": total_lines,
            "start_line": start,
            "end_line": end,
            "lines": selected_lines,
        }

    def grep_search_code(
        self,
        pattern: str,
        directory: str | None = None,
        path: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search across repository source files for a string or regex pattern."""
        matches = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return {"error": f"Invalid regular expression pattern: {exc}"}

        target_dir = directory.replace("\\", "/").lower() if directory else None
        target_path_filter = path.replace("\\", "/").lower() if path else None

        for file_path, file_obj in self.files_by_path.items():
            norm_path = file_path.replace("\\", "/").lower()
            if target_dir and target_dir not in norm_path:
                continue
            if target_path_filter and target_path_filter not in norm_path:
                continue

            # Check if file path matches pattern
            if regex.search(file_path):
                first_lines = file_obj.content.splitlines()[:3]
                matches.append({
                    "path": file_path,
                    "line": 1,
                    "content": f"[Path matched pattern] Preview: {first_lines[0] if first_lines else ''}",
                })

            for line_idx, line in enumerate(file_obj.content.splitlines(), start=1):
                if regex.search(line):
                    matches.append({
                        "path": file_path,
                        "line": line_idx,
                        "content": line.strip(),
                    })

        return {
            "query_pattern": pattern,
            "total_matches": len(matches),
            "matches": matches[:30],
        }

    def find_repository_files(self, pattern: str, **kwargs: Any) -> dict[str, Any]:
        """Find repository file paths matching a keyword or pattern."""
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        matching_paths = [p for p in self.files_by_path.keys() if regex.search(p)]
        return {
            "query_pattern": pattern,
            "total_matches": len(matching_paths),
            "files": matching_paths[:50],
        }

    def get_file_ast_symbols(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Extract Python AST symbols (functions, classes, imports) for a given Python file."""
        source_file = self._get_or_fetch_file(path)
        if not source_file:
            return {"error": f"File '{path}' not found."}

        if source_file.language != "python":
            return {"error": f"File '{source_file.path}' is language '{source_file.language}', AST analyzer only supports Python."}

        analyzer = PythonASTAnalyzer()
        try:
            analysis = analyzer.analyze_file(source_file.content)
            return {
                "path": source_file.path,
                "functions": [f["name"] for f in analysis.get("functions", [])],
                "classes": [c["name"] for c in analysis.get("classes", [])],
                "imports": analysis.get("imports", []),
            }
        except Exception as exc:
            return {"error": f"AST analysis failed for '{source_file.path}': {exc}"}

    def list_repository_issues(self, **kwargs: Any) -> dict[str, Any]:
        """List reported open issues from the repository context."""
        issues = []
        for issue in self.context.existing_issues[:15]:
            issues.append({
                "number": issue.number,
                "title": issue.title,
                "labels": issue.labels,
                "state": issue.state,
                "author": issue.user_login,
            })
        return {
            "total_issues": len(self.context.existing_issues),
            "issues": issues,
        }

    def get_issue_details(self, issue_number: int, **kwargs: Any) -> dict[str, Any]:
        """Retrieve full details, error logs, and description of a specific GitHub issue."""
        for issue in self.context.existing_issues:
            if issue.number == issue_number:
                return {
                    "number": issue.number,
                    "title": issue.title,
                    "body": issue.body or "No description provided.",
                    "labels": issue.labels,
                    "state": issue.state,
                    "url": issue.html_url,
                    "author": issue.user_login,
                }
        return {"error": f"Issue #{issue_number} not found in repository issues."}

    def register_all(self, registry: ToolRegistry) -> None:
        """Register all evidence tools into the given ToolRegistry."""
        registry.register_tool(
            name="read_source_file_lines",
            description="Read a range of line numbers from a specific repository source file.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository file path"},
                    "start_line": {"type": "integer", "description": "1-based starting line number"},
                    "end_line": {"type": "integer", "description": "1-based ending line number"},
                },
                "required": ["path", "start_line", "end_line"],
            },
            handler=self.read_source_file_lines,
        )

        registry.register_tool(
            name="grep_search_code",
            description="Search code across repository source files using a keyword or regex pattern, with optional directory filter.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Keyword or regex pattern to search for"},
                    "directory": {"type": "string", "description": "Optional directory path to filter within, e.g. 'providers/'"},
                    "path": {"type": "string", "description": "Optional file path substring filter"},
                },
                "required": ["pattern"],
            },
            handler=self.grep_search_code,
        )

        registry.register_tool(
            name="find_repository_files",
            description="Find repository file paths matching a keyword, file extension, or directory path.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Keyword or substring to match file paths against, e.g. 'claude' or 'provider'"},
                },
                "required": ["pattern"],
            },
            handler=self.find_repository_files,
        )

        registry.register_tool(
            name="get_file_ast_symbols",
            description="Inspect AST symbols (function names, class names, imports) in a Python file.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository Python file path"},
                },
                "required": ["path"],
            },
            handler=self.get_file_ast_symbols,
        )

        registry.register_tool(
            name="list_repository_issues",
            description="List reported open issues from the repository context to understand reported bugs.",
            parameters_schema={
                "type": "object",
                "properties": {},
            },
            handler=self.list_repository_issues,
        )

        registry.register_tool(
            name="get_issue_details",
            description="Fetch full description, error logs, and reproduction details for a specific GitHub issue number.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "issue_number": {"type": "integer", "description": "Issue number to inspect"},
                },
                "required": ["issue_number"],
            },
            handler=self.get_issue_details,
        )
