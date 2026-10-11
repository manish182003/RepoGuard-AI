from app.schemas.github import (
    RepositoryInfo,
    RepositorySnapshot,
    SourceFile
)
from app.tools.repository_analysis import RepositoryAnalysisService

def test_analyze_repository():
    repository=RepositoryInfo(
        owner="example",
        name="demo",
        full_name="example/demo",
        default_branch="main",
        description="demo repository",
        stars=10,
        forks=2,
        is_private=False
    )

    snapshot=RepositorySnapshot(
        repository=repository,
        files=[
            SourceFile(
                path="client.py",
                sha="abc123",
                size=100,
                content="""
import requests

response=requests.get(url)
""",
                language="python"
            ),
            SourceFile(
                path="utils.py",
                sha="def456",
                size=100,
                content=""""
def add(a,b):
    return a + b                             
""",
                language="python"
            )
        ]
    )

    service=RepositoryAnalysisService()
    result=service.analyze_repository(snapshot)

    assert result.repository.full_name=="example/demo"
    assert len(result.files)==2

    assert len(result.findings)==1

    finding=result.findings[0]

    assert finding.rule=="PYTHON-HTTP-NO-TIMEOUT"
    assert finding.path=="client.py"