"""Focused tests for the pure-API arbitration gold panel measurement instrument.

Covers the deterministic logic only (reconciliation routing, agreement math,
reference comparison, honest degradation, safety invariants). No network.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from scripts import run_luban_arbitration_gold_panel as panel


def _const_judge(verdict: str) -> panel.JudgeFn:
    def judge(point, answer, anchor):  # noqa: ANN001
        return {"verdict": verdict, "evidence_span": answer[:5], "confidence": 0.9}
    return judge


def _abstain_judge() -> panel.JudgeFn:
    def judge(point, answer, anchor):  # noqa: ANN001
        return {"verdict": panel.ABSTAIN, "abstain_reason": "transport"}
    return judge


POINT = {"point_id": "P1", "max_score": 5, "criterion": "x"}
ANCHOR = {"question_id": "Q", "stem": "s", "total_score": 5}


# ---------------------------------------------------------------- reconciliation


def test_unanimous_route_skips_arbiter():
    fns = {"a": _const_judge("hit"), "b": _const_judge("hit"), "c": _const_judge("hit"),
           "arb": _const_judge("miss")}
    rec = panel.reconcile_point(POINT, "answer", ANCHOR, fns, ["a", "b", "c"], "arb")
    assert rec["route"] == "unanimous"
    assert rec["consensus_verdict"] == "hit"
    assert rec["panel_unanimous"] is True
    assert rec["arbiter_vote"] is None  # arbiter never consulted on unanimous


def test_majority_confirmed_by_arbiter():
    fns = {"a": _const_judge("hit"), "b": _const_judge("hit"), "c": _const_judge("partial"),
           "arb": _const_judge("hit")}
    rec = panel.reconcile_point(POINT, "answer", ANCHOR, fns, ["a", "b", "c"], "arb")
    assert rec["route"] == "majority_review_confirmed"
    assert rec["consensus_verdict"] == "hit"
    assert rec["panel_unanimous"] is False


def test_majority_unconfirmed_keeps_majority_but_flags():
    fns = {"a": _const_judge("hit"), "b": _const_judge("hit"), "c": _const_judge("miss"),
           "arb": _const_judge("partial")}
    rec = panel.reconcile_point(POINT, "answer", ANCHOR, fns, ["a", "b", "c"], "arb")
    assert rec["route"] == "majority_review_unconfirmed"
    assert rec["consensus_verdict"] == "hit"  # majority still wins; arbiter dissent recorded


def test_three_way_split_resolved_by_arbiter():
    fns = {"a": _const_judge("hit"), "b": _const_judge("partial"), "c": _const_judge("miss"),
           "arb": _const_judge("partial")}
    rec = panel.reconcile_point(POINT, "answer", ANCHOR, fns, ["a", "b", "c"], "arb")
    assert rec["route"] == "arbitration"
    assert rec["consensus_verdict"] == "partial"


def test_split_with_abstaining_arbiter_stays_unadjudicated():
    fns = {"a": _const_judge("hit"), "b": _const_judge("partial"), "c": _const_judge("miss"),
           "arb": _abstain_judge()}
    rec = panel.reconcile_point(POINT, "answer", ANCHOR, fns, ["a", "b", "c"], "arb")
    assert rec["route"] == "arbitration_unresolved"
    assert rec["consensus_verdict"] == panel.UNADJUDICATED  # never fabricates a verdict


def test_panel_abstention_is_never_an_accept():
    # two abstain, one hit -> top_count=1, size=3, no majority -> arbiter decides
    fns = {"a": _abstain_judge(), "b": _abstain_judge(), "c": _const_judge("hit"),
           "arb": _const_judge("miss")}
    rec = panel.reconcile_point(POINT, "answer", ANCHOR, fns, ["a", "b", "c"], "arb")
    assert rec["route"] == "arbitration"
    assert rec["consensus_verdict"] == "miss"
    assert rec["panel_unanimous"] is False


# ---------------------------------------------------------------- agreement math


def test_pairwise_agreement_full():
    assert panel._pairwise_agreement(["hit", "hit", "hit"]) == 1.0


def test_pairwise_agreement_partial():
    # pairs: (hit,hit)=agree (hit,miss)=no (hit,miss)=no -> 1/3
    assert panel._pairwise_agreement(["hit", "hit", "miss"]) == pytest.approx(0.3333, abs=1e-3)


def test_pairwise_agreement_excludes_abstain():
    assert panel._pairwise_agreement(["hit", "hit", panel.ABSTAIN]) == 1.0
    assert panel._pairwise_agreement(["hit", panel.ABSTAIN, panel.ABSTAIN]) is None


def test_reference_label_lookup():
    ledger = {"point_hits": [{"point_id": "P1", "hit": "hit"}, {"point_id": "P2", "hit": "miss"}]}
    assert panel._reference_label(ledger, "P1") == "hit"
    assert panel._reference_label(ledger, "P2") == "miss"
    assert panel._reference_label(ledger, "P9") is None


# ---------------------------------------------------------------- fleiss kappa


def test_fleiss_kappa_perfect_agreement_is_one():
    # every item: all 3 raters pick "hit" (constant rater count) -> kappa 1.0
    items = [Counter({"hit": 3}) for _ in range(5)]
    assert panel._fleiss_kappa(items) == 1.0


def test_fleiss_kappa_below_chance_can_go_negative():
    # maximal within-item disagreement across a balanced category mix -> kappa<=0
    items = [Counter({"hit": 1, "partial": 1, "miss": 1}) for _ in range(6)]
    kappa = panel._fleiss_kappa(items)
    assert kappa is not None and kappa <= 0.0


def test_slice_fleiss_kappa_excludes_abstention_rows():
    panel_ids = ["a", "b", "c"]
    rows = [
        {"blind_votes": {"a": "hit", "b": "hit", "c": "hit"}},        # scored
        {"blind_votes": {"a": "hit", "b": panel.ABSTAIN, "c": "hit"}},  # excluded (abstain)
        {"blind_votes": {"a": "miss", "b": "miss", "c": "miss"}},     # scored
    ]
    block = panel._slice_fleiss_kappa(rows, panel_ids)
    assert block["scored_item_count"] == 2
    assert block["excluded_for_abstention"] == 1
    assert block["rater_count"] == 3
    # two unanimous items -> kappa 1.0 -> quality claim allowed
    assert block["fleiss_kappa"] == 1.0
    assert block["quality_claim_allowed"] is True
    assert block["label_authority"] == "ai_arbitration_panel_candidate"


def test_slice_fleiss_kappa_low_agreement_blocks_quality_claim():
    panel_ids = ["a", "b", "c"]
    rows = [{"blind_votes": {"a": "hit", "b": "partial", "c": "miss"}} for _ in range(6)]
    block = panel._slice_fleiss_kappa(rows, panel_ids)
    assert block["fleiss_kappa"] is not None and block["fleiss_kappa"] < 0.6
    assert block["quality_claim_allowed"] is False
    assert block["label_authority"] == "ai_council_directional"


def test_shape_report_exposes_kappa_trust_gate(tmp_path: Path):
    rc = panel.main([
        "--cases", "Q2-1A436000-罚则",
        "--tier", "shape",
        "--max-students", "3",
        "--output", str(tmp_path / "out.json"),
    ])
    assert rc == 0
    report = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    # top-level trust gate is always present and consistent with the aggregate block
    assert "quality_claim_allowed" in report
    assert report["gold_label_authority"] == report["label_authority"]
    kappa_block = report["aggregate"]["panel_fleiss_kappa"]
    assert kappa_block["threshold"] == 0.6
    assert report["quality_claim_allowed"] == kappa_block["quality_claim_allowed"]


# ---------------------------------------------------------------- degradation


def test_build_live_judges_degrades_on_missing_keys():
    # empty env: every provider missing -> panel cannot reach 3 live models
    fns, _stats, roster = panel.build_live_judges(env={})
    assert roster["blind_panel_live"] == []
    assert len(roster["blind_panel_degraded"]) == len(panel.PANEL_SPECS)
    assert roster["arbiter"] is None
    assert fns == {}


def test_build_live_judges_partial_keys_named_honestly():
    fns, _stats, roster = panel.build_live_judges(env={"DEEPSEEK_API_KEY": "k"})
    # deepseek panel member + reasoner arbiter live; qwen + glm degraded
    assert "deepseek-v4-flash" in roster["blind_panel_live"]
    assert roster["arbiter"] == "deepseek-reasoner"
    degraded_ids = {d["model_id"] for d in roster["blind_panel_degraded"]}
    assert degraded_ids == {"qwen-max", "glm-4-plus"}


def test_deepseek_chat_not_a_panel_member():
    # deepseek-chat is aliased to v4-flash backend; it must not double-count.
    assert "deepseek-chat" not in panel.PANEL_SPECS


# ---------------------------------------------------------------- end-to-end shape


def test_shape_tier_run_produces_safe_report(tmp_path: Path):
    rc = panel.main([
        "--cases", "Q3-1A433000",
        "--tier", "shape",
        "--max-students", "2",
        "--output", str(tmp_path / "out.json"),
    ])
    assert rc == 0
    report = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert report["classification"] == "candidate_only"
    assert report["review_status"] == "review_only"
    assert report["production_write_count"] == 0
    assert report["safety"] == {
        "production_db_write": False,
        "canonical_truth_write": False,
        "published_registry_write": False,
        "remote_write": False,
    }
    agg = report["aggregate"]
    assert agg["per_point_count"] == 20  # Q3 has 10 points x 2 students
    assert 0.0 <= agg["panel_unanimity_rate"] <= 1.0
    assert agg["reference_checkable_count"] <= agg["per_point_count"]
    assert (tmp_path / "out_rows.json").exists() is False  # rows file uses with_name
    assert (tmp_path / "panel_validation_rows.json").exists()


def test_live_tier_requires_double_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(panel.LIVE_ENV_FLAG, raising=False)
    rc = panel.main([
        "--cases", "Q3-1A433000",
        "--tier", "live",  # no --live, no env flag
        "--output", str(tmp_path / "out.json"),
    ])
    assert rc == 2  # refuses live without double opt-in


def test_unknown_case_rejected(tmp_path: Path):
    rc = panel.main([
        "--cases", "Q-DOES-NOT-EXIST",
        "--tier", "shape",
        "--output", str(tmp_path / "out.json"),
    ])
    assert rc == 2
