"""Focused tests for the pure-API arbitration gold panel measurement instrument.

Covers the deterministic logic only (reconciliation routing, agreement math,
reference comparison, honest degradation, safety invariants). No network.
"""
from __future__ import annotations

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
