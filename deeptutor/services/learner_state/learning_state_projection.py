"""Batch B Task 4: three-layer learning state projection.

Reads ``learner_memory_events.learning_evidence`` (the only learning fact
ledger) and emits three parallel projection arrays —
``knowledge_state`` / ``ability_state`` / ``behavior_state`` — plus a
``source_status`` self-disclosure block.

Design notes:

- This is a focused sibling of ``learning_synthesis.py``. The synthesis
  function composes the projection via :func:`project_three_layer_learning_state`
  and stashes it under ``projection["learning_state"]``; the read model
  reads from there. We do NOT grow ``learning_synthesis.py`` (already 900+
  lines).
- The cluster key for recurrence is
  ``(primary_knowledge_node_id, ability_dimension, error_code)`` per the
  transformation plan.
- We never fabricate evidence: every state row carries ``evidence_refs``.
- Conversation evidence may contribute ``behavior_state.still_confused``
  / ``explained`` only; it cannot move a learner to ``stable`` on its own.
- ``granularity="keyword_only"`` evidence is locked at ``observed`` — the
  UI must show these as "审题要点", never as full scoring-point mastery.
- Legacy evidence (no rubric, no ability_dimension, no knowledge node) is
  silently tolerated and counted in ``source_status.legacy_count``.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY
from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.taxonomy.construction_learning_graph import (
    get_learning_graph_node,
)
from deeptutor.services.taxonomy.construction_taxonomy import student_facing_label

_ABILITY_DIMENSIONS = (
    "question_reading",
    "code_application",
    "calculation",
    "expression",
    "transfer",
    "review_execution",
)

_ALLOWED_CONVERSATION_SIGNALS = frozenset({
    "answer_explanation",
    "concept_explain",
    "mistake_explain",
    "still_confused",
    "corrected_misconception",
    "verified_understanding",
    "home_prompt_clicked",
})


# ─── Public API ────────────────────────────────────────────────────────────


def project_three_layer_learning_state(
    *,
    events: Iterable[LearnerStateEvent],
) -> dict[str, Any]:
    """Compose knowledge / ability / behavior projections from learning evidence.

    The input ``events`` iterable is consumed read-only; payloads are not
    mutated. The result is a fresh dict safe for the caller to embed in a
    larger projection.
    """
    ordered = sorted(
        list(events),
        key=lambda event: (str(event.created_at or ""), str(event.event_id or "")),
    )

    grading_facts: list[dict[str, Any]] = []
    conversation_signals: list[dict[str, Any]] = []
    legacy_count = 0

    for event in ordered:
        fact = _extract_grading_fact(event)
        if fact is not None:
            grading_facts.extend(fact)
            continue
        signal = _extract_conversation_signal(event)
        if signal is not None:
            conversation_signals.append(signal)
            continue
        if _is_learning_evidence_event(event):
            legacy_count += 1

    knowledge_state = _build_knowledge_state(grading_facts)
    ability_state = _build_ability_state(grading_facts)
    behavior_state = _build_behavior_state(
        grading_facts=grading_facts,
        conversation_signals=conversation_signals,
    )

    return {
        "knowledge_state": knowledge_state,
        "ability_state": ability_state,
        "behavior_state": behavior_state,
        "source_status": {
            "authority": "learner_memory_events.learning_evidence",
            "model": "rule_based_v1",
            "legacy_count": legacy_count,
            "grading_fact_count": len(grading_facts),
            "conversation_signal_count": len(conversation_signals),
        },
    }


# ─── Extraction ───────────────────────────────────────────────────────────


def _is_learning_evidence_event(event: LearnerStateEvent) -> bool:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    return (
        str(getattr(event, "memory_kind", "") or "").strip() == "learning_evidence"
        or str(payload.get("event_type") or "").strip() == "learning_evidence"
    )


def _extract_grading_fact(event: LearnerStateEvent) -> list[dict[str, Any]] | None:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if str(payload.get("evidence_source") or "").strip() == "conversation_synthesis":
        return None
    if not _is_learning_evidence_event(event):
        return None

    event_id = str(getattr(event, "event_id", "") or "").strip()
    created_at = str(getattr(event, "created_at", "") or "").strip()
    is_correct = _is_correct(payload)

    rubric = _safe_dict(payload.get("rubric"))
    granularity = str(rubric.get("granularity") or "").strip()
    rubric_mode = str(rubric.get("rubric_mode") or "").strip()
    rubric_specs = _safe_list(rubric.get("scoring_points"))
    rubric_hits = _safe_list(rubric.get("scoring_point_hits"))

    fact_rows: list[dict[str, Any]] = []

    # Path 1: rubric block with scoring_points → one fact per spec/hit pair.
    if rubric_specs:
        hit_by_point = {
            str(item.get("point_id") or "").strip(): item
            for item in rubric_hits
            if isinstance(item, dict)
        }
        for spec in rubric_specs:
            if not isinstance(spec, dict):
                continue
            point_id = str(spec.get("point_id") or "").strip()
            if not point_id:
                continue
            hit = hit_by_point.get(point_id) or {}
            error_code = str(hit.get("error_code") or "").strip()
            error_code = error_code if error_code in ERROR_CODE_REGISTRY else ""
            knowledge_node_id = _clean(spec.get("knowledge_node_id"))
            ability_dim = _normalize_ability(spec.get("ability_dimension"))
            if not ability_dim:
                ability_dim = _ability_from_error_code(error_code)
            fact_rows.append({
                "event_id": event_id,
                "created_at": created_at,
                "is_correct": _hit_is_correct(hit, fallback=is_correct),
                "knowledge_node_id": knowledge_node_id or _fallback_concept(payload),
                "ability_dimension": ability_dim,
                "error_code": error_code,
                "granularity": granularity or "scoring_point" if rubric_mode in {"grading_key", "curated_rubric"} else granularity,
                "rubric_mode": rubric_mode,
            })

    # Path 2: no rubric but error_events present → one fact per error event.
    if not fact_rows:
        error_events = _safe_list(payload.get("error_events") or payload.get("errors"))
        for error in error_events:
            if not isinstance(error, dict):
                continue
            error_code = str(error.get("error_code") or "").strip()
            normalized_code = error_code if error_code in ERROR_CODE_REGISTRY else ""
            concept = _clean(error.get("concept_tag")) or _fallback_concept(payload)
            ability_dim = _ability_from_error_code(normalized_code)
            if not (concept and ability_dim):
                continue
            fact_rows.append({
                "event_id": event_id,
                "created_at": created_at,
                "is_correct": is_correct,
                "knowledge_node_id": concept,
                "ability_dimension": ability_dim,
                "error_code": normalized_code,
                "granularity": "",
                "rubric_mode": "",
            })

    # Path 3: a clean success event (no errors) on a known concept still
    # informs improvement / stable signals.
    if not fact_rows and is_correct:
        concept = _fallback_concept(payload)
        if concept:
            fact_rows.append({
                "event_id": event_id,
                "created_at": created_at,
                "is_correct": True,
                "knowledge_node_id": concept,
                "ability_dimension": "",
                "error_code": "",
                "granularity": "",
                "rubric_mode": "",
            })

    return fact_rows or None


def _extract_conversation_signal(event: LearnerStateEvent) -> dict[str, Any] | None:
    payload = _safe_dict(getattr(event, "payload_json", {}))
    if str(payload.get("evidence_source") or "").strip() != "conversation_synthesis":
        return None
    if not _is_learning_evidence_event(event):
        return None
    signal_type = str(payload.get("learning_signal_type") or "").strip()
    if signal_type not in _ALLOWED_CONVERSATION_SIGNALS:
        return None
    return {
        "event_id": str(getattr(event, "event_id", "") or "").strip(),
        "created_at": str(getattr(event, "created_at", "") or "").strip(),
        "signal_type": signal_type,
        "concept": _clean(_safe_dict(payload.get("next_training_signal")).get("concept")),
    }


# ─── Builders ─────────────────────────────────────────────────────────────


def _build_knowledge_state(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        node_id = fact["knowledge_node_id"]
        if not node_id:
            continue
        groups[node_id].append(fact)

    state_items: list[dict[str, Any]] = []
    for node_id, rows in sorted(groups.items()):
        granularity = _dominant_granularity(rows)
        state_items.append({
            "node_id": node_id,
            "label": _resolve_label(node_id),
            "state": _classify_concept_state(rows, granularity=granularity),
            "evidence_count": len(rows),
            "evidence_refs": _ordered_event_ids(rows),
            "granularity": granularity,
            "last_observed_at": max(row["created_at"] for row in rows),
        })
    return state_items


def _build_ability_state(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        dim = fact["ability_dimension"]
        if not dim:
            continue
        groups[dim].append(fact)

    state_items: list[dict[str, Any]] = []
    for dim in _ABILITY_DIMENSIONS:
        rows = groups.get(dim) or []
        if not rows:
            continue
        granularity = _dominant_granularity(rows)
        state_items.append({
            "dimension": dim,
            "state": _classify_concept_state(rows, granularity=granularity),
            "evidence_count": len(rows),
            "evidence_refs": _ordered_event_ids(rows),
            "last_observed_at": max(row["created_at"] for row in rows),
        })
    return state_items


def _build_behavior_state(
    *,
    grading_facts: list[dict[str, Any]],
    conversation_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    # Recurrence: cluster on (node, ability_dimension, error_code).
    cluster_keys: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in grading_facts:
        if fact["is_correct"]:
            continue  # only repeated MISSES form recurrence
        key = (
            fact["knowledge_node_id"],
            fact["ability_dimension"],
            fact["error_code"],
        )
        if not all(key):
            continue
        cluster_keys[key].append(fact)

    recurring_refs: list[str] = []
    for rows in cluster_keys.values():
        if len(rows) >= 2:
            recurring_refs.extend(row["event_id"] for row in rows)
    if recurring_refs:
        items.append({
            "dimension": "recurrence",
            "state": "recurring",
            "evidence_count": len(recurring_refs),
            "evidence_refs": sorted(set(recurring_refs)),
        })

    # still_confused: from conversation evidence.
    confused = [s for s in conversation_signals if s["signal_type"] == "still_confused"]
    if confused:
        items.append({
            "dimension": "still_confused",
            "state": "active",
            "evidence_count": len(confused),
            "evidence_refs": [s["event_id"] for s in confused],
        })

    # explained / verified_understanding: conversation evidence that an
    # explanation was delivered — useful for the UI to show "已讲解但待验证".
    explained = [
        s
        for s in conversation_signals
        if s["signal_type"] in {"answer_explanation", "concept_explain", "mistake_explain", "verified_understanding"}
    ]
    if explained:
        items.append({
            "dimension": "explained",
            "state": "delivered",
            "evidence_count": len(explained),
            "evidence_refs": [s["event_id"] for s in explained],
        })

    return items


# ─── State classification helpers ─────────────────────────────────────────


def _classify_concept_state(
    rows: list[dict[str, Any]],
    *,
    granularity: str,
) -> str:
    """Knowledge / ability state buckets per the plan.

    - keyword_only granularity is locked at ``observed`` (never escalates).
    - One row → observed.
    - All correct → stable (when ≥ 2) else observed.
    - Negative then more-recent positive → improving.
    - All negative ≥ 2 → weak.
    - Mixed without recovery → unstable.
    """
    if granularity == "keyword_only":
        return "observed"
    if len(rows) <= 0:
        return "observed"
    if len(rows) == 1:
        return "observed"

    rows_sorted = sorted(rows, key=lambda r: r["created_at"])
    positives = [r for r in rows_sorted if r["is_correct"]]
    negatives = [r for r in rows_sorted if not r["is_correct"]]

    if not negatives:
        return "stable"
    if not positives:
        return "weak"

    # Mixed: improving when the most recent event is positive AND a negative
    # exists earlier; unstable otherwise.
    most_recent_is_correct = rows_sorted[-1]["is_correct"]
    if most_recent_is_correct:
        return "improving"
    return "unstable"


def _dominant_granularity(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.get("granularity") or ""] += 1
    # keyword_only wins if any row has it (the UI must downgrade the cluster).
    if counts.get("keyword_only", 0) > 0 and counts.get("scoring_point", 0) == 0:
        return "keyword_only"
    if counts.get("scoring_point", 0) > 0:
        return "scoring_point"
    return ""


def _ordered_event_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for row in sorted(rows, key=lambda r: r["created_at"]):
        event_id = row["event_id"]
        if event_id and event_id not in seen:
            seen.add(event_id)
            ids.append(event_id)
    return ids


# ─── Resolvers ────────────────────────────────────────────────────────────


def _resolve_label(node_id: str) -> str:
    node = get_learning_graph_node(node_id)
    if node and node.get("label"):
        return str(node["label"])
    # student-facing: code -> Chinese name (or generic), never the raw node code
    return student_facing_label(node_id, generic="相关考点")


def _ability_from_error_code(code: str) -> str:
    spec = ERROR_CODE_REGISTRY.get(code or "")
    if not spec:
        return ""
    dim = spec.get("ability_dimension") or ""
    return dim if dim in _ABILITY_DIMENSIONS else ""


def _normalize_ability(value: Any) -> str:
    text = str(value or "").strip()
    return text if text in _ABILITY_DIMENSIONS else ""


def _fallback_concept(payload: dict[str, Any]) -> str:
    signal = _safe_dict(payload.get("next_training_signal"))
    concept = _clean(signal.get("concept"))
    if concept:
        return concept
    for error in _safe_list(payload.get("error_events")):
        if isinstance(error, dict):
            tag = _clean(error.get("concept_tag"))
            if tag:
                return tag
    return ""


def _is_correct(payload: dict[str, Any]) -> bool:
    try:
        awarded = float(payload.get("score_awarded") or 0)
        max_score = float(payload.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return max_score > 0 and awarded >= max_score


def _hit_is_correct(hit: dict[str, Any], *, fallback: bool) -> bool:
    if "hit" in hit:
        return bool(hit.get("hit"))
    return fallback


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["project_three_layer_learning_state"]
