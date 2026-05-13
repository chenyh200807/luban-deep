from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.normalization import (
    coerce_jsonish,
    compact_text,
    is_meaningful,
    normalize_choice_letters,
    normalize_options,
)
from deeptutor.services.construction_grading.schema import (
    EvidenceRef,
    GradingErrorEvent,
    MCQGradingResult,
)

def _question_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("original_id") or row.get("question_id") or "").strip()


def _evidence_refs(row: dict[str, Any]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for field in (
        "correct_answer",
        "options",
        "option_reasoning",
        "analysis",
        "trap_type",
        "testing_focus",
        "grading_keywords",
        "source_meta",
        "node_code",
    ):
        value = coerce_jsonish(row.get(field))
        if is_meaningful(value):
            refs.append(EvidenceRef(source="questions_bank", field=field, value=value))
    return refs


def _option_reasoning(row: dict[str, Any]) -> dict[str, Any]:
    value = coerce_jsonish(row.get("option_reasoning"))
    return value if isinstance(value, dict) else {}


def _option_error_event(
    *,
    option: str,
    option_payload: Any,
    fallback_code: str,
    concept_tag: str,
) -> GradingErrorEvent:
    payload = option_payload if isinstance(option_payload, dict) else {}
    explanation = compact_text(payload.get("explanation")) or f"{option} 选项不符合标准答案。"
    return GradingErrorEvent(
        error_code=fallback_code,
        severity=0.8,
        concept_tag=concept_tag,
        evidence=option,
        diagnosis=explanation,
    )


def grade_mcq_submission(question_row: dict[str, Any], user_answer: Any) -> MCQGradingResult:
    """Grade single/multi-choice answers from existing questions_bank fields."""

    row = dict(question_row or {})
    correct_answer = normalize_choice_letters(row.get("correct_answer"))
    selected = list(normalize_choice_letters(user_answer))
    correct = list(correct_answer)
    selected_set = set(selected)
    correct_set = set(correct)
    missed = [option for option in correct if option not in selected_set]
    extra = [option for option in selected if option not in correct_set]
    is_correct = bool(correct_answer) and not missed and not extra
    question_type = str(row.get("question_type") or "choice").strip()
    concept_tag = str(row.get("node_code") or row.get("testing_focus") or "").strip()
    reasoning = _option_reasoning(row)

    errors: list[GradingErrorEvent] = []
    for option in extra:
        errors.append(
            _option_error_event(
                option=option,
                option_payload=reasoning.get(option),
                fallback_code="M07",
                concept_tag=concept_tag,
            )
        )
    for option in missed:
        errors.append(
            GradingErrorEvent(
                error_code="M06",
                severity=0.7,
                concept_tag=concept_tag,
                evidence=option,
                diagnosis=f"漏选 {option}，该选项属于标准答案。",
            )
        )
    if not errors and not is_correct and correct_answer:
        errors.append(
            GradingErrorEvent(
                error_code="M02",
                severity=0.7,
                concept_tag=concept_tag,
                evidence="".join(selected),
                diagnosis="作答与标准答案不一致。",
            )
        )

    options = normalize_options(row.get("options"))
    focus = str(row.get("testing_focus") or row.get("trap_type") or row.get("node_code") or "").strip()
    return MCQGradingResult(
        question_id=_question_id(row),
        question_type=question_type,
        user_answer="".join(selected),
        correct_answer=correct_answer,
        selected_options=selected,
        missed_options=missed,
        extra_options=extra,
        is_correct=is_correct,
        score_awarded=1.0 if is_correct else 0.0,
        max_score=1.0,
        evidence_refs=_evidence_refs(row),
        error_events=errors,
        next_training_signal={
            "concept": concept_tag,
            "focus": focus,
            "option_count": len(options),
        },
    )
