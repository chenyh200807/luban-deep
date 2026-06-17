"""Tests for best_quality_ai_draft.py — the 4-model adjudicated AI-Draft.

All tests are deterministic and synthesize model_outputs in-process
({model: {point_id: pred}}); they NEVER touch a live provider key nor the
cached 485 file (except the explicit fail-closed path, which is forced via
monkeypatch to a missing/empty fixture). The guards (span fail-closed,
high_risk/unsupported never auto_certified, pending_review_score != 0) are
owned by ai_draft_shadow and only re-asserted here at the draft surface.
"""
from __future__ import annotations

import json

import pytest

from deeptutor.services.construction_grading import best_quality_ai_draft as bq
from deeptutor.services.construction_grading.best_quality_ai_draft import (
    BestQualityUnavailable,
    best_quality_draft,
    load_cached_4model_predictions,
)

STUDENT_ID = "stu-001"

# ---- synthetic question (typed_policy + max_score per scoring point) ----------


def _point(point_id: str, policy_type: str, *, required_terms=None, max_score: float = 2.0) -> dict:
    return {
        "point_id": point_id,
        "label": f"label-{point_id}",
        "max_score": max_score,
        "typed_policy": {
            "policy_type": policy_type,
            "required_terms": list(required_terms or []),
        },
    }


def _question(points: list[dict], *, case_id: str = "case-A", max_score: float = 6.0) -> dict:
    return {"case_id": case_id, "stem": "施工题干", "scoring_points": points, "max_score": max_score}


def _pred(point_id: str, hit: str, *, score: float, evidence_span: str = "", rationale: str = "") -> dict:
    return {
        "point_id": point_id,
        "hit": hit,
        "score": score,
        "evidence_span": evidence_span,
        "rationale": rationale,
    }


def _pr_by_id(draft: dict, point_id: str) -> dict:
    return next(p for p in draft["point_results"] if p["point_id"] == point_id)


# ---- 1. four-model unanimous -> that label, score = mean of same-label models --


def test_four_model_unanimous_takes_label_and_mean_score():
    answer = "本工程采用大体积混凝土进行温度控制以防止裂缝产生。"
    span = "大体积混凝土"
    points = [_point("p1", "list_rule", max_score=2.0)]
    model_outputs = {
        "gpt": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "opus": {"p1": _pred("p1", "hit", score=1.8, evidence_span=span)},
        "deepseek": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "qwen": {"p1": _pred("p1", "hit", score=1.6, evidence_span=span)},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    pr = _pr_by_id(draft, "p1")
    assert pr["hit"] == "hit"
    # mean of all four (all share the adjudicated label) = (2.0+1.8+2.0+1.6)/4 = 1.85
    assert pr["score"] == pytest.approx(1.85)
    assert pr["adjudication_reason"] == "四模一致"
    assert pr["auto_certified"] is True
    assert pr["high_risk_review"] is False
    assert pr["unsupported"] is False


# ---- 2. exact_required disagreement -> take strict side = miss (踩字纪律) --------


def test_exact_required_disagreement_takes_strict_miss():
    answer = "我把它叫做受力筋，大概就是承重的钢筋。"
    points = [_point("p1", "exact_required", required_terms=["受力钢筋"], max_score=2.0)]
    model_outputs = {
        # GPT 放水 hit, Opus 严格 miss, DeepSeek partial, Qwen miss
        "gpt": {"p1": _pred("p1", "hit", score=2.0, evidence_span="受力筋", rationale="近义可视为命中")},
        "opus": {"p1": _pred("p1", "miss", score=0.0, evidence_span="", rationale="未写出规范术语")},
        "deepseek": {"p1": _pred("p1", "partial", score=1.0, evidence_span="受力筋", rationale="只写了一半")},
        "qwen": {"p1": _pred("p1", "miss", score=0.0, evidence_span="")},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    pr = _pr_by_id(draft, "p1")
    assert pr["hit"] == "miss"
    assert pr["score"] in (0, 0.0)
    assert "取严" in pr["adjudication_reason"]
    # model votes preserved for audit
    assert pr["model_votes"]["gpt"]["hit"] == "hit"
    assert pr["model_votes"]["opus"]["hit"] == "miss"
    assert pr["model_votes"]["deepseek"]["hit"] == "partial"
    assert pr["model_votes"]["qwen"]["hit"] == "miss"
    # miss is not pending and not unsupported (no positive claim survived)
    assert pr["unsupported"] is False


# ---- 3. exact_required 2-2 hard split -> high_risk_review, not auto_certified ----


def test_exact_required_hard_split_routes_to_high_risk_review():
    answer = "采用受力钢筋作为主筋承担拉力，受力钢筋布置在受拉区。"
    span = "受力钢筋"
    points = [_point("p1", "exact_required", required_terms=["受力钢筋"], max_score=2.0)]
    model_outputs = {
        # 2 hit / 2 miss -> hard split
        "gpt": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span, rationale="术语完整命中")},
        "opus": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span, rationale="术语完整命中")},
        "deepseek": {"p1": _pred("p1", "miss", score=0.0, evidence_span="")},
        "qwen": {"p1": _pred("p1", "miss", score=0.0, evidence_span="")},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    pr = _pr_by_id(draft, "p1")
    # exact_required strict on disagreement -> miss, but the hard split must be flagged
    assert pr["high_risk_review"] is True
    assert pr["auto_certified"] is False


# ---- 4. list_rule disagreement -> reasonable partial (fact-coverage, not substring) --


def test_list_rule_split_yields_partial():
    answer = "现场已做安全交底、设置临边防护、配备灭火器材。"
    span = "安全交底"
    points = [_point("p1", "list_rule", required_terms=["安全交底", "临边防护", "消防器材"], max_score=3.0)]
    model_outputs = {
        # 2 partial / 2 hit -> no strict majority -> list_rule tie defaults to partial
        "gpt": {"p1": _pred("p1", "hit", score=3.0, evidence_span=span)},
        "opus": {"p1": _pred("p1", "partial", score=1.5, evidence_span=span)},
        "deepseek": {"p1": _pred("p1", "partial", score=2.0, evidence_span=span)},
        "qwen": {"p1": _pred("p1", "hit", score=3.0, evidence_span=span)},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    pr = _pr_by_id(draft, "p1")
    assert pr["hit"] == "partial"
    # partial score = mean of the partial-voting models = (1.5+2.0)/2 = 1.75, capped semantics aside
    assert pr["score"] == pytest.approx(1.75)
    assert "list_rule" in pr["adjudication_reason"]


# ---- 5. unsupported span fail-closed: positive label w/ span not in answer -------


def test_unsupported_span_fail_closed():
    answer = "本工程使用普通混凝土，未提及温控措施。"
    # adjudicated positive but the agreeing span text does NOT appear in the answer
    span = "大体积混凝土温度控制"
    points = [_point("p1", "list_rule", max_score=2.0)]
    model_outputs = {
        "gpt": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "opus": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "deepseek": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "qwen": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    pr = _pr_by_id(draft, "p1")
    assert pr["unsupported"] is True
    assert pr["auto_certified"] is False


# ---- 6. high_risk / unsupported never auto_certified; pending_review_score != 0 --


def test_high_risk_and_unsupported_never_auto_certified_and_pending_not_zeroed():
    answer = "采用受力钢筋作为主筋。现场已做安全交底。"
    points = [
        # p1: hard-split exact_required (pending, score survives as draft score)
        _point("p1", "exact_required", required_terms=["受力钢筋"], max_score=2.0),
        # p2: clean unanimous hit (auto_certified)
        _point("p2", "list_rule", required_terms=["安全交底"], max_score=2.0),
    ]
    span1 = "受力钢筋"
    span2 = "安全交底"
    model_outputs = {
        "gpt": {
            "p1": _pred("p1", "hit", score=2.0, evidence_span=span1, rationale="术语命中"),
            "p2": _pred("p2", "hit", score=2.0, evidence_span=span2),
        },
        "opus": {
            "p1": _pred("p1", "hit", score=2.0, evidence_span=span1, rationale="术语命中"),
            "p2": _pred("p2", "hit", score=2.0, evidence_span=span2),
        },
        "deepseek": {
            "p1": _pred("p1", "miss", score=0.0, evidence_span=""),
            "p2": _pred("p2", "hit", score=2.0, evidence_span=span2),
        },
        "qwen": {
            "p1": _pred("p1", "miss", score=0.0, evidence_span=""),
            "p2": _pred("p2", "hit", score=2.0, evidence_span=span2),
        },
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    # no point may be both pending/unsupported AND auto_certified
    for pr in draft["point_results"]:
        if pr["high_risk_review"] or pr["unsupported"]:
            assert pr["auto_certified"] is False
    assert draft["bad_certified_count"] == 0
    # p1 is the hard-split pending point (exact_required strict -> miss -> 0)
    p1 = _pr_by_id(draft, "p1")
    assert p1["high_risk_review"] is True
    assert p1["auto_certified"] is False
    # p2 is the clean unanimous hit; mean of all four hit-models = 2.0
    p2 = _pr_by_id(draft, "p2")
    assert p2["auto_certified"] is True
    assert draft["auto_certified_score"] == pytest.approx(2.0)
    # certified total excludes pending; pending tracked separately and never auto-counted
    assert draft["total_score_certified_only"] == draft["auto_certified_score"]


def test_pending_review_score_carries_nonzero_when_pending_point_scored():
    # Construct a pending point that DID receive a positive adjudicated score, to prove
    # pending_review_score is not forced to 0 (display must not treat pending as 0).
    answer = "现场已做安全交底、临边防护、配备消防器材，措施齐全。"
    span = "安全交底"
    # list_rule hard split (2 hit / 2 partial) -> adjudicated partial; force high_risk via a juror flag
    points = [_point("p1", "list_rule", required_terms=["安全交底"], max_score=3.0)]
    model_outputs = {
        "gpt": {"p1": _pred("p1", "hit", score=3.0, evidence_span=span)},
        "opus": {"p1": _pred("p1", "hit", score=3.0, evidence_span=span)},
        # partial on list_rule contributes abstention risk; weak span/hedge pushes >= tau
        "deepseek": {"p1": _pred("p1", "partial", score=2.0, evidence_span=span, rationale="部分覆盖，不确定")},
        "qwen": {"p1": _pred("p1", "partial", score=2.0, evidence_span=span, rationale="部分覆盖，不确定")},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    pr = _pr_by_id(draft, "p1")
    assert pr["hit"] == "partial"
    assert pr["score"] == pytest.approx(2.0)  # mean of the two partial-voting models
    # list_rule + partial triggers selective-abstention proxy -> high_risk_review (pending)
    assert pr["high_risk_review"] is True
    assert pr["auto_certified"] is False
    # the crux: pending score is carried, NOT zeroed, and NOT folded into certified total
    assert draft["pending_review_score"] == pytest.approx(2.0)
    assert draft["auto_certified_score"] == pytest.approx(0.0)
    assert draft["total_score_certified_only"] == pytest.approx(0.0)


# ---- 7. output schema compatible with existing AI-Draft -------------------------


def test_output_schema_is_ai_draft_compatible():
    answer = "采用大体积混凝土并做温度控制。"
    span = "大体积混凝土"
    points = [_point("p1", "list_rule", max_score=2.0)]
    model_outputs = {
        "gpt": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "opus": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "deepseek": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
        "qwen": {"p1": _pred("p1", "hit", score=2.0, evidence_span=span)},
    }
    draft = best_quality_draft(_question(points), answer, model_outputs, points=points, student_id=STUDENT_ID)
    # top-level markers identifying this as a non-production, candidate-only 4-model draft
    assert draft["authority"] == "best_quality_4model_shadow"
    assert draft["engine"] == "best_quality_4model"
    assert draft["candidate_only"] is True
    assert draft["not_production_grade"] is True
    assert "point_results" in draft and draft["point_results"]
    required_keys = {
        "policy_type", "hit", "score", "max_score", "evidence_span", "rationale",
        "model_votes", "adjudication_reason", "high_risk_review", "unsupported", "auto_certified",
    }
    for pr in draft["point_results"]:
        missing = required_keys - set(pr)
        assert not missing, f"point_result missing keys: {missing}"
        assert pr["max_score"] == pytest.approx(2.0)


# ---- 8. load_cached_4model_predictions fails closed with <3 jurors ---------------


def test_load_cached_raises_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(bq, "CACHED_4MODEL", tmp_path / "does_not_exist.json")
    with pytest.raises(BestQualityUnavailable):
        load_cached_4model_predictions("case-A", STUDENT_ID)


def test_load_cached_raises_when_fewer_than_three_jurors(monkeypatch, tmp_path):
    # only TWO arms present for the requested sample -> insufficient jury -> fail closed
    fixture = {
        "prediction_sets": [
            {
                "arm": "gpt55_primary",
                "predictions": [
                    {"case_id": "case-A", "student_id": STUDENT_ID, "point_id": "p1", "hit": "hit", "score": 2.0},
                ],
            },
            {
                "arm": "opus48_primary",
                "predictions": [
                    {"case_id": "case-A", "student_id": STUDENT_ID, "point_id": "p1", "hit": "miss", "score": 0.0},
                ],
            },
        ]
    }
    path = tmp_path / "two_juror.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(bq, "CACHED_4MODEL", path)
    with pytest.raises(BestQualityUnavailable):
        load_cached_4model_predictions("case-A", STUDENT_ID)


def test_load_cached_ok_with_three_jurors(monkeypatch, tmp_path):
    fixture = {
        "prediction_sets": [
            {
                "arm": arm,
                "predictions": [
                    {"case_id": "case-A", "student_id": STUDENT_ID, "point_id": "p1", "hit": "hit", "score": 2.0},
                ],
            }
            for arm in ("gpt55_primary", "opus48_primary", "deepseek_v4_flash_typed_policy_primary")
        ]
    }
    path = tmp_path / "three_juror.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(bq, "CACHED_4MODEL", path)
    out = load_cached_4model_predictions("case-A", STUDENT_ID)
    assert set(out) == {"gpt", "opus", "deepseek"}
    assert out["gpt"]["p1"]["hit"] == "hit"
