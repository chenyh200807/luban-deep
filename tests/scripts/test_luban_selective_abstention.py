from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_selective_abstention import metrics_on, risk_score

REPO = Path(__file__).resolve().parents[2]
O = REPO / "artifacts/luban_consensus_gold/selective_abstention_qwk_20260604"


# ---- risk signal ----

def test_miss_is_not_an_abstention_candidate() -> None:
    p = {"hit": "miss", "score": 0, "evidence_span": "", "rationale": ""}
    assert risk_score(p, {"policy_type": "list_rule"}, ["miss", "miss", "miss"]) == -1.0


def test_jury_disagreement_raises_risk() -> None:
    p = {"hit": "partial", "score": 1, "evidence_span": "学生原文片段", "rationale": "ok"}
    info = {"policy_type": "list_rule"}
    low = risk_score(p, info, ["partial", "partial", "partial"])   # jury agrees
    high = risk_score(p, info, ["miss", "miss", "miss"])           # jury all disagree
    assert high > low


def test_weak_span_and_hedge_add_risk() -> None:
    info = {"policy_type": "exact_required"}
    jur = ["hit", "hit", "hit"]
    clean = risk_score({"hit": "hit", "score": 1, "evidence_span": "明确的学生原文", "rationale": "命中"}, info, jur)
    weak = risk_score({"hit": "hit", "score": 1, "evidence_span": "", "rationale": "近义,可能"}, info, jur)
    assert weak > clean


# ---- abstention only moves to review, never changes score ----

def test_metrics_on_counts_hard_violations() -> None:
    ds = {("Q", "S", "P1"): {"hit": "partial", "score": 0.5, "evidence_span": "x"}}
    pidx = {("Q", "S", "P1"): {"policy_type": "exact_required"}}
    gold = {("Q", "S", "P1"): {"gold_hit": "miss", "gold_score": 0.0}}
    m = metrics_on(list(ds), ds, pidx, gold)
    assert m["exact_major"] == 1  # exact_required gold=miss but pred=partial -> 踩字 violation counted


# ---- generated-artifact gates ----

@pytest.mark.skipif(not (O / "certified_subset_metrics.json").exists(), reason="abstention not generated")
def test_certified_subset_keeps_hard_gates_zero() -> None:
    m = json.loads((O / "certified_subset_metrics.json").read_text(encoding="utf-8"))["certified_subset"]
    assert m["exact_major"] == 0
    assert m["unsupported"] == 0
    assert m["penalty_major"] == 0


@pytest.mark.skipif(not (O / "certified_subset_metrics.json").exists(), reason="abstention not generated")
def test_three_gate_readings_present_and_v2_is_candidate_only() -> None:
    g = json.loads((O / "certified_subset_metrics.json").read_text(encoding="utf-8"))["gate_readings"]
    assert "legacy_raw_score_delta_gate" in g
    assert "candidate_only" in g["metric_v2_qwk_candidate_gate"]   # must NOT be sold as a real STRONG-GO
    assert "NOT a production accuracy claim" in g["product_test_gate"]


@pytest.mark.skipif(not (O / "selected_threshold.json").exists(), reason="abstention not generated")
def test_selected_threshold_within_high_risk_budget() -> None:
    s = json.loads((O / "selected_threshold.json").read_text(encoding="utf-8"))
    if "tau" in s:  # a threshold was found
        assert s["high_risk_review_ratio"] <= 0.10
        assert s["auto_hit"] >= 0.94
        assert s["exact_major"] == 0 and s["unsupported"] == 0
