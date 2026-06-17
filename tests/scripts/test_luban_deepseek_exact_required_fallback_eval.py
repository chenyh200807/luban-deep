from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_deepseek_exact_required_fallback_eval import (
    _gate,
    _is_unsupported,
    evaluate,
    fallback_fires,
)

REPO = Path(__file__).resolve().parents[2]
D = REPO / "artifacts/luban_consensus_gold/deepseek_exact_required_fallback_20260603"


# ---- trigger scope is narrow and exact_required-only ----

def test_q10_half_term_positive_is_captured() -> None:
    point = {"policy_type": "exact_required", "required_terms": ["数控钢筋调直切断机"]}
    pred = {"hit": "partial", "score": 0.5, "evidence_span": "普通钢筋调直机的钢筋调直工艺",
            "rationale": "学生只写了一半（普通钢筋调直机），缺少'数控钢筋调直切断机'"}
    fires, reason = fallback_fires(point, pred)
    assert fires is True
    assert "near_synonym" in reason or "span_lacks" in reason


def test_list_rule_never_triggers_exact_fallback() -> None:
    point = {"policy_type": "list_rule", "required_terms": ["甲", "乙", "丙"]}
    pred = {"hit": "partial", "score": 0.6, "evidence_span": "只写了甲",
            "rationale": "学生只命中一半，缺少乙丙"}
    fires, _ = fallback_fires(point, pred)
    assert fires is False


def test_calculation_never_triggers_exact_fallback() -> None:
    point = {"policy_type": "calculation", "required_terms": []}
    pred = {"hit": "partial", "score": 1.0, "evidence_span": "约等于结果",
            "rationale": "过程相当于正确，约等于答案"}
    fires, _ = fallback_fires(point, pred)
    assert fires is False


def test_penalty_and_figure_never_trigger() -> None:
    for ptype in ("penalty_rule", "figure_label"):
        point = {"policy_type": ptype, "required_terms": ["术语"]}
        pred = {"hit": "hit", "score": 1.0, "evidence_span": "近义表达", "rationale": "近义但相当于正确"}
        assert fallback_fires(point, pred)[0] is False


def test_exact_required_clean_hit_does_not_trigger() -> None:
    # student wrote the exact official term, no near-synonym admission -> keep auto
    point = {"policy_type": "exact_required", "required_terms": ["数控钢筋调直切断机"]}
    pred = {"hit": "hit", "score": 1.0, "evidence_span": "数控钢筋调直切断机",
            "rationale": "学生逐字写出官方术语，命中"}
    assert fallback_fires(point, pred)[0] is False


def test_exact_required_miss_does_not_trigger() -> None:
    point = {"policy_type": "exact_required", "required_terms": ["术语"]}
    pred = {"hit": "miss", "score": 0, "evidence_span": "", "rationale": "缺少术语"}
    assert fallback_fires(point, pred)[0] is False


# ---- unsupported_positive is positive-only (the gate bug fix) ----

def test_miss_with_empty_span_is_not_unsupported_positive() -> None:
    assert _is_unsupported({"hit": "miss", "score": 0, "evidence_span": "", "unsupported": True}) is False


def test_positive_with_empty_span_is_unsupported() -> None:
    assert _is_unsupported({"hit": "hit", "score": 1, "evidence_span": ""}) is True
    assert _is_unsupported({"hit": "partial", "score": 0.5, "evidence_span": "学生原文"}) is False


# ---- before/after metrics + high_risk_review accounting ----

def test_evaluate_moves_triggered_out_of_auto_and_zeroes_violation() -> None:
    points = {
        ("Q", "S", "P1"): {"policy_type": "exact_required", "required_terms": ["数控钢筋调直切断机"]},
        ("Q", "S", "P2"): {"policy_type": "list_rule", "required_terms": ["甲", "乙"]},
    }
    preds = {
        ("Q", "S", "P1"): {"case_id": "Q", "student_id": "S", "point_id": "P1", "hit": "partial",
                            "score": 0.5, "evidence_span": "普通机", "rationale": "只写了一半，缺少数控钢筋调直切断机"},
        ("Q", "S", "P2"): {"case_id": "Q", "student_id": "S", "point_id": "P2", "hit": "hit",
                            "score": 1.0, "evidence_span": "甲乙", "rationale": "命中"},
    }
    gold = {
        ("Q", "S", "P1"): {"case_id": "Q", "student_id": "S", "point_id": "P1", "gold_hit": "miss", "gold_score": 0.0},
        ("Q", "S", "P2"): {"case_id": "Q", "student_id": "S", "point_id": "P2", "gold_hit": "hit", "gold_score": 1.0},
    }
    r = evaluate(points, preds, gold)
    # P1 (exact_required violation) moved to high_risk_review; P2 (list_rule) stays auto
    assert r["before"]["exact_required_major_violation"] == 1
    assert r["after"]["exact_required_major_violation"] == 0
    assert r["after"]["high_risk_review_points"] == 1
    assert r["after"]["auto_graded_points"] == 1
    assert any(t["key"] == ("Q", "S", "P1") for t in r["triggered"])


def test_gate_blocks_when_violation_remains() -> None:
    after = {"exact_required_major_violation": 1, "unsupported_positive": 0,
             "point_hit_agreement": 0.99, "mean_abs_score_delta": 0.0}
    v, reasons = _gate(after, 0.02, 0.98)
    assert v == "NO-GO"


def test_gate_strong_go_on_clean_after() -> None:
    after = {"exact_required_major_violation": 0, "unsupported_positive": 0,
             "point_hit_agreement": 1.0, "mean_abs_score_delta": 0.0054}
    v, _ = _gate(after, 0.0184, 0.9816)
    assert v == "STRONG-GO"


# ---- generated-artifact gates (held-out) ----

@pytest.mark.skipif(not (D / "fallback_before_after_metrics_heldout_175.json").exists(), reason="held-out not generated")
def test_heldout_captures_q10_and_zeroes_violation() -> None:
    m = json.loads((D / "fallback_before_after_metrics_heldout_175.json").read_text(encoding="utf-8"))
    assert m["before"]["exact_required_major_violation"] == 1
    assert m["after"]["exact_required_major_violation"] == 0
    assert m["after"]["unsupported_positive"] == 0
    assert m["after"]["auto_coverage"] >= 0.95
    triggered = {(t["key"][0], t["key"][1], t["key"][2]) for t in m["triggered"]}
    assert ("Q10-1A422000", "S2", "P4") in triggered
    assert m["gate_verdict"] == "STRONG-GO"
