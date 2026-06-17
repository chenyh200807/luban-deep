from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_list_rule_semantic_model_bakeoff import ARM_PROMPTS, build_eval_set

REPO = Path(__file__).resolve().parents[2]
O = REPO / "artifacts/luban_consensus_gold/list_rule_semantic_model_bakeoff_20260603"


# ---- protocol prompts keep exact_required strict + no deterministic patch ----

def test_arm_prompts_keep_exact_required_strict() -> None:
    for name, p in ARM_PROMPTS.items():
        assert "exact_required" in p
        # both arms must protect exact_required from list_rule loosening
        assert "逐字" in p
        assert "不被 list_rule 语义宽松污染" in p or "不走此语义放宽" in p


def test_arm_prompts_require_evidence_span_and_items() -> None:
    for p in ARM_PROMPTS.values():
        assert "evidence_span" in p
        assert "high_risk_review" in p  # uncertain -> review, not hard credit


# ---- eval set integrity ----

def test_build_eval_set_only_list_rule_points() -> None:
    rows = build_eval_set()
    assert rows
    # every row is a list_rule point with required fields
    for r in rows[:50]:
        assert "list_rule_items" in r and "loo_gold" in r and "current_deepseek_pred" in r
        assert r["layer"] in ("list_rule_frontier", "list_rule_all_consensus")


# ---- generated-artifact gates (skip until model arms produced) ----

@pytest.mark.skipif(not (O / "score_delta_decomposition.json").exists(), reason="decomposition not generated")
def test_score_delta_decomposition_shows_high_max_inflation() -> None:
    d = json.loads((O / "score_delta_decomposition.json").read_text(encoding="utf-8"))["by_max_score_bucket"]
    # raw delta grows with max_score bucket (structural inflation)
    assert d["4+"]["raw_score_delta"] > d["0-1"]["raw_score_delta"]
    # normalized stays a diagnostic, not a gate replacement
    assert "normalized_per_point_delta" in d["4+"]


@pytest.mark.skipif(not (O / "arm_metrics.json").exists(), reason="arm metrics not generated")
def test_arm_metrics_baseline_and_adopted_arm_keep_exact_required_clean() -> None:
    m = json.loads((O / "arm_metrics.json").read_text(encoding="utf-8"))
    # baseline and the adopted semantic-protocol arm must keep 踩字 clean + no unsupported
    for arm in ("baseline", "list_rule_semantic_protocol"):
        g = m[arm]["overall_485_gate"]
        assert g["exact_major"] == 0, f"{arm} exact_required regression"
        assert g["unsupported"] == 0, f"{arm} unsupported positive"
    # invariant: ANY arm that breaks exact_required MUST be gated NO-GO (踩字 zero-tolerance)
    for arm, r in m.items():
        g = r["overall_485_gate"]
        assert g["gate_verdict"] in ("STRONG-GO", "WEAK-GO", "NO-GO")
        if g["exact_major"] > 0 or g["unsupported"] > 0:
            assert g["gate_verdict"] == "NO-GO", f"{arm} broke a hard gate but was not NO-GO"


@pytest.mark.skipif(not (O / "arm_metrics.json").exists(), reason="arm metrics not generated")
def test_semantic_protocol_lifts_auto_hit_without_breaking_taqi() -> None:
    m = json.loads((O / "arm_metrics.json").read_text(encoding="utf-8"))
    base = m["baseline"]["overall_485_gate"]
    sem = m["list_rule_semantic_protocol"]["overall_485_gate"]
    # the central finding: model-side semantic protocol raises auto_hit and keeps exact_major 0
    assert sem["auto_hit"] >= base["auto_hit"]
    assert sem["exact_major"] == 0


@pytest.mark.skipif(not (O / "frontier_review_metrics.json").exists(), reason="frontier review not generated")
def test_frontier_reviewer_trigger_rate_and_no_regression() -> None:
    f = json.loads((O / "frontier_review_metrics.json").read_text(encoding="utf-8"))
    c3 = f["config3_flash_plus_frontier_reviewer"]
    assert c3["exact_major"] == 0 and c3["unsupported"] == 0
    assert f["reviewer_trigger_rate_of_gold"] <= 0.10  # <=10% trigger
    # leakage caveat must be present (reviewer in jury)
    assert "LEAKAGE_CAVEAT" in f["reviewer_vs_gold_on_ingold_17"]
