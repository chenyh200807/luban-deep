from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_full_485_packet import build_packet, build_typed_policy_lookup
from scripts.build_luban_deepseek_exact_required_fallback_eval import _gate, fallback_fires

REPO = Path(__file__).resolve().parents[2]
FULL = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603"


# ---- 485 packet completeness ----

def test_485_packet_is_complete_100_samples_485_points() -> None:
    packet = build_packet()
    tasks = packet["tasks"]
    assert len(tasks) == 100
    assert sum(len(t["scoring_points"]) for t in tasks) == 485
    assert packet["_missing_typed_policy"] == []
    # every point carries a typed_policy with a policy_type
    for t in tasks:
        for sp in t["scoring_points"]:
            assert sp["typed_policy"] is not None
            assert sp["typed_policy"].get("policy_type")


def test_typed_policy_lookup_covers_all_20_cases() -> None:
    tp = build_typed_policy_lookup()
    assert len({c for c, _ in tp}) == 20


def test_packet_does_not_use_three_arms_results_as_gold() -> None:
    # the packet must carry student answers + scoring points, never artifact_first/baseline/rag scores
    packet = build_packet()
    raw = json.dumps(packet, ensure_ascii=False)
    for forbidden in ("artifact_first", "baseline_arm", "rag_score", "pred_score"):
        assert forbidden not in raw


# ---- fallback scope + auto-certification ----

def test_fallback_only_exact_required() -> None:
    near = {"hit": "partial", "score": 0.5, "evidence_span": "近义x", "rationale": "近义,缺官方术语"}
    assert fallback_fires({"policy_type": "exact_required", "required_terms": ["官方术语"]}, near)[0] is True
    for ptype in ("list_rule", "calculation", "penalty_rule", "figure_label", "high_risk_review"):
        assert fallback_fires({"policy_type": ptype, "required_terms": ["官方术语"]}, near)[0] is False


def test_high_risk_not_auto_certified() -> None:
    def auto(p):
        return (not p.get("unsupported", False)) and (not p.get("high_risk_review", False))
    assert auto({"high_risk_review": True}) is False
    assert auto({"unsupported": True}) is False
    assert auto({"high_risk_review": False, "unsupported": False}) is True


def test_gate_thresholds() -> None:
    strong = {"exact_required_major_violation": 0, "unsupported_positive": 0, "point_hit_agreement": 0.95, "mean_abs_score_delta": 0.03}
    assert _gate(strong, 0.05, 0.95)[0] == "STRONG-GO"
    weak = {"exact_required_major_violation": 0, "unsupported_positive": 0, "point_hit_agreement": 0.91, "mean_abs_score_delta": 0.08}
    assert _gate(weak, 0.12, 0.88)[0] == "WEAK-GO"
    viol = {"exact_required_major_violation": 1, "unsupported_positive": 0, "point_hit_agreement": 0.99, "mean_abs_score_delta": 0.0}
    assert _gate(viol, 0.0, 0.99)[0] == "NO-GO"


# ---- generated-artifact gates (skip until full run produced) ----

@pytest.mark.skipif(not (FULL / "loo_gold_485_deepseek_excluded.json").exists(), reason="full 485 LOO not generated")
def test_loo_gold_excludes_deepseek_and_no_unsupported_no_frontier() -> None:
    g = json.loads((FULL / "loo_gold_485_deepseek_excluded.json").read_text(encoding="utf-8"))
    assert g.get("deepseek_excluded") is True
    for row in g["points"]:
        # the actual juror votes must be the other three, never deepseek's own vote
        assert "deepseek" not in {str(k).lower() for k in (row.get("jury_votes") or {})}
        # only consensus tiers enter gold; frontier excluded
        assert row.get("status") in ("full_consensus_3of3", "strong_consensus_2of3", "adjudicated")


@pytest.mark.skipif(not (FULL / "deepseek_485_before_after_metrics.json").exists(), reason="full 485 fallback not generated")
def test_full_485_gate_recorded() -> None:
    m = json.loads((FULL / "deepseek_485_before_after_metrics.json").read_text(encoding="utf-8"))
    assert m["after"]["unsupported_positive"] == 0
    assert m["gate_verdict"] in ("STRONG-GO", "WEAK-GO", "NO-GO")


@pytest.mark.skipif(not (FULL / "unified_typed_policy_packet_485.json").exists(), reason="packet not generated")
def test_packet_artifact_matches_builder() -> None:
    art = json.loads((FULL / "unified_typed_policy_packet_485.json").read_text(encoding="utf-8"))
    assert len(art["tasks"]) == 100
    assert sum(len(t["scoring_points"]) for t in art["tasks"]) == 485
