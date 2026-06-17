from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_485_list_rule_policy import (
    apply_fail_closed,
    apply_recompute,
    classify_list_rule_residual,
    gate_metrics,
)

REPO = Path(__file__).resolve().parents[2]
F = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603"


def _pidx(*types):
    return {("Q", "S", f"P{i}"): {"policy_type": t, "list_spec": {"terms": ["甲", "乙"], "denominator": 2}, "max": 2}
            for i, t in enumerate(types, 1)}


# ---- residual classification ----

def test_list_rule_residual_classification_types() -> None:
    pt = {"list_spec": {"terms": ["环境", "气候", "地形"], "denominator": 3}}
    # deepseek miss but span has enumerated paraphrase with 0 verbatim hits -> generic_label_over_credit
    pred = {"hit": "miss", "score": 0, "evidence_span": "天气好不好、地方在哪儿、活儿难不难"}
    gold = {"gold_hit": "partial", "gold_score": 1.0}
    assert classify_list_rule_residual(pt, pred, gold) == "generic_label_over_credit"
    # deepseek miss but span literally contains items -> label_vs_score_mismatch
    pred2 = {"hit": "miss", "score": 0, "evidence_span": "环境、气候都考虑了"}
    assert classify_list_rule_residual(pt, pred2, gold) == "label_vs_score_mismatch"
    # empty span miss -> evidence_span_insufficient
    pred3 = {"hit": "miss", "score": 0, "evidence_span": ""}
    assert classify_list_rule_residual(pt, pred3, gold) == "evidence_span_insufficient"


# ---- policies only touch list_rule ----

def test_list_rule_policy_v1_does_not_touch_exact_required() -> None:
    ds = {
        ("Q", "S", "P1"): {"case_id": "Q", "student_id": "S", "point_id": "P1", "hit": "hit", "score": 1.0, "evidence_span": "近义词", "rationale": "近义"},
        ("Q", "S", "P2"): {"case_id": "Q", "student_id": "S", "point_id": "P2", "hit": "miss", "score": 0, "evidence_span": "甲；乙；丙"},
    }
    pidx = {("Q", "S", "P1"): {"policy_type": "exact_required", "list_spec": {}, "max": 2},
            ("Q", "S", "P2"): {"policy_type": "list_rule", "list_spec": {"terms": ["甲", "乙"], "denominator": 2}, "max": 2}}
    for fn in (apply_recompute, apply_fail_closed):
        out = fn(ds, pidx)
        # exact_required point untouched
        assert out[("Q", "S", "P1")]["hit"] == "hit"
        assert out[("Q", "S", "P1")]["score"] == 1.0
        assert out[("Q", "S", "P1")].get("high_risk_review") is not True


def test_recompute_only_changes_list_rule_and_uses_official_denominator() -> None:
    ds = {("Q", "S", "P2"): {"case_id": "Q", "student_id": "S", "point_id": "P2", "hit": "miss", "score": 0, "evidence_span": "甲、乙"}}
    pidx = {("Q", "S", "P2"): {"policy_type": "list_rule", "list_spec": {"terms": ["甲", "乙"], "denominator": 2}, "max": 2}}
    out = apply_recompute(ds, pidx)
    # k=2/n=2 -> hit, score 2.0 (recomputed from official denominator, not from gold)
    assert out[("Q", "S", "P2")]["hit"] == "hit"
    assert out[("Q", "S", "P2")]["score"] == 2.0


def test_fail_closed_quarantines_to_high_risk_without_changing_score() -> None:
    ds = {("Q", "S", "P2"): {"case_id": "Q", "student_id": "S", "point_id": "P2", "hit": "miss", "score": 0, "evidence_span": "甲；乙；丙"}}
    pidx = {("Q", "S", "P2"): {"policy_type": "list_rule", "list_spec": {"terms": ["甲", "乙"], "denominator": 2}, "max": 2}}
    out = apply_fail_closed(ds, pidx)
    assert out[("Q", "S", "P2")]["high_risk_review"] is True
    assert out[("Q", "S", "P2")]["score"] == 0  # score NOT changed


# ---- gate invariants ----

def _mini_gold_and_preds():
    ds = {
        ("Q", "S", "P1"): {"case_id": "Q", "student_id": "S", "point_id": "P1", "hit": "hit", "score": 2.0, "evidence_span": "甲乙"},
    }
    pidx = {("Q", "S", "P1"): {"policy_type": "list_rule", "list_spec": {"terms": ["甲", "乙"], "denominator": 2}, "max": 2}}
    gold = {("Q", "S", "P1"): {"case_id": "Q", "student_id": "S", "point_id": "P1", "gold_hit": "hit", "gold_score": 2.0}}
    return ds, pidx, gold


def test_list_rule_policy_v1_unsupported_positive_stays_zero() -> None:
    ds, pidx, gold = _mini_gold_and_preds()
    for arm in (ds, apply_recompute(ds, pidx), apply_fail_closed(ds, pidx)):
        m = gate_metrics(arm, pidx, gold)
        assert m["unsupported"] == 0
        assert m["exact_major"] == 0


def test_list_rule_policy_v1_gate_metrics_shape() -> None:
    ds, pidx, gold = _mini_gold_and_preds()
    m = gate_metrics(ds, pidx, gold)
    for key in ("auto_coverage", "auto_hit", "score_delta", "exact_major", "unsupported", "high_risk_review", "gate_verdict"):
        assert key in m
    assert m["gate_verdict"] in ("STRONG-GO", "WEAK-GO", "NO-GO")


# ---- generated-artifact gates ----

@pytest.mark.skipif(not (F / "list_rule_policy_ab_485.json").exists(), reason="ab not generated")
def test_ab_artifact_records_three_arms_and_no_exact_regression() -> None:
    ab = json.loads((F / "list_rule_policy_ab_485.json").read_text(encoding="utf-8"))
    arms = ab["arms"]
    assert set(arms) == {"baseline_after_fallback", "list_rule_policy_v1_recompute", "list_rule_policy_v1_fail_closed"}
    # no arm may introduce exact_required / penalty regression or unsupported
    for name, r in arms.items():
        assert r["exact_major"] == 0, name
        assert r["penalty_major"] == 0, name
        assert r["unsupported"] == 0, name


@pytest.mark.skipif(not (F / "list_rule_policy_ab_485.json").exists(), reason="ab not generated")
def test_list_rule_policy_v1_frontier_not_forced_into_gold() -> None:
    cov = json.loads((F / "consensus_coverage_report_485.json").read_text(encoding="utf-8"))
    assert cov["frontier_points"] > 0
    assert cov["deepseek_self_vote_in_gold"] == 0
    assert cov["unsupported_positive_into_gold"] == 0
