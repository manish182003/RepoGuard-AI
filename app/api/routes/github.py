from fastapi import APIRouter, HTTPException, Query
from app.tools.github import GitHubTool
from app.utils.source import file_content_to_source_file
from app.tools.repository import RepositoryIngestionService
from app.tools.repository_analysis import RepositoryAnalysisService

router=APIRouter(prefix="/github",tags=["Github"])
github_tool=GitHubTool()
repository_service=RepositoryIngestionService()
repository_analysis_service=RepositoryAnalysisService()

@router.get("/repository")
async def get_repository(url:str=Query(...,description="Github Repository URL")):
    try:
        repository=await github_tool.get_repository(url)

        return repository

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
  
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Github API request failed: {exc}"         
        ) from exc


@router.get("/repository/tree")
async def get_repository_tree(url:str=Query(...,description="Github Repository URL")):
    try:
        files=await github_tool.get_file_tree(url)

        return {
            "count":len(files),
            "files":files
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Github API request failed: {exc}"
        ) from exc

@router.get("/file")
async def get_file(
    url:str=Query(...,description="Github Repository Url"),
    path:str=Query(...,description="Path of the File inside repository")    
    ):
    try:
        file_content=await github_tool.get_file_content(url,path)

        return file_content
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Github API request failed: {exc}"
        ) from exc


@router.get("/source")
async def get_source(
    url:str=Query(...,description="Github Repository URL"),
    path:str=Query(...,description="Path of the file inside repository")
    ):
    try:
        file_content=await github_tool.get_file_content(url,path)

        source_file=file_content_to_source_file(file_content=file_content)

        return source_file
    except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
    except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Github API request failed: {exc}"
            ) from exc

@router.get("/repository/snapshot")
async def get_repository_snapshot(url:str=Query(...,description="Github Repository Url")):
     try:
          snapshot=await repository_service.build_snapshot(url)
          return snapshot

     except ValueError as exc:
                 raise HTTPException(
                     status_code=400,
                     detail=str(exc),
                 ) from exc
     except Exception as exc:
                 raise HTTPException(
                     status_code=500,
                     detail=f"Github API request failed: {exc}"
                 ) from exc

@router.get("/repository/analyze")
async def analyze_repository(url:str=Query(...,description="Github Repository URL")):
     try:
          snapshot=await repository_service.build_snapshot(url)
          analysis= repository_analysis_service.analyze_repository(snapshot)

          return analysis
     except ValueError as exc:
                      raise HTTPException(
                          status_code=400,
                          detail=str(exc),
                      ) from exc
     except Exception as exc:
                      raise HTTPException(
                          status_code=500,
                          detail=f"Github API request failed: {exc}"
                      ) from exc 


@router.get("/repository/issues")
async def get_repository_issues(url:str=Query(...,description="GitHub Repository URL."),
                                state:str=Query("open",description="Issue state: open, closed or all")):
      try:
            issues=await github_tool.get_issues(url,state)

            return {
                   "count":len(issues),
                   "issues":issues
            }
      

      except ValueError as exc:
                           raise HTTPException(
                               status_code=400,
                               detail=str(exc),
                           ) from exc
      except Exception as exc:
                           raise HTTPException(
                               status_code=500,
                               detail=f"Github API request failed: {exc}"
                           ) from exc 
