from __future__ import annotations

from deeptutor.services.question_followup import (
    annotate_submission_context_from_message,
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_result_summary,
)
from deeptutor.services.rag.pipelines.supabase import SupabasePipeline

# Bank stores D=5% (correct); learner pastes their own surface where A=5%.
_BANK_EXACT = {
    "id": "q1",
    "stem": "某工程屋面为压型金属板，设计无要求时屋面坡度最小值是（）。",
    "question_type": "choice",
    "answer_kind": "mcq",
    "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
    "correct_answer": "D",
}
_LEARNER_QUERY = (
    "某工程屋面为压型金属板，设计无要求时屋面坡度最小值是（）。"
    "A.5% B.2% C.3% D.1%。我选A"
)


def _project(eq, query):
    return SupabasePipeline._project_mcq_exact_question_to_query_surface(eq, query)


def test_projection_remaps_correct_answer_to_learner_surface() -> None:
    p = _project(_BANK_EXACT, _LEARNER_QUERY)
    # 5% is option A on the learner's surface -> correct_answer must become A.
    assert p["correct_answer"] == "A"
    assert p["options"]["A"] == "5%"
    assert (p.get("metadata") or {}).get("canonical_correct_answer") == "D"


def test_grading_marks_learner_surface_correct_answer_right() -> None:
    # End-to-end: projected exact_question -> grading context -> grade the learner's "A".
    eq = _project(_BANK_EXACT, _LEARNER_QUERY)
    summary = build_choice_result_summary_from_exact_question(eq)
    ctx = build_question_followup_context_from_result_summary(summary, "", reveal_answers=True)
    graded_right = annotate_submission_context_from_message("我选A", ctx)
    assert graded_right["is_correct"] is True  # answered 5% (A) -> correct
    graded_wrong = annotate_submission_context_from_message("我选D", ctx)
    assert graded_wrong["is_correct"] is False  # answered 1% (D on their surface) -> wrong


def test_projection_failsafe_keeps_bank_surface_when_values_do_not_map() -> None:
    # Learner surface values don't correspond to the bank values -> keep bank surface.
    p = _project(_BANK_EXACT, "完全不同的题面 A.红 B.绿 C.蓝 D.黄。我选A")
    assert p["correct_answer"] == "D"  # unchanged


def test_projection_skips_non_mcq() -> None:
    case = {**_BANK_EXACT, "answer_kind": "case_study"}
    assert _project(case, _LEARNER_QUERY)["correct_answer"] == "D"  # untouched
