"""Unified GradingPacket Builder (M25-A, fat skill).

Selects ONE lane and builds a scoped packet (master plan §0.25.1 / §0.25.3). Pure routing:
  * objective_choice — packet carries ``answer_key`` as authority; the LLM may only explain,
    never decide correctness (``llm_may_decide_correctness=False``).
  * case_question — scoped rubric/source/spec/list/student_answer; objective rules NOT applied.
  * calculation_spec — machine-checkable spec lane.
  * retrieval_only — citations/explanation, NO grading decision.
  * open_world — not-in-bank fail-open teaching; ``unverified_diagnostic`` / ``needs_review``,
    never claims official answer, never auto-scores, emits a compiler candidate work-order.

No LLM is called here; this is lane selection + scoped-context assembly only.
"""
from __future__ import annotations

from typing import Any

LANE_OBJECTIVE = "objective_choice"
LANE_CASE = "case_question"
LANE_CALCULATION = "calculation_spec"
LANE_RETRIEVAL = "retrieval_only"
LANE_OPEN_WORLD = "open_world"

_OBJECTIVE_TYPES = {
    "single_choice", "multiple_choice", "multi_choice", "true_false",
    "judge", "judgement", "judgment", "mcq", "choice", "tf",
}
_CASE_TYPES = {"case", "case_question", "subjective", "short_answer", "essay"}
_CALC_TYPES = {"calculation", "calc", "spec", "computation", "numeric"}
_RETRIEVAL_TYPES = {"retrieval", "retrieval_only", "explain", "lookup", "concept"}


def select_lane(canonical_context: dict[str, Any]) -> str:
    """Pick the lane from the upstream canonical question context (resolver authority)."""
    if str(canonical_context.get("status") or "").strip().lower() == "unresolved":
        return LANE_OPEN_WORLD
    qt = str(canonical_context.get("question_type") or "").strip().lower()
    if qt in _OBJECTIVE_TYPES:
        return LANE_OBJECTIVE
    if qt in _CASE_TYPES:
        return LANE_CASE
    if qt in _CALC_TYPES:
        return LANE_CALCULATION
    if qt in _RETRIEVAL_TYPES:
        return LANE_RETRIEVAL
    # Unknown type but resolved identity: default to retrieval/explanation (no grading) — never
    # fabricate an objective verdict for an unclassified type.
    return LANE_RETRIEVAL


def _objective_packet(ctx: dict[str, Any], learner_context: Any, selected_option: Any,
                      answer_key: str | None) -> dict[str, Any]:
    return {
        "lane": LANE_OBJECTIVE,
        "canonical_question_context": ctx,
        "answer_key": answer_key if answer_key is not None else str(ctx.get("answer_key") or ""),
        "selected_option": selected_option,
        "learner_context": learner_context or {},
        "explanation_sources": list(ctx.get("source_refs") or []),
        "grading_authority": "answer_key",
        "llm_role": "explanation_and_diagnosis_only",
        "llm_may_decide_correctness": False,
    }


def _case_packet(ctx: dict[str, Any], learner_context: Any, student_answer: Any) -> dict[str, Any]:
    return {
        "lane": LANE_CASE,
        "canonical_question_context": ctx,
        "student_answer": student_answer,
        "learner_context": learner_context or {},
        "scoped": {
            "rubric": ctx.get("rubric"),
            "source_refs": list(ctx.get("source_refs") or []),
            "spec": ctx.get("spec"),
            "list_rules": ctx.get("list_rules"),
        },
        "grading_authority": "rubric+source+spec+list+runtime_llm_adjudication",
        "objective_rules_applied": False,
    }


def _calculation_packet(ctx: dict[str, Any], student_answer: Any) -> dict[str, Any]:
    return {
        "lane": LANE_CALCULATION,
        "canonical_question_context": ctx,
        "student_answer": student_answer,
        "grading_authority": "machine_checkable_spec",
        "llm_may_decide_correctness": False,
    }


def _retrieval_packet(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": LANE_RETRIEVAL,
        "canonical_question_context": ctx,
        "citations": list(ctx.get("source_refs") or []),
        "grading_decision": None,
    }


def _open_world_packet(ctx: dict[str, Any], learner_context: Any, student_answer: Any) -> dict[str, Any]:
    return {
        "lane": LANE_OPEN_WORLD,
        "raw_context": ctx,
        "learner_context": learner_context or {},
        "student_answer": student_answer,
        "teaching": True,
        "label": "unverified_diagnostic",
        "official_answer_claimed": False,
        "auto_score": False,
        "candidate_work_order": {
            "kind": "open_world_compiler_candidate",
            "reason": "not resolved to a canonical question; fail-open teaching only",
            "promote_to_release": False,
        },
    }


def build_grading_packet(
    canonical_context: dict[str, Any],
    *,
    learner_context: Any | None = None,
    selected_option: Any | None = None,
    student_answer: Any | None = None,
    answer_key: str | None = None,
) -> dict[str, Any]:
    """Build a scoped, single-lane grading packet. Pure routing; no LLM, no grading decision here."""
    lane = select_lane(canonical_context)
    if lane == LANE_OBJECTIVE:
        return _objective_packet(canonical_context, learner_context, selected_option, answer_key)
    if lane == LANE_CASE:
        return _case_packet(canonical_context, learner_context, student_answer)
    if lane == LANE_CALCULATION:
        return _calculation_packet(canonical_context, student_answer)
    if lane == LANE_RETRIEVAL:
        return _retrieval_packet(canonical_context)
    return _open_world_packet(canonical_context, learner_context, student_answer)
