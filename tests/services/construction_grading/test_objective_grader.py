"""M25-B: objective deterministic grader — true_false alias matrix + choice, fail-safe."""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.objective_grader import (
    grade_objective_submission,
    normalize_true_false,
)


@pytest.mark.parametrize("raw,expected", [
    ("T", "T"), ("t", "T"), ("True", "T"), ("TRUE", "T"), ("对", "T"), ("正确", "T"),
    ("yes", "T"), ("√", "T"), ("1", "T"), ("A", "T"),
    ("F", "F"), ("f", "F"), ("False", "F"), ("错", "F"), ("错误", "F"), ("no", "F"),
    ("×", "F"), ("0", "F"), ("B", "F"),
    ("", ""), ("maybe", ""), ("xyz", ""),
])
def test_true_false_alias_normalization(raw, expected):
    assert normalize_true_false(raw) == expected


def test_true_false_correct_and_wrong():
    # answer_key F (错). Student says 错/false/B -> correct; says 对/A -> wrong.
    for sel in ("错", "false", "F", "B", "×"):
        r = grade_objective_submission(answer_key="F", selected=sel, question_type="true_false")
        assert r["is_correct"] is True and r["score"] == 1.0
    for sel in ("对", "true", "T", "A"):
        r = grade_objective_submission(answer_key="F", selected=sel, question_type="true_false")
        assert r["is_correct"] is False and r["score"] == 0.0


def test_true_false_invalid_input_is_wrong_not_exception():
    r = grade_objective_submission(answer_key="T", selected="garbage", question_type="true_false")
    assert r["is_correct"] is False
    r2 = grade_objective_submission(answer_key="T", selected="", question_type="true_false")
    assert r2["is_correct"] is False


def test_single_choice():
    r = grade_objective_submission(answer_key="A", selected="a", question_type="single_choice")
    assert r["is_correct"] is True


def test_multi_choice_order_independent_and_missed_extra():
    r = grade_objective_submission(answer_key="ABD", selected="DBA", question_type="multiple_choice")
    assert r["is_correct"] is True
    r2 = grade_objective_submission(answer_key="ABD", selected="AB", question_type="multiple_choice")
    assert r2["is_correct"] is False and r2["missed"] == ["D"]
    r3 = grade_objective_submission(answer_key="ABD", selected="ABDC", question_type="multiple_choice")
    assert r3["is_correct"] is False and r3["extra"] == ["C"]


def test_result_shape_and_authority_flags():
    r = grade_objective_submission(answer_key="A", selected="A", question_type="single_choice")
    assert r["llm_may_decide_correctness"] is False
    assert r["authority_kind"] == "objective_answer_key_candidate"
    assert r["status"] == "candidate_unverified"
    assert "correct_option_set_hash" in r and "selected_option_normalized" in r
