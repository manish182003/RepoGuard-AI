from pydantic import BaseModel
from app.schemas.finding import Finding
from app.schemas.github import RepositoryInfo

class FileAnalysis(BaseModel):
    path:str
    language:str
    status:str
    functions:list[dict]=[]
    classes:list[dict]=[]
    imports:list[str]=[]
    function_calls:list[dict]=[]
    findings: list[Finding] = []
    error:str | None=None

class RepositoryAnalysis(BaseModel):
    repository:RepositoryInfo
    files:list[FileAnalysis]
    findings:list[Finding]=[]