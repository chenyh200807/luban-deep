"""M17B/M18 guards: council aggregator + opus judge unit logic, and emitted artifact safety."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/runtime_llm_ai_council_scaleout_m17b_m18_20260604"

_spec = importlib.util.spec_from_file_location(
    "scaleout_m17b", REPO / "scripts" / "run_luban_runtime_llm_adjudication_scaleout_m17b_m18.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _j(n):
    return json.loads((OUT / n).read_text("utf-8"))


def _jl(n):
    return [json.loads(l) for l in (OUT / n).read_text("utf-8").splitlines() if l.strip()]


# ---- unit: aggregator + opus judge (no live call) ----

def test_council_never_upgrades_source_gap():
    agg = sc._aggregate_council({"a": {"decision": "external"}, "b": {"decision": "keep"}})
    assert agg["council_replaced_source"] is False
    assert agg["source_gap_upgraded"] is False
    assert agg["human_reviewed"] is False and agg["po_reviewed"] is False
    assert agg["reviewer_type"] == "ai_expert_council"


def test_aggregator_priority_validator_rule_fix_wins():
    agg = sc._aggregate_council({"a": {"decision": "validator_rule_fix"}, "b": {"decision": "keep"}, "c": {"decision": "keep"}})
    assert agg["ai_expert_council_final"] == "validator_rule_fix"


def test_aggregator_drop_requires_two_seats():
    one = sc._aggregate_council({"a": {"decision": "drop"}, "b": {"decision": "keep"}, "c": {"decision": "keep"}})
    two = sc._aggregate_council({"a": {"decision": "drop"}, "b": {"decision": "drop"}, "c": {"decision": "keep"}})
    assert one["ai_expert_council_final"] == "keep"   # single drop not enough
    assert two["ai_expert_council_final"] == "drop"


def test_opus_judge_is_non_human_and_pattern_genuine():
    v = sc._opus_judge({"llm_disposition": "accept", "deterministic_auto": False,
                        "downgrade_reason": "deterministic_matcher_rejected_llm_accept"})
    assert v["reviewer"] == "opus48_in_session"
    assert v["decision"] == "keep"  # validator floor upheld
    v2 = sc._opus_judge({"llm_disposition": "accept", "deterministic_auto": True,
                         "downgrade_reason": "evidence_span_not_in_student_answer"})
    assert v2["decision"] == "validator_rule_fix"


# ---- artifact safety (after the scaleout run) ----

def test_safety_invariants_all_zero():
    m = _j("release_readiness_matrix.json")
    assert m["false_positive"] == 0
    assert m["bad_certified"] == 0
    assert m["source_mismatch"] == 0
    assert m["official_answer_as_textbook"] == 0
    assert m["model_vote_as_source"] == 0
    assert m["council_replaced_source"] == 0
    assert m["list_partial_auto"] == 0
    assert m["legacy_equal_rate"] == 1.0
    assert m["production_write_count"] == 0
    assert m["production_default_enabled"] is False


def test_council_votes_are_ai_not_human():
    for v in _jl("ai_council_votes.jsonl"):
        assert v["reviewer_type"] == "ai_expert_council"
        assert v["human_reviewed"] is False
        assert v["po_reviewed"] is False
        assert v["council_replaced_source"] is False
        assert v["ai_expert_council_final"] in sc.COUNCIL_ACTIONS


def test_artifact_feedback_stops_at_candidate():
    for c in _jl("artifact_feedback_candidates.jsonl"):
        assert c["touches_release_registry"] is False
        assert c["source_gap_upgraded"] is False
        assert c["reviewer_type"] == "ai_expert_council"


def test_learning_brain_no_overreach():
    a = _j("learning_brain_event_quality_audit.json")
    assert a["mastery_raised_any"] is False
    assert a["writeback_any"] is False
    assert a["canonical_truth_written"] == 0
    assert a["shadow_promoted_to_mastery"] == 0
    assert a["pcp_is_second_memory"] is False


def test_qwen_fallback_really_ran():
    fb = _j("qwen_vs_deepseek_fallback_metrics.json")
    assert fb["forced_fallback_attempts"] >= 1
    assert fb["qwen_fallback_live_success"] >= 1  # real Qwen fallback, not a unit mock


def test_verdict_and_production_no_go():
    g = _j("go_no_go_m17b_m18.json")
    assert g["m17b_m18_verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert g["production_v1"] == "NO-GO"
    assert g["production_default_enable"] == "NO-GO"
    assert g["production_default"] == "OFF"
    m = g["metrics"]
    assert m["false_positive"] == 0 and m["source_mismatch"] == 0 and m["legacy_equal_rate"] == 1.0
