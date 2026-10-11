from app.schemas.analysis import RepositoryAnalysis,FileAnalysis
from app.schemas.github import RepositorySnapshot
from app.tools.code_analysis import CodeAnalysisService

class RepositoryAnalysisService:
    """Analysis all supported files in the Repository"""

    def __init__(self,code_analysis_service:CodeAnalysisService | None=None):
        self.code_analysis_service=code_analysis_service or CodeAnalysisService()

    def analyze_repository(self,snapshot:RepositorySnapshot)->RepositoryAnalysis:
        file_analyses:list[FileAnalysis]=[]

        for source_file in snapshot.files:
            result=self.code_analysis_service.analyze_file(source_file)
            file_analyses.append(result)

        findings=[]

        for file_analysis in file_analyses:
            findings.extend(file_analysis.findings)

        return RepositoryAnalysis(
            repository=snapshot.repository,
            files=file_analyses,
            findings=findings
        )




