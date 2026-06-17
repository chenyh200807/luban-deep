from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_distillation_samples_v0 import (
    build_distillation_samples,
    build_manifest,
    build_sample,
)

REPO = Path(__file__).resolve().parents[2]


def _question() -> dict:
    """A golden case shape with one exact_required-discipline point and one
    list_rule-partial point, plus an eval sample answer."""
    return {
        "case_id": "QT",
        "stem": "案例题干",
        "official_answer": "标准答案",
        "max_score": 6,
        "gold_scoring_points": [
            {"point_id": "P1", "label": "踩字点", "max_score": 3},
            {"point_id": "P2", "label": "列举点", "max_score": 3},
        ],
        "eval_samples": [
            {"student_id": "S1", "answer_text": "学生写了数控钢筋调直切断机和甲"}
        ],
    }


def _artifact() -> dict:
    return {
        "question_id": "QT",
        "scoring_points": [
            {
                "point_id": "P1",
                "policy_type": "exact_required",
                "required_terms": ["数控钢筋调直切断机"],
                "max_score": 3,
            },
            {
                "point_id": "P2",
                "policy_type": "list_rule",
                "required_terms": ["甲", "乙"],
                "max_score": 3,
            },
        ],
    }


def _draft() -> dict:
    """A best_quality adjudicated draft shape: one exact_required hit,
    one list_rule partial, plus an unconfirmed high_risk point."""
    return {
        "question_id": "QT",
        "student_id": "S1",
        "authority": "best_quality_4model_shadow",
        "engine": "best_quality_4model",
        "model_set": ["gpt55", "opus48", "deepseek_v4", "qwen37"],
        "prediction_source": "cached_4model_485",
        "point_results": [
            {
                "point_id": "P1",
                "policy_type": "exact_required",
                "hit": "hit",
                "score": 3.0,
                "max_score": 3,
                "evidence_span": "数控钢筋调直切断机",
                "rationale": "四模一致",
                "auto_certified": True,
                "high_risk_review": False,
                "unsupported": False,
                "review_reason": None,
                "display_status": "auto_certified",
                "model_votes": {
                    "gpt": {"hit": "hit", "score": 3},
                    "opus": {"hit": "hit", "score": 3},
                    "deepseek": {"hit": "hit", "score": 3},
                    "qwen": {"hit": "hit", "score": 3},
                },
                "disagreement_summary": "... → 裁决 hit",
                "adjudication_reason": "四模一致",
            },
            {
                "point_id": "P2",
                "policy_type": "list_rule",
                "hit": "partial",
                "score": 1.5,
                "max_score": 3,
                "evidence_span": "甲",
                "rationale": "list_rule 语义裁决：按事实覆盖多数派 partial",
                "auto_certified": True,
                "high_risk_review": False,
                "unsupported": False,
                "review_reason": None,
                "display_status": "auto_certified",
                "model_votes": {
                    "gpt": {"hit": "partial", "score": 1.5},
                    "opus": {"hit": "partial", "score": 1.5},
                    "deepseek": {"hit": "hit", "score": 3},
                    "qwen": {"hit": "miss", "score": 0},
                },
                "disagreement_summary": "... → 裁决 partial",
                "adjudication_reason": "list_rule 语义裁决",
            },
            {
                "point_id": "P3",
                "policy_type": "exact_required",
                "hit": "hit",
                "score": 2.0,
                "max_score": 2,
                "evidence_span": "存疑命中",
                "rationale": "硬分裂",
                "auto_certified": False,
                "high_risk_review": True,
                "unsupported": False,
                "review_reason": "selective_abstention_proxy",
                "display_status": "pending_review",
                "model_votes": {
                    "gpt": {"hit": "hit", "score": 2},
                    "opus": {"hit": "miss", "score": 0},
                    "deepseek": {"hit": "hit", "score": 2},
                    "qwen": {"hit": "miss", "score": 0},
                },
                "disagreement_summary": "... → 裁决 hit",
                "adjudication_reason": "硬分裂",
            },
        ],
    }


def test_build_sample_structure_complete() -> None:
    samples = build_sample(_question(), "S1", _draft(), _artifact())
    assert len(samples) == 3
    s = samples[0]
    # question context
    assert s["question_id"] == "QT"
    assert s["stem"] == "案例题干"
    assert s["official_answer"] == "标准答案"
    assert s["student_id"] == "S1"
    assert s["student_answer"]
    # scoring artifact projection
    assert s["scoring_artifact"]["policy_type"] == "exact_required"
    assert s["scoring_artifact"]["required_terms"] == ["数控钢筋调直切断机"]
    assert s["scoring_artifact"]["max_score"] == 3
    # adjudicated point_result fields
    assert s["point_result"]["hit"] == "hit"
    assert s["point_result"]["score"] == 3.0
    assert s["evidence_span"] == "数控钢筋调直切断机"
    assert s["rationale"]
    assert s["model_votes"]["gpt"]["hit"] == "hit"
    # provenance markers
    assert s["best_quality_source"] == "cached_4model_485"
    assert s["model_set"] == ["gpt55", "opus48", "deepseek_v4", "qwen37"]


def test_unconfirmed_high_risk_not_marked_gold_correct() -> None:
    samples = build_sample(_question(), "S1", _draft(), _artifact())
    by_id = {s["point_id"]: s for s in samples}
    # confirmed auto_certified hit IS gold label
    assert by_id["P1"]["is_gold_label"] is True
    assert by_id["P1"]["high_risk"] is False
    assert by_id["P1"]["label_status"] == "best_quality_certified"
    # unconfirmed high_risk point MUST NOT be a gold correct answer
    assert by_id["P3"]["high_risk"] is True
    assert by_id["P3"]["is_gold_label"] is False
    assert by_id["P3"]["label_status"] == "pending_review"
    assert by_id["P3"]["high_risk_reason"] == "selective_abstention_proxy"


def test_discipline_case_tagging() -> None:
    samples = build_sample(_question(), "S1", _draft(), _artifact())
    by_id = {s["point_id"]: s for s in samples}
    # exact_required hit -> discipline case (踩字纪律)
    assert by_id["P1"]["case_tag"] == "exact_required_discipline"
    # list_rule partial -> list_rule partial case
    assert by_id["P2"]["case_tag"] == "list_rule_partial"


def test_manifest_counts_and_distribution() -> None:
    samples = build_sample(_question(), "S1", _draft(), _artifact())
    manifest = build_manifest(samples)
    assert manifest["sample_count"] == 3
    assert manifest["policy_type_distribution"]["exact_required"] == 2
    assert manifest["policy_type_distribution"]["list_rule"] == 1
    assert manifest["gold_label_count"] == 2  # P3 is pending_review, not gold
    assert manifest["high_risk_count"] == 1
    # P1 (certified hit) and P3 (pending_review hit) are both exact_required hits;
    # case_tag stratifies by policy/hit pattern, independent of confirmation status.
    assert manifest["exact_required_discipline_count"] == 2
    assert manifest["list_rule_partial_count"] == 1


def test_build_distillation_samples_deterministic_over_golden() -> None:
    a = build_distillation_samples()
    b = build_distillation_samples()
    assert a == b  # determinism: no clock, no randomness, cached predictions only
    assert len(a) > 0
    # never trains / touches production: every sample is offline-labeled
    for s in a:
        assert s["best_quality_source"]
        # high_risk samples never claim to be gold correct
        if s["high_risk"]:
            assert s["is_gold_label"] is False


def test_no_unconfirmed_high_risk_is_gold_over_golden() -> None:
    samples = build_distillation_samples()
    bad = [s for s in samples if s["high_risk"] and s["is_gold_label"]]
    assert bad == []
