"""Stream D — minimal Learning-Brain read-back -> learner profile + next steps.

This is a THIN service helper. It does NOT build a Learning-Brain platform, add a
table, or touch any DB / RAG / production runtime. It reads back the EXISTING
``learning_evidence_payload`` (produced by ``build_learning_evidence_payload`` and
``build_teacher_review_writeback``) and synthesizes a minimal, stable learner
profile that pilot (Stream B) can consume directly.

Single authority rule (hard constraint):
  - A point counts as ``mastered`` ONLY when its teacher-reviewed disposition is
    ``mastery_eligible == True``. high_risk / unsupported / uncertified points are
    NEVER mastered — they fall into ``weaknesses`` (or are simply skipped). This
    mirrors ``teacher_review_writeback._mastery``; we re-read its decision rather
    than re-deriving a second one.

It reuses ``ERROR_CODE_REGISTRY`` for label / ability_dimension so no second label
map is introduced.

Public API (stable — Stream B's only synthesis entry point):

    synthesize_learner_profile(payloads: list[dict]) -> {
        "weaknesses": [
            {"dimension", "error_code", "label", "count", "sample_point_ids"}
        ],
        "mastered_points": [
            {"point_id", "label", "ability_dimension", "policy_type"}
        ],
        "next_suggestions": [
            {"action", "dimension", "error_code", "label", "reason", "point_ids"}
        ],
    }
"""
from __future__ import annotations

from typing import Any

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

# error_code -> coached next action. Maps the E-series gaps Stream C emits onto the
# four review actions the product offers. Anything unmapped falls back to a generic
# "review the textbook clause" action so a profile is never empty for a known gap.
_SUGGESTION_BY_CODE: dict[str, dict[str, str]] = {
    "E03": {"action": "review_textbook_term", "reason": "复习教材术语：关键词缺失，按教材原文逐字补齐"},
    "E02": {"action": "drill_list_questions", "reason": "补练列举题：采分点遗漏，练习按条目完整列举"},
    "E09": {"action": "redo_calculation", "reason": "重做计算题：计算错误，重走计算步骤与单位核对"},
    "E05": {"action": "reread_code_clause", "reason": "重看规范条文：审题方向错误，对照规范条文校准答题方向"},
    "E06": {"action": "reread_code_clause", "reason": "重看规范条文：程序顺序错误，对照规范条文校准程序步骤"},
}
_DEFAULT_SUGGESTION = {"action": "review_textbook_term", "reason": "复习教材原文：按采分点回到教材出处复核"}

# Dimensions Stream B surfaces first, in priority order. Other dimensions still
# emit suggestions; this only orders the head of the list deterministically.
_DIMENSION_PRIORITY = [
    "question_reading",
    "code_application",
    "calculation",
    "expression",
    "transfer",
    "review_execution",
]


def synthesize_learner_profile(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate teacher-reviewed learning evidence into a minimal learner profile.

    *payloads* are ``learning_evidence_payload`` dicts. Each may carry a
    ``next_training_signal.teacher_review_points`` block (when produced by Stream
    C's ``build_teacher_review_writeback``) — that block is the single authority
    for mastery. Payloads without it are still read for weakness signals via
    ``error_events``; they contribute no mastery.

    Returns a dict with ``weaknesses``, ``mastered_points`` and
    ``next_suggestions``. Deterministic for a given input ordering.
    """
    weakness_acc: dict[str, _WeaknessBucket] = {}
    mastered: list[dict[str, Any]] = []
    mastered_seen: set[str] = set()

    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        review_points = _teacher_review_points(payload)
        review_by_diagnosis = _index_by_diagnosis(review_points)

        _collect_mastery(review_points, mastered, mastered_seen)
        _collect_weaknesses(payload, review_by_diagnosis, weakness_acc)

    weaknesses = _finalize_weaknesses(weakness_acc)
    next_suggestions = _suggestions_from_weaknesses(weaknesses)
    return {
        "weaknesses": weaknesses,
        "mastered_points": mastered,
        "next_suggestions": next_suggestions,
    }


class _WeaknessBucket:
    """Mutable accumulator for one ability_dimension/error_code combination."""

    __slots__ = ("dimension", "error_code", "label", "count", "point_ids")

    def __init__(self, *, dimension: str, error_code: str, label: str) -> None:
        self.dimension = dimension
        self.error_code = error_code
        self.label = label
        self.count = 0
        self.point_ids: list[str] = []

    def add(self, point_id: str) -> None:
        self.count += 1
        if point_id and point_id not in self.point_ids:
            self.point_ids.append(point_id)


def _collect_mastery(
    review_points: list[dict[str, Any]],
    mastered: list[dict[str, Any]],
    seen: set[str],
) -> None:
    """Append confident-mastery points. The ONLY mastery authority is the
    teacher-reviewed ``mastery_eligible`` flag — high_risk / unsupported /
    uncertified points are mastery_eligible=False upstream and never land here."""
    for row in review_points:
        if not bool(row.get("mastery_eligible")):
            continue
        point_id = _text(row.get("point_id"))
        if not point_id or point_id in seen:
            continue
        seen.add(point_id)
        # ``teacher_review_points`` carries no human label (Stream C's _point_event
        # drops it), so the stable point_id is the canonical identifier. Fall back
        # to it for label so the field is never empty.
        mastered.append({
            "point_id": point_id,
            "label": _text(row.get("label") or row.get("concept_tag")) or point_id,
            "ability_dimension": _dimension_for_policy(_text(row.get("policy_type"))),
            "policy_type": _text(row.get("policy_type")),
        })


def _collect_weaknesses(
    payload: dict[str, Any],
    review_by_diagnosis: dict[str, dict[str, Any]],
    weakness_acc: dict[str, _WeaknessBucket],
) -> None:
    """Aggregate one payload's error_events into the weakness buckets.

    Mastery-eligible points emit no error_event upstream, so iterating error
    events alone never double-counts a mastered point. Each event is mapped to
    its registry ability_dimension and bucketed by (dimension, error_code).

    The originating point_id is recovered by matching the error_event's
    ``diagnosis`` against the teacher_review_points (Stream C writes the same
    diagnosis on both). When no review block exists the event's ``concept_tag``
    (label-or-point_id) is the best available identifier."""
    errors = payload.get("error_events") or payload.get("errors") or []
    for error in errors:
        if not isinstance(error, dict):
            continue
        error_code = _normalize_code(error.get("error_code"))
        spec = ERROR_CODE_REGISTRY.get(error_code, ERROR_CODE_REGISTRY["unknown_error"])
        dimension = spec["ability_dimension"]
        label = spec["label"]
        point_id = _point_id_for_error(error, review_by_diagnosis)

        key = f"{dimension}:{error_code}"
        bucket = weakness_acc.get(key)
        if bucket is None:
            bucket = _WeaknessBucket(dimension=dimension, error_code=error_code, label=label)
            weakness_acc[key] = bucket
        bucket.add(point_id)


def _finalize_weaknesses(weakness_acc: dict[str, _WeaknessBucket]) -> list[dict[str, Any]]:
    """Sort weaknesses by dimension priority, then by descending count, then code."""
    def sort_key(bucket: _WeaknessBucket) -> tuple[int, int, str]:
        try:
            dim_rank = _DIMENSION_PRIORITY.index(bucket.dimension)
        except ValueError:
            dim_rank = len(_DIMENSION_PRIORITY)
        return (dim_rank, -bucket.count, bucket.error_code)

    ordered = sorted(weakness_acc.values(), key=sort_key)
    return [
        {
            "dimension": bucket.dimension,
            "error_code": bucket.error_code,
            "label": bucket.label,
            "count": bucket.count,
            "sample_point_ids": list(bucket.point_ids),
        }
        for bucket in ordered
    ]


def _suggestions_from_weaknesses(weaknesses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One next-step suggestion per weakness, in the same priority order."""
    suggestions: list[dict[str, Any]] = []
    for weakness in weaknesses:
        error_code = weakness["error_code"]
        mapping = _SUGGESTION_BY_CODE.get(error_code, _DEFAULT_SUGGESTION)
        suggestions.append({
            "action": mapping["action"],
            "dimension": weakness["dimension"],
            "error_code": error_code,
            "label": weakness["label"],
            "reason": mapping["reason"],
            "point_ids": list(weakness["sample_point_ids"]),
        })
    return suggestions


def _teacher_review_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    signal = payload.get("next_training_signal")
    if not isinstance(signal, dict):
        return []
    points = signal.get("teacher_review_points")
    return [p for p in points if isinstance(p, dict)] if isinstance(points, list) else []


def _index_by_diagnosis(review_points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map diagnosis text -> review point. Stream C writes the same diagnosis on
    both the error_event and the teacher_review_point, so this is the reliable
    link back to a point_id (review points carry no label)."""
    index: dict[str, dict[str, Any]] = {}
    for row in review_points:
        key = _text(row.get("diagnosis"))
        if key and key not in index:
            index[key] = row
    return index


def _point_id_for_error(error: dict[str, Any], review_by_diagnosis: dict[str, dict[str, Any]]) -> str:
    row = review_by_diagnosis.get(_text(error.get("diagnosis")))
    if row is not None:
        return _text(row.get("point_id"))
    # No teacher-review block (raw learning_evidence payload): concept_tag is the
    # best available identifier (label-or-point_id, per Stream C's error event).
    return _text(error.get("concept_tag"))


def _dimension_for_policy(policy_type: str) -> str:
    """Best-effort ability_dimension for a mastered point from its policy_type.

    Mirrors the error_code mapping Stream C uses (calculation->E09 etc.) so a
    mastered calculation point reports ``calculation`` rather than a generic
    bucket. Unknown policies fall back to ``code_application`` (规范运用)."""
    policy = policy_type.lower()
    if policy == "calculation":
        return ERROR_CODE_REGISTRY["E09"]["ability_dimension"]
    if policy == "direction_check":
        return ERROR_CODE_REGISTRY["E05"]["ability_dimension"]
    if policy == "list_rule":
        return ERROR_CODE_REGISTRY["E02"]["ability_dimension"]
    if policy == "exact_required":
        return ERROR_CODE_REGISTRY["E03"]["ability_dimension"]
    return ERROR_CODE_REGISTRY["E01"]["ability_dimension"]


def _normalize_code(value: Any) -> str:
    code = _text(value)
    return code if code in ERROR_CODE_REGISTRY else "unknown_error"


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["synthesize_learner_profile"]
