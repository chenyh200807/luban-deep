"""Batch C Task 7: scoring point map read projection.

Focused sibling read model that reads ``learner_memory_events.learning_evidence``
(via the canonical ``payload.rubric`` block) and emits the采分点 漏分 map
that the student page surfaces.

Hard rules from the plan:

- Read-only — never writes ``questions_bank.grading_rubric`` or any
  table. The projection is built from the in-memory event stream the
  synthesis pipeline already buffers.
- Items with ``rubric_mode ∈ {grading_key, curated_rubric}`` surface
  as ``granularity="scoring_point"`` (UI label: 采分点).
- Items with ``rubric_mode == projected_rubric`` surface as
  ``granularity="keyword_only"`` only for audited >=70% clusters
  (UI label: 审题要点); weaker clusters stay ``rubric_pending``.
- ``rubric_mode == open_skill`` evidence contributes nothing to the map.
- ``empty_state`` is one of ``""`` / ``no_evidence`` / ``rubric_pending``;
  the UI uses it to decide whether to render the map or an honest
  empty placeholder.
- Every item cites real ``evidence_refs``. Items with miss_count == 0
  (only hits) are dropped: the map projects misses, not aspirations.
- ``next_action.intent`` is a ``training_intent`` v2 dict so the prescription
  flow stays under the canonical authority.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Any, Iterable

from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.learner_state.subjective_focus import subjective_focus_projection
from deeptutor.services.learner_state.training_intent import (
    PRESCRIPTION_AUTHORITY,
    build_learning_training_intent,
    prioritize_training_intents,
)


_MAP_ELIGIBLE_MODES = frozenset({"grading_key", "curated_rubric", "projected_rubric"})
_SCORING_POINT_MODES = frozenset({"grading_key", "curated_rubric"})
_PROJECTED_RUBRIC_ELIGIBLE_CLUSTER_PREFIXES = frozenset({
    "1A41101",
    "1A41302",
    "1A41306",
    "1A42200",
    "1A42203",
    "1A43500",
    "1A43700",
    "1A43800",
})


def build_scoring_point_map_read_projection(
    *,
    events: Iterable[LearnerStateEvent],
    user_id: str = "",
    now_iso: str = "",
) -> dict[str, Any]:
    """Compose the scoring-point map from ``learning_evidence`` events.

    ``user_id`` is required for downstream ``training_intent`` construction;
    ``now_iso`` is currently unused but reserved for time-aware reordering
    in future iterations (kept in the signature so callers stay stable).
    """
    case_events = _case_events(events)
    total_case_event_count = len(case_events)

    # Aggregate misses by (point_id, granularity); each scoring point in the
    # map is a single row that may cite multiple attempt event_ids.
    by_point: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    map_eligible_event_count = 0
    projected_rubric_blocked_event_count = 0

    for event in case_events:
        payload = _safe_dict(getattr(event, "payload_json", {}))
        rubric = _safe_dict(payload.get("rubric"))
        rubric_mode = str(rubric.get("rubric_mode") or "").strip()
        if rubric_mode not in _MAP_ELIGIBLE_MODES:
            continue
        granularity = (
            "scoring_point" if rubric_mode in _SCORING_POINT_MODES else "keyword_only"
        )
        rubric_specs = _safe_list(rubric.get("scoring_points"))
        rubric_hits = _safe_list(rubric.get("scoring_point_hits"))
        if not rubric_specs:
            continue
        if (
            rubric_mode == "projected_rubric"
            and not any(
                _projected_rubric_spec_eligible(spec) for spec in rubric_specs
            )
        ):
            projected_rubric_blocked_event_count += 1
            continue

        map_eligible_event_count += 1
        hit_index = {
            str(hit.get("point_id") or "").strip(): hit
            for hit in rubric_hits
            if isinstance(hit, dict)
        }

        for spec in rubric_specs:
            if not isinstance(spec, dict):
                continue
            if (
                rubric_mode == "projected_rubric"
                and not _projected_rubric_spec_eligible(spec)
            ):
                continue
            point_id = str(spec.get("point_id") or "").strip()
            if not point_id:
                continue
            hit_payload = hit_index.get(point_id) or {}
            is_hit = bool(hit_payload.get("hit"))

            row = by_point.setdefault(
                (point_id, granularity),
                {
                    "point_id": point_id,
                    "label": str(spec.get("label") or "").strip() or point_id,
                    "granularity": granularity,
                    "rubric_mode": rubric_mode,
                    "knowledge_node_id": str(spec.get("knowledge_node_id") or "").strip(),
                    "ability_dimension": str(spec.get("ability_dimension") or "").strip(),
                    "miss_count": 0,
                    "evidence_refs": [],
                    "evidence_seen": set(),
                    "error_codes": [],
                    "miss_reasons": [],
                },
            )
            event_id = str(getattr(event, "event_id", "") or "").strip()
            if is_hit:
                continue
            if event_id and event_id not in row["evidence_seen"]:
                row["evidence_seen"].add(event_id)
                row["evidence_refs"].append(event_id)
                row["miss_count"] += 1
                if hit_payload.get("error_code"):
                    code = str(hit_payload.get("error_code") or "").strip()
                    if code and code not in row["error_codes"]:
                        row["error_codes"].append(code)
                miss_reason = str(hit_payload.get("miss_reason") or "").strip()
                if miss_reason and miss_reason not in row["miss_reasons"]:
                    row["miss_reasons"].append(miss_reason)

    items: list[dict[str, Any]] = []
    for row in by_point.values():
        if row["miss_count"] <= 0:
            continue
        row.pop("evidence_seen", None)
        row["next_action"] = _next_action(row, user_id=user_id)
        items.append(row)
    # 关注线（G3 surgical 落点）：subjective_focus 事件 → concept 权重，喂进唯一消费
    # prioritize_training_intents 的这一处。无 subjective_focus 事件时 inert（写入侧=🟡）。
    _apply_training_intent_priority(
        items,
        focus_weights=subjective_focus_projection(events, now_iso=now_iso),
    )

    scoring_point_items = sum(1 for item in items if item["granularity"] == "scoring_point")
    keyword_only_items = sum(1 for item in items if item["granularity"] == "keyword_only")
    point_id_namespace_duplicate_risks = _point_id_namespace_duplicate_risks(items)

    empty_state = _resolve_empty_state(
        items=items,
        case_event_count=total_case_event_count,
        map_eligible_event_count=map_eligible_event_count,
    )

    return {
        "items": items,
        "empty_state": empty_state,
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "prescription_authority": PRESCRIPTION_AUTHORITY,
            "model": "rule_based_v1",
            "total_case_event_count": total_case_event_count,
            "map_eligible_event_count": map_eligible_event_count,
            "projected_rubric_blocked_event_count": (
                projected_rubric_blocked_event_count
            ),
            "scoring_point_items": scoring_point_items,
            "keyword_only_items": keyword_only_items,
            "point_id_namespace_duplicate_risks": point_id_namespace_duplicate_risks,
        },
    }


# ─── Helpers ──────────────────────────────────────────────────────────────


def _case_events(events: Iterable[LearnerStateEvent]) -> list[LearnerStateEvent]:
    """Return the construction_grading learning_evidence events only."""
    result: list[LearnerStateEvent] = []
    for event in events:
        if not _is_learning_evidence(event):
            continue
        payload = _safe_dict(getattr(event, "payload_json", {}))
        if str(payload.get("evidence_source") or "").strip() != "construction_grading":
            # conversation_synthesis and other non-grading evidence do not
            # contribute scoring points to the map.
            if str(payload.get("evidence_source") or "").strip():
                continue
            # Legacy / unset evidence_source: only count if the payload
            # carries a rubric block (i.e. it really is a grading event).
            if "rubric" not in payload:
                continue
        result.append(event)
    return sorted(
        result,
        key=lambda evt: (str(evt.created_at or ""), str(evt.event_id or "")),
    )


def _is_learning_evidence(event: LearnerStateEvent) -> bool:
    if str(getattr(event, "memory_kind", "") or "").strip() == "learning_evidence":
        return True
    payload = _safe_dict(getattr(event, "payload_json", {}))
    return str(payload.get("event_type") or "").strip() == "learning_evidence"


def _projected_rubric_spec_eligible(spec: Any) -> bool:
    if not isinstance(spec, dict):
        return False
    node_id = str(spec.get("knowledge_node_id") or "").strip()
    return any(
        node_id.startswith(prefix)
        for prefix in _PROJECTED_RUBRIC_ELIGIBLE_CLUSTER_PREFIXES
    )


def _resolve_empty_state(
    *,
    items: list[dict[str, Any]],
    case_event_count: int,
    map_eligible_event_count: int,
) -> str:
    if items:
        return ""
    if case_event_count == 0:
        return "no_evidence"
    # Case events exist but produce no usable map rows — either every
    # eligible event was a hit (good!) or all events were open_skill.
    # In both cases the UI must show "rubric_pending" so the learner
    # knows the map intentionally has nothing to show, rather than the
    # backend failing.
    return "rubric_pending"


def _point_id_namespace_duplicate_risks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_label: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in items:
        label = str(item.get("label") or "").strip()
        granularity = str(item.get("granularity") or "").strip()
        point_id = str(item.get("point_id") or "").strip()
        if label and granularity and point_id:
            by_label[(label, granularity)].add(point_id)
    risks: list[dict[str, Any]] = []
    for (label, granularity), point_ids in sorted(by_label.items()):
        if len(point_ids) <= 1:
            continue
        risks.append(
            {
                "label": label,
                "granularity": granularity,
                "point_ids": sorted(point_ids),
                "risk": "cross_epoch_point_id_namespace_not_merged",
            }
        )
    return risks


def _next_action(row: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    """Build the canonical training_intent v2 for this map row."""
    primary_error_code = row["error_codes"][0] if row["error_codes"] else ""
    intent = build_learning_training_intent(
        user_id=user_id,
        concept_id=row.get("knowledge_node_id") or "",
        concept_label=row.get("label") or "",
        error_code=primary_error_code,
        evidence_refs=list(row.get("evidence_refs") or []),
        ability_dimension=row.get("ability_dimension") or "",
        source="scoring_point_map",
        reason="repeated_scoring_point_miss",
    )
    intent["recurrence"] = row.get("miss_count") or 0
    intent["exam_weight"] = 1.0
    kind = "repair_and_verify" if intent["status"] == "active" else "discovery_probe"
    return {"kind": kind, "intent": intent}


def _apply_training_intent_priority(
    items: list[dict[str, Any]],
    focus_weights: dict[str, float] | None = None,
) -> None:
    weights = focus_weights or {}
    intents: list[dict[str, Any]] = []
    for item in items:
        intent = _safe_dict(_safe_dict(item.get("next_action")).get("intent"))
        concept_id = str(intent.get("concept_id") or "").strip()
        if concept_id and concept_id in weights:
            # 关注线（A 层）：打 subjective_focus_weight，_intent_priority 的 α=0.5
            # 上限随即生效——关注重排同档采分点，但盖不过证据关键弱点。不进掌握。
            intent = {**intent, "subjective_focus_weight": weights[concept_id]}
        intents.append(intent)
    prioritized = prioritize_training_intents(intents, max_active=3)
    by_id = {
        str(intent.get("training_intent_id") or ""): intent
        for intent in prioritized
        if str(intent.get("training_intent_id") or "").strip()
    }
    for item in items:
        next_action = _safe_dict(item.get("next_action"))
        intent = _safe_dict(next_action.get("intent"))
        intent_id = str(intent.get("training_intent_id") or "")
        prioritized_intent = by_id.get(intent_id)
        if not prioritized_intent:
            continue
        next_action["intent"] = prioritized_intent
        next_action["kind"] = (
            "repair_and_verify"
            if prioritized_intent.get("status") == "active"
            else "queued_repair"
        )
        item["next_action"] = next_action


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


__all__ = ["build_scoring_point_map_read_projection"]
