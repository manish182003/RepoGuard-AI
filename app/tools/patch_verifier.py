import ast
import logging
from pydantic import BaseModel
from app.tools.patch_generator import GeneratedPatch

logger = logging.getLogger(__name__)


class PatchVerificationResult(BaseModel):
    success: bool
    syntax_check: str
    modified_content: str | None = None
    error: str | None = None


class PatchVerifier:
    """Verifies generated patches by applying code replacements and checking AST syntax."""

    def _apply_replacement(
        self, original_content: str, target_code: str, replacement_code: str
    ) -> str | None:
        """Apply replacement cleanly, supporting exact matches and whitespace-tolerant line matches."""
        if target_code in original_content:
            return original_content.replace(target_code, replacement_code, 1)

        target_lines = [l.strip() for l in target_code.splitlines() if l.strip()]
        if not target_lines:
            return None

        orig_lines = original_content.splitlines(keepends=True)
        n = len(target_lines)

        for i in range(len(orig_lines) - n + 1):
            window = [orig_lines[i + j].strip() for j in range(n)]
            if window == target_lines:
                # Determine leading indentation of first matched line in original
                first_orig = orig_lines[i]
                leading_indent = first_orig[:len(first_orig) - len(first_orig.lstrip())]

                # Re-indent replacement code lines
                repl_lines = replacement_code.splitlines()
                target_first = target_code.splitlines()[0]
                target_base_indent = target_first[:len(target_first) - len(target_first.lstrip())]

                reindented_repl = []
                for r in repl_lines:
                    if r.startswith(target_base_indent):
                        adjusted = leading_indent + r[len(target_base_indent):]
                    else:
                        adjusted = leading_indent + r.lstrip()
                    reindented_repl.append(adjusted)

                newline = "\n" if "\n" in orig_lines[i] else ""
                repl_text = "\n".join(reindented_repl) + newline
                new_lines = orig_lines[:i] + [repl_text] + orig_lines[i + n:]
                return "".join(new_lines)

        return None

    def verify_patch(
        self,
        patch: GeneratedPatch,
        original_content: str,
    ) -> PatchVerificationResult:
        modified = self._apply_replacement(original_content, patch.target_code, patch.replacement_code)
        if modified is None:
            return PatchVerificationResult(
                success=False,
                syntax_check="skipped",
                error=f"Target code snippet not found in '{patch.path}'. Patch cannot be applied cleanly.",
            )

        # Check Python syntax and semantic symbols if file is Python
        if patch.path.endswith(".py"):
            try:
                ast.parse(modified)
            except SyntaxError as exc:
                return PatchVerificationResult(
                    success=False,
                    syntax_check="failed",
                    modified_content=modified,
                    error=f"Applied patch introduced Python syntax error at line {exc.lineno}: {exc.msg}",
                )

            semantic_err = self._verify_python_semantics(patch, modified)
            if semantic_err:
                return PatchVerificationResult(
                    success=False,
                    syntax_check="semantic_failed",
                    modified_content=modified,
                    error=semantic_err,
                )

        return PatchVerificationResult(
            success=True,
            syntax_check="passed",
            modified_content=modified,
        )

    def _verify_python_semantics(self, patch: GeneratedPatch, modified: str) -> str | None:
        """Perform static AST semantic checks to detect hallucinated method and function calls."""
        try:
            tree = ast.parse(modified)
        except SyntaxError:
            return None

        import builtins

        # 1. Extract newly introduced self.<method>() calls in replacement_code
        def get_self_calls(snippet: str) -> set[str]:
            calls = set()
            try:
                wrapped = "def _dummy(self):\n" + "\n".join("    " + l for l in snippet.splitlines())
                t = ast.parse(wrapped)
                for n in ast.walk(t):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                        if isinstance(n.func.value, ast.Name) and n.func.value.id == "self":
                            calls.add(n.func.attr)
            except Exception:
                pass
            return calls

        target_self_calls = get_self_calls(patch.target_code)
        repl_self_calls = get_self_calls(patch.replacement_code)
        new_self_calls = repl_self_calls - target_self_calls

        standard_object_methods = {
            "__init__", "__str__", "__repr__", "__call__", "__eq__", "__ne__",
            "__enter__", "__exit__", "__aenter__", "__aexit__", "__getitem__",
            "__setitem__", "__len__", "__iter__", "__next__", "__aiter__", "__anext__"
        }

        if new_self_calls:
            classes_in_file = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
            all_defined_methods = set()
            for cls_node in classes_in_file:
                methods = {
                    m.name for m in cls_node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                all_defined_methods.update(methods)

            if classes_in_file:
                for call in new_self_calls:
                    if call not in standard_object_methods and call not in all_defined_methods:
                        return (
                            f"Applied patch introduced call to undefined method 'self.{call}()'. "
                            f"Method is never defined in this class or file."
                        )

        # 2. Extract standalone function calls func() in replacement_code
        def get_global_calls(snippet: str) -> set[str]:
            calls = set()
            try:
                wrapped = "def _dummy():\n" + "\n".join("    " + l for l in snippet.splitlines())
                t = ast.parse(wrapped)
                for n in ast.walk(t):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                        calls.add(n.func.id)
            except Exception:
                pass
            return calls

        target_global_calls = get_global_calls(patch.target_code)
        repl_global_calls = get_global_calls(patch.replacement_code)
        new_global_calls = repl_global_calls - target_global_calls

        if new_global_calls:
            imports = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    for a in n.names:
                        imports.add(a.asname or a.name.split(".")[0])
                elif isinstance(n, ast.ImportFrom):
                    for a in n.names:
                        imports.add(a.asname or a.name)

            defined_callables = {
                n.name for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }
            builtins_set = set(dir(builtins))
            available = imports | defined_callables | builtins_set

            for g_call in new_global_calls:
                if g_call not in available:
                    return (
                        f"Applied patch introduced call to undefined function or class '{g_call}()'. "
                        f"It is not imported or defined in this file."
                    )

        return None
