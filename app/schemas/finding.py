import uuid
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Finding(BaseModel):
    """Standardized finding model representing a candidate or confirmed defect."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule: str
    path: str
    line: int = Field(ge=1)
    title: str
    description: str = ""
    severity: Literal["critical", "high", "medium", "low", "info"] = "medium"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence: list[str] = Field(default_factory=list)
    detection_source: Literal["ast_rule", "llm_investigation", "static_analysis"] = "ast_rule"
    status: Literal[
        "candidate",
        "investigating",
        "supported",
        "reproduced",
        "rejected",
        "fixed",
        "validated",
    ] = "candidate"
    related_issue_id: int | None = None
    repro_status: Literal["untested", "passed", "failed"] = "untested"
    fix_status: Literal["unfixed", "patched", "pr_opened"] = "unfixed"
    status_reason: str | None = None

    @field_validator("evidence", mode="before")
    @classmethod
    def coerce_evidence(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


class FindingTransitionRequest(BaseModel):
    """Schema for requesting a valid status transition on a finding."""
    target_status: Literal[
        "candidate",
        "investigating",
        "supported",
        "reproduced",
        "rejected",
        "fixed",
        "validated",
    ]
    reason: str