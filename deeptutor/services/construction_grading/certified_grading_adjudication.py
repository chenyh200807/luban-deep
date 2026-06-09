from __future__ import annotations

from typing import Any

CERTIFIED_GRADING_ADJUDICATION_SOURCE = "certified_grading_policy"
DEFAULT_CERTIFIED_GRADING_MIN_CONFIDENCE = 0.85
_RESOLVED_CONFLICT_STATUSES = {"", "none", "no_conflict", "resolved", "not_applicable"}
_CERTIFIED_STATUSES = {"published", "certified", "release_truth", "production"}


def attach_certified_grading_adjudication(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach a trusted adjudication only when a published grading policy is explicit.

    This is production-time consumption of a design-time certified policy. It never
    infers certification from a generic curated rubric or an LLM answer.
    """

    out = dict(payload or {})
    policy = certified_grading_policy_from_payload(out)
    trusted = trusted_adjudication_from_certified_policy(policy)
    if not trusted:
        return out

    signal = dict(out.get("next_training_signal") or {})
    signal["certified_grading_policy"] = _policy_public_payload(policy)
    signal["trusted_adjudication"] = trusted
    signal["final_adjudication_result"] = {
        "trusted_adjudication": trusted,
        "certified_grading_policy": _policy_public_payload(policy),
        "score_awarded": out.get("score_awarded"),
        "max_score": out.get("max_score"),
    }
    out["next_training_signal"] = signal
    out["certified_grading_policy"] = _policy_public_payload(policy)
    out["claim_promotion_allowed"] = True
    out["preview_only"] = False
    out["mastery_raised"] = False
    out["canonical_truth_written"] = False
    return out


def certified_grading_policy_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
    candidates = (
        signal.get("certified_grading_policy"),
        payload.get("certified_grading_policy"),
        signal.get("trusted_grading_policy"),
        payload.get("trusted_grading_policy"),
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def trusted_adjudication_from_certified_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if not policy:
        return {}
    status = _text(policy.get("status") or policy.get("registry_status")).lower()
    certified = bool(policy.get("certified") is True or status in _CERTIFIED_STATUSES)
    if not certified:
        return {}

    policy_id = _text(policy.get("policy_id") or policy.get("id"))
    rubric_hash = _text(policy.get("rubric_hash") or policy.get("rubric_id_hash"))
    grader_version = _text(policy.get("grader_version") or policy.get("version"))
    if not (policy_id and rubric_hash and grader_version):
        return {}
    if bool(policy.get("requires_human")):
        return {}

    confidence = _float(policy.get("confidence"))
    if confidence is None or confidence < _min_confidence(policy):
        return {}
    conflict_status = _text(policy.get("conflict_status") or "resolved").lower()
    if conflict_status not in _RESOLVED_CONFLICT_STATUSES:
        return {}

    return {
        "source": CERTIFIED_GRADING_ADJUDICATION_SOURCE,
        "confidence": confidence,
        "conflict_status": conflict_status or "resolved",
        "requires_human": False,
        "policy_id": policy_id,
        "rubric_hash": rubric_hash,
        "grader_version": grader_version,
    }


def _policy_public_payload(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": _text(policy.get("policy_id") or policy.get("id")),
        "rubric_hash": _text(policy.get("rubric_hash") or policy.get("rubric_id_hash")),
        "grader_version": _text(policy.get("grader_version") or policy.get("version")),
        "status": _text(policy.get("status") or policy.get("registry_status")),
        "confidence": _float(policy.get("confidence")),
        "conflict_status": _text(policy.get("conflict_status") or "resolved").lower() or "resolved",
    }


def _min_confidence(policy: dict[str, Any]) -> float:
    configured = _float(policy.get("min_confidence"))
    return configured if configured is not None else DEFAULT_CERTIFIED_GRADING_MIN_CONFIDENCE


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()
