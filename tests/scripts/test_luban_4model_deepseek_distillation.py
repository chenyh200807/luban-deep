from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_luban_4model_deepseek_distillation import (
    ARM_ALIASES,
    _gate,
    build_distillation_examples,
)

REPO = Path(__file__).resolve().parents[2]
D = REPO / "artifacts/luban_consensus_gold/expanded_4model_deepseek_distillation_20260603"


# ---- gate logic (pure unit) ----

def test_gate_strong_go() -> None:
    v, _ = _gate(hit=0.9930, score_delta=0.0054, unsupported=0, exact_major=0, penalty_major=0, parse_failure=0.0)
    assert v == "STRONG-GO"


def test_gate_weak_go() -> None:
    v, r = _gate(hit=0.921, score_delta=0.09, unsupported=0, exact_major=0, penalty_major=0, parse_failure=0.0)
    assert v == "WEAK-GO"


def test_exact_required_major_violation_forces_no_go_even_with_high_hit() -> None:
    # the real DeepSeek case: excellent hit but ONE 踩字 leniency -> NO-GO
    v, r = _gate(hit=0.9930, score_delta=0.0054, unsupported=0, exact_major=1, penalty_major=0, parse_failure=0.0)
    assert v == "NO-GO"
    assert "exact_required_major_violation>0" in r


def test_unsupported_positive_forces_no_go() -> None:
    v, r = _gate(hit=0.99, score_delta=0.0, unsupported=1, exact_major=0, penalty_major=0, parse_failure=0.0)
    assert v == "NO-GO"
    assert "unsupported_positive>0" in r


def test_low_hit_is_no_go() -> None:
    v, _ = _gate(hit=0.85, score_delta=0.0, unsupported=0, exact_major=0, penalty_major=0, parse_failure=0.0)
    assert v == "NO-GO"


# ---- distillation examples are leak-safe ----

def test_distillation_examples_have_no_final_answer_labels() -> None:
    book = [{"conflict_axis": "list_rule"}, {"conflict_axis": "exact_required"}]
    ex = build_distillation_examples(book)
    for e in ex:
        # never asserts a concrete hit/miss gold; uncertainty -> review
        assert e["decision_when_uncertain"] == "high_risk_review"
        assert "gold_hit" not in e and "gold_score" not in e


def test_deepseek_juror_alias_mapping_is_distinct() -> None:
    # the deepseek juror must be a distinct alias so LOO can exclude it
    assert ARM_ALIASES["deepseek_v4_flash_typed_policy_primary"] == "deepseek"
    assert len(set(ARM_ALIASES.values())) == 4


# ---- generated-artifact gates (skip if not produced) ----

@pytest.mark.skipif(not (D / "consensus_coverage_report.json").exists(), reason="artifacts not generated")
def test_gold_tiers_sum_and_no_unsupported_into_gold() -> None:
    c = json.loads((D / "consensus_coverage_report.json").read_text(encoding="utf-8"))
    assert c["full_consensus_gold"] + c["strong_plus_adjudicated_gold"] == c["consensus_gold_total"]
    assert c["full_consensus_gold"] + c["strong_plus_adjudicated_gold"] + c["frontier_policy_queue"] == c["total_points"]
    assert c["unsupported_positive_into_gold"] == 0


@pytest.mark.skipif(not (D / "consensus_gold_expanded.json").exists(), reason="artifacts not generated")
def test_frontier_unresolved_not_in_gold() -> None:
    gold = json.loads((D / "consensus_gold_expanded.json").read_text(encoding="utf-8"))
    gold_keys = {(p["case_id"], p["student_id"], p["point_id"]) for p in gold["points"]}
    fq = list(csv.DictReader((D / "frontier_policy_queue.csv").read_text(encoding="utf-8").splitlines()))
    assert fq, "frontier queue must be non-empty"
    for r in fq:
        assert (r["case_id"], r["student_id"], r["point_id"]) not in gold_keys


@pytest.mark.skipif(not (D / "deepseek_metrics_vs_consensus_gold.json").exists(), reason="artifacts not generated")
def test_deepseek_evaluated_leave_one_out_no_self_leak() -> None:
    m = json.loads((D / "deepseek_metrics_vs_consensus_gold.json").read_text(encoding="utf-8"))
    loo = m["deepseek_v4_flash"]["leave_one_out_unbiased"]
    # the unbiased jury that scores deepseek must NOT contain deepseek itself
    assert "deepseek" not in loo["jury"]
    assert loo["jury"] == "gpt+opus+qwen37"
    # head-to-head must be computed from LOO numbers, not the contaminated gold
    assert m["head_to_head_loo"]["deepseek_hit"] == loo["point_hit_agreement"]


@pytest.mark.skipif(not (D / "typed_policy_casebook.json").exists(), reason="artifacts not generated")
def test_casebook_no_human_or_ledger_leak_and_frontier_not_auto_gradeable() -> None:
    raw = (D / "typed_policy_casebook.json").read_text(encoding="utf-8")
    for forbidden in ("human_hit", "human_score", "ground_truth_ledger", "ledger_point_rows"):
        assert forbidden not in raw
    book = json.loads(raw)
    assert book, "casebook must be non-empty"
    for c in book:
        assert c["final_consensus"] == "needs_policy_review"
        assert c["safe_for_auto_grading"] is False


@pytest.mark.skipif(not (D / "FINDING_4model_consensus_deepseek_distillation_20260603.md").exists(), reason="finding not generated")
def test_finding_states_boundary_and_loo() -> None:
    f = (D / "FINDING_4model_consensus_deepseek_distillation_20260603.md").read_text(encoding="utf-8")
    assert "directional" in f and "shadow" in f
    assert "leave-one-out" in f or "leave_one_out" in f or "LOO" in f
    assert "0.9930" in f or "0.993" in f
