"""Batch D Task 10: teacher / sales evidence story read projection.

This service-only projection turns existing learning evidence into a bounded
"found -> trained -> verified" story. It is not a learner-state authority and
does not expose an endpoint; all claims must cite existing evidence refs.
"""
from __future__ import annotations

from typing import Any, Iterable

from deeptutor.services.learner_state.redaction import (
    redact_chat_text,
    redact_payload,
)
from deeptutor.services.learner_state.prescription_outcome_read_model import (
    build_prescription_outcomes_read_projection,
)
from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)

_SALES_CLAIMS = {
    "observed_learning_pattern": "系统已观察到可复盘的学习模式",
    "locate_miss_mechanism_and_verify_repair": "不是多刷题，而是定位丢分机制并验证修复",
}


def build_evidence_story_read_model(
    *,
    user_id: str,
    evidence_events: Iterable[Any],
    learning_state: dict[str, Any] | None = None,
    scoring_point_map: dict[str, Any] | None = None,
    prescription_outcomes: list[dict[str, Any]] | None = None,
    now_iso: str = "",
    max_clusters: int = 3,
) -> dict[str, Any]:
    events = list(evidence_events or [])
    event_ids = {
        str(getattr(event, "event_id", "") or "").strip()
        for event in events
        if str(getattr(event, "event_id", "") or "").strip()
    }
    if scoring_point_map is None:
        scoring_point_map = build_scoring_point_map_read_projection(
            events=events, user_id=str(user_id or "")
        )
    if prescription_outcomes is None:
        prescription_outcomes = build_prescription_outcomes_read_projection(events=events)

    chain: list[dict[str, Any]] = []
    initial = _initial_pattern_item(
        scoring_point_map=_safe_dict(scoring_point_map),
        event_ids=event_ids,
        max_clusters=max_clusters,
    )
    if initial:
        chain.append(initial)

    outcome = _best_prescription_outcome(prescription_outcomes or [], event_ids=event_ids)
    if outcome:
        chain.append({
            "type": "prescription_assigned",
            "claim": "系统已基于上述证据生成定向训练",
            "claim_code": "repair_plan_started",
            "evidence_refs": _valid_refs(outcome.get("evidence_refs"), event_ids),
        })
        if outcome.get("status") == "verified":
            chain.append({
                "type": "verified_improvement",
                "claim": "系统已观察到一次验证通过",
                "claim_code": "verification_probe_passed",
                "evidence_refs": _valid_refs(outcome.get("evidence_refs"), event_ids),
            })

    chain = [item for item in chain if item.get("evidence_refs")]
    all_refs = _dedupe_refs(ref for item in chain for ref in item.get("evidence_refs", []))
    degraded = not bool(chain)
    blocked_reasons = [] if chain else ["insufficient_evidence"]
    legacy_count = _legacy_event_count(events)
    value_claim = ""
    if all_refs:
        value_claim = (
            "locate_miss_mechanism_and_verify_repair"
            if any(item.get("type") == "verified_improvement" for item in chain)
            else "observed_learning_pattern"
        )
    story = {
        "ok": True,
        "schema_version": 1,
        "authority": {
            "read_model": "evidence-story-read-model",
            "source": "learner_memory_events.learning_evidence",
            "learning_state_source": "learning_state_projection",
            "scoring_point_map_source": "scoring_point_map_read_model",
            "prescription_source": "training_intent/prescription_outcomes",
            "public_endpoint": False,
        },
        "headline": _headline(chain),
        "evidence_chain": chain,
        "teacher_summary": {
            "summary": "建议围绕已引用证据复盘错因，并安排后续验证题。",
            "allowed_actions": ["review_scoring_point_cluster", "assign_followup_probe"],
            "evidence_refs": all_refs,
        },
        "sales_summary": {
            "value_claim": value_claim,
            "value_claim_label": _SALES_CLAIMS.get(value_claim, ""),
            "claim_strength": "evidence_backed" if all_refs else "insufficient_evidence",
            "evidence_refs": all_refs,
        },
        "privacy": {
            "redacted": True,
            "learner_handle": "learner_a",
            "raw_chat_included": False,
        },
        "samples": _anonymized_samples(scoring_point_map=_safe_dict(scoring_point_map), event_ids=event_ids),
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "event_count": len(events),
            "story_cluster_count": len(chain),
            "legacy_event_count": legacy_count,
            "degraded": degraded,
            "blocked_reasons": blocked_reasons,
        },
    }
    return redact_payload(story)


def _initial_pattern_item(
    *,
    scoring_point_map: dict[str, Any],
    event_ids: set[str],
    max_clusters: int,
) -> dict[str, Any] | None:
    items = [
        _safe_dict(item)
        for item in list(scoring_point_map.get("items") or [])[: max(1, int(max_clusters or 3))]
        if isinstance(item, dict)
    ]
    for item in items:
        refs = _valid_refs(item.get("evidence_refs"), event_ids)
        if not refs:
            continue
        label = str(item.get("label") or item.get("point_id") or "学习证据").strip()
        if str(item.get("granularity") or "") == "keyword_only":
            kind = "审题要点"
        else:
            kind = "采分点"
        return {
            "type": "initial_pattern",
            "claim": f"系统观察到同一{kind}反复失分：{redact_chat_text(label)}",
            "claim_code": "repeated_scoring_point_miss",
            "evidence_refs": refs,
        }
    return None


def _best_prescription_outcome(
    outcomes: list[dict[str, Any]], *, event_ids: set[str]
) -> dict[str, Any]:
    for status in ("verified", "not_verified", "needs_followup", "assigned", "in_progress"):
        for outcome in outcomes:
            if _safe_dict(outcome).get("status") != status:
                continue
            if _valid_refs(_safe_dict(outcome).get("evidence_refs"), event_ids):
                return _safe_dict(outcome)
    return {}


def _valid_refs(raw_refs: Any, event_ids: set[str]) -> list[str]:
    refs = []
    for ref in list(raw_refs or []):
        value = str(ref or "").strip()
        if value and value in event_ids and value not in refs:
            refs.append(value)
    return refs


def _dedupe_refs(refs: Iterable[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        value = str(ref or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _legacy_event_count(events: list[Any]) -> int:
    count = 0
    for event in events:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        if "rubric" not in payload and not payload.get("error_events"):
            count += 1
    return count


def _headline(chain: list[dict[str, Any]]) -> str:
    if any(item.get("type") == "verified_improvement" for item in chain):
        return "已从错因定位推进到验证通过"
    if chain:
        return "已形成可复盘的学习证据链"
    return "暂无足够证据生成学习故事"


def _anonymized_samples(*, scoring_point_map: dict[str, Any], event_ids: set[str]) -> list[dict[str, Any]]:
    for item in list(scoring_point_map.get("items") or []):
        if not isinstance(item, dict):
            continue
        refs = _valid_refs(item.get("evidence_refs"), event_ids)
        if not refs:
            continue
        return [{
            "learner_handle": "learner_a",
            "cluster": str(item.get("point_id") or "").strip(),
            "label": redact_chat_text(item.get("label") or ""),
            "evidence_refs": refs[:1],
        }]
    return []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


__all__ = ["build_evidence_story_read_model", "redact_chat_text"]
