from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any, Iterable

from deeptutor.services.learner_state.canonical_truth_policy import (
    trusted_adjudication_from_quality,
)
from deeptutor.services.learner_state.evidence_lifecycle import (
    LEARNING_EVIDENCE_SOURCE_FEATURES as LEARNING_EVIDENCE_SOURCE_FEATURES,
)
from deeptutor.services.learner_state.evidence_lifecycle import (
    PRACTICE_EVIDENCE_SOURCE_FEATURES as PRACTICE_EVIDENCE_SOURCE_FEATURES,
)
from deeptutor.services.learner_state.evidence_lifecycle import (
    committed_retest_completion_ids,
    distinct_attempt_count,
    event_promotion_allowed,
    evidence_attempt_id,
    is_learning_evidence_event,
    is_retest_completion_terminal,
    promotion_allowed,
)
from deeptutor.services.learner_state.learning_state_projection import (
    project_three_layer_learning_state,
)
from deeptutor.services.learner_state.memory_lifecycle import (
    confidence_for_evidence_level,
    evidence_level_rank,
    lifecycle_stage_for_evidence_level,
    max_evidence_level,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

# source_feature 白名单的单一 authority(每个词汇一个 authority,病D-3):
# - PRACTICE_EVIDENCE_SOURCE_FEATURES = 判分级练-evidence 子集
#   (pack_lifecycle_projection._is_practice_evidence 等读侧引用,禁手工拷贝)
# - LEARNING_EVIDENCE_SOURCE_FEATURES = 证据编译器认的全集(练 + 对话合成);
#   写侧 auto-synthesis 触发过滤(learner_state/service.py)引用同一份。
_ALLOWED_EDGE_TYPES = {
    "question_tests_concept",
    "submission_answered_question",
    "question_has_rubric_item",
    "submission_missed_rubric_item",
    "rubric_item_maps_to_error",
    "submission_triggered_error",
    "error_points_to_training",
    "training_uses_question",
    "training_improved_error",
}


def synthesize_learning_truth(
    events: Iterable[LearnerStateEvent],
    *,
    previous_projection: dict[str, Any] | None = None,
    synthesis_status: str = "dry_run_ok",
    event_limit: int | None = None,
) -> dict[str, Any]:
    ordered_events = sorted(list(events), key=lambda event: (str(event.created_at or ""), str(event.event_id or "")))
    committed_retest_ids = committed_retest_completion_ids(ordered_events)
    # Phase -1.D: opt-in event window. Keeps the most-recent N events when
    # event_limit > 0; zero/negative/None disable windowing so existing
    # callers see no behavior change. The truncated flag surfaces upward so
    # the read model and UI can disclose "本次画像基于最近 N 次作答".
    window_truncated = False
    if isinstance(event_limit, int) and event_limit > 0 and len(ordered_events) > event_limit:
        ordered_events = ordered_events[-event_limit:]
        window_truncated = True
    learning_items = [
        item
        for event in ordered_events
        if _is_learning_evidence(event) and _is_release_eligible_evidence(event)
        for item in _learning_items(event, committed_retest_ids=committed_retest_ids)
    ]
    # Review-only observation channel: candidate/shadow learning evidence excluded by
    # the release-eligibility safety net is OBSERVED here instead of silently dropped.
    # Nothing downstream (weak_points / compiled_objects / PCP) consumes this list —
    # it carries zero truth or claim authority.
    candidate_observations = [
        _candidate_observation(event)
        for event in ordered_events
        if _is_candidate_learning_evidence(event)
    ]
    learning_items = [item for item in learning_items if item is not None]
    manual_events = [_manual_correction(event) for event in ordered_events if _is_manual_correction(event)]
    manual_events = [item for item in manual_events if item is not None]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    observed_candidates: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    conflict_count = 0

    for item in learning_items:
        conflict_count += len(item["conflicting_event_ids"])
        if item["is_improvement"] and item["promotion_allowed"]:
            improvements.append({
                "concept_id": item["concept_id"],
                "error_code": item["error_code"],
                "event_id": item["event_id"],
                "observed_at": item["observed_at"],
            })
            continue
        if (
            not item["promotion_allowed"]
            or item["source_feature"] == "conversation_synthesis"
            or not item["concept_id"]
            or not item["error_code"]
            or not item["question_id"]
            or _blocks_stable_learning_truth(item["evidence_cap_reasons"])
        ):
            observed_candidates.append(_candidate(item, evidence_level="L0_observed"))
            continue
        grouped[(item["concept_id"], item["error_code"])].append(item)

    raw_weak_points: list[dict[str, Any]] = []
    for (concept_id, error_code), items in sorted(grouped.items()):
        candidate = _candidate_from_items(concept_id, error_code, items)
        top_level = ""
        for item in items:
            top_level = max_evidence_level(top_level, _clean_text(item.get("evidence_level")))
        if evidence_level_rank(top_level) >= evidence_level_rank("L2_confirmed"):
            # §6-1 同族:字面 == "L2_confirmed" 曾把 L2_real_retest 降档;
            # 按 rank 判 L2 档并保真最高 level(真懂信号不在聚合层丢失)。
            raw_weak_points.append({**candidate, "evidence_level": top_level})
        elif distinct_attempt_count(items) >= 2:
            raw_weak_points.append({**candidate, "evidence_level": "L1_repeated"})
        else:
            observed_candidates.append({**candidate, "evidence_level": "L0_observed"})

    active_baseline_keys = {
        (_clean_text(item.get("concept_id")), _clean_text(item.get("error_code")))
        for item in raw_weak_points
    }
    improvements = [
        item
        for item in improvements
        if not _clean_text(item.get("error_code"))
        or (_clean_text(item.get("concept_id")), _clean_text(item.get("error_code")))
        in active_baseline_keys
    ]
    improved_keys = _resolved_improved_keys(improvements=improvements)
    weak_points = _active_weak_points(
        raw_weak_points=raw_weak_points,
        observed_candidates=observed_candidates,
        manual_events=manual_events,
        improved_keys=improved_keys,
    )
    observed_candidates = [_with_claim_lifecycle(item) for item in observed_candidates]
    weak_points = [_with_claim_lifecycle(item) for item in weak_points]
    stale_claims = [
        _with_claim_lifecycle({
            "concept_id": weak["concept_id"],
            "error_code": weak["error_code"],
            "reason": "later_training_improved",
            "supporting_event_ids": list(weak.get("supporting_event_ids") or []),
            "evidence_level": weak.get("evidence_level") or "L1_repeated",
            "decay_state": "improving",
        })
        for weak in raw_weak_points
        if (weak.get("concept_id"), weak.get("error_code")) in improved_keys
    ]
    compiled_objects = _build_compiled_objects(
        grouped=grouped,
        observed_candidates=observed_candidates,
        weak_points=raw_weak_points,
        improvements=improvements,
        manual_events=manual_events,
    )
    projection: dict[str, Any] = {
        "schema_version": 2,
        "generated_by": "nightly_synthesis",
        "subject": "construction_exam_learning_truth",
        "compiled_objects": compiled_objects,
        "weak_points": weak_points,
        "observed_candidates": observed_candidates,
        "candidate_observations": candidate_observations,
        "improvement_signals": improvements,
        "stale_claims": stale_claims,
        "typed_graph": project_learning_graph(ordered_events),
        "window_truncated": window_truncated,
        "learning_state": project_three_layer_learning_state(events=ordered_events),
    }
    projection["synthesis_run"] = _synthesis_run(
        events=ordered_events,
        projection=projection,
        previous_projection=previous_projection or {},
        created_claim_count=len(weak_points),
        decayed_claim_count=len(stale_claims),
        conflict_count=conflict_count,
        manual_override_count=len(manual_events),
        trusted_adjudication=_trusted_adjudication_summary(
            events=ordered_events,
            weak_points=[*weak_points, *stale_claims],
        ),
        status=synthesis_status,
    )
    return projection


def project_learning_graph(events: Iterable[LearnerStateEvent]) -> dict[str, Any]:
    edges: list[dict[str, Any]] = []
    readiness_gaps: list[dict[str, Any]] = []
    for event in events:
        if not _is_learning_evidence(event):
            continue
        if is_retest_completion_terminal(event):
            continue
        payload = dict(event.payload_json or {})
        event_edges: list[dict[str, Any]] = []
        for raw_edge in list(payload.get("typed_edges") or []):
            if not isinstance(raw_edge, dict):
                continue
            edge = dict(raw_edge)
            edge["evidence_event_id"] = event.event_id
            edge["observed_at"] = event.created_at
            if _valid_edge(edge):
                event_edges.append(edge)
            else:
                readiness_gaps.append({
                    "code": "invalid_graph_edge",
                    "evidence_event_id": event.event_id,
                    "edge_type": _clean_text(edge.get("edge_type")),
                    "severity": "warning",
                })
        edges.extend(event_edges)
        readiness_gaps.extend(_graph_readiness_gaps(event, payload, event_edges))
    return {"schema_version": 1, "edges": edges, "readiness_gaps": readiness_gaps}


def find_next_training_targets(
    projection: dict[str, Any],
    *,
    concept_id: str,
    error_code: str,
) -> list[dict[str, Any]]:
    concept = _clean_text(concept_id)
    code = _clean_text(error_code)
    targets: list[dict[str, Any]] = []
    for weak in list(projection.get("weak_points") or []):
        if not isinstance(weak, dict):
            continue
        if _clean_text(weak.get("concept_id")) != concept or _clean_text(weak.get("error_code")) != code:
            continue
        training = weak.get("recommended_training") if isinstance(weak.get("recommended_training"), dict) else {}
        targets.append({
            "concept_id": concept,
            "error_code": code,
            "training": dict(training),
            "reason_event_ids": list(weak.get("supporting_event_ids") or []),
        })
    return targets


def find_question_graph_context(projection: dict[str, Any], *, question_id: str) -> dict[str, Any]:
    """Return concept/rubric/error/training graph context for a question."""

    target = _clean_text(question_id)
    graph = projection.get("typed_graph") if isinstance(projection.get("typed_graph"), dict) else {}
    compiled = projection.get("compiled_objects") if isinstance(projection.get("compiled_objects"), dict) else {}
    concepts: list[str] = []
    rubric_items: list[str] = []
    errors: list[str] = []
    training_targets: list[str] = []
    evidence_event_ids: list[str] = []
    rubric_seen: set[str] = set()
    error_seen: set[str] = set()

    for edge in _graph_edges(graph):
        from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
        to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
        edge_type = _clean_text(edge.get("edge_type"))
        if edge_type == "question_tests_concept" and _clean_text(from_node.get("id")) == target:
            _append_unique_text(concepts, to_node.get("id"))
            _append_unique_text(evidence_event_ids, edge.get("evidence_event_id"))
        if edge_type == "question_has_rubric_item" and _clean_text(from_node.get("id")) == target:
            rubric_id = _clean_text(to_node.get("id"))
            _append_unique_text(rubric_items, rubric_id)
            if rubric_id:
                rubric_seen.add(rubric_id)
            _append_unique_text(evidence_event_ids, edge.get("evidence_event_id"))

    for object_key, object_value in compiled.items():
        if not isinstance(object_value, dict):
            continue
        if not str(object_key).startswith(f"rubric_item:{target}:"):
            continue
        rubric_id = _clean_text(object_value.get("object_id"))
        _append_unique_text(rubric_items, rubric_id)
        if rubric_id:
            rubric_seen.add(rubric_id)
        for event_id in list(object_value.get("supporting_event_ids") or []):
            _append_unique_text(evidence_event_ids, event_id)

    evidence_set = set(evidence_event_ids)
    for object_key, object_value in compiled.items():
        if not isinstance(object_value, dict) or not str(object_key).startswith("error:"):
            continue
        supporting_ids = {_clean_text(item) for item in list(object_value.get("supporting_event_ids") or [])}
        if not evidence_set.intersection(supporting_ids):
            continue
        error_id = _clean_text(object_value.get("object_id"))
        _append_unique_text(errors, error_id)
        if error_id:
            error_seen.add(error_id)

    for edge in _graph_edges(graph):
        from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
        to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
        edge_type = _clean_text(edge.get("edge_type"))
        if edge_type == "rubric_item_maps_to_error" and _clean_text(from_node.get("id")) in rubric_seen:
            error_id = _clean_text(to_node.get("id"))
            _append_unique_text(errors, error_id)
            if error_id:
                error_seen.add(error_id)
            _append_unique_text(evidence_event_ids, edge.get("evidence_event_id"))
        if (
            edge_type == "error_points_to_training"
            and _clean_text(from_node.get("id")) in error_seen
            and _clean_text(edge.get("evidence_event_id")) in evidence_set
        ):
            _append_unique_text(training_targets, to_node.get("id"))
            _append_unique_text(evidence_event_ids, edge.get("evidence_event_id"))

    return {
        "question_id": target,
        "concept_ids": concepts,
        "rubric_item_ids": rubric_items,
        "error_ids": errors,
        "training_target_ids": training_targets,
        "evidence_event_ids": evidence_event_ids,
    }


def find_concept_evidence(projection: dict[str, Any], *, concept_id: str) -> dict[str, Any]:
    key = f"concept:{_clean_text(concept_id)}"
    compiled = projection.get("compiled_objects") if isinstance(projection.get("compiled_objects"), dict) else {}
    concept = dict(compiled.get(key) or {})
    return {
        "concept_id": _clean_text(concept_id),
        "current_truth": concept.get("current_truth", ""),
        "evidence_level": concept.get("evidence_level", ""),
        "supporting_event_ids": list(concept.get("supporting_event_ids") or []),
        "conflicting_event_ids": list(concept.get("conflicting_event_ids") or []),
        "timeline_refs": list(concept.get("timeline_refs") or []),
    }


def trace_training_recommendation(
    projection: dict[str, Any],
    *,
    training_id: str,
) -> dict[str, Any]:
    target = _clean_text(training_id)
    graph = projection.get("typed_graph") if isinstance(projection.get("typed_graph"), dict) else {}
    error_ids: list[str] = []
    reason_event_ids: list[str] = []
    for edge in _graph_edges(graph):
        to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
        if edge.get("edge_type") != "error_points_to_training" or _clean_text(to_node.get("id")) != target:
            continue
        from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
        _append_unique_text(error_ids, from_node.get("id"))
        _append_unique_text(reason_event_ids, edge.get("evidence_event_id"))
    return {
        "training_id": target,
        "error_ids": error_ids,
        "reason_event_ids": reason_event_ids,
    }


def render_learning_truth_summary_md(projection: dict[str, Any]) -> str:
    lines = ["## 学习事实编译", ""]
    weak_points = list(projection.get("weak_points") or [])
    if not weak_points:
        lines.append("- 暂无达到长期画像阈值的稳定薄弱点。")
        return "\n".join(lines).strip()
    for item in weak_points:
        lines.append(
            "- "
            + f"{item.get('concept_id')}: {item.get('error_code')} "
            + f"({item.get('evidence_level')}, evidence={','.join(item.get('supporting_event_ids') or [])})"
        )
    return "\n".join(lines).strip()


def _is_learning_evidence(event: LearnerStateEvent) -> bool:
    return is_learning_evidence_event(event)


def _is_release_eligible_evidence(event: LearnerStateEvent) -> bool:
    """SAFETY NET (defensive read filter): shadow/candidate or not-writeback-eligible evidence must NEVER
    become a claim / weak point / PersonalizationContextPack input, even if such a row somehow leaked into
    learner_memory_events (writeback is gated at write time, but the read path must be correct on its own —
    the PCP now surfaces claims into live turns). Excludes ONLY rows POSITIVELY marked shadow/candidate or
    explicitly writeback_eligible=False; rows that simply omit the marker are kept (no regression)."""
    payload = dict(event.payload_json or {})
    authority = str(payload.get("authority") or "").strip().lower()
    if authority.endswith("_shadow") or authority in {"ai_draft_shadow", "best_quality_4model_shadow"}:
        return False
    if payload.get("candidate_only") is True:
        return False
    quality = payload.get("quality")
    if isinstance(quality, dict):
        if quality.get("candidate_only") is True or str(quality.get("authority") or "").lower().endswith("_shadow"):
            return False
        if quality.get("writeback_eligible") is False:   # explicit False only; absent -> keep
            return False
    return True


def _is_candidate_learning_evidence(event: LearnerStateEvent) -> bool:
    """Learning-evidence-shaped rows excluded by the release-eligibility safety net.

    Broader than _is_learning_evidence on source_feature on purpose: candidate
    sources (e.g. rich_leaf_shadow_candidate) are not allowed evidence sources,
    but they must still be visible in the review-only observation channel."""
    payload = dict(event.payload_json or {})
    if event.memory_kind != "learning_evidence" or payload.get("event_type") != "learning_evidence":
        return False
    return not _is_release_eligible_evidence(event)


def _candidate_observation(event: LearnerStateEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    trace = payload.get("rich_leaf_trace") if isinstance(payload.get("rich_leaf_trace"), dict) else {}
    return {
        "event_id": event.event_id,
        "source_feature": event.source_feature,
        "authority": _clean_text(quality.get("authority") or payload.get("authority")),
        "evidence_level": _clean_text(quality.get("evidence_level")),
        "leaf_id": _clean_text(trace.get("leaf_id")),
        "question_id": _clean_text(payload.get("question_id")),
        "observed_at": event.created_at,
        "candidate_only": True,
        "review_only": True,
        "claim_promotion_allowed": False,
        "excluded_from_truth_reason": "not_release_eligible",
    }


def _is_manual_correction(event: LearnerStateEvent) -> bool:
    payload = dict(event.payload_json or {})
    return (
        event.source_feature == "manual_correction"
        or event.memory_kind == "learning_correction"
        or payload.get("event_type") == "manual_correction"
    )


def _learning_items(
    event: LearnerStateEvent,
    *,
    committed_retest_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    payload = dict(event.payload_json or {})
    attempt_id = evidence_attempt_id(event, payload)
    can_promote = event_promotion_allowed(
        event,
        committed_retest_ids=committed_retest_ids,
    )
    errors = [error for error in list(payload.get("error_events") or payload.get("errors") or []) if isinstance(error, dict)]
    signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
    question_id = _clean_text(payload.get("question_id"))
    turn_id = _clean_text(payload.get("turn_id")) or _clean_text(event.source_id)
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    evidence_level = _learning_item_evidence_level(quality=quality, signal=signal)
    canonical_concept = _canonical_topic_concept_id(payload)
    conflicting_event_ids = [
        _clean_text(item)
        for item in list(quality.get("conflicting_event_ids") or payload.get("conflicting_event_ids") or [])
        if _clean_text(item)
    ]
    if not errors and _is_improvement(payload):
        concept = canonical_concept or _clean_text(signal.get("concept"))
        if not concept:
            return []
        error_code = _improvement_error_code(payload, concept_id=concept)
        return [{
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "observed_at": event.created_at,
            "question_id": question_id,
            "turn_id": turn_id,
            "concept_id": concept,
            "error_code": error_code,
            "rubric_item_id": "",
            "diagnosis": "",
            "recommended_training": dict(signal),
            "conflicting_event_ids": conflicting_event_ids,
            "evidence_cap_reasons": _evidence_cap_reasons(quality),
            "evidence_level": evidence_level,
            "claim_promotion_allowed": payload.get("claim_promotion_allowed"),
            "promotion_allowed": can_promote,
            "attempt_id": attempt_id,
            "is_improvement": True,
        }]
    if not errors:
        return []

    items: list[dict[str, Any]] = []
    fallback_rubric_id = _rubric_from_edges(payload)
    for error in errors:
        concept = canonical_concept or _clean_text(error.get("concept_tag") or signal.get("concept"))
        error_code = _clean_text(error.get("error_code"))
        rubric_item_id = _clean_text(error.get("rubric_item_id")) or fallback_rubric_id
        items.append({
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "observed_at": event.created_at,
            "question_id": question_id,
            "turn_id": turn_id,
            "concept_id": concept,
            "error_code": error_code,
            "rubric_item_id": rubric_item_id,
            # M32 Task 4: make the claim explainable. The canonical GradingErrorEvent
            # (construction_grading/schema.py) carries the answer span in ``evidence``;
            # the v1 rubric path may instead use ``evidence_span``. The mistake TYPE is
            # already the claim's ``error_code`` — we do not duplicate it under a second
            # key (single authority per fact). Diagnosis falls back to the span.
            "diagnosis": _clean_text(
                error.get("diagnosis") or error.get("evidence") or error.get("evidence_span")
            ),
            "evidence_span": _clean_text(error.get("evidence_span") or error.get("evidence")),
            "recommended_training": dict(signal),
            "conflicting_event_ids": conflicting_event_ids,
            "evidence_cap_reasons": _evidence_cap_reasons(quality),
            "evidence_level": evidence_level,
            "claim_promotion_allowed": payload.get("claim_promotion_allowed"),
            "promotion_allowed": can_promote,
            "attempt_id": attempt_id,
            "is_improvement": False,
        })
    return items


def _canonical_topic_concept_id(payload: dict[str, Any]) -> str:
    topic = payload.get("canonical_topic") if isinstance(payload.get("canonical_topic"), dict) else {}
    return _clean_text(topic.get("taxonomy_code") or topic.get("taxonomy_id") or topic.get("label"))


def _learning_item_evidence_level(*, quality: dict[str, Any], signal: dict[str, Any]) -> str:
    explicit_level = _clean_text(quality.get("evidence_level"))
    if explicit_level == "L2_real_retest":
        return explicit_level
    trusted = trusted_adjudication_from_quality(quality, signal)
    if trusted and trusted.get("requires_human") is not True:
        return "L2_confirmed"
    return explicit_level


def _evidence_cap_reasons(quality: dict[str, Any]) -> list[str]:
    return [
        _clean_text(item)
        for item in list(quality.get("evidence_cap_reasons") or [])
        if _clean_text(item)
    ]


def _blocks_stable_learning_truth(cap_reasons: list[str]) -> bool:
    blocking_caps = {
        "missing_question_id",
        "rag_degraded",
        "missing_rag_evidence",
        "conversation_signal_not_grading_truth",
    }
    return bool(blocking_caps.intersection({_clean_text(item) for item in cap_reasons}))


def _active_weak_points(
    *,
    raw_weak_points: list[dict[str, Any]],
    observed_candidates: list[dict[str, Any]],
    manual_events: list[dict[str, Any]],
    improved_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    manual_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for manual_event in manual_events:
        manual_by_key[(manual_event["concept_id"], manual_event["error_code"])].append(manual_event)

    active: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for weak in raw_weak_points:
        key = (_clean_text(weak.get("concept_id")), _clean_text(weak.get("error_code")))
        seen_keys.add(key)
        if key in improved_keys:
            continue
        manual_for_key = manual_by_key.get(key, [])
        if _has_manual_supersede(manual_for_key):
            continue
        item = dict(weak)
        confirmations = _manual_confirmations(manual_for_key)
        if confirmations:
            item["evidence_level"] = "L2_confirmed"
            item["supporting_event_ids"] = _dedupe([
                *list(item.get("supporting_event_ids") or []),
                *[confirmation["event_id"] for confirmation in confirmations],
            ])
        active.append(item)

    for observed in observed_candidates:
        key = (_clean_text(observed.get("concept_id")), _clean_text(observed.get("error_code")))
        if not key[0] or not key[1] or key in seen_keys or key in improved_keys:
            continue
        if _clean_text(observed.get("source_feature")) == "conversation_synthesis":
            continue
        if _blocks_stable_learning_truth(list(observed.get("evidence_cap_reasons") or [])):
            continue
        confirmations = _manual_confirmations(manual_by_key.get(key, []))
        if not confirmations:
            continue
        item = dict(observed)
        item["evidence_level"] = "L2_confirmed"
        item["supporting_event_ids"] = _dedupe([
            *list(item.get("supporting_event_ids") or []),
            *[confirmation["event_id"] for confirmation in confirmations],
        ])
        active.append(item)
    return active


def _manual_confirmations(manual_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in manual_events if item.get("action") in {"confirm", "confirmed"}]


def _has_manual_supersede(manual_events: list[dict[str, Any]]) -> bool:
    return any(item.get("action") not in {"confirm", "confirmed"} for item in manual_events)


def _manual_correction(event: LearnerStateEvent) -> dict[str, Any] | None:
    payload = dict(event.payload_json or {})
    concept = _clean_text(payload.get("concept_id"))
    error_code = _clean_text(payload.get("error_code"))
    if not concept or not error_code:
        return None
    return {
        "event_id": event.event_id,
        "observed_at": event.created_at,
        "concept_id": concept,
        "error_code": error_code,
        "action": _clean_text(payload.get("action") or payload.get("correction_type") or "supersede"),
        "correction": _clean_text(payload.get("correction")),
        "supersedes_event_ids": [
            _clean_text(item)
            for item in list(payload.get("supersedes_event_ids") or [])
            if _clean_text(item)
        ],
    }


def _candidate(item: dict[str, Any], *, evidence_level: str) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "concept_id": item.get("concept_id", ""),
        "error_code": item.get("error_code", ""),
        "claim": _claim_text(item.get("concept_id", ""), item.get("error_code", "")),
        "supporting_event_ids": [item["event_id"]],
        "last_observed_at": item["observed_at"],
        "recommended_training": dict(item.get("recommended_training") or {}),
        "evidence_level": evidence_level,
        "source_feature": item.get("source_feature", ""),
        "claim_promotion_allowed": item.get("claim_promotion_allowed"),
        "memory_lifecycle_stage": lifecycle_stage_for_evidence_level(evidence_level),
        "evidence_cap_reasons": list(item.get("evidence_cap_reasons") or []),
        # D-class: 1-element timeline for the single-observation path (append-only).
        "occurrence_timeline": _occurrence_timeline([item]),
    }
    # M32 Task 4: explainable claim — surface the answer span / diagnosis when present.
    # Append-only: absent on a legacy item -> claim stays byte-identical to the legacy shape.
    _attach_claim_evidence(claim, item)
    return _with_claim_lifecycle(claim)


def _attach_claim_evidence(claim: dict[str, Any], source: dict[str, Any]) -> None:
    """Add the M32 explainability fields only when non-empty (append-only)."""
    diagnosis = _clean_text(source.get("diagnosis"))
    if diagnosis:
        claim["diagnosis"] = diagnosis
    evidence_span = _clean_text(source.get("evidence_span"))
    if evidence_span:
        claim["evidence_span"] = evidence_span


def _occurrence_timeline(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """D-class: chronological error recurrence timeline (append-only, oldest-first)."""
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda i: str(i.get("observed_at") or "")):
        eid = str(item.get("event_id") or "")
        if eid in seen:
            continue
        seen.add(eid)
        entries.append({
            "event_id": eid,
            "observed_at": str(item.get("observed_at") or ""),
            "question_id": _clean_text(item.get("question_id")),
            "turn_id": _clean_text(item.get("turn_id")),
        })
    return entries


def _candidate_from_items(concept_id: str, error_code: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    def _latest(field: str) -> str:
        for entry in reversed(items):
            value = _clean_text(entry.get(field))
            if value:
                return value
        return ""

    candidate: dict[str, Any] = {
        "concept_id": concept_id,
        "error_code": error_code,
        "claim": _claim_text(concept_id, error_code),
        "supporting_event_ids": [item["event_id"] for item in items],
        "last_observed_at": items[-1]["observed_at"],
        "recommended_training": _first_training_signal(items),
        # D-class: error time-series — when did each mistake recur? (append-only)
        "occurrence_timeline": _occurrence_timeline(items),
    }
    # M32 Task 4: surface the most recent answer span / diagnosis (append-only). The mistake
    # TYPE is already the claim's error_code — not duplicated under a second key.
    _attach_claim_evidence(candidate, {"diagnosis": _latest("diagnosis"), "evidence_span": _latest("evidence_span")})
    return candidate


def _build_compiled_objects(
    *,
    grouped: dict[tuple[str, str], list[dict[str, Any]]],
    observed_candidates: list[dict[str, Any]],
    weak_points: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
    manual_events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    objects: dict[str, dict[str, Any]] = {}
    weak_keys = {(weak["concept_id"], weak["error_code"]) for weak in weak_points}
    improving_keys = _resolved_improved_keys(improvements=improvements)
    manual_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for manual_event in manual_events:
        manual_by_key[(manual_event["concept_id"], manual_event["error_code"])].append(manual_event)

    for key, items in grouped.items():
        concept_id, error_code = key
        evidence_level = "L1_repeated" if key in weak_keys else "L0_observed"
        decay_state = "improving" if key in improving_keys else "active"
        manual_for_key = manual_by_key.get(key, [])
        confirmations_for_key = [item for item in manual_for_key if item.get("action") in {"confirm", "confirmed"}]
        supersedes_for_key = [item for item in manual_for_key if item.get("action") not in {"confirm", "confirmed"}]
        if confirmations_for_key:
            evidence_level = "L2_confirmed"
            decay_state = "active"
        if supersedes_for_key:
            decay_state = "superseded"
        supporting_event_ids = [item["event_id"] for item in items]
        timeline = [_timeline_ref(item) for item in items]
        conflicting_ids = sorted({conflict for item in items for conflict in item.get("conflicting_event_ids", [])})
        superseded_ids = [item["event_id"] for item in supersedes_for_key]
        confirmation_timeline = [_manual_timeline_ref(item) for item in confirmations_for_key]
        object_timeline = [*timeline, *confirmation_timeline]
        object_supporting_ids = [*supporting_event_ids, *[item["event_id"] for item in confirmations_for_key]]
        _put_object(
            objects,
            object_type="concept",
            object_id=concept_id,
            current_truth=_concept_claim_text(concept_id, grouped=grouped),
            evidence_level=evidence_level,
            supporting_event_ids=object_supporting_ids,
            conflicting_event_ids=conflicting_ids,
            superseded_by_event_ids=superseded_ids,
            timeline_refs=object_timeline,
            decay_state=decay_state,
        )
        _put_object(
            objects,
            object_type="error",
            object_id=f"{concept_id}:{error_code}",
            current_truth=_claim_text(concept_id, error_code),
            evidence_level=evidence_level,
            supporting_event_ids=object_supporting_ids,
            conflicting_event_ids=conflicting_ids,
            superseded_by_event_ids=superseded_ids,
            timeline_refs=object_timeline,
            decay_state=decay_state,
        )
        for item in items:
            if item.get("question_id"):
                _put_object(
                    objects,
                    object_type="question",
                    object_id=item["question_id"],
                    current_truth=f"题目 {item['question_id']} 触发了 {error_code} 相关错因观察。",
                    evidence_level="L0_observed",
                    supporting_event_ids=[item["event_id"]],
                    conflicting_event_ids=[],
                    superseded_by_event_ids=[],
                    timeline_refs=[_timeline_ref(item)],
                    decay_state="active",
                )
            if item.get("question_id") and item.get("rubric_item_id"):
                _put_object(
                    objects,
                    object_type="rubric_item",
                    object_id=f"{item['question_id']}:{item['rubric_item_id']}",
                    current_truth=f"采分点 {item['rubric_item_id']} 在本次作答中未命中。",
                    evidence_level="L0_observed",
                    supporting_event_ids=[item["event_id"]],
                    conflicting_event_ids=[],
                    superseded_by_event_ids=[],
                    timeline_refs=[_timeline_ref(item)],
                    decay_state="active",
                )
            if item.get("turn_id"):
                _put_object(
                    objects,
                    object_type="submission",
                    object_id=item["turn_id"],
                    current_truth=f"作答 {item['turn_id']} 产生了结构化阅卷证据。",
                    evidence_level="L0_observed",
                    supporting_event_ids=[item["event_id"]],
                    conflicting_event_ids=[],
                    superseded_by_event_ids=[],
                    timeline_refs=[_timeline_ref(item)],
                    decay_state="active",
                )
    for observed in observed_candidates:
        if (
            _clean_text(observed.get("source_feature")) == "conversation_synthesis"
            or _blocks_stable_learning_truth(list(observed.get("evidence_cap_reasons") or []))
        ):
            continue
        if observed.get("concept_id") and observed.get("error_code") and observed.get("supporting_event_ids"):
            event_id = observed["supporting_event_ids"][0]
            _put_object(
                objects,
                object_type="error",
                object_id=f"{observed['concept_id']}:{observed['error_code']}",
                current_truth=observed["claim"],
                evidence_level="L0_observed",
                supporting_event_ids=[event_id],
                conflicting_event_ids=[],
                superseded_by_event_ids=[],
                timeline_refs=[{"event_id": event_id, "event_type": "learning_evidence"}],
                decay_state="active",
            )
    return objects


def _put_object(
    objects: dict[str, dict[str, Any]],
    *,
    object_type: str,
    object_id: str,
    current_truth: str,
    evidence_level: str,
    supporting_event_ids: list[str],
    conflicting_event_ids: list[str],
    superseded_by_event_ids: list[str],
    timeline_refs: list[dict[str, Any]],
    decay_state: str,
) -> None:
    object_id = _clean_text(object_id)
    if not object_id:
        return
    key = f"{object_type}:{object_id}"
    previous = objects.get(key)
    if previous:
        supporting_event_ids = _dedupe([*previous.get("supporting_event_ids", []), *supporting_event_ids])
        conflicting_event_ids = _dedupe([*previous.get("conflicting_event_ids", []), *conflicting_event_ids])
        superseded_by_event_ids = _dedupe([
            *previous.get("superseded_by_event_ids", []),
            *superseded_by_event_ids,
        ])
        timeline_refs = [*previous.get("timeline_refs", []), *timeline_refs]
    final_evidence_level = max_evidence_level(previous.get("evidence_level") if previous else "", evidence_level)
    final_decay_state = decay_state if decay_state != "active" else (previous or {}).get("decay_state", "active")
    final_supporting_event_ids = _dedupe(supporting_event_ids)
    claim_status = _claim_status(final_evidence_level, final_decay_state)
    objects[key] = {
        "object_type": object_type,
        "object_id": object_id,
        "current_truth": current_truth,
        "evidence_level": final_evidence_level,
        "confidence": confidence_for_evidence_level(final_evidence_level),
        "supporting_event_ids": final_supporting_event_ids,
        "evidence_refs": final_supporting_event_ids,
        "conflicting_event_ids": _dedupe(conflicting_event_ids),
        "superseded_by_event_ids": _dedupe(superseded_by_event_ids),
        "valid_since": _first_observed(timeline_refs),
        "last_observed_at": _last_observed(timeline_refs),
        "decay_state": final_decay_state,
        "claim_status": claim_status,
        "lifecycle": _claim_lifecycle(
            status=claim_status,
            evidence_level=final_evidence_level,
            decay_state=final_decay_state,
            supporting_event_ids=final_supporting_event_ids,
        ),
        "timeline_refs": timeline_refs,
    }


def _with_claim_lifecycle(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    evidence_level = _clean_text(enriched.get("evidence_level")) or "L0_observed"
    decay_state = _clean_text(enriched.get("decay_state")) or "active"
    supporting_event_ids = _dedupe([_clean_text(item) for item in list(enriched.get("supporting_event_ids") or [])])
    status = _claim_status(evidence_level, decay_state)
    enriched["memory_lifecycle_stage"] = lifecycle_stage_for_evidence_level(evidence_level)
    enriched["claim_status"] = status
    enriched["evidence_refs"] = supporting_event_ids
    enriched["supporting_event_ids"] = supporting_event_ids
    enriched["lifecycle"] = _claim_lifecycle(
        status=status,
        evidence_level=evidence_level,
        decay_state=decay_state,
        supporting_event_ids=supporting_event_ids,
    )
    return enriched


def _claim_status(evidence_level: str, decay_state: str) -> str:
    if decay_state == "superseded":
        return "superseded"
    if decay_state in {"improving", "stale"}:
        return "stale"
    if evidence_level_rank(evidence_level) >= evidence_level_rank("L2_confirmed"):
        return "confirmed"
    if evidence_level == "L1_repeated":
        return "repeated"
    return "observed"


def _claim_lifecycle(
    *,
    status: str,
    evidence_level: str,
    decay_state: str,
    supporting_event_ids: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "evidence_level": evidence_level,
        "decay_state": decay_state,
        "supporting_event_count": len(supporting_event_ids),
    }


def _synthesis_run(
    *,
    events: list[LearnerStateEvent],
    projection: dict[str, Any],
    previous_projection: dict[str, Any],
    created_claim_count: int,
    decayed_claim_count: int,
    conflict_count: int,
    manual_override_count: int,
    trusted_adjudication: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    input_hash = _hash_json([
        {
            "event_id": event.event_id,
            "created_at": event.created_at,
            "memory_kind": event.memory_kind,
            "source_feature": event.source_feature,
            "payload_json": event.payload_json,
        }
        for event in events
    ])
    output_hash = _projection_hash(projection)
    return {
        "synthesis_run_id": f"syn_{input_hash.removeprefix('sha256:')[:16]}",
        "input_event_count": len(events),
        "input_event_ids_hash": input_hash,
        "previous_projection_hash": _previous_projection_hash(previous_projection),
        "output_projection_hash": output_hash,
        "created_claim_count": created_claim_count,
        "updated_claim_count": 0,
        "decayed_claim_count": decayed_claim_count,
        "conflict_count": conflict_count,
        "manual_override_count": manual_override_count,
        "trusted_adjudication": dict(trusted_adjudication or {}),
        "status": _clean_text(status) or "dry_run_ok",
    }


def _trusted_adjudication_summary(
    *,
    events: list[LearnerStateEvent],
    weak_points: list[dict[str, Any]],
) -> dict[str, Any]:
    supporting_ids = {
        _clean_text(event_id)
        for weak in weak_points
        for event_id in list(weak.get("supporting_event_ids") or [])
        if _clean_text(event_id)
    }
    if not supporting_ids:
        return {}

    events_by_id = {event.event_id: event for event in events}
    trusted_entries: list[dict[str, Any]] = []
    for event_id in sorted(supporting_ids):
        event = events_by_id.get(event_id)
        if event is None:
            return {"source": "", "conflict_status": "missing_supporting_event", "requires_human": True}
        payload = dict(event.payload_json or {})
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
        trusted = trusted_adjudication_from_quality(quality, signal)
        if not trusted:
            return {"source": "", "conflict_status": "missing_trusted_adjudication", "requires_human": True}
        trusted_entries.append(trusted)

    sources = {_clean_text(item.get("source")).lower() for item in trusted_entries if _clean_text(item.get("source"))}
    source = sorted(sources)[0] if len(sources) == 1 else "mixed_trusted_adjudication"
    confidences = [
        float(item["confidence"])
        for item in trusted_entries
        if _is_float_like(item.get("confidence"))
    ]
    statuses = {
        _clean_text(item.get("conflict_status")).lower() or "resolved"
        for item in trusted_entries
    }
    conflict_status = "resolved" if statuses.issubset({"resolved", "none", "no_conflict", "not_applicable"}) else "unresolved"
    summary = {
        "source": source,
        "confidence": min(confidences) if confidences else None,
        "conflict_status": conflict_status,
        "requires_human": any(bool(item.get("requires_human")) for item in trusted_entries),
        "supporting_event_count": len(supporting_ids),
    }
    if source == "certified_grading_policy":
        for key in ("policy_id", "rubric_hash", "grader_version"):
            values = {_clean_text(item.get(key)) for item in trusted_entries if _clean_text(item.get(key))}
            if len(values) == 1:
                summary[key] = values.pop()
            else:
                summary["conflict_status"] = "unresolved"
                summary["requires_human"] = True
    return summary


def _is_float_like(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _valid_edge(edge: dict[str, Any]) -> bool:
    edge_type = _clean_text(edge.get("edge_type"))
    if edge_type not in _ALLOWED_EDGE_TYPES:
        return False
    from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
    to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
    if not (
        _clean_text(from_node.get("type"))
        and _clean_text(from_node.get("id"))
        and _clean_text(to_node.get("type"))
        and _clean_text(to_node.get("id"))
        and _clean_text(edge.get("evidence_event_id"))
        and _clean_text(edge.get("source_feature"))
        and _clean_text(edge.get("observed_at"))
    ):
        return False
    try:
        confidence = float(edge.get("confidence"))
    except (TypeError, ValueError):
        return False
    return 0 <= confidence <= 1


def _graph_readiness_gaps(
    event: LearnerStateEvent,
    payload: dict[str, Any],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    question_id = _clean_text(payload.get("question_id"))
    if not question_id:
        return [{
            "code": "missing_question_id",
            "evidence_event_id": event.event_id,
            "severity": "blocker",
        }]
    has_concept_edge = any(
        edge.get("edge_type") == "question_tests_concept"
        and isinstance(edge.get("from"), dict)
        and _clean_text(edge["from"].get("id")) == question_id
        for edge in edges
    )
    if has_concept_edge:
        return []
    return [{
        "code": "missing_concept_edge",
        "question_id": question_id,
        "evidence_event_id": event.event_id,
        "severity": "warning",
    }]


def _graph_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [edge for edge in list(graph.get("edges") or []) if isinstance(edge, dict)]


def _append_unique_text(values: list[str], value: Any) -> None:
    text = _clean_text(value)
    if text and text not in values:
        values.append(text)


def _resolved_improved_keys(*, improvements: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (_clean_text(item.get("concept_id")), _clean_text(item.get("error_code")))
        for item in improvements
        if _clean_text(item.get("concept_id")) and _clean_text(item.get("error_code"))
    }


def _is_improvement(payload: dict[str, Any]) -> bool:
    # M32 Task 6: a simulated / preview / non-promotable grade is NOT a real retest pass and
    # must never clear a weakness (simulated_retest_as_real == 0). The real-pipeline guarantee
    # rides on ``preview_only`` / ``claim_promotion_allowed`` (set by build_learning_evidence_*);
    # ``qa_simulated`` is the project's explicit simulation marker (runtime_llm_adjudicator /
    # beta_shadow_loader). Only a real graded attempt — none of these flags — may improve.
    if not promotion_allowed(payload):
        return False
    source = _clean_text(payload.get("evidence_source"))
    if source == "assessment_testset" and _clean_text(payload.get("practice_mode")) not in {"review", "verification"}:
        return False
    try:
        max_score = float(payload.get("max_score") or 0)
        score = float(payload.get("score_awarded") or 0)
        return max_score > 0 and score >= max_score and not payload.get("error_events")
    except (TypeError, ValueError):
        return False


def _is_low_measurement_confidence(value: Any) -> bool:
    if isinstance(value, dict):
        level = _clean_text(value.get("level")).lower()
        return level == "low"
    return _clean_text(value).lower() == "low"


def _improvement_error_code(payload: dict[str, Any], *, concept_id: str) -> str:
    signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
    for key in ("error_code", "target_error_code", "error"):
        code = _clean_text(signal.get(key))
        if code:
            return code

    for edge in list(payload.get("typed_edges") or []):
        if not isinstance(edge, dict):
            continue
        if edge.get("edge_type") not in {"training_improved_error", "error_points_to_training"}:
            continue
        from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
        to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
        for node in (from_node, to_node):
            if node.get("type") != "error":
                continue
            error_id = _clean_text(node.get("id"))
            if not error_id:
                continue
            if ":" in error_id:
                concept, code = error_id.split(":", 1)
                if _clean_text(concept) == concept_id and _clean_text(code):
                    return _clean_text(code)
            elif error_id.startswith("E"):
                return error_id
    return ""


def _rubric_from_edges(payload: dict[str, Any]) -> str:
    for edge in list(payload.get("typed_edges") or []):
        if not isinstance(edge, dict):
            continue
        if edge.get("edge_type") != "submission_missed_rubric_item":
            continue
        target = edge.get("to") if isinstance(edge.get("to"), dict) else {}
        target_id = _clean_text(target.get("id"))
        if ":" in target_id:
            return target_id.rsplit(":", 1)[-1]
        if target_id:
            return target_id
    return ""


def _timeline_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": item["event_id"],
        "event_type": "learning_evidence",
        "observed_at": item["observed_at"],
        "summary": item.get("diagnosis", ""),
    }


def _manual_timeline_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": item["event_id"],
        "event_type": "manual_correction",
        "observed_at": item["observed_at"],
        "summary": item.get("correction", ""),
    }


def _claim_text(concept_id: Any, error_code: Any) -> str:
    concept = _clean_text(concept_id) or "unknown_concept"
    code = _clean_text(error_code) or "unknown_error"
    return f"{concept} 上出现 {code} 错因观察"


def _concept_claim_text(
    concept_id: Any,
    *,
    grouped: dict[tuple[str, str], list[dict[str, Any]]],
) -> str:
    concept = _clean_text(concept_id) or "unknown_concept"
    error_codes = [
        _clean_text(error_code)
        for group_concept, error_code in sorted(grouped)
        if _clean_text(group_concept) == concept and _clean_text(error_code)
    ]
    if not error_codes:
        return f"{concept} 上出现错因观察"
    return f"{concept} 上出现 {', '.join(_dedupe(error_codes))} 等错因观察"


def _first_training_signal(items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in items:
        signal = item.get("recommended_training")
        if isinstance(signal, dict) and signal:
            return dict(signal)
    return {}


def _first_observed(timeline_refs: list[dict[str, Any]]) -> str:
    values = [_clean_text(item.get("observed_at")) for item in timeline_refs if _clean_text(item.get("observed_at"))]
    return min(values) if values else ""


def _last_observed(timeline_refs: list[dict[str, Any]]) -> str:
    values = [_clean_text(item.get("observed_at")) for item in timeline_refs if _clean_text(item.get("observed_at"))]
    return max(values) if values else ""


def _dedupe(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result


def _previous_projection_hash(previous_projection: dict[str, Any]) -> str:
    run = previous_projection.get("synthesis_run") if isinstance(previous_projection.get("synthesis_run"), dict) else {}
    output_hash = _clean_text(run.get("output_projection_hash"))
    if output_hash:
        return output_hash
    return _projection_hash(previous_projection)


def _projection_hash(projection: dict[str, Any]) -> str:
    return _hash_json({key: value for key, value in dict(projection or {}).items() if key != "synthesis_run"})


def _hash_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
