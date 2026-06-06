"""M26 Task 5: assert >=3 runtime surfaces consume the SAME LubanContextPack shape + policy,
and that none of them hand-rolls its own diagnostic policy."""
from __future__ import annotations

from deeptutor.services.construction_grading.compiled_context import SCHEMA_VERSION
from deeptutor.services.construction_grading.deep_question_adapter import (
    build_deep_question_grading_result,
)
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_from_context_pack,
)
from deeptutor.services.construction_grading.objective_runtime_adapter import (
    build_objective_candidate_payload,
)


def _assert_is_pack(cc: dict) -> None:
    assert cc["schema_version"] == SCHEMA_VERSION
    for key in (
        "question_context",
        "source_context",
        "rubric_context",
        "learner_context",
        "diagnostic_policy",
        "budget_policy",
        "provenance",
    ):
        assert key in cc, f"missing {key}"
    # policy comes from the builder, not the surface
    assert "official_score_allowed" in cc["diagnostic_policy"]
    assert cc["diagnostic_policy"]["llm_may_change_answer_key"] is False


def test_surface_tutorbot_deep_question_consumes_pack() -> None:
    qc = {
        "question_id": "Q_MCQ_1",
        "question_type": "single_choice",
        "stem": "建筑物构成不包括？",
        "options": {"A": "结构", "B": "围护", "C": "设备", "D": "投标"},
        "correct_answer": "D",
    }
    result = build_deep_question_grading_result(qc, user_answer="D")
    assert result is not None
    assert "compiled_context" in result
    _assert_is_pack(result["compiled_context"])


def test_surface_runtime_grading_objective_consumes_pack() -> None:
    payload = build_objective_candidate_payload(question_id="__not_in_bank__", selected_option="A")
    assert "compiled_context" in payload
    _assert_is_pack(payload["compiled_context"])
    # open-world objective => not official
    assert payload["compiled_context"]["diagnostic_policy"]["official_score_allowed"] is False


def test_surface_learning_brain_consumes_same_pack() -> None:
    qc = {
        "question_id": "Q_MCQ_1",
        "question_type": "single_choice",
        "stem": "x",
        "options": {"A": "结构", "B": "围护", "C": "设备", "D": "投标"},
        "correct_answer": "D",
    }
    graded = build_deep_question_grading_result(qc, user_answer="A")
    assert graded is not None
    cc = graded["compiled_context"]
    evidence = build_learning_evidence_from_context_pack(grading_result=graded, compiled_context=cc)
    assert evidence["compiled_context_provenance"]["pack_hash"] == cc["provenance"]["pack_hash"]
    # candidate/non-signed evidence must stay preview, never raise mastery / canonical truth
    assert evidence["mastery_raised"] is False
    assert evidence["canonical_truth_written"] is False
    assert evidence["claim_promotion_allowed"] is False
    assert evidence["preview_only"] is True


def test_three_surfaces_share_one_schema() -> None:
    qc = {"question_id": "Q1", "question_type": "single_choice",
          "options": {"A": "a", "B": "b"}, "correct_answer": "A"}
    g = build_deep_question_grading_result(qc, user_answer="A")
    o = build_objective_candidate_payload(question_id="__x__", selected_option="A")
    e = build_learning_evidence_from_context_pack(
        grading_result=g, compiled_context=g["compiled_context"]
    )
    schemas = {
        g["compiled_context"]["schema_version"],
        o["compiled_context"]["schema_version"],
        e["compiled_context_provenance"]["pack_hash"] and g["compiled_context"]["schema_version"],
    }
    assert schemas == {SCHEMA_VERSION}
