from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.build_luban_qwen_fewshot_ab import compute_list_rule_only_ab
from scripts.build_luban_qwen_list_rule_only_fewshot import build_prompt, leak_check

REPO = Path(__file__).resolve().parents[2]
AB = REPO / "artifacts/luban_consensus_gold/qwen_list_rule_only_ab_20260603"


def _m(hit, score, unsup, list_dis, exact_dis=0, exact_viol=0, pen_viol=0, calc_dis=0):
    return {
        "point_hit_agreement": hit, "mean_abs_score_delta": score, "unsupported_positive": unsup,
        "list_rule_disagreements": list_dis, "exact_required_disagreements": exact_dis,
        "exact_required_major_violation": exact_viol, "penalty_rule_major_violation": pen_viol,
        "calculation_disagreements": calc_dis,
    }


# ---- prompt is list_rule-only and leak-safe ----

def test_prompt_has_no_exact_required_or_review_directives() -> None:
    p = build_prompt()
    assert "exact_required_near_synonym" not in p
    assert "近义" not in p
    assert "吃不准" not in p
    # no global review default directive
    assert not re.search(r"默认\s*review|标\s*review", p)


def test_prompt_has_no_gold_human_ledger_or_heldout_leakage() -> None:
    p = build_prompt()
    for forbidden in ("human_hit", "human_score", "ground_truth_ledger", "ledger_point_rows", "consensus_gold_v1"):
        assert forbidden not in p
    assert not re.search(r"Q\d+-1A\d+|Q\d+-NA", p)
    # builder's own leak gate must pass clean
    assert leak_check(p) == []


def test_prompt_keeps_list_rule_kn_and_label_vs_score() -> None:
    p = build_prompt()
    assert "k/n" in p
    assert "list_rule" in p
    assert "partial" in p and "miss" in p


# ---- stricter verdict ----

def test_unsupported_positive_triggers_no_go() -> None:
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16), _m(0.97, 0.01, 1, 10))
    assert d["verdict"] == "NO-GO"
    assert "unsupported_positive>0" in d["verdict_reasons"]


def test_exact_required_major_violation_triggers_no_go() -> None:
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16), _m(0.97, 0.01, 0, 12, exact_viol=1))
    assert d["verdict"] == "NO-GO"
    assert "exact_required_major_violation>0" in d["verdict_reasons"]


def test_list_rule_no_improvement_is_no_go() -> None:
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16), _m(0.96, 0.02, 0, 16))
    assert d["verdict"] == "NO-GO"
    assert "list_rule no improvement" in d["verdict_reasons"]


def test_list_rule_down_no_regression_hit_flat_is_go() -> None:
    # list_rule down, hit up, exact_required not increased, score within +0.01 -> GO
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16), _m(0.9571, 0.0227, 0, 13))
    assert d["verdict"] == "GO"


def test_list_rule_down_hit_small_drop_is_weak_go() -> None:
    # hit drops 0.002 (<=0.003), list_rule down, no regression -> WEAK-GO
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16), _m(0.9551, 0.0277, 0, 13))
    assert d["verdict"] == "WEAK-GO"


def test_hit_big_drop_is_no_go() -> None:
    # hit drops 0.01 (>0.003) without offsetting -> NO-GO
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16), _m(0.9471, 0.0227, 0, 13))
    assert d["verdict"] == "NO-GO"


def test_exact_required_increase_blocks_go_allows_weak_go() -> None:
    # exact_required disagreements up but no major violation, hit flat -> not GO (downgrade to WEAK-GO)
    d = compute_list_rule_only_ab(_m(0.9571, 0.0227, 0, 16, exact_dis=0), _m(0.9571, 0.0227, 0, 13, exact_dis=1))
    assert d["verdict"] == "WEAK-GO"


# ---- generated-artifact gates (skip if not yet produced) ----

@pytest.mark.skipif(not (AB / "qwen_list_rule_only_run_prompt.md").exists(), reason="ab artifacts not generated")
def test_run_prompt_file_is_leak_safe() -> None:
    p = (AB / "qwen_list_rule_only_run_prompt.md").read_text(encoding="utf-8")
    assert leak_check(p) == []
    assert "exact_required_near_synonym" not in p


@pytest.mark.skipif(not (AB / "FINDING_qwen_list_rule_only_ab_20260603.md").exists(), reason="finding not generated")
def test_finding_states_directional_shadow_boundary() -> None:
    f = (AB / "FINDING_qwen_list_rule_only_ab_20260603.md").read_text(encoding="utf-8")
    assert "directional" in f and "shadow" in f
    assert any(v in f for v in ("GO", "WEAK-GO", "NO-GO"))
