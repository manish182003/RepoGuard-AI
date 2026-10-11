
import ast

from app.schemas.context import RepositoryContext
from app.schemas.investigation import InvestigationHypothesis


class HypothesisValidator:
    def validate(
        self,
        hypothesis: InvestigationHypothesis,
        context: RepositoryContext,
    ) -> dict:
        files = {
            source_file.path: source_file
            for source_file in context.snapshot.files
        }

        source_file = files.get(hypothesis.path)

        if source_file is None:
            return {
                "status": "rejected",
                "reason": "Referenced file was not found in the repository snapshot.",
            }

        lines = source_file.content.splitlines()

        if hypothesis.line > len(lines):
            return {
                "status": "rejected",
                "reason": "Reported line number exceeds the file length.",
            }

        result = {
            "status": "needs_review",
            "reason": "The finding requires additional verification.",
            "actual_line": lines[hypothesis.line - 1],
        }

        if source_file.language == "python":
            try:
                ast.parse(source_file.content)
            except SyntaxError as exc:
                result["syntax_check"] = "failed"
                result["syntax_error_line"] = exc.lineno
                result["syntax_error"] = exc.msg
            else:
                result["syntax_check"] = "passed"

                if (
                    "syntax" in hypothesis.description.lower()
                    or "syntax" in hypothesis.title.lower()
                ):
                    result["reason"] = (
                        "The complete Python file parses successfully; "
                        "the claimed syntax defect is not supported."
                    )
                    result["status"] = "rejected"

        return result
