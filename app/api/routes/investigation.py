import asyncio
import json
import logging
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel

from app.core.policy import PolicyEngine
from app.llm import LLMAuthenticationError, LLMError, LLMRateLimitError
from app.schemas.investigation import InvestigationRequest
from app.services.orchestrator import RepoGuardOrchestrator
from app.tools.github_pr import GitHubPRAutomation, PRCreationRequest
from app.tools.fork_service import GitHubForkService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investigation", tags=["Investigation"])

# In-memory store for pending approval jobs
PENDING_APPROVAL_JOBS: dict[str, dict[str, Any]] = {}


class PRApprovalRequest(BaseModel):
    job_id: str
    human_approved_for_pr: bool = True


@router.post("")
async def investigate_repository(request: InvestigationRequest):
    """Synchronous end-to-end investigation pipeline endpoint."""
    orchestrator = RepoGuardOrchestrator()

    try:
        result = await orchestrator.run_pipeline(
            repository_url=request.repository_url,
            issue_state=request.issue_state,
            auto_generate_patch=request.auto_generate_patch,
            human_approved_for_pr=request.human_approved_for_pr,
            target_issue_number=request.target_issue_number,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve repository context from GitHub",
        ) from exc
    except (httpx.RequestError, RuntimeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not retrieve repository context",
        ) from exc
    except LLMAuthenticationError as exc:
        raise HTTPException(
            status_code=503,
            detail="LLM API key is not configured or invalid",
        ) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="LLM rate limit or TPM budget exceeded",
        ) from exc
    except (LLMError, ValueError) as exc:
        logger.exception("LLM investigation failed")
        raise HTTPException(
            status_code=502,
            detail="Investigation request failed",
        ) from exc
    except Exception as exc:
        logger.exception("Repository investigation failed")
        raise HTTPException(
            status_code=502,
            detail="Investigation failed. Check the server logs.",
        ) from exc


@router.post("/stream")
async def stream_investigate_repository(request: InvestigationRequest):
    """Real-time Server-Sent Events (SSE) streaming endpoint with human approval job tracking."""

    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    async def on_event_callback(event_type: str, data: dict) -> None:
        if event_type == "human_approval_required":
            # Save job state for approval
            PENDING_APPROVAL_JOBS[job_id] = {
                "job_id": job_id,
                "repository_url": request.repository_url,
                "data": data,
            }
            data["job_id"] = job_id

        await queue.put((event_type, data))

    async def run_pipeline_task():
        orchestrator = RepoGuardOrchestrator()
        try:
            await orchestrator.run_pipeline(
                repository_url=request.repository_url,
                issue_state=request.issue_state,
                auto_generate_patch=request.auto_generate_patch,
                human_approved_for_pr=request.human_approved_for_pr,
                target_issue_number=request.target_issue_number,
                on_event=on_event_callback,
            )
        except Exception as exc:
            logger.exception("Streaming pipeline background task failed")
            await queue.put(("pipeline_failed", {"error": str(exc)}))
        finally:
            await queue.put(None)

    async def event_generator():
        task = asyncio.create_task(run_pipeline_task())

        while True:
            item = await queue.get()
            if item is None:
                break

            event_type, data = item
            payload = {"event": event_type, "data": data}
            yield f"data: {json.dumps(payload)}\n\n"

        await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/approve")
async def approve_pr_creation(request: PRApprovalRequest):
    """Human-in-the-Loop Phase 2 approval endpoint to create GitHub Fork & Pull Request."""

    job = PENDING_APPROVAL_JOBS.get(request.job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Pending approval job '{request.job_id}' not found or expired.",
        )

    if not request.human_approved_for_pr:
        del PENDING_APPROVAL_JOBS[request.job_id]
        return {
            "status": "rejected_by_user",
            "message": "Pull Request creation rejected by human user.",
        }

    # Execute approved GitHub Fork & PR creation
    try:
        policy = PolicyEngine()
        data = job["data"]
        target_repo = data.get("target_repository", "owner/repo")
        owner, repo = target_repo.split("/")

        fork_service = GitHubForkService()
        fork_details = await fork_service.ensure_fork(owner, repo)

        pr_automation = GitHubPRAutomation(policy_engine=policy)
        patch_path = data.get("patch_path", "test/test_outputfilter.py")
        modified_content = data.get("modified_content")
        default_branch = data.get("default_branch") or fork_details.default_branch or "main"
        rel_issue_id = data.get("related_issue_id")
        path_slug = patch_path.replace("/", "_").replace(".", "_")
        branch_name = f"repoguard/fix-{path_slug}-{uuid.uuid4().hex[:6]}"

        if modified_content:
            await pr_automation.prepare_branch_and_commit(
                owner=fork_details.owner,
                repo=fork_details.name,
                branch_name=branch_name,
                base_branch=default_branch,
                file_path=patch_path,
                modified_content=modified_content,
                commit_message=f"fix(repoguard): automated patch for {patch_path}",
            )
        else:
            return {
                "job_id": request.job_id,
                "status": "failed",
                "pr_result": {
                    "success": False,
                    "error": "Cannot create Pull Request: No modified code content available to commit (the proposed patch did not match the target file cleanly).",
                },
            }

        head_ref = f"{fork_details.owner}:{branch_name}" if fork_details.is_fork else branch_name
        issue_link = f"\n\nFixes #{rel_issue_id}" if rel_issue_id else ""
        pr_title = f"fix(repoguard): automated verified defect patch for {patch_path}"
        if rel_issue_id:
            pr_title += f" (fixes #{rel_issue_id})"

        pr_body = await pr_automation.format_pr_body(
            owner=fork_details.parent_owner,
            repo=fork_details.parent_name,
            file_path=patch_path,
            explanation=data.get("patch_summary", "Verified fix"),
            issue_id=rel_issue_id,
            base_branch=default_branch,
        )

        pr_req = PRCreationRequest(
            repository_owner=fork_details.parent_owner,
            repository_name=fork_details.parent_name,
            branch_name=branch_name,
            title=pr_title,
            body=pr_body,
            head_branch=head_ref,
            base_branch=default_branch,
            human_approved=True,
        )

        pr_res = await pr_automation.create_pull_request(pr_req)

        # Fallback to fork PR if upstream repository restricts API pull requests
        if not pr_res.success and fork_details.is_fork:
            logger.warning(
                f"Upstream PR failed ({pr_res.error}). Upstream organization likely restricts third-party API PRs. "
                f"Creating PR on user's fork ({fork_details.owner}/{fork_details.name}) instead..."
            )
            upstream_url = (
                f"https://github.com/{fork_details.parent_owner}/{fork_details.parent_name}/compare/"
                f"{default_branch}...{fork_details.owner}:{branch_name}?expand=1"
            )
            fork_pr_req = PRCreationRequest(
                repository_owner=fork_details.owner,
                repository_name=fork_details.name,
                branch_name=branch_name,
                title=pr_title,
                body=(
                    f"{pr_body}\n\n"
                    f"> **Upstream PR Link**:\n"
                    f"> [Click here to submit this Pull Request to {fork_details.parent_full_name}]({upstream_url})"
                ),
                head_branch=branch_name,
                base_branch=fork_details.default_branch,
                human_approved=True,
            )
            fork_pr_res = await pr_automation.create_pull_request(fork_pr_req)
            if fork_pr_res.success:
                fork_pr_res.upstream_compare_url = upstream_url
                pr_res = fork_pr_res

        # Cleanup job after processing
        del PENDING_APPROVAL_JOBS[request.job_id]

        return {
            "job_id": request.job_id,
            "status": "approved",
            "pr_result": pr_res.model_dump(),
        }
    except Exception as exc:
        logger.exception("Failed to execute approved PR creation")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to execute approved PR: {exc}",
        ) from exc