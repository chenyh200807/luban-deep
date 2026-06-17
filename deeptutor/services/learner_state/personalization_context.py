from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from deeptutor.services.learner_state.learning_trajectory import group_typed_edges
from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.training_intent import build_learning_training_intent

_STABLE_CLAIM_STATUSES = {"confirmed", "repeated", "observed"}
_GAP_CLAIM_STATUSES = {"stale", "superseded", "contradicted", "rejected"}
# 时间规则（遗忘曲线第一步）：active claim 末次证据超过该天数 → 进入 review_due。
REVIEW_DUE_AFTER_DAYS = 14

# Canonical schema id for register-before-use (schema-governance P2: this module is the
# single producer + single schema authority for the PersonalizationContextPack consumed
# across learner_state → capabilities/deep_question → construction_grading (adjudicator/
# writeback) → rag). The pack payload keeps the integer ``schema_version`` (1) + the
# ``source: "PersonalizationContextPack"`` tag for consumer compatibility; this string id
# makes the schema VISIBLE to the schema-registry closure so a competing PCP schema can
# never appear unregistered. Registered as T2 runtime-canonical in contracts/schema_registry.yaml.
SCHEMA_ID = "personalization_context_pack.v1"


def build_personalization_context_pack(
    *,
    user_id: str,
    learning_brain: dict[str, Any] | None,
    active_training_intent: dict[str, Any] | None = None,
    recent_events: list[Any] | None = None,
    max_claims: int = 5,
    now: float | None = None,
) -> dict[str, Any]:
    claims = _claim_views(learning_brain, max_claims=max_claims)
    improvement_signals = _improvement_signals(learning_brain)
    review_due = _review_due_claims(claims, now=now)
    intent = dict(active_training_intent or {}) if isinstance(active_training_intent, dict) else {}
    if not intent:
        # 无显式 intent 时复习项优先：时间规则只影响"先练哪个"的视图选择，
        # 不改变任何 claim 权威状态。
        review_due_ids = {item["claim_id"] for item in review_due}
        intent_claim = next(
            (claim for claim in claims if claim.get("claim_id") in review_due_ids),
            claims[0] if claims else {},
        )
        intent = _training_intent_from_claim(user_id=user_id, claim=intent_claim)
    actions = build_next_best_actions(
        user_id=user_id,
        training_intents=[intent] if intent else [],
        # 图谱自接线：投影里的真实错因图直通 NBA，why_this_now 优先引用
        # 真实 error→training 边而非泛化的证据计数。仍是只读视图。
        graph_chain=group_typed_edges(learning_brain),
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
        "recent_improvement_signals": improvement_signals,
        "recent_evidence_refs": _recent_evidence_refs(recent_events, claims),
        "active_training_intent": intent,
        "next_best_action_candidates": actions,
        "review_due": review_due,
        "feedback_guidance": _feedback_guidance(
            claims=claims,
            improvement_signals=improvement_signals,
            actions=actions,
        ),
        "gaps": _claim_gaps(learning_brain),
    }


def _review_due_claims(claims: list[dict[str, Any]], *, now: float | None) -> list[dict[str, Any]]:
    current = time.time() if now is None else float(now)
    due: list[dict[str, Any]] = []
    for claim in claims:
        if str(claim.get("decay_state") or "active") != "active":
            continue
        last_observed = str(claim.get("last_observed_at") or "").strip()
        last_ts = _parse_iso_timestamp(last_observed)
        if last_ts is None:
            continue
        days = (current - last_ts) / 86400.0
        if days >= REVIEW_DUE_AFTER_DAYS:
            due.append({
                "claim_id": str(claim.get("claim_id") or "").strip(),
                "concept_id": str(claim.get("concept_id") or "").strip(),
                "label": str(claim.get("label") or "").strip(),
                "last_observed_at": last_observed,
                "days_since_last_evidence": int(days),
                "reason": "time_rule_review_due",
            })
    due.sort(key=lambda item: -item["days_since_last_evidence"])
    return due


def _parse_iso_timestamp(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _claim_views(learning_brain: dict[str, Any] | None, *, max_claims: int) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    for item in _compiled_objects(learning_brain):
        status = str(item.get("claim_status") or "observed").strip() or "observed"
        if status not in _STABLE_CLAIM_STATUSES:
            continue
        evidence_refs = _refs(item.get("evidence_refs")) or _refs(item.get("supporting_event_ids"))
        if not evidence_refs:
            continue
        timeline = _timeline_entries(item.get("occurrence_timeline") or item.get("timeline_refs"))
        occurrence_count = max(len(timeline), len(evidence_refs))
        # 末次证据时间必须取自完整 timeline（升序），不能用截断后的展示片段。
        last_observed_at = timeline[-1]["observed_at"] if timeline else ""
        decay_state = str(item.get("decay_state") or "active").strip() or "active"
        views.append({
            "claim_id": str(item.get("object_id") or item.get("claim_id") or "").strip(),
            "object_type": str(item.get("object_type") or "").strip(),
            "claim_status": status,
            "decay_state": decay_state,
            "trend_state": _trend_state(
                claim_status=status,
                decay_state=decay_state,
                occurrence_count=occurrence_count,
            ),
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
            "occurrence_count": occurrence_count,
            "occurrence_timeline": timeline[:5],
            "last_observed_at": last_observed_at,
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


def _improvement_signals(learning_brain: dict[str, Any] | None) -> list[dict[str, str]]:
    brain = dict(learning_brain or {}) if isinstance(learning_brain, dict) else {}
    signals: list[dict[str, str]] = []
    for item in list(brain.get("improvement_signals") or []):
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            continue
        signals.append({
            "concept_id": str(item.get("concept_id") or "").strip(),
            "error_code": str(item.get("error_code") or "").strip(),
            "event_id": event_id,
            "observed_at": str(item.get("observed_at") or "").strip(),
        })
    return signals[:5]


def _feedback_guidance(
    *,
    claims: list[dict[str, Any]],
    improvement_signals: list[dict[str, str]],
    actions: list[dict[str, Any]],
) -> dict[str, str]:
    action = actions[0] if actions else {}
    action_target = str(action.get("target") or action.get("title") or "").strip()
    if improvement_signals:
        return {
            "authority": "PersonalizationContextPack_read_only",
            "grading_tone": "retest_improvement_followup",
            "explanation_depth": "compare_retest_delta",
            "prior_claim_label": "",
            "next_action_hint": f"复测已有改善，下一题继续验证：{action_target}" if action_target else "复测已有改善，下一题继续验证。",
        }
    claim = claims[0] if claims else {}
    status = str(claim.get("claim_status") or "").strip()
    trend_state = str(claim.get("trend_state") or "").strip()
    label = str(claim.get("label") or claim.get("claim_id") or "").strip()
    if status in {"repeated", "confirmed"} or trend_state == "repeated_active":
        tone = "advanced_repeat_mistake"
        depth = "reference_prior_pattern"
    elif status == "observed":
        tone = "scaffolded_first_observation"
        depth = "concept_and_required_term"
    else:
        tone = "neutral"
        depth = "standard_point_explanation"
    return {
        "authority": "PersonalizationContextPack_read_only",
        "grading_tone": tone,
        "explanation_depth": depth,
        "prior_claim_label": label,
        "next_action_hint": f"下一题：{action_target}" if action_target else "",
    }


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


def _training_intent_from_claim(*, user_id: str, claim: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(claim, dict):
        return {}
    evidence_refs = _refs(claim.get("evidence_refs"))
    if not evidence_refs:
        return {}
    concept_id = str(claim.get("concept_id") or "").strip()
    error_code = ""
    claim_id = str(claim.get("claim_id") or "").strip()
    if not concept_id and ":" in claim_id:
        concept_id = claim_id.split(":", 1)[0].strip()
    if ":" in claim_id:
        error_code = claim_id.rsplit(":", 1)[-1].strip()
    intent = build_learning_training_intent(
        user_id=str(user_id or "").strip(),
        concept_id=concept_id,
        concept_label=str(claim.get("label") or claim.get("claim_id") or "").strip(),
        error_code=error_code,
        error_label=error_code,
        evidence_refs=evidence_refs,
        training_mode="case_repair",
        source="PersonalizationContextPack",
        reason="confirmed_or_repeated_learning_claim",
    )
    intent["recurrence"] = int(claim.get("occurrence_count") or len(evidence_refs))
    return intent


def _trend_state(*, claim_status: str, decay_state: str, occurrence_count: int) -> str:
    if decay_state == "improving":
        return "retest_improving"
    if claim_status in {"repeated", "confirmed"} or occurrence_count >= 2:
        return "repeated_active"
    return "first_observation"


def _timeline_entries(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        return []
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in list(value or []):
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id") or "").strip()
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        entries.append({
            "event_id": event_id,
            "observed_at": str(item.get("observed_at") or "").strip(),
            "question_id": str(item.get("question_id") or "").strip(),
            "turn_id": str(item.get("turn_id") or "").strip(),
        })
    entries.sort(key=lambda item: (item["observed_at"], item["event_id"]))
    return entries


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
