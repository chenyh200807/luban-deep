"""Tests for deterministic answer-correctness scoring + cross-model report.

Validates the quality/verified-transmit logic with synthetic Q+A so it is
correct the moment a real question bank + keyed model runs plug in.
"""

from __future__ import annotations

from deeptutor.services.benchmark.quality_scoring import (
    CorrectnessScore,
    cross_model_correctness_report,
    score_answer_correctness,
)

_MCQ = {
    "answer_kind": "mcq",
    "correct_answer": "B",
    "stem": "施工现场临时用电组织设计应由谁编制？",
    "analysis": "B 选项符合规范。",
    "options": {"A": "项目负责人", "B": "电气工程技术人员", "C": "专职安全员", "D": "监理工程师"},
}
_FREE = {
    "answer_kind": "free_text",
    "correct_answer": "应先进行验槽，确认地基承载力满足设计要求后方可施工。",
}


def test_mcq_correct_and_incorrect() -> None:
    good = "标准答案：B。B. 电气工程技术人员。"
    bad = "标准答案：C。C. 专职安全员。"
    assert score_answer_correctness(question_id="q1", exact_question=_MCQ, response=good).correct is True
    assert score_answer_correctness(question_id="q1", exact_question=_MCQ, response=bad).correct is False


def test_mcq_closed_book_bare_letter_is_correct() -> None:
    """Closed-book scoring must reward a correct *letter* even when the model
    does not restate the option text — the realistic closed-book answer shape.
    (The rendering-faithfulness oracle wrongly rejected this; closed-book
    correctness is a different question scored by letter, not by restatement.)"""
    bare = "答案：B"
    reasoned = "题目考查工业建筑分类。逐项分析后，仓储建筑属于工业建筑。\n答案：B"
    assert score_answer_correctness(question_id="q1", exact_question=_MCQ, response=bare).correct is True
    assert score_answer_correctness(question_id="q1", exact_question=_MCQ, response=reasoned).correct is True


def test_mcq_multi_answer_letters() -> None:
    multi = {"answer_kind": "mcq", "correct_answer": "ABD", "options": {"A": "x", "B": "y", "C": "z", "D": "w"}}
    assert score_answer_correctness(question_id="m1", exact_question=multi, response="答案：A、B、D").correct is True
    assert score_answer_correctness(question_id="m1", exact_question=multi, response="答案：A、B").correct is False
    assert score_answer_correctness(question_id="m1", exact_question=multi, response="未给出答案").correct is False


def test_free_text_correct_and_incorrect() -> None:
    good = "依据规范，应先进行验槽，确认地基承载力满足设计要求后方可施工。"
    bad = "直接开始施工即可。"
    assert score_answer_correctness(question_id="q2", exact_question=_FREE, response=good).correct is True
    assert score_answer_correctness(question_id="q2", exact_question=_FREE, response=bad).correct is False


def test_case_study_requires_all_covered_answers_present() -> None:
    cs = {
        "answer_kind": "case_study",
        "case_bundle": {
            "covered_subquestions": [
                {"display_index": "1", "authoritative_answer": "先核查关键线路。"},
                {"display_index": "2", "authoritative_answer": "再调整资源投入。"},
            ],
            "coverage_ratio": 1.0,
            "coverage_state": "multi_subquestion_exact",
        },
    }
    full = "第一步先核查关键线路。第二步再调整资源投入。"
    partial = "先核查关键线路。"
    assert score_answer_correctness(question_id="q3", exact_question=cs, response=full).correct is True
    assert score_answer_correctness(question_id="q3", exact_question=cs, response=partial).correct is False


def test_cross_model_report_flags_upgrade_safe_when_no_regression() -> None:
    by_model = {
        "deepseek-v4-flash": [
            CorrectnessScore("q1", "mcq", True),
            CorrectnessScore("q2", "free_text", False),
        ],
        "candidate-stronger": [
            CorrectnessScore("q1", "mcq", True),
            CorrectnessScore("q2", "free_text", True),  # improved, no regression
        ],
    }
    report = cross_model_correctness_report(by_model, baseline_model="deepseek-v4-flash")
    assert report["per_model"]["candidate-stronger"]["accuracy"] == 1.0
    assert report["accuracy_delta_vs_baseline"]["candidate-stronger"] == 0.5
    assert report["regressions"] == []
    assert report["upgrade_safe"] is True


def test_cross_model_report_catches_per_question_regression() -> None:
    by_model = {
        "baseline": [CorrectnessScore("q1", "mcq", True), CorrectnessScore("q2", "mcq", True)],
        "candidate": [CorrectnessScore("q1", "mcq", True), CorrectnessScore("q2", "mcq", False)],  # q2 regressed
    }
    report = cross_model_correctness_report(by_model, baseline_model="baseline")
    assert report["upgrade_safe"] is False
    assert any(r.get("question_id") == "q2" for r in report["regressions"])
