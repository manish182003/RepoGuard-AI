import re
import logging
from typing import Literal
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SECRET_PATTERNS = [
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
    re.compile(r"gsk_[a-zA-Z0-9_-]{20,64}"),
    re.compile(r"sk-[a-zA-Z0-9]{20,64}"),
]


class SecurityPolicy(BaseModel):
    require_human_approval_for_prs: bool = True
    allow_fork_creation: bool = True
    max_pr_per_run: int = 1


class ExecutionDecision(BaseModel):
    allowed: bool
    risk_level: Literal["low", "medium", "high"]
    requires_approval: bool
    reason: str
    jev_safety_score: float | None = None
    jev_confidence: float | None = None


class PolicyEngine:
    """Enforces safety rules, permission checks, risk classification, and secret redaction."""

    def __init__(self, policy: SecurityPolicy | None = None):
        self.policy = policy or SecurityPolicy()

    def evaluate_action(
        self,
        action: Literal["read_code", "run_sandbox", "create_branch", "open_pr"],
        human_approved: bool = False,
    ) -> ExecutionDecision:
        """Evaluate whether an action is allowed under the security policy."""

        if action in ("read_code", "ast_analysis"):
            return ExecutionDecision(
                allowed=True,
                risk_level="low",
                requires_approval=False,
                reason="Read-only operation permitted.",
            )

        if action == "run_sandbox":
            return ExecutionDecision(
                allowed=True,
                risk_level="medium",
                requires_approval=False,
                reason="Isolated workspace operation permitted.",
            )

        if action in ("create_branch", "open_pr"):
            if self.policy.require_human_approval_for_prs and not human_approved:
                return ExecutionDecision(
                    allowed=False,
                    risk_level="high",
                    requires_approval=True,
                    reason="Opening a GitHub Pull Request requires explicit human approval.",
                )

            return ExecutionDecision(
                allowed=True,
                risk_level="high",
                requires_approval=True,
                reason="High-risk GitHub operation approved by human user.",
            )

        return ExecutionDecision(
            allowed=False,
            risk_level="high",
            requires_approval=True,
            reason=f"Unknown action '{action}' blocked by policy.",
        )

    async def evaluate_action_with_jev(
        self,
        action: Literal["read_code", "run_sandbox", "create_branch", "open_pr"],
        human_approved: bool = False,
        patch_summary: str = "",
        target_file: str = "",
        diff: str = "",
    ) -> ExecutionDecision:
        """Asynchronously evaluate policy action augmented by TypeSafe Jev risk scoring."""
        base_decision = self.evaluate_action(action, human_approved=human_approved)

        if action in ("open_pr", "create_branch") and patch_summary:
            try:
                from app.services.jev_client import JevDecisionService
                jev = JevDecisionService()
                eval_res = await jev.evaluate_patch_risk(
                    patch_summary=patch_summary,
                    target_file=target_file,
                    diff=diff,
                )
                base_decision.risk_level = eval_res.risk_tier
                base_decision.jev_safety_score = eval_res.safety_probability
                base_decision.jev_confidence = eval_res.confidence
            except Exception as exc:
                logger.debug(f"Jev policy scoring skipped: {exc}")

        return base_decision

    def redact_secrets(self, text: str) -> str:
        """Sanitize text by replacing secret patterns (API keys, tokens) with [REDACTED]."""
        sanitized = text
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
        return sanitized
