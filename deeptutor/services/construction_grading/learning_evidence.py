from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from deeptutor.services.construction_grading.audit import reconcile_grader_output
from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult
from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

_REASONING_BLOCK_RE = re.compile(r"<(?:think|thinking)\b[^>]*>.*?</(?:think|thinking)>", re.IGNORECASE | re.DOTALL)
_REASONING_OPEN_RE = re.compile(r"<(?:think|thinking)\b[^>]*>.*$", re.IGNORECASE | re.DOTALL)
_REASONING_TAG_RE = re.compile(r"</?(?:think|thinking)\b[^>]*>", re.IGNORECASE)
_RAG_SOURCES = {"rag", "kb", "kb_chunk", "kb_chunks", "retrieval", "evidence_bundle"}


def build_learning_evidence_payload(
    *,
    grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any],
    turn_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    payload = _grading_result_payload(grading_result)
    question_id = _clean_text(payload.get("question_id") or payload.get("id"))
    question_type = _normalize_question_type(payload.get("type") or payload.get("question_type"))
    errors = [_clean_dict(error) for error in list(payload.get("error_events") or [])]
    rubric_items = [_rubric_payload(item, index=index) for index, item in enumerate(list(payload.get("rubric_items") or []), 1)]
    evidence_refs = _normalize_evidence_refs(
        payload.get("evidence_refs"),
        question_id=question_id,
        turn_id=turn_id,
        source_id=_clean_text(payload.get("grading_result_id") or payload.get("source_id")),
        trace_id=_clean_text(payload.get("trace_id") or payload.get("langfuse_trace_id")),
    )
    score_awarded = payload.get("score_awarded")
    max_score = payload.get("max_score")
    next_training_signal = _clean_dict(payload.get("next_training_signal"))
    grading_mode = _clean_text(payload.get("grading_mode"))
    question_stem = _clean_text(
        payload.get("question_stem")
        or payload.get("stem")
        or payload.get("question_text")
        or payload.get("question")
    )
    explanation = payload.get("explanation")
    explanation_missing_reason = _clean_text(payload.get("explanation_missing_reason"))
    quality = _quality_from_payload(
        question_id=question_id,
        question_stem=question_stem,
        errors=errors,
        evidence_refs=evidence_refs,
        grading_mode=grading_mode,
        score_awarded=score_awarded,
        max_score=max_score,
        explanation=explanation,
        explanation_missing_reason=explanation_missing_reason,
        next_training_signal=next_training_signal,
    )

    return {
        "schema_version": 1,
        "event_type": "learning_evidence",
        "legacy_event_type": "construction_grading_error",
        "source": "construction_grading",
        "turn_id": _clean_text(turn_id),
        "session_id": _clean_text(session_id),
        "question_id": question_id,
        "question_type": question_type,
        "question_stem": _clean_text(
            payload.get("question_stem")
            or payload.get("stem")
            or payload.get("question_text")
            or payload.get("question")
        ),
        "options": payload.get("options") if isinstance(payload.get("options"), (dict, list)) else {},
        "user_answer": _clean_text(payload.get("user_answer")),
        "correct_answer": _clean_text(payload.get("correct_answer")),
        "selected_options": list(payload.get("selected_options") or []),
        "missed_options": list(payload.get("missed_options") or []),
        "extra_options": list(payload.get("extra_options") or []),
        "score_awarded": score_awarded,
        "max_score": max_score,
        "score_ratio": _score_ratio(score_awarded, max_score),
        "explanation": _explanation_payload(explanation),
        "grading_mode": grading_mode or None,
        "rubric": _normalized_rubric_block(payload),
        "rubric_items": rubric_items,
        "evidence_refs": evidence_refs,
        "rag_evidence_refs": [ref for ref in evidence_refs if ref.get("source_type") == "rag_evidence"],
        "error_events": errors,
        "errors": errors,
        "next_training_signal": next_training_signal,
        "typed_edges": _typed_edges_from_payload(
            question_id=question_id,
            turn_id=turn_id,
            rubric_items=rubric_items,
            errors=errors,
            next_training_signal=next_training_signal,
        ),
        "quality": quality,
    }


def build_learning_evidence_dedupe_key(*, user_id: str, payload_json: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "user_id": _clean_text(user_id),
            "memory_kind": "learning_evidence",
            "turn_id": payload_json.get("turn_id"),
            "session_id": payload_json.get("session_id"),
            "question_type": payload_json.get("question_type"),
            "question_id": payload_json.get("question_id"),
            "user_answer": payload_json.get("user_answer"),
            "error_events": payload_json.get("error_events") or [],
            "score_awarded": payload_json.get("score_awarded"),
            "max_score": payload_json.get("max_score"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _grading_result_payload(grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(grading_result, dict):
        payload = dict(grading_result)
    else:
        payload = grading_result.to_dict()
        if isinstance(grading_result, CaseGradingResult):
            payload["type"] = "case"
        elif isinstance(grading_result, MCQGradingResult):
            payload["type"] = "mcq"
    payload["error_events"] = [_error_event_payload(error) for error in payload.get("error_events") or []]
    return payload


_RUBRIC_MODES_SCORING_POINT = frozenset({"grading_key", "curated_rubric"})
_RUBRIC_MODES_KEYWORD_ONLY = frozenset({"projected_rubric"})


def _normalized_rubric_block(payload: dict[str, Any]) -> dict[str, Any]:
    """Batch A Task 2: emit a rubric block on the learning_evidence payload.

    Always returns a dict; consumers can rely on the keys ``rubric_mode``,
    ``granularity``, ``scoring_points``, ``scoring_point_hits``,
    ``grader_disagreement`` being present. The block is purely descriptive —
    it never carries a writeback marker (the normalizer is read-only).

    Authority order for ``rubric_mode``:

    1. ``payload["rubric"]["rubric_mode"]`` if explicitly supplied.
    2. Derived from ``payload["grading_mode"]`` + ``payload["next_training_signal"]
       ["grading_source"]`` — when grading_source is ``grading_key`` the mode is
       elevated from ``curated_rubric`` to ``grading_key`` to preserve the
       4-tier authority the case_kernel exposes.
    3. Empty string when nothing is available.
    """
    raw_rubric = payload.get("rubric") if isinstance(payload.get("rubric"), dict) else {}
    rubric_mode = _resolve_rubric_mode(raw_rubric, payload)

    rubric_specs = _normalize_rubric_specs(raw_rubric.get("scoring_points"))
    audit = reconcile_grader_output(
        rubric_specs=rubric_specs,
        llm_output={"scoring_point_hits": list(raw_rubric.get("scoring_point_hits") or [])},
    )
    accepted_hits = [_normalize_scoring_hit(hit) for hit in audit["accepted_hits"]]
    disagreement = [dict(item) for item in audit["disagreement"]]

    block: dict[str, Any] = {
        "rubric_id": _clean_text(raw_rubric.get("rubric_id")),
        "rubric_version": _clean_text(raw_rubric.get("rubric_version")),
        "rubric_mode": rubric_mode,
        "granularity": _rubric_granularity(rubric_mode),
        "scoring_points": rubric_specs,
        "scoring_point_hits": accepted_hits,
        "grader_disagreement": disagreement,
    }
    return block


def _resolve_rubric_mode(raw_rubric: dict[str, Any], payload: dict[str, Any]) -> str:
    explicit = _clean_text(raw_rubric.get("rubric_mode"))
    if explicit:
        return explicit
    derived = _clean_text(payload.get("grading_mode"))
    if not derived:
        return ""
    signal = payload.get("next_training_signal")
    if isinstance(signal, dict):
        source = _clean_text(signal.get("grading_source"))
        if source == "grading_key" and derived == "curated_rubric":
            return "grading_key"
    return derived


def _rubric_granularity(rubric_mode: str) -> str:
    if rubric_mode in _RUBRIC_MODES_SCORING_POINT:
        return "scoring_point"
    if rubric_mode in _RUBRIC_MODES_KEYWORD_ONLY:
        return "keyword_only"
    return ""


def _normalize_rubric_specs(raw: Any) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for entry in list(raw or []):
        if not isinstance(entry, dict):
            continue
        point_id = _clean_text(entry.get("point_id"))
        if not point_id:
            continue
        specs.append({
            "point_id": point_id,
            "label": _clean_text(entry.get("label")),
            "max_score": entry.get("max_score"),
            "ability_dimension": _clean_text(entry.get("ability_dimension")),
            "knowledge_node_id": _clean_text(entry.get("knowledge_node_id")),
        })
    return specs


def _normalize_scoring_hit(hit: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {
        "point_id": _clean_text(hit.get("point_id")),
        "hit": bool(hit.get("hit")),
        "awarded_score": hit.get("awarded_score"),
        "miss_reason": _clean_text(hit.get("miss_reason")),
        "evidence_text": _clean_text(hit.get("evidence_text")),
    }
    raw_code = _clean_text(hit.get("error_code"))
    if raw_code:
        cleaned["error_code"] = raw_code if raw_code in ERROR_CODE_REGISTRY else "unknown_error"
    return cleaned


def _explanation_payload(value: Any) -> dict[str, Any] | str:
    """Normalize a grader-supplied explanation for emission into learning_evidence.

    Preserves arbitrary dict keys (so future graders adding `tutor_note`, `analysis`,
    etc. survive) while stripping reasoning tags via ``_clean_text``. Strings are
    cleaned verbatim. Empty/None input returns ``{}`` so downstream
    ``has_explanation_content`` reports False without losing key presence.
    """
    if isinstance(value, dict):
        return {
            str(key): _clean_text(nested)
            for key, nested in value.items()
            if _clean_text(nested)
        }
    text = _clean_text(value)
    return text if text else {}


def _error_event_payload(error: Any) -> dict[str, Any]:
    if hasattr(error, "to_dict"):
        return _clean_dict(error.to_dict())
    if isinstance(error, dict):
        return _clean_dict(error)
    return {"diagnosis": _clean_text(error)}


def _typed_edges_from_payload(
    *,
    question_id: str,
    turn_id: str,
    rubric_items: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    next_training_signal: dict[str, Any],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    submission_id = _clean_text(turn_id) or question_id
    concept_id = _clean_text(next_training_signal.get("concept")) or _first_error_concept(errors)
    if question_id and concept_id:
        edges.append(_edge("question_tests_concept", "question", question_id, "concept", concept_id))
    if submission_id and question_id:
        edges.append(_edge("submission_answered_question", "submission", submission_id, "question", question_id))

    rubric_by_text: dict[str, str] = {}
    for item in rubric_items:
        rubric_id = _clean_text(item.get("rubric_item_id"))
        if not rubric_id:
            continue
        criterion = _clean_text(item.get("criterion"))
        evidence_text = _clean_text(item.get("evidence_text"))
        if question_id:
            edges.append(_edge("question_has_rubric_item", "question", question_id, "rubric_item", rubric_id))
        for key in {criterion, evidence_text}:
            if key:
                rubric_by_text[key] = rubric_id
        if submission_id and item.get("status") == "miss":
            edges.append(_edge("submission_missed_rubric_item", "submission", submission_id, "rubric_item", rubric_id))

    for error in errors:
        error_code = _clean_text(error.get("error_code")) or "unknown_error"
        concept = _clean_text(error.get("concept_tag")) or concept_id
        error_id = f"{concept}:{error_code}" if concept else error_code
        rubric_id = _matching_rubric_id(error, rubric_by_text)
        confidence = _confidence(error.get("severity"))
        if rubric_id:
            edges.append(
                _edge(
                    "rubric_item_maps_to_error",
                    "rubric_item",
                    rubric_id,
                    "error",
                    error_id,
                    confidence=confidence,
                )
            )
        if submission_id:
            edges.append(
                _edge(
                    "submission_triggered_error",
                    "submission",
                    submission_id,
                    "error",
                    error_id,
                    confidence=confidence,
                )
            )
        training_id = _training_id(concept=concept, error_code=error_code, signal=next_training_signal)
        if training_id:
            edges.append(
                _edge(
                    "error_points_to_training",
                    "error",
                    error_id,
                    "next_training",
                    training_id,
                    confidence=confidence,
                )
            )
    return _dedupe_edges(edges)


def _normalize_evidence_refs(
    raw_refs: Any,
    *,
    question_id: str,
    turn_id: str,
    source_id: str,
    trace_id: str,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if source_id or turn_id:
        refs.append({"source_type": "grading_result", "source_id": source_id or turn_id})
    if question_id:
        refs.append({"source_type": "active_question", "source_id": question_id})
    if turn_id:
        refs.append({"source_type": "answer_history", "source_id": turn_id})
    if trace_id:
        refs.append({"source_type": "trace", "source_id": trace_id})

    for item in list(raw_refs or []):
        ref = _clean_dict(item)
        source = _clean_text(ref.get("source") or ref.get("source_type")).lower()
        field = _clean_text(ref.get("field") or ref.get("source_id") or ref.get("id") or ref.get("chunk_id"))
        source_type = _source_type_from_ref(source)
        source_ref_id = field or _clean_text(ref.get("value"))[:80] or source or "unknown"
        normalized = {"source_type": source_type, "source_id": source_ref_id}
        if source:
            normalized["source"] = source
        if field:
            normalized["field"] = field
        retrieval_status = _clean_text(ref.get("retrieval_status"))
        if retrieval_status:
            normalized["retrieval_status"] = retrieval_status
        if "value" in ref:
            normalized["value"] = ref.get("value")
        refs.append(normalized)
    return _dedupe_refs(refs)


def _source_type_from_ref(source: str) -> str:
    if source in _RAG_SOURCES:
        return "rag_evidence"
    if source in {"trace", "langfuse", "langfuse_trace"}:
        return "trace"
    if source in {"manual_correction", "teacher_fix", "operator_fix"}:
        return "manual_correction"
    if source in {"grading_result", "construction_grading"}:
        return "grading_result"
    if source == "assessment":
        return "assessment"
    return "active_question"


def compute_quality_signals(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute the full quality dict from a flat payload dict.

    This is the **single producer** of quality dicts.  All callers — both the
    canonical build path and the legacy read-model path — must go through here.

    Required keys consumed from *payload* (all optional; missing → safe default):
        question_id, question_stem, score_awarded, max_score, explanation,
        explanation_missing_reason, error_events / errors, evidence_refs,
        grading_mode, next_training_signal, _cap_reasons (pre-built list).
    """
    question_id = _clean_text(payload.get("question_id"))
    question_stem = _clean_text(
        payload.get("question_stem")
        or payload.get("stem")
        or payload.get("question_text")
        or payload.get("question")
    )
    score_awarded = payload.get("score_awarded")
    max_score = payload.get("max_score")
    explanation = payload.get("explanation")
    explanation_missing_reason = _clean_text(payload.get("explanation_missing_reason"))
    errors = [e for e in list(payload.get("error_events") or payload.get("errors") or []) if isinstance(e, dict)]
    evidence_refs = list(payload.get("evidence_refs") or [])
    grading_mode = _clean_text(payload.get("grading_mode"))
    next_training_signal: dict[str, Any] = payload.get("next_training_signal") or {}

    # ── Legacy cap_reasons ────────────────────────────────────────────────────
    cap_reasons: list[str] = list(payload.get("_cap_reasons") or [])
    if not question_id:
        cap_reasons.append("missing_question_id")
    if any(str(ref.get("retrieval_status") or "").lower() == "degraded" for ref in evidence_refs):
        cap_reasons.append("rag_degraded")
    if errors and not any(ref.get("source_type") == "rag_evidence" for ref in evidence_refs):
        cap_reasons.append("missing_rag_evidence")
    if grading_mode == "open_skill":
        cap_reasons.append("open_skill_requires_repetition_or_manual_confirmation")

    # ── New quality-gate fields ───────────────────────────────────────────────
    has_question_ref = bool(question_id)
    has_score_signal = score_awarded is not None or max_score is not None
    progress_countable = has_question_ref and has_score_signal

    has_explanation = has_explanation_content(explanation)

    has_answer = bool(
        (score_awarded is not None and max_score is not None)
        or errors
    )
    detail_ready = bool(question_stem and has_answer and has_explanation)

    concept_label = _clean_text(next_training_signal.get("concept"))
    if not concept_label:
        for error in errors:
            tag = _clean_text(error.get("concept_tag"))
            if tag:
                concept_label = tag
                break
    has_concept = bool(concept_label)
    has_result = has_question_ref and has_score_signal
    truth_eligible = has_concept and has_result

    missing_fields: list[str] = []
    if not has_explanation:
        missing_fields.append("explanation")
    if not has_concept:
        missing_fields.append("concept_label")
    if not question_stem:
        missing_fields.append("question_stem")
    if not has_question_ref:
        missing_fields.append("question_ref")

    degraded_parts: list[str] = []
    if not detail_ready:
        if not has_explanation:
            if explanation_missing_reason:
                degraded_parts.append("解析待补全")
            else:
                degraded_parts.append("解析暂缺")
        if not question_stem:
            degraded_parts.append("题干暂缺")
    degraded_reason = "；".join(degraded_parts)

    return {
        "evidence_level": "L0_observed",
        "writeback_eligible": bool(errors),
        "stable_truth_eligible": False,
        "evidence_cap_reasons": cap_reasons,
        "detail_ready": detail_ready,
        "progress_countable": progress_countable,
        "truth_eligible": truth_eligible,
        "missing_fields": missing_fields,
        "degraded_reason": degraded_reason,
    }


def _quality_from_payload(
    *,
    question_id: str,
    errors: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
    grading_mode: str,
    question_stem: str = "",
    score_awarded: Any = None,
    max_score: Any = None,
    explanation: Any = None,
    explanation_missing_reason: str = "",
    next_training_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Private wrapper: converts keyword-arg call convention → compute_quality_signals."""
    return compute_quality_signals({
        "question_id": question_id,
        "question_stem": question_stem,
        "score_awarded": score_awarded,
        "max_score": max_score,
        "explanation": explanation,
        "explanation_missing_reason": explanation_missing_reason,
        "error_events": errors,
        "evidence_refs": evidence_refs,
        "grading_mode": grading_mode,
        "next_training_signal": next_training_signal or {},
    })


def has_explanation_content(explanation: Any) -> bool:
    """Return True if explanation contains usable textual content."""
    if explanation is None:
        return False
    if isinstance(explanation, str):
        return bool(explanation.strip())
    if isinstance(explanation, dict):
        return any(
            isinstance(value, str) and str(value).strip()
            for value in explanation.values()
        )
    if isinstance(explanation, list):
        return any(has_explanation_content(item) for item in explanation)
    return False


def _rubric_payload(item: Any, *, index: int) -> dict[str, Any]:
    payload = _clean_dict(item)
    payload.setdefault("rubric_item_id", f"r{index}")
    return payload


def _edge(
    edge_type: str,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    *,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "edge_type": edge_type,
        "from": {"type": from_type, "id": _clean_text(from_id)},
        "to": {"type": to_type, "id": _clean_text(to_id)},
        "source_feature": "construction_grading",
        "confidence": confidence,
    }


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for edge in edges:
        key = json.dumps(edge, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        key = (_clean_text(ref.get("source_type")), _clean_text(ref.get("source_id")))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _matching_rubric_id(error: dict[str, Any], rubric_by_text: dict[str, str]) -> str:
    for key in (
        _clean_text(error.get("evidence")),
        _clean_text(error.get("criterion")),
        _clean_text(error.get("rubric_item_id")),
    ):
        if key and key in rubric_by_text:
            return rubric_by_text[key]
        if key and key.startswith("r"):
            return key
    return ""


def _first_error_concept(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        concept = _clean_text(error.get("concept_tag"))
        if concept:
            return concept
    return ""


def _training_id(*, concept: str, error_code: str, signal: dict[str, Any]) -> str:
    focus = _clean_text(signal.get("focus")) or "repair"
    mode = _clean_text(signal.get("mode")) or "practice"
    base = ":".join(part for part in (concept, error_code, mode, focus[:24]) if part)
    return base


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 1.0


def _score_ratio(score_awarded: Any, max_score: Any) -> float | None:
    try:
        max_score_float = float(max_score or 0)
        if max_score_float <= 0:
            return None
        return float(score_awarded or 0) / max_score_float
    except (TypeError, ValueError):
        return None


def _normalize_question_type(value: Any) -> str:
    text = _clean_text(value).lower()
    if text in {"case_study", "case", "subjective"}:
        return "case"
    if text in {"choice", "single_choice", "multiple_choice", "multi_choice", "judge", "judgment", "mcq"}:
        return "mcq"
    return text or "unknown"


def _clean_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): _clean_value(value) for key, value in payload.items()}


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        return _clean_dict(value)
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    return value


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = _REASONING_BLOCK_RE.sub("", text)
    text = _REASONING_OPEN_RE.sub("", text)
    return _REASONING_TAG_RE.sub("", text).strip()
