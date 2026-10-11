from pydantic import BaseModel

class RepositoryInfo(BaseModel):
    owner:str
    name:str
    full_name:str
    default_branch:str
    description:str | None=None
    stars:int
    forks:int
    is_private:bool

class FileEntry(BaseModel):
    path:str
    sha:str
    size:int | None=None
    url:str
    html_url:str
    git_url:str | None=None
    download_url:str | None=None
    type:str

class FileContent(BaseModel):
    path:str
    sha:str
    size:int
    content:str
    encoding:str

class SourceFile(BaseModel):
    path:str
    sha:str
    size:int
    content:str
    language:str

class RepositorySnapshot(BaseModel):
    repository:RepositoryInfo
    files:list[SourceFile]


class IssueInfo(BaseModel):
    number:int
    title:str
    body:str|None=None
    state:str
    labels:list[str]
    html_url:str
    user_login:str | None=None
    created_at:str
    updated_at:str