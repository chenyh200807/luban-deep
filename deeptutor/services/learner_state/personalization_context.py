from __future__ import annotations

from typing import Any

from deeptutor.services.learner_state.next_best_action import build_next_best_actions


_STABLE_CLAIM_STATUSES = {"confirmed", "repeated", "observed"}
_GAP_CLAIM_STATUSES = {"stale", "superseded", "contradicted", "rejected"}


def build_personalization_context_pack(
    *,
    user_id: str,
    learning_brain: dict[str, Any] | None,
    active_training_intent: dict[str, Any] | None = None,
    recent_events: list[Any] | None = None,
    max_claims: int = 5,
) -> dict[str, Any]:
    claims = _claim_views(learning_brain, max_claims=max_claims)
    intent = dict(active_training_intent or {}) if isinstance(active_training_intent, dict) else {}
    actions = build_next_best_actions(
        user_id=user_id,
        training_intents=[intent] if intent else [],
        max_actions=1,
    )
    return {
        "schema_version": 1,
        "user_id": str(user_id or "").strip(),
        "source": "PersonalizationContextPack",
        "authority": {
            "claims": "learning_synthesis",
            "evidence": "learner_memory_events.learning_evidence",
            "prescription": "training_intent",
        },
        "top_claims": claims,
        "recent_evidence_refs": _recent_evidence_refs(recent_events, claims),
        "active_training_intent": intent,
        "next_best_action_candidates": actions,
        "gaps": _claim_gaps(learning_brain),
    }


def _claim_views(learning_brain: dict[str, Any] | None, *, max_claims: int) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    for item in _compiled_objects(learning_brain):
        status = str(item.get("claim_status") or "observed").strip() or "observed"
        if status not in _STABLE_CLAIM_STATUSES:
            continue
        evidence_refs = _refs(item.get("evidence_refs")) or _refs(item.get("supporting_event_ids"))
        if not evidence_refs:
            continue
        views.append({
            "claim_id": str(item.get("object_id") or item.get("claim_id") or "").strip(),
            "object_type": str(item.get("object_type") or "").strip(),
            "claim_status": status,
            "concept_id": str(item.get("concept_id") or "").strip(),
            "label": str(
                item.get("label")
                or item.get("display_title")
                or item.get("current_truth")
                or item.get("claim")
                or ""
            ).strip(),
            "confidence": item.get("confidence"),
            "evidence_refs": evidence_refs[:5],
        })
    views.sort(key=lambda item: (_status_rank(item.get("claim_status")), -float(item.get("confidence") or 0)))
    return views[: max(1, int(max_claims or 5))]


def _claim_gaps(learning_brain: dict[str, Any] | None) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for item in _compiled_objects(learning_brain):
        status = str(item.get("claim_status") or "").strip()
        if status in _GAP_CLAIM_STATUSES:
            gaps.append({
                "claim_id": str(item.get("object_id") or item.get("claim_id") or "").strip(),
                "reason": f"claim_{status}",
            })
    return gaps


def _recent_evidence_refs(recent_events: list[Any] | None, claims: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for event in list(recent_events or []):
        if isinstance(event, dict):
            refs.extend(_refs([event.get("event_id")]))
        else:
            refs.extend(_refs([getattr(event, "event_id", "")]))
    for claim in claims:
        refs.extend(_refs(claim.get("evidence_refs")))
    return _dedupe_refs(refs)[:10]


def _compiled_objects(learning_brain: dict[str, Any] | None) -> list[dict[str, Any]]:
    brain = dict(learning_brain or {}) if isinstance(learning_brain, dict) else {}
    objects = brain.get("compiled_objects") or []
    if isinstance(objects, dict):
        return [dict(item) for item in objects.values() if isinstance(item, dict)]
    return [dict(item) for item in list(objects or []) if isinstance(item, dict)]


def _refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item or "").strip() for item in list(value or []) if str(item or "").strip()]


def _dedupe_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _status_rank(status: Any) -> int:
    return {"confirmed": 0, "repeated": 1, "observed": 2}.get(str(status or "").strip(), 9)


__all__ = ["build_personalization_context_pack"]
