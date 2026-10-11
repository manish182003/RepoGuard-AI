from typing import Literal

from pydantic import BaseModel, Field


class InvestigationHypothesis(BaseModel):
    title: str
    description: str
    path: str
    line: int = Field(ge=1)
    severity: Literal[
        "critical", "high", "medium", "low", "info"
    ]
    evidence: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class InvestigationResult(BaseModel):
    summary: str
    hypotheses: list[InvestigationHypothesis]


class InvestigationRequest(BaseModel):
    repository_url: str
    issue_state: Literal["open", "closed", "all"] = "open"
    auto_generate_patch: bool = True
    human_approved_for_pr: bool = False
    target_issue_number: int | None = None
