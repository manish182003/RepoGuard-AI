import ast

from app.schemas.finding import Finding


class PythonRuleEngine:
    """Run deterministic rules against Python source code."""

    def check_http_timeouts(
        self,
        source: str,
        path: str,
    ) -> list[Finding]:
        tree = ast.parse(source)

        findings = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if not self._is_requests_call(node):
                continue

            has_timeout = any(
                keyword.arg == "timeout"
                for keyword in node.keywords
            )

            if has_timeout:
                continue

            findings.append(
                Finding(
                    rule="PYTHON-HTTP-NO-TIMEOUT",
                    severity="medium",
                    path=path,
                    line=node.lineno,
                    title="HTTP request does not specify a timeout",
                    evidence=(
                        "requests HTTP call does not provide "
                        "a timeout argument."
                    ),
                    confidence=0.95,
                )
            )

        return findings

    def check_bare_except(self, source: str, path: str) -> list[Finding]:
        """Detect bare except clauses (except:) that swallow SystemExit and KeyboardInterrupt."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(
                    Finding(
                        rule="PYTHON-BARE-EXCEPT",
                        severity="medium",
                        path=path,
                        line=node.lineno,
                        title="Bare except clause detected",
                        evidence="Bare except: clause catches base Exception and SystemExit.",
                        confidence=0.9,
                    )
                )
        return findings

    def check_mutable_default_args(self, source: str, path: str) -> list[Finding]:
        """Detect mutable default arguments (list, dict, set) in function definitions."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        findings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        findings.append(
                            Finding(
                                rule="PYTHON-MUTABLE-DEFAULT-ARG",
                                severity="medium",
                                path=path,
                                line=node.lineno,
                                title=f"Function '{node.name}' uses a mutable default argument",
                                evidence=f"Default parameter value for '{node.name}' is a mutable literal.",
                                confidence=0.9,
                            )
                        )
        return findings

    def run_all_rules(self, source: str, path: str) -> list[Finding]:
        """Run all deterministic rule checks against the provided source code."""
        findings = []
        findings.extend(self.check_http_timeouts(source, path))
        findings.extend(self.check_bare_except(source, path))
        findings.extend(self.check_mutable_default_args(source, path))
        return findings

    def _is_requests_call(self, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Attribute):
            return False

        if node.func.attr not in {
            "get",
            "post",
            "put",
            "patch",
            "delete",
            "head",
            "options",
        }:
            return False

        return (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "requests"
        )