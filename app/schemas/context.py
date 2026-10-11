from pydantic import BaseModel

from app.schemas.github import RepositorySnapshot,IssueInfo

class RepositoryContext(BaseModel):
    snapshot:RepositorySnapshot
    existing_issues:list[IssueInfo]