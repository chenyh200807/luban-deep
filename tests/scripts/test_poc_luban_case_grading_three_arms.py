from __future__ import annotations

import json
from pathlib import Path

from scripts.poc_luban_case_grading_three_arms import (
    compile_kernel_scoring_points,
    compile_penalty_rules,
    extract_required_terms,
    gold_from_ledger,
    run_pilot,
    summarize_three_arm_results,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "deeptutor"
    / "services"
    / "benchmark"
    / "fixtures"
    / "luban_case_grading_golden_v1.json"
)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _case(case_id: str) -> dict:
    return next(case for case in _fixture()["cases"] if case["case_id"] == case_id)


def test_luban_golden_fixture_schema_for_pilot() -> None:
    payload = _fixture()

    assert payload["suite"] == "luban_case_grading_golden_v1"
    assert payload["exam_scope"] == "一级建造师建筑实务"
    assert payload["version"] == "v0"
    assert "同义词/近义词/口号/大白话一律不给分" in payload["grading_guideline"]["命中hit"]
    assert len(payload["cases"]) == 20
    assert sum(len(case["eval_samples"]) for case in payload["cases"]) == 100
    assert all(case["gold_scoring_points"] for case in payload["cases"])
    assert all(sample.get("ground_truth_ledger") for case in payload["cases"] for sample in case["eval_samples"])


def test_gold_score_uses_ledger_not_blind_grade_for_q1_partial() -> None:
    case = _case("Q1-NA")
    sample = next(sample for sample in case["eval_samples"] if sample["student_id"] == "S2")

    gold = gold_from_ledger(case, sample)

    assert gold["score"] == 3.3333
    assert gold["score"] != sample["blind_grade"]["total"]
    assert gold["point_rows"][0]["ledger_hit"] == "partial"
    assert gold["point_rows"][0]["matched_terms"] == [
        "施工总进度计划表(图)",
        "分期(分批)实施工程的开、竣工日期及工期一览表",
    ]


def test_list_rule_compiles_to_atomic_original_terms_without_synonyms() -> None:
    case = _case("Q1-NA")
    point = case["gold_scoring_points"][0]

    terms = extract_required_terms(point)
    compiled = compile_kernel_scoring_points(case)

    assert terms == [
        "施工总进度计划表(图)",
        "分期(分批)实施工程的开、竣工日期及工期一览表",
        "资源需要量及供应平衡表",
    ]
    assert len(compiled) == 3
    assert {item["keywords"][0] for item in compiled} == set(terms)
    assert all(item["criterion"].startswith("P1::") for item in compiled)


def test_negated_wrong_subject_is_not_compiled_as_positive_keyword() -> None:
    case = _case("Q4-1A434000-罚则")
    compiled = compile_kernel_scoring_points(case)

    p1_keywords = [
        item["keywords"][0]
        for item in compiled
        if item["criterion"].startswith("P1::")
    ]

    assert "见证人员" in p1_keywords
    assert "试验员" not in p1_keywords


def test_penalty_rule_compiles_to_structured_grading_key_asset() -> None:
    case = _case("Q4-1A434000-罚则")

    rules = compile_penalty_rules(case)

    assert rules == [
        {
            "rule_id": "multi_answer_no_score",
            "type": "multi_answer_no_score",
            "trigger": {"max_answered_items": 2, "pattern": "不妥"},
            "zero_point_ids": ["P1", "P2"],
            "source_field": "golden.penalty_rule",
        }
    ]


def test_compiler_does_not_emit_overbroad_principle_keyword() -> None:
    case = _case("Q19-1A432000")
    compiled = compile_kernel_scoring_points(case)

    p2_keywords = [
        item["keywords"][0]
        for item in compiled
        if item["criterion"].startswith("P2::")
    ]

    assert "原则" not in p2_keywords
    assert {"依法履约", "诚实信用", "全面履行", "协调合作", "维护权益", "动态管理"} <= set(p2_keywords)


def test_compiler_does_not_emit_scoring_instruction_as_official_term() -> None:
    case = _case("Q12-1A412000-罚则")

    terms = {
        item["keywords"][0]
        for item in compile_kernel_scoring_points(case)
    }

    assert "0项=0" not in terms
    assert "1项=0.5" not in terms
    assert "命中3项=1.5" not in terms


def test_compiler_does_not_fallback_to_full_label_when_no_official_terms() -> None:
    case = _case("Q5-1A432000")
    compiled = compile_kernel_scoring_points(case)

    assert all("须写出规范条款原文" not in item["keywords"][0] for item in compiled)


def test_compiler_extracts_calculation_result_values_as_official_terms() -> None:
    case = _case("Q20-1A413000")
    terms = {item["keywords"][0] for item in compile_kernel_scoring_points(case)}

    assert "400kg" in terms
    assert "320kg" in terms
    assert "707.2kg" in terms


def test_compiler_preserves_fill_blank_answer_label_context() -> None:
    case = _case("Q10-1A422000")
    compiled = compile_kernel_scoring_points(case)

    p1 = next(item for item in compiled if item["criterion"] == "P1::限制")
    p2 = next(item for item in compiled if item["criterion"] == "P2::禁止")

    assert p1["answer_label"] == "A"
    assert p2["answer_label"] == "B"


def test_summarize_three_arm_results_reports_core_metrics() -> None:
    rows = [
        {
            "case_id": "c1",
            "arm": "baseline",
            "score_delta": 1.0,
            "point_recall": 0.5,
            "point_precision": 1.0,
            "term_recall": 0.5,
            "term_precision": 1.0,
            "hallucination": False,
            "token_proxy": 100,
            "latency_ms": 1.0,
        },
        {
            "case_id": "c1",
            "arm": "artifact_first",
            "score_delta": 0.0,
            "point_recall": 1.0,
            "point_precision": 1.0,
            "term_recall": 1.0,
            "term_precision": 1.0,
            "hallucination": False,
            "token_proxy": 40,
            "latency_ms": 2.0,
        },
    ]

    summary = summarize_three_arm_results(rows)

    assert summary["baseline"]["case_count"] == 1
    assert summary["baseline"]["mean_abs_score_delta"] == 1.0
    assert summary["artifact_first"]["mean_point_recall"] == 1.0
    assert summary["artifact_first"]["mean_token_proxy"] == 40.0


def test_run_pilot_records_authority_and_rag_trace() -> None:
    report = run_pilot(fixture_path=FIXTURE, case_ids=["Q1-NA"])

    artifact_rows = [row for row in report["rows"] if row["arm"] == "artifact_first"]
    baseline_rows = [row for row in report["rows"] if row["arm"] == "baseline"]
    rag_rows = [row for row in report["rows"] if row["arm"] == "rag"]

    assert artifact_rows
    assert all(row["grading_source"] == "grading_key" for row in artifact_rows)
    assert all(row["grading_source"] != "grading_key" for row in baseline_rows)
    assert all(row["evidence_ref_count"] > 0 for row in rag_rows)
    assert report["rag_trace"]["evidence_in_result"] is True
