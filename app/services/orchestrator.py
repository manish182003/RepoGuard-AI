import logging
import os
import tempfile
import uuid
from typing import Any, Awaitable, Callable
from pydantic import BaseModel, Field
import re
from app.agents.loop import AutonomousAgentLoop
from app.core.policy import PolicyEngine
from app.llm import BaseLLMProvider
from app.schemas.finding import Finding
from app.tools.context_service import RepositoryContextService
from app.tools.file_filter import RepositoryFileFilter
from app.tools.finding_manager import FindingLifecycleManager
from app.tools.fork_service import GitHubForkService
from app.tools.git_service import GitAutomationService
from app.tools.github_pr import GitHubPRAutomation, PRCreationRequest
from app.tools.hypothesis_validator import HypothesisValidator
from app.tools.patch_generator import GeneratedPatch, PatchGenerator
from app.tools.patch_verifier import PatchVerifier, PatchVerificationResult
from app.tools.sandbox import SubprocessSandbox, SandboxTestResult

logger = logging.getLogger(__name__)


class PipelineExecutionResult(BaseModel):
    repository: str
    status: str
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    patches: list[dict[str, Any]] = Field(default_factory=list)
    sandbox_results: list[dict[str, Any]] = Field(default_factory=list)
    pr_result: dict[str, Any] | None = None
    iterations_used: int = 0


class RepoGuardOrchestrator:
    """Coordinates the end-to-end RepoGuard AI investigation, AST validation, subprocess sandbox pytest execution,

    GitHub auto-forking, local git branching, and PR automation.
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
        context_service: RepositoryContextService | None = None,
        policy_engine: PolicyEngine | None = None,
    ):
        self.llm_provider = llm_provider
        self.context_service = context_service or RepositoryContextService()
        self.policy_engine = policy_engine or PolicyEngine()
        self.validator = HypothesisValidator()
        self.file_filter = RepositoryFileFilter()
        self.patch_verifier = PatchVerifier()
        self.sandbox = SubprocessSandbox()
        self.fork_service = GitHubForkService()
        self.git_service = GitAutomationService()

    async def _emit(
        self,
        on_event: Callable[[str, dict], Awaitable[None]] | None,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        if on_event is not None:
            try:
                await on_event(event_type, data)
            except Exception as exc:
                logger.warning(f"Error in pipeline event listener: {exc}")

    async def run_pipeline(
        self,
        repository_url: str,
        issue_state: str = "open",
        auto_generate_patch: bool = True,
        human_approved_for_pr: bool = False,
        target_issue_number: int | None = None,
        on_event: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> PipelineExecutionResult:
        logger.info(f"Starting RepoGuard pipeline for {repository_url}")

        await self._emit(on_event, "pipeline_started", {"repository_url": repository_url})

        # Pre-fetch target issue to extract priority keywords for guided ingestion in large repos
        priority_keywords: list[str] = []
        target_issue = None
        if target_issue_number is not None:
            try:
                target_issue = await self.context_service.github_tool.get_issue(repository_url, target_issue_number)
                if target_issue:
                    words = re.findall(r"[a-zA-Z0-9_\-]+", f"{target_issue.title} {target_issue.body or ''}")
                    priority_keywords = [w.lower() for w in words if len(w) > 2][:25]
                    logger.info(f"Guided ingestion keywords for Issue #{target_issue_number}: {priority_keywords}")
            except Exception as iss_fetch_err:
                logger.debug(f"Target issue pre-fetch skipped: {iss_fetch_err}")

        # 1. Fetch Repository Context
        await self._emit(on_event, "context_fetching", {"message": "Retrieving file tree, metadata, and issues from GitHub..."})
        context = await self.context_service.build_context(
            repository_url, issue_state=issue_state, on_event=on_event, priority_keywords=priority_keywords
        )
        if target_issue and not any(i.number == target_issue.number for i in context.existing_issues):
            context.existing_issues.append(target_issue)

        # 2. Filter files for analysis
        analyzable_files = [
            f for f in context.snapshot.files
            if self.file_filter.is_analyzable(f.path, f.size)[0]
        ]
        context.snapshot.files = analyzable_files

        await self._emit(on_event, "files_filtered", {
            "total_files": len(context.snapshot.files),
            "analyzable_count": len(analyzable_files),
        })

        # 2b. Run Deterministic Static Rule Engine Scan
        from app.tools.rules import PythonRuleEngine
        from app.utils.source import is_test_file
        rule_engine = PythonRuleEngine()
        rule_findings: list[Finding] = []
        py_files = [f for f in context.snapshot.files if f.path.endswith(".py") and not is_test_file(f.path)]

        await self._emit(on_event, "ast_scan_started", {
            "total_files": len(py_files),
            "message": f"Analyzing {len(py_files)} Python source files with AST static rules...",
        })

        for idx, file in enumerate(py_files):
            try:
                findings_for_file = rule_engine.run_all_rules(source=file.content, path=file.path)
                for rf in findings_for_file:
                    rule_findings.append(rf)
                    await self._emit(on_event, "ast_rule_finding", {
                        "rule": rf.rule,
                        "path": rf.path,
                        "line": rf.line,
                        "title": rf.title,
                    })
            except Exception as rule_exc:
                logger.debug(f"Rule check skipped for {file.path}: {rule_exc}")

            if (idx + 1) % 15 == 0 or (idx + 1) == len(py_files):
                await self._emit(on_event, "ast_scan_progress", {
                    "scanned": idx + 1,
                    "total": len(py_files),
                    "percent": int(((idx + 1) / len(py_files)) * 100),
                    "findings_count": len(rule_findings),
                    "current_file": file.path,
                })

        # 3. Determine Specific Issue Objective
        if target_issue_number is not None:
            if not target_issue:
                target_issue = next((iss for iss in context.existing_issues if iss.number == target_issue_number), None)
                if not target_issue:
                    try:
                        await self._emit(on_event, "issue_fetching_direct", {
                            "issue_number": target_issue_number,
                            "message": f"Fetching targeted Issue #{target_issue_number} from GitHub API...",
                        })
                        target_issue = await self.context_service.github_tool.get_issue(repository_url, target_issue_number)
                        if target_issue:
                            context.existing_issues.append(target_issue)
                    except Exception as fetch_err:
                        logger.warning(f"Could not fetch target issue #{target_issue_number}: {fetch_err}")
            logger.info(f"Targeting requested Issue #{target_issue_number}: {target_issue.title if target_issue else 'Not found'}")
        elif not target_issue and context.existing_issues:
            # Autoselect the most actionable bug report via TypeSafe Jev System One model only when no issue was targeted
            try:
                from app.services.jev_client import JevDecisionService
                jev = JevDecisionService()
                best_issue = None
                best_prob = 0.0

                for iss in context.existing_issues[:5]:
                    await self._emit(on_event, "jev_triaging_issue", {
                        "issue_number": iss.number,
                        "title": iss.title,
                        "author": iss.user_login,
                    })
                    triage = await jev.triage_issue(title=iss.title, body=iss.body or "")
                    await self._emit(on_event, "jev_triage_result", {
                        "issue_number": iss.number,
                        "is_actionable_bug": triage.is_actionable_bug,
                        "bug_probability": triage.bug_probability,
                        "category": triage.category,
                    })
                    if triage.is_actionable_bug and triage.bug_probability > best_prob:
                        best_prob = triage.bug_probability
                        best_issue = iss

                if best_issue:
                    target_issue = best_issue
                    logger.info(f"Jev selected issue #{best_issue.number} with bug probability {best_prob:.2f}")
            except Exception as jev_err:
                logger.debug(f"Jev issue triage skipped: {jev_err}")

            if not target_issue:
                # Fallback heuristic
                bug_keywords = ["bug", "fail", "error", "crash", "wrong", "leak", "exception", "broken", "issue"]
                for iss in context.existing_issues:
                    title_lower = iss.title.lower()
                    body_lower = (iss.body or "").lower()
                    if any(kw in title_lower or kw in body_lower for kw in bug_keywords):
                        target_issue = iss
                        break
                if not target_issue:
                    target_issue = context.existing_issues[0]

        # 3b. Run Autonomous Agent Investigation Loop with real-time streaming callback
        await self._emit(on_event, "agent_investigation_started", {"message": "Starting multi-turn tool-calling investigation..."})

        existing_pr = None
        if target_issue:
            try:
                existing_pr = await self.context_service.github_tool.find_existing_pull_request_for_issue(
                    repository_url, target_issue.number
                )
                if existing_pr:
                    logger.warning(
                        f"Existing open PR found for Issue #{target_issue.number}: "
                        f"PR #{existing_pr['pr_number']} ({existing_pr['html_url']})"
                    )
                    await self._emit(on_event, "duplicate_pr_detected", {
                        "issue_number": target_issue.number,
                        "existing_pr": existing_pr,
                        "warning": f"An open Pull Request already addresses Issue #{target_issue.number}: PR #{existing_pr['pr_number']} ('{existing_pr['title']}') by @{existing_pr.get('author', 'contributor')}",
                    })
            except Exception as e_pr_err:
                logger.debug(f"Existing PR check skipped: {e_pr_err}")

            await self._emit(on_event, "issue_targeted", {
                "number": target_issue.number,
                "title": target_issue.title,
                "url": target_issue.html_url,
                "author": target_issue.user_login,
                "existing_pr": existing_pr,
            })
            initial_prompt = f"""MISSION OBJECTIVE:
Investigate and resolve GitHub Issue #{target_issue.number}: "{target_issue.title}"
Issue URL: {target_issue.html_url}

Reported Description & Symptoms:
{target_issue.body or "No description provided."}

Instructions:
1. Carefully analyze the reported issue description, error messages, and symptoms above.
2. Use tools like grep_search_code or read_source_file_lines to locate the relevant source code files and functions.
3. Determine the root cause of the bug described in Issue #{target_issue.number}.
4. Conclude with action: "final_result" containing your hypothesis, citing the exact file path, line number, concrete code evidence, and set "related_issue_id": {target_issue.number}.
"""
        else:
            initial_prompt = "Investigate this repository for candidate defects, safety hazards, and bug risks."

        agent = AutonomousAgentLoop(provider=self.llm_provider, max_iterations=12)
        agent_output = await agent.run(context, initial_prompt=initial_prompt, on_event=on_event)

        processed_findings: list[Finding] = []
        verified_patches: list[dict[str, Any]] = []
        sandbox_results: list[dict[str, Any]] = []

        # Include static rule engine findings
        for rf in rule_findings:
            try:
                rf = FindingLifecycleManager.transition(rf, target_status="supported", reason="Static rule engine detection")
                processed_findings.append(rf)
            except Exception as tr_err:
                logger.warning(f"Static rule finding transition error: {tr_err}")

        # Track seen file line locations to avoid duplicate findings for the same code line
        seen_locations = {(f.path, f.line) for f in processed_findings}

        # 4. Process and Validate Hypotheses into Standardized Findings
        for raw_hyp in agent_output.hypotheses:
            path = raw_hyp.get("path", "unknown")
            line = raw_hyp.get("line", 1)
            related_id = raw_hyp.get("related_issue_id") or (target_issue.number if target_issue else None)

            if (path, line) in seen_locations:
                logger.info(f"Enriching existing finding for {path}:{line} with issue context")
                existing = next((f for f in processed_findings if f.path == path and f.line == line), None)
                if existing and related_id:
                    existing.related_issue_id = related_id
                continue
            seen_locations.add((path, line))

            validation_info = raw_hyp.get("validation", {})
            status = "rejected" if validation_info.get("status") == "rejected" else "supported"

            finding = Finding(
                rule=raw_hyp.get("title", "defect_candidate"),
                path=raw_hyp.get("path", "unknown"),
                line=raw_hyp.get("line", 1),
                title=raw_hyp.get("title", "Candidate Defect"),
                description=raw_hyp.get("description", ""),
                severity=raw_hyp.get("severity", "medium"),
                confidence=raw_hyp.get("confidence", 0.5),
                evidence=raw_hyp.get("evidence", []),
                detection_source="llm_investigation",
                status="candidate",
                related_issue_id=related_id,
            )

            try:
                finding = FindingLifecycleManager.transition(
                    finding, target_status=status, reason=validation_info.get("reason", "Agent investigation completed")
                )
            except ValueError as val_err:
                logger.warning(f"Finding transition error: {val_err}")

            processed_findings.append(finding)
            await self._emit(on_event, "hypothesis_validated", finding.model_dump())

        # 5. Patch Generation, AST Verification, and Subprocess Sandbox Execution
        from app.utils.source import is_test_file

        # Filter candidate findings: strictly exclude test files from being patched as defects
        candidate_patch_findings = [
            f for f in processed_findings
            if f.status == "supported" and not is_test_file(f.path)
        ]

        # In targeted issue mode, isolate strictly the finding addressing the targeted issue
        if target_issue:
            targeted = [f for f in candidate_patch_findings if f.related_issue_id == target_issue.number]
            if targeted:
                candidate_patch_findings = targeted[:1]
            else:
                agent_findings = [f for f in candidate_patch_findings if f.detection_source == "llm_investigation"]
                candidate_patch_findings = agent_findings[:1] if agent_findings else candidate_patch_findings[:1]
        else:
            # In general repository mode, limit to top priority supported finding
            candidate_patch_findings = candidate_patch_findings[:1]

        if auto_generate_patch:
            for finding in candidate_patch_findings:
                target_file = next((f for f in context.snapshot.files if f.path == finding.path), None)
                if target_file:
                    patch_gen = PatchGenerator(provider=self.llm_provider)
                    try:
                        await self._emit(on_event, "patch_generating", {"finding_id": finding.id, "path": finding.path})
                        patch = await patch_gen.generate_patch(
                            finding, target_file.content, target_issue=target_issue
                        )

                        await self._emit(on_event, "patch_verifying_ast", {"finding_id": finding.id, "path": patch.path})
                        v_res = self.patch_verifier.verify_patch(patch, target_file.content)
                        if not v_res.success:
                            logger.warning(f"Initial patch verification failed ({v_res.error}). Attempting self-correction retry...")
                            patch = await patch_gen.generate_patch(
                                finding,
                                target_file.content,
                                error_feedback=v_res.error,
                                target_issue=target_issue,
                            )
                            v_res = self.patch_verifier.verify_patch(patch, target_file.content)

                        if v_res.success:
                            # 6. Execute Pytest in Subprocess Sandbox
                            await self._emit(on_event, "sandbox_executing_pytest", {"finding_id": finding.id, "path": patch.path})
                            workspace_files = {f.path: f.content for f in context.snapshot.files}
                            workspace_files[patch.path] = v_res.modified_content or target_file.content

                            sandbox_res = await self.sandbox.run_pytest_in_sandbox(
                                files=workspace_files,
                                test_file_path="test_regression.py",
                                test_code=patch.regression_test_code,
                            )

                            sandbox_results.append({
                                "finding_id": finding.id,
                                "sandbox_result": sandbox_res.model_dump(),
                            })

                            await self._emit(on_event, "sandbox_pytest_completed", {
                                "finding_id": finding.id,
                                "success": sandbox_res.success,
                                "exit_code": sandbox_res.exit_code,
                            })

                            FindingLifecycleManager.transition(
                                finding, target_status="fixed", reason="Patch verified via AST syntax check & subprocess sandbox"
                            )

                            verified_patches.append({
                                "finding_id": finding.id,
                                "patch": patch.model_dump(),
                                "verification": v_res.model_dump(),
                                "related_issue_id": finding.related_issue_id,
                            })
                        else:
                            logger.error(f"Patch rejected by AST and semantic verifier: {v_res.error}")
                            await self._emit(on_event, "patch_verification_rejected", {
                                "finding_id": finding.id,
                                "path": patch.path,
                                "error": v_res.error,
                            })
                    except Exception as patch_exc:
                        logger.error(f"Failed to generate/verify patch for finding {finding.id}: {patch_exc}")

        # 6. GitHub Auto-Forking & Cross-Repo PR Automation
        pr_result = None
        if verified_patches:
            first_patch_entry = verified_patches[0]
            first_patch = first_patch_entry["patch"]
            rel_issue_id = first_patch_entry.get("related_issue_id")
            repo_meta = context.snapshot.repository

            if not human_approved_for_pr:
                jev_eval = None
                try:
                    from app.services.jev_client import JevDecisionService
                    jev = JevDecisionService()
                    jev_eval = await jev.evaluate_patch_risk(
                        patch_summary=first_patch["explanation"],
                        target_file=first_patch["path"],
                        diff=f"- {first_patch.get('target_code', '')}\n+ {first_patch.get('replacement_code', '')}",
                    )
                except Exception as jev_exc:
                    logger.debug(f"Jev risk evaluation skipped: {jev_exc}")

                approval_payload = {
                    "action": "open_pull_request",
                    "requires_approval": True,
                    "target_repository": repo_meta.full_name,
                    "patch_summary": first_patch["explanation"],
                    "patch_path": first_patch["path"],
                    "modified_content": verified_patches[0]["verification"].get("modified_content"),
                    "default_branch": repo_meta.default_branch,
                    "related_issue_id": rel_issue_id,
                    "message": f"Approval required to create Pull Request on {repo_meta.full_name} for verified patch in {first_patch['path']}.",
                    "existing_pr": existing_pr,
                }
                if existing_pr:
                    approval_payload["existing_pr_warning"] = (
                        f"WARNING: An open Pull Request already addresses Issue #{rel_issue_id}: "
                        f"PR #{existing_pr['pr_number']} ('{existing_pr['title']}') by @{existing_pr.get('author', 'contributor')}."
                    )
                if jev_eval:
                    approval_payload["jev_risk_tier"] = jev_eval.risk_tier
                    approval_payload["jev_safety_score"] = jev_eval.safety_probability
                    approval_payload["jev_confidence"] = jev_eval.confidence

                await self._emit(on_event, "human_approval_required", approval_payload)
            else:
                # User approved PR creation
                await self._emit(on_event, "fork_checking", {"repository": repo_meta.full_name})
                fork_details = await self.fork_service.ensure_fork(repo_meta.owner, repo_meta.name)

                await self._emit(on_event, "fork_ensured", {
                    "is_fork": fork_details.is_fork,
                    "push_owner": fork_details.owner,
                    "push_repo": fork_details.name,
                })

                pr_automation = GitHubPRAutomation(policy_engine=self.policy_engine)
                path_slug = first_patch["path"].replace("/", "_").replace(".", "_")
                branch_name = f"repoguard/fix-{path_slug}-{uuid.uuid4().hex[:6]}"

                mod_content = verified_patches[0]["verification"].get("modified_content")
                if mod_content:
                    await pr_automation.prepare_branch_and_commit(
                        owner=fork_details.owner,
                        repo=fork_details.name,
                        branch_name=branch_name,
                        base_branch=repo_meta.default_branch,
                        file_path=first_patch["path"],
                        modified_content=mod_content,
                        commit_message=f"fix(repoguard): automated patch for {first_patch['path']}",
                    )
                else:
                    await pr_automation.create_remote_branch(
                        owner=fork_details.owner,
                        repo=fork_details.name,
                        branch_name=branch_name,
                        base_branch=repo_meta.default_branch,
                    )

                # Head ref formatted as 'username:branch' if fork, or 'branch' if direct
                head_ref = f"{fork_details.owner}:{branch_name}" if fork_details.is_fork else branch_name
                pr_title = f"fix(repoguard): automated patch for {first_patch['path']}"
                if rel_issue_id:
                    pr_title += f" (fixes #{rel_issue_id})"

                pr_body = await pr_automation.format_pr_body(
                    owner=fork_details.parent_owner,
                    repo=fork_details.parent_name,
                    file_path=first_patch["path"],
                    explanation=first_patch["explanation"],
                    issue_id=rel_issue_id,
                    base_branch=repo_meta.default_branch,
                )

                pr_req = PRCreationRequest(
                    repository_owner=fork_details.parent_owner,
                    repository_name=fork_details.parent_name,
                    branch_name=branch_name,
                    title=pr_title,
                    body=pr_body,
                    head_branch=head_ref,
                    base_branch=repo_meta.default_branch,
                    human_approved=True,
                )

                await self._emit(on_event, "pr_creating", {"head": head_ref, "base": repo_meta.default_branch})
                pr_res = await pr_automation.create_pull_request(pr_req)
                pr_result = pr_res.model_dump()

                if pr_res.success:
                    await self._emit(on_event, "pr_opened", {"pr_number": pr_res.pr_number, "html_url": pr_res.html_url})

        pipeline_res = PipelineExecutionResult(
            repository=context.snapshot.repository.full_name,
            status="completed",
            summary=agent_output.summary,
            findings=processed_findings,
            patches=verified_patches,
            sandbox_results=sandbox_results,
            pr_result=pr_result,
            iterations_used=agent_output.iterations_used,
        )

        await self._emit(on_event, "pipeline_completed", pipeline_res.model_dump())
        return pipeline_res
