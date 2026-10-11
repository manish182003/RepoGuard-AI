from app.schemas.analysis import FileAnalysis
from app.schemas.github import SourceFile
from app.tools.ast_analyzer import PythonASTAnalyzer
from app.tools.rules import PythonRuleEngine

class CodeAnalysisService:
    """Run language-specific static analysis on source files"""
    def __init__(self,ast_analyzer:PythonASTAnalyzer | None=None,rule_engine: PythonRuleEngine | None = None,):
        self.ast_analyzer= ast_analyzer or  PythonASTAnalyzer()
        self.rule_engine = rule_engine or PythonRuleEngine()

    def analyze_file(self,source_file:SourceFile)->FileAnalysis:
        if source_file.language!="python":
            return FileAnalysis(
                path=source_file.path,
                language=source_file.language,
                status="unsupported"
            )

        try:
            result=self.ast_analyzer.analyze_file(source_file.content)
        except SyntaxError as exc:
            return FileAnalysis(
                path=source_file.path,
                language=source_file.language,
                status="syntax_error",
                error=str(exc)
            )

        findings = self.rule_engine.check_http_timeouts(
                    source=source_file.content,
                    path=source_file.path,
                )

        

        return FileAnalysis(
            path=source_file.path,
            language=source_file.language,
            status="analyzed",
            findings=findings,
            **result
        )
