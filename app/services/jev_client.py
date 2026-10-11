import logging
from typing import Any, Literal
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class JevIssueEvaluation(BaseModel):
    is_actionable_bug: bool
    bug_probability: float = Field(ge=0.0, le=1.0)
    category: str
    confidence: float = 0.0


class JevPatchEvaluation(BaseModel):
    is_safe: bool
    safety_probability: float = Field(ge=0.0, le=1.0)
    risk_tier: Literal["low", "medium", "high"]
    confidence: float = 0.0


class JevToolGateEvaluation(BaseModel):
    is_allowed: bool
    safety_probability: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool


class JevDecisionService:
    """TypeSafe Jev System One Decision Client via OpenRouter Decisions API.
    
    Provides structured, probabilistic decision primitives (Noul, Choice, Score)
    for issue triage, security policy gating, and patch risk evaluation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "typesafe/jev-1.13",
        timeout: float = 15.0,
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model
        self.timeout = timeout
        self.endpoint = "https://openrouter.ai/api/alpha/decisions"

    async def _post_decision(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any] | None:
        if not self.api_key:
            logger.debug("OpenRouter API key is not configured; skipping Jev decision call.")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "state": state,
            "questions": questions,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(self.endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("answers", {})
                else:
                    logger.warning(f"Jev API returned status {res.status_code}: {res.text}")
                    return None
        except Exception as exc:
            logger.warning(f"Jev decision request failed: {exc}")
            return None

    async def triage_issue(self, title: str, body: str) -> JevIssueEvaluation:
        """Use Jev to evaluate whether a GitHub issue is an actionable code defect."""
        state = {
            "title": title[:300],
            "body": (body or "")[:1200],
        }
        questions = {
            "is_actionable_bug": {
                "type": "noul",
                "instructions": "Is this issue an actionable software bug or regression in the code repository?",
                "criteria": {
                    "true": "Broken behavior, regression, logic error, memory leak, or crash in code.",
                    "false": "Feature request, question, translation, or documentation discussion.",
                },
            },
            "category": {
                "type": "choice",
                "instructions": "What category best describes this problem?",
                "criteria": {
                    "logic_defect": "Incorrect condition, wrong calculation, or broken control flow.",
                    "crash": "Unhandled exception, panic, or crash.",
                    "feature_request": "Enhancement or proposal.",
                },
            },
        }

        answers = await self._post_decision(state, questions)
        if answers:
            noul_data = answers.get("is_actionable_bug", {})
            prob = float(noul_data.get("noul", 0.5))
            choice_data = answers.get("category", {})
            cat = str(choice_data.get("choice", "logic_defect"))
            conf = float(choice_data.get("confidence", 0.5))

            return JevIssueEvaluation(
                is_actionable_bug=(prob >= 0.65),
                bug_probability=prob,
                category=cat,
                confidence=conf,
            )

        # Fallback heuristic if API call fails
        title_lower = title.lower()
        bug_keywords = ["bug", "fail", "error", "crash", "wrong", "leak", "exception", "broken"]
        is_bug = any(kw in title_lower for kw in bug_keywords)
        return JevIssueEvaluation(
            is_actionable_bug=is_bug,
            bug_probability=0.8 if is_bug else 0.3,
            category="logic_defect" if is_bug else "feature_request",
            confidence=0.5,
        )

    async def evaluate_patch_risk(
        self,
        patch_summary: str,
        target_file: str,
        diff: str = "",
    ) -> JevPatchEvaluation:
        """Use Jev to score the risk tier and safety of a proposed patch before opening a PR."""
        state = {
            "target_file": target_file,
            "explanation": patch_summary[:600],
            "diff": diff[:1500] if diff else "diff snippet not available",
        }
        questions = {
            "is_safe_remediation": {
                "type": "noul",
                "instructions": "Is this code patch a safe, targeted bug remediation without introducing critical security hazards?",
                "criteria": {
                    "true": "Safe defect fix that preserves core functionality.",
                    "false": "Destructive change, security vulnerability, or credential leak.",
                },
            },
            "risk_tier": {
                "type": "choice",
                "instructions": "What is the risk level of applying this patch automatically?",
                "criteria": {
                    "low": "Minor isolated bug fix or safe condition update in non-security module.",
                    "medium": "Changes parsing or serialization behavior across core modules.",
                    "high": "Modifies authentication, cryptographic keys, permissions, or system credentials.",
                },
            },
        }

        answers = await self._post_decision(state, questions)
        if answers:
            noul_data = answers.get("is_safe_remediation", {})
            prob = float(noul_data.get("noul", 0.8))
            choice_data = answers.get("risk_tier", {})
            tier = str(choice_data.get("choice", "medium"))
            if tier not in ("low", "medium", "high"):
                tier = "medium"
            conf = float(choice_data.get("confidence", 0.5))

            return JevPatchEvaluation(
                is_safe=(prob >= 0.5),
                safety_probability=prob,
                risk_tier=tier,
                confidence=conf,
            )

        # Fallback heuristic
        is_sec = any(w in target_file.lower() for w in ["auth", "token", "password", "security", "crypto"])
        return JevPatchEvaluation(
            is_safe=True,
            safety_probability=0.85,
            risk_tier="high" if is_sec else "medium",
            confidence=0.5,
        )
