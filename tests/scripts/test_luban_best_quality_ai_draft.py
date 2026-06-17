from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.best_quality_ai_draft import (
    BestQualityUnavailable,
    _adjudicate_point,
    adjudicate,
    best_quality_draft,
    load_cached_4model_predictions,
)

_POINTS = [
    {"point_id": "P1", "max_score": 2, "label": "官方术语", "typed_policy": {"policy_type": "exact_required", "required_terms": ["数控钢筋调直切断机"]}},
    {"point_id": "P2", "max_score": 2, "label": "列举项", "typed_policy": {"policy_type": "list_rule", "required_terms": ["甲", "乙"], "denominator": 2}},
]
_QUESTION = {"case_id": "QX", "max_score": 4, "scoring_points": _POINTS}
_ANSWER = "学生写了普通钢筋调直机；还有甲和乙"


# ---- adjudication logic (fat skill) ----

def test_exact_required_disagreement_takes_strict_side() -> None:
    votes = {"gpt": {"hit": "miss", "score": 0}, "opus": {"hit": "miss", "score": 0},
             "deepseek": {"hit": "partial", "score": 1, "evidence_span": "普通钢筋调直机", "rationale": "半术语"},
             "qwen": {"hit": "miss", "score": 0}}
    pred, extra = _adjudicate_point("P1", "exact_required", votes)
    assert pred["hit"] == "miss"  # 踩字取严，纠正 DeepSeek 放水
    assert "取严" in pred["rationale"]
    assert extra["model_votes"]["deepseek"]["hit"] == "partial"
    assert "DEEPSEEK:partial" in extra["disagreement_summary"]


def test_list_rule_disagreement_takes_semantic_majority_partial() -> None:
    votes = {"gpt": {"hit": "miss", "score": 0}, "opus": {"hit": "partial", "score": 2, "evidence_span": "甲乙"},
             "deepseek": {"hit": "partial", "score": 2, "evidence_span": "甲乙"}, "qwen": {"hit": "partial", "score": 2, "evidence_span": "甲乙"}}
    pred, _ = _adjudicate_point("P2", "list_rule", votes)
    assert pred["hit"] == "partial"  # 3/4 partial -> semantic partial, not mechanical miss
    assert pred["score"] == 2.0


def test_hard_split_routes_to_high_risk() -> None:
    votes = {"gpt": {"hit": "hit", "score": 2}, "opus": {"hit": "miss", "score": 0},
             "deepseek": {"hit": "partial", "score": 1}, "qwen": {"hit": "miss", "score": 0}}
    pred, _ = _adjudicate_point("P1", "exact_required", votes)
    assert pred["high_risk"] is True  # genuine ambiguity -> human review


def test_unanimous_keeps_label() -> None:
    votes = {m: {"hit": "hit", "score": 2, "evidence_span": "甲乙"} for m in ("gpt", "opus", "deepseek", "qwen")}
    pred, extra = _adjudicate_point("P2", "list_rule", votes)
    assert pred["hit"] == "hit"
    assert "一致" in extra["adjudication_reason"]


# ---- full draft reuses ai_draft_shadow guards + schema ----

def _model_outputs():
    return {
        "gpt": {"P1": {"hit": "miss", "score": 0}, "P2": {"hit": "partial", "score": 1, "evidence_span": "甲和乙"}},
        "opus": {"P1": {"hit": "miss", "score": 0}, "P2": {"hit": "partial", "score": 1, "evidence_span": "甲和乙"}},
        "deepseek": {"P1": {"hit": "partial", "score": 1, "evidence_span": "普通钢筋调直机", "rationale": "半术语"}, "P2": {"hit": "partial", "score": 1, "evidence_span": "甲和乙"}},
        "qwen": {"P1": {"hit": "miss", "score": 0}, "P2": {"hit": "miss", "score": 0}},
    }


def test_best_quality_draft_schema_and_guards() -> None:
    d = best_quality_draft(_QUESTION, _ANSWER, _model_outputs(), points=_POINTS, student_id="S1")
    assert d["authority"] == "best_quality_4model_shadow"
    assert d["engine"] == "best_quality_4model"
    assert d["prediction_source"] == "cached_4model_485"
    assert d["candidate_only"] is True and d["not_production_grade"] is True
    assert d["bad_certified_count"] == 0
    # P1 adjudicated strict miss (DeepSeek leniency overruled)
    p1 = next(p for p in d["point_results"] if p["point_id"] == "P1")
    assert p1["hit"] == "miss"
    assert "model_votes" in p1 and "adjudication_reason" in p1 and "disagreement_summary" in p1
    # high_risk / unsupported never auto_certified; pending score preserved (not 0)
    for p in d["point_results"]:
        if p["high_risk_review"] or p["unsupported"]:
            assert p["auto_certified"] is False
    assert d["model_draft_score"] >= d["auto_certified_score"]


def test_adjudicate_insufficient_jurors_routes_to_review() -> None:
    # only 1 model for P1 -> review, not fabricated
    preds, extras = adjudicate(_POINTS, {"gpt": {"P1": {"hit": "hit", "score": 2}}, "opus": {"P2": {"hit": "miss"}}})
    p1 = next(p for p in preds if p["point_id"] == "P1")
    assert p1["high_risk"] is True


# ---- fail-closed: no 4-model predictions ----

def test_load_cached_raises_when_sample_absent() -> None:
    with pytest.raises(BestQualityUnavailable):
        load_cached_4model_predictions("NO-SUCH-CASE", "S9")
