from __future__ import annotations

from typing import Any


UNSUPPORTED_CLAIM = "unsupported_claim"
STALE_CLAIM_NEEDS_RETEST = "stale_claim_needs_retest"
CONTRADICTED_CLAIM = "contradicted_claim"
MISSING_NEXT_ACTION = "missing_next_action"
GRAPH_GAP = "graph_gap"
GENERIC_PERSONALIZATION = "generic_personalization"


def lint_learning_brain_projection(projection: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = projection if isinstance(projection, dict) else {}
    issues: list[dict[str, Any]] = []
    claims = [*_weak_points(payload), *_compiled_objects(payload)]
    for claim in claims:
        claim_id = _claim_id(claim)
        evidence_refs = _refs(claim.get("evidence_refs")) or _refs(claim.get("supporting_event_ids"))
        status = str(claim.get("claim_status") or claim.get("status") or "").strip()
        if not evidence_refs:
            issues.append({"code": UNSUPPORTED_CLAIM, "claim_id": claim_id})
        if status == "stale" or bool(claim.get("stale")):
            issues.append({"code": STALE_CLAIM_NEEDS_RETEST, "claim_id": claim_id})
        if status == "contradicted" or _refs(claim.get("conflicting_event_ids")):
            issues.append({"code": CONTRADICTED_CLAIM, "claim_id": claim_id})

    next_actions = _next_actions(payload)
    if claims and not any(_refs(action.get("evidence_refs")) for action in next_actions):
        issues.append({"code": MISSING_NEXT_ACTION, "claim_id": ""})

    graph = payload.get("typed_graph") if isinstance(payload.get("typed_graph"), dict) else {}
    for gap in list(graph.get("readiness_gaps") or payload.get("typed_graph_readiness_gaps") or []):
        if isinstance(gap, dict):
            issues.append({"code": GRAPH_GAP, "detail": str(gap.get("code") or "").strip()})
        elif str(gap or "").strip():
            issues.append({"code": GRAPH_GAP, "detail": str(gap).strip()})

    for action in next_actions:
        title = str(action.get("title") or action.get("primary_action") or "").strip()
        evidence_refs = _refs(action.get("evidence_refs"))
        if title in {"先完成一组练习", "先补一条可诊断证据", "先完成一组专项训练"} and not evidence_refs:
            issues.append({"code": GENERIC_PERSONALIZATION, "claim_id": ""})
    return issues


def _weak_points(projection: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(projection.get("weak_points") or []) if isinstance(item, dict)]


def _compiled_objects(projection: dict[str, Any]) -> list[dict[str, Any]]:
    objects = projection.get("compiled_objects") or projection.get("objects") or {}
    if isinstance(objects, dict):
        return [dict(item) for item in objects.values() if isinstance(item, dict)]
    return [dict(item) for item in list(objects or []) if isinstance(item, dict)]


def _next_actions(projection: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    direct = projection.get("next_best_actions")
    if isinstance(direct, list):
        out.extend(dict(item) for item in direct if isinstance(item, dict))
    context = projection.get("personalization_context") if isinstance(projection.get("personalization_context"), dict) else {}
    actions = context.get("next_best_action_candidates") if isinstance(context, dict) else []
    out.extend(dict(item) for item in list(actions or []) if isinstance(item, dict))
    return out


def _claim_id(claim: dict[str, Any]) -> str:
    return str(
        claim.get("claim_id")
        or claim.get("object_id")
        or ":".join(
            item
            for item in [
                str(claim.get("concept_id") or "").strip(),
                str(claim.get("error_code") or "").strip(),
            ]
            if item
        )
        or ""
    ).strip()


def _refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item or "").strip() for item in list(value or []) if str(item or "").strip()]


__all__ = [
    "UNSUPPORTED_CLAIM",
    "STALE_CLAIM_NEEDS_RETEST",
    "CONTRADICTED_CLAIM",
    "MISSING_NEXT_ACTION",
    "GRAPH_GAP",
    "GENERIC_PERSONALIZATION",
    "lint_learning_brain_projection",
]
