from pydantic import BaseModel

class RepositoryWorkspace(BaseModel):
    repository_url:str
    path:str
    branch:str
    commit_sha:str