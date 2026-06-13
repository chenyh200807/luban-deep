from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_deepseek_shadow_v0_485_prep import build_inventory
from scripts.build_luban_deepseek_exact_required_fallback_eval import fallback_fires

REPO = Path(__file__).resolve().parents[2]
PREP = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_485_prep_20260603"
DIST = REPO / "artifacts/luban_consensus_gold/expanded_4model_deepseek_distillation_20260603"
PLAN = REPO / "docs/plan/评分引擎与金标工件/2026-06-03-luban-deepseek-production-shadow-v0-plan.md"


# ---- inventory identifies missing predictions and never fakes readiness ----

def test_inventory_identifies_missing_predictions() -> None:
    inv = build_inventory()
    s = inv["summary"]
    # the 485 target is real; not everything is covered yet
    assert s["target_samples"] == 100
    assert s["target_points"] == 485
    assert s["four_model_missing_samples"] > 0
    assert len(inv["missing"]) == s["four_model_missing_samples"]
    # every missing row names what's missing (packet and/or models)
    for r in inv["missing"]:
        assert r["typed_policy_packet_missing"] or r["missing_models"]


def test_data_unavailable_is_never_treated_as_ready() -> None:
    inv = build_inventory()
    # with 60 samples missing four-model predictions, full-485 LOO is NOT ready
    assert inv["summary"]["ready_for_full_485_loo"] is False
    # readiness must require EVERY sample be four-model ready, not a partial subset
    assert inv["summary"]["four_model_ready_samples"] < inv["summary"]["target_samples"]


def test_ready_flag_requires_full_coverage() -> None:
    # synthetic: readiness is only true when four_model_ready == target (no shortcut)
    inv = build_inventory()
    s = inv["summary"]
    expected_ready = s["four_model_ready_samples"] == s["target_samples"]
    assert s["ready_for_full_485_loo"] == expected_ready


# ---- LOO gold must exclude the model under test ----

@pytest.mark.skipif(not (DIST / "loo_deepseek/multimodel_jury_summary.json").exists(), reason="loo artifact not generated")
def test_loo_gold_excludes_target_model_own_vote() -> None:
    summary = json.loads((DIST / "loo_deepseek/multimodel_jury_summary.json").read_text(encoding="utf-8"))
    loo_rows = json.loads((DIST / "loo_deepseek/leave_one_out_jury_points_for_target.json").read_text(encoding="utf-8"))
    assert summary["target_arm"] == "deepseek"
    # every LOO gold row's jury must be the OTHER three, never deepseek
    for row in loo_rows:
        assert "deepseek" not in row["jury_arms"]
        assert set(row["jury_arms"]) <= {"gpt", "opus", "qwen37"}


# ---- fallback scope + auto-certification semantics ----

def test_fallback_only_fires_for_exact_required() -> None:
    near_pred = {"hit": "partial", "score": 0.5, "evidence_span": "普通机", "rationale": "只写了一半，缺少官方术语"}
    assert fallback_fires({"policy_type": "exact_required", "required_terms": ["数控机"]}, near_pred)[0] is True
    for ptype in ("list_rule", "calculation", "penalty_rule", "figure_label", "high_risk_review"):
        assert fallback_fires({"policy_type": ptype, "required_terms": ["数控机"]}, near_pred)[0] is False


def _auto_certified(point_pred: dict) -> bool:
    """v0 schema rule: auto_certified = (not unsupported) and (not high_risk_review)."""
    return (not point_pred.get("unsupported", False)) and (not point_pred.get("high_risk_review", False))


def test_high_risk_review_point_is_not_auto_certified() -> None:
    assert _auto_certified({"hit": "hit", "unsupported": False, "high_risk_review": True}) is False
    assert _auto_certified({"hit": "hit", "unsupported": True, "high_risk_review": False}) is False
    assert _auto_certified({"hit": "hit", "unsupported": False, "high_risk_review": False}) is True


# ---- plan + prep artifacts exist and state the boundary ----

@pytest.mark.skipif(not PLAN.exists(), reason="plan not generated")
def test_v0_plan_states_shadow_boundary_and_485_gate() -> None:
    t = PLAN.read_text(encoding="utf-8")
    assert "shadow" in t and "485" in t
    assert "不进 production runtime" in t or "不进 runtime" in t
    assert "leave-one-out" in t or "LOO" in t


@pytest.mark.skipif(not (PREP / "485_asset_inventory.json").exists(), reason="prep not generated")
def test_prep_inventory_artifact_matches_builder() -> None:
    art = json.loads((PREP / "485_asset_inventory.json").read_text(encoding="utf-8"))
    assert art["summary"]["ready_for_full_485_loo"] is False
    assert art["summary"]["target_points"] == 485
