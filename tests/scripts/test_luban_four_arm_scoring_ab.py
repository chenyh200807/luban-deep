"""四臂 A/B runner 纯函数测试（hermetic，不打外网）。"""
from __future__ import annotations

import json
from typing import Any

from scripts.run_luban_four_arm_scoring_ab import (
    kernel_question_row,
    kernel_grading_key,
    predicted_hit_point_ids_from_kernel,
    score_row,
    summarize_arm,
    verdict_ceiling_from_labels,
)


def _manifest_question() -> dict[str, Any]:
    return {
        "question_id": "Q1__P01",
        "stem": "【背景】……【问题】指出不妥之处。",
        "total_score": 7.0,
        "scoring_points": [
            {"point_id": "Q1__P01::SP01", "criterion": "不妥一：应由见证人员记录",
             "max_score": 3.5, "policy_type": "qualitative", "required_terms": [],
             "negative_evidence": [], "source_refs": []},
            {"point_id": "Q1__P01::SP02", "criterion": "不妥二：检测费用应由建设单位单独列支",
             "max_score": 3.5, "policy_type": "qualitative", "required_terms": [],
             "negative_evidence": [], "source_refs": []},
        ],
    }


def test_kernel_question_row_projects_reference_answer_from_criteria():
    row = kernel_question_row(_manifest_question())
    assert row["question_id"] == "Q1__P01"
    assert "见证人员记录" in row["correct_answer"]
    assert "单独列支" in row["correct_answer"]
    assert row["question_type"] == "case_study"


def test_kernel_grading_key_keeps_point_id_in_criterion():
    key = kernel_grading_key(_manifest_question())
    crits = [sp["criterion"] for sp in key["scoring_points"]]
    assert all("::SP" in c for c in crits)
    assert key["scoring_points"][0]["score"] == 3.5


def test_predicted_hit_point_ids_from_kernel_parses_prefixed_criterion():
    rubric_items = [
        {"criterion": "Q1__P01::SP01::不妥一", "status": "full"},
        {"criterion": "Q1__P01::SP02::不妥二", "status": "miss"},
    ]
    assert predicted_hit_point_ids_from_kernel(rubric_items) == {"Q1__P01::SP01"}


def test_score_row_metrics_against_gold():
    gold_row = {
        "question_id": "Q1__P01",
        "gold_score": 3.5,
        "gold_point_matches": [
            {"point_id": "Q1__P01::SP01", "status": "hit"},
            {"point_id": "Q1__P01::SP02", "status": "miss"},
        ],
    }
    out = score_row(
        gold_row=gold_row,
        predicted_score=7.0,
        predicted_hit_ids={"Q1__P01::SP01", "Q1__P01::SP02"},
        max_score=7.0,
        evidence_span_hit_count=1,
        predicted_hit_count=2,
    )
    assert out["abs_score_delta"] == 3.5
    assert out["point_precision"] == 0.5     # SP02 是误命中
    assert out["point_recall"] == 1.0
    assert out["over_credit"] is True        # 7.0 > 3.5 + 0.2*7.0
    assert out["evidence_span_rate"] == 0.5


def test_summarize_arm_aggregates():
    rows = [
        {"abs_score_delta": 1.0, "point_precision": 1.0, "point_recall": 0.5,
         "over_credit": False, "evidence_span_rate": 1.0, "latency_ms": 10,
         "token_total": 100, "high_risk_review": False},
        {"abs_score_delta": 3.0, "point_precision": 0.5, "point_recall": 1.0,
         "over_credit": True, "evidence_span_rate": 0.0, "latency_ms": 30,
         "token_total": 300, "high_risk_review": True},
    ]
    s = summarize_arm(rows)
    assert s["score_mae"] == 2.0
    assert s["point_precision"] == 0.75
    assert s["fail_open_rate"] == 0.5
    assert s["high_risk_review_rate"] == 0.5
    assert s["mean_token"] == 200


def test_verdict_ceiling_from_labels_directional_when_gold_minority():
    labels = ["ai_governed_gold"] * 8 + ["ai_council_directional"] * 154
    out = verdict_ceiling_from_labels(labels)
    assert out["verdict_ceiling"] == "DIRECTIONAL_SHADOW"
    assert out["quality_claim_allowed"] is False
