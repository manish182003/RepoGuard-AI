import hashlib
import logging
from app.schemas.finding import Finding

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"investigating", "supported", "rejected"},
    "investigating": {"supported", "rejected"},
    "supported": {"reproduced", "fixed", "rejected"},
    "reproduced": {"fixed", "rejected"},
    "fixed": {"validated", "rejected"},
    "validated": set(),
    "rejected": {"candidate"},  # allow re-evaluating rejected findings if new evidence is found
}


class FindingLifecycleManager:
    """Manages creation, deduplication key generation, and valid state transitions of findings."""

    @staticmethod
    def generate_dedup_key(path: str, line: int, rule: str) -> str:
        """Generate a deterministic deduplication hash key for a finding."""
        raw_key = f"{path.strip()}:{line}:{rule.strip()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def transition(finding: Finding, target_status: str, reason: str) -> Finding:
        """Attempt to transition a finding to a new target status.

        Raises ValueError if the status transition is invalid according to policy.
        """
        current_status = finding.status

        if target_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
            raise ValueError(
                f"Invalid status transition from '{current_status}' to '{target_status}'. "
                f"Allowed target states: {sorted(list(ALLOWED_TRANSITIONS.get(current_status, set())))}"
            )

        finding.status = target_status  # type: ignore[assignment]
        finding.status_reason = reason
        logger.info(f"Finding {finding.id} transitioned from '{current_status}' to '{target_status}': {reason}")
        return finding
