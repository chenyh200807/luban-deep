from __future__ import annotations

from typing import Any


REQUIRED_RUNTIME_FIELDS = (
    "owner_role",
    "review_authority",
    "supersede_policy",
)

VALID_M35_STATUSES = {"release_candidate", "shadow_candidate", "blocked"}
VALID_LIFECYCLE_STATUSES = {
    "candidate",
    "reviewed",
    "shadow_candidate",
    "release_candidate",
    "controlled_default",
    "superseded",
    "blocked",
}
RUNTIME_CONSUMABLE_STATUSES = {"release_candidate", "shadow_candidate"}


def evaluate_m35_artifact_governance(artifact: dict[str, Any]) -> dict[str, Any]:
    """Evaluate M35 artifact ownership/lifecycle gates.

    This is a governance read model only. It never promotes official scoring
    authority, writes a registry, or mutates learner truth.
    """
    status = str(artifact.get("status") or "")
    lifecycle_status = str(artifact.get("lifecycle_status") or status)
    quality_gates = artifact.get("quality_gates") if isinstance(artifact.get("quality_gates"), dict) else {}
    blocking_reasons: list[str] = []

    if not artifact.get("artifact_version"):
        blocking_reasons.append("missing_artifact_version")

    for field in REQUIRED_RUNTIME_FIELDS:
        if not artifact.get(field):
            blocking_reasons.append(f"missing_{field}")

    if not artifact.get("rollback_policy"):
        blocking_reasons.append("missing_rollback_policy")

    if not artifact.get("source_refs"):
        blocking_reasons.append("missing_source_refs")

    if status not in VALID_M35_STATUSES:
        blocking_reasons.append("invalid_m35_status")

    if lifecycle_status not in VALID_LIFECYCLE_STATUSES:
        blocking_reasons.append("invalid_lifecycle_status")

    if quality_gates.get("score_sum_ok") is not True:
        blocking_reasons.append("score_sum_not_verified")

    if _as_float(
        quality_gates.get("source_validity", quality_gates.get("source_refs_verified_rate"))
    ) < 0.95:
        blocking_reasons.append("source_validity_below_gate")

    runtime_consumable = not blocking_reasons and status in RUNTIME_CONSUMABLE_STATUSES

    return {
        "runtime_consumable": runtime_consumable,
        "official_score_allowed": False,
        "lifecycle_status": lifecycle_status,
        "blocking_reasons": blocking_reasons,
    }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
