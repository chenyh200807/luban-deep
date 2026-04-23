"""Controlled promotion helpers for benchmark registry cases."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from deeptutor.services.benchmark.models import ALLOWED_CASE_TIERS

_NEXT_TIER = {
    "incident_replay": "regression_tier",
    "regression_tier": "gate_stable",
}

_TARGET_SUITE_BY_TIER = {
    "regression_tier": "regression_watch",
    "gate_stable": "pr_gate_core",
}


def _move_case_to_target_suite(
    *,
    registry_payload: dict[str, Any],
    case_id: str,
    target_tier: str,
) -> None:
    suites = registry_payload.get("suites")
    if not isinstance(suites, dict):
        raise TypeError("registry payload must contain suites mapping")

    target_suite_name = _TARGET_SUITE_BY_TIER.get(target_tier)
    if not target_suite_name:
        return
    target_suite = suites.get(target_suite_name)
    if not isinstance(target_suite, dict):
        raise ValueError(f"Missing benchmark suite for target_tier: {target_suite_name}")

    for suite_name, suite_payload in suites.items():
        if not isinstance(suite_payload, dict):
            raise TypeError(f"benchmark suite must be a mapping: {suite_name}")
        case_ids = [str(item) for item in (suite_payload.get("case_ids") or [])]
        suite_payload["case_ids"] = [item for item in case_ids if item != case_id]

    target_case_ids = [str(item) for item in (target_suite.get("case_ids") or [])]
    if case_id not in target_case_ids:
        target_case_ids.append(case_id)
    target_suite["case_ids"] = target_case_ids


def promote_registry_case_payload(
    *,
    registry_payload: dict[str, Any],
    case_id: str,
    target_tier: str,
    reason: str = "",
) -> dict[str, Any]:
    """Return a new registry payload with one controlled case promotion applied."""

    normalized_case_id = str(case_id or "").strip()
    normalized_target_tier = str(target_tier or "").strip()
    if not normalized_case_id:
        raise ValueError("case_id is required")
    if normalized_target_tier not in ALLOWED_CASE_TIERS:
        raise ValueError(f"Unsupported target_tier: {target_tier}")
    if normalized_target_tier == "exploratory":
        raise ValueError("exploratory is not a promotion target")

    next_payload = deepcopy(registry_payload)
    cases = next_payload.get("cases")
    if not isinstance(cases, dict):
        raise TypeError("registry payload must contain cases mapping")
    case_payload = cases.get(normalized_case_id)
    if not isinstance(case_payload, dict):
        raise ValueError(f"Unknown benchmark case_id: {normalized_case_id}")

    current_tier = str(case_payload.get("case_tier") or "").strip()
    expected_target = _NEXT_TIER.get(current_tier)
    if expected_target != normalized_target_tier:
        raise ValueError(
            f"Invalid promotion transition: {current_tier} -> {normalized_target_tier}"
        )

    case_payload["case_tier"] = normalized_target_tier
    case_payload["promotion_status"] = "promoted"
    case_payload["promoted_from_case_id"] = str(
        case_payload.get("promoted_from_case_id") or normalized_case_id
    ).strip()
    _move_case_to_target_suite(
        registry_payload=next_payload,
        case_id=normalized_case_id,
        target_tier=normalized_target_tier,
    )
    if current_tier == "incident_replay":
        case_payload["origin_type"] = "incident_replay"
        case_payload["origin_ref"] = str(case_payload.get("origin_ref") or normalized_case_id).strip()
    if reason:
        case_payload["promotion_reason"] = str(reason).strip()
    return next_payload


def build_case_acceptance_snapshot(registry_payload: dict[str, Any], case_id: str) -> dict[str, Any]:
    """Answer the PRD section 16 acceptance questions for one case."""

    normalized_case_id = str(case_id or "").strip()
    cases = registry_payload.get("cases") or {}
    suites = registry_payload.get("suites") or {}
    case_payload = cases.get(normalized_case_id)
    if not isinstance(case_payload, dict):
        raise ValueError(f"Unknown benchmark case_id: {normalized_case_id}")
    suite_names = [
        suite_name
        for suite_name, suite_payload in suites.items()
        if normalized_case_id in (suite_payload.get("case_ids") or [])
    ]
    case_tier = str(case_payload.get("case_tier") or "")
    return {
        "case_id": normalized_case_id,
        "registered": True,
        "contract_domain": case_payload.get("contract_domain"),
        "suite_names": suite_names,
        "failure_taxonomy_scope": case_payload.get("failure_taxonomy_scope") or [],
        "affects_pre_release_gate": "pr_gate_core" in suite_names or case_tier == "gate_stable",
        "is_incident_promoted": case_payload.get("origin_type") == "incident_replay",
        "promotion_status": case_payload.get("promotion_status"),
        "promoted_from_case_id": case_payload.get("promoted_from_case_id") or "",
    }
