from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_luban_qwen_fewshot_ab import compute_ab_delta

REPO = Path(__file__).resolve().parents[2]
AB = REPO / "artifacts/luban_consensus_gold/qwen_fewshot_ab_20260603"


def _m(hit, score, unsup, dis, list_dis, exact_viol=0, pen_viol=0, calc_dis=0):
    return {
        "point_hit_agreement": hit, "mean_abs_score_delta": score, "unsupported_positive": unsup,
        "disagreement_count": dis, "list_rule_disagreements": list_dis, "exact_required_disagreements": 0,
        "exact_required_major_violation": exact_viol, "penalty_rule_major_violation": pen_viol,
        "calculation_disagreements": calc_dis, "penalty_rule_disagreements": 0,
    }


def test_ab_delta_computes_correctly() -> None:
    base = _m(0.9571, 0.0227, 0, 16, 16)
    few = _m(0.9509, 0.0404, 1, 16, 14, exact_viol=1)
    d = compute_ab_delta(base, few)
    assert d["delta_hit_agreement"] == -0.0062
    assert d["list_rule_disagreement_delta"] == -2
    assert d["exact_required_major_violation_delta"] == 1


def test_unsupported_positive_triggers_no_go() -> None:
    d = compute_ab_delta(_m(0.96, 0.02, 0, 16, 16), _m(0.97, 0.01, 1, 10, 10))  # everything better but unsup=1
    assert d["verdict"] == "NO-GO"
    assert "unsupported_positive>0" in d["verdict_reasons"]


def test_exact_required_major_violation_triggers_no_go() -> None:
    d = compute_ab_delta(_m(0.96, 0.02, 0, 16, 16), _m(0.97, 0.01, 0, 12, 12, exact_viol=1))
    assert d["verdict"] == "NO-GO"
    assert "exact_required major regression" in d["verdict_reasons"]


def test_list_rule_down_no_regression_is_go() -> None:
    # hit up, score not worse, list_rule down, no regression -> STRONG-GO
    d = compute_ab_delta(_m(0.95, 0.03, 0, 16, 16), _m(0.97, 0.02, 0, 12, 12))
    assert d["verdict"] in ("STRONG-GO", "WEAK-GO")
    # weak-go: hit flat, score within +0.01, list_rule down
    d2 = compute_ab_delta(_m(0.95, 0.03, 0, 16, 16), _m(0.95, 0.035, 0, 14, 14))
    assert d2["verdict"] == "WEAK-GO"


@pytest.mark.skipif(not (AB / "qwen_fewshot_run_prompt.md").exists(), reason="ab artifacts not generated")
def test_fewshot_run_prompt_has_no_gold_human_ledger_or_heldout_caseids() -> None:
    import re

    p = (AB / "qwen_fewshot_run_prompt.md").read_text(encoding="utf-8")
    for forbidden in ("human_hit", "human_score", "ground_truth_ledger", "ledger_point_rows", "consensus_gold_v1"):
        assert forbidden not in p
    # no held-out case ids (target leakage)
    assert not re.search(r"Q\d+-1A\d+|Q\d+-NA", p)


@pytest.mark.skipif(not (AB / "FINDING_qwen_fewshot_ab_20260603.md").exists(), reason="finding not generated")
def test_finding_states_directional_shadow_boundary() -> None:
    f = (AB / "FINDING_qwen_fewshot_ab_20260603.md").read_text(encoding="utf-8")
    assert "directional" in f and "shadow" in f
    assert "NO-GO" in f
