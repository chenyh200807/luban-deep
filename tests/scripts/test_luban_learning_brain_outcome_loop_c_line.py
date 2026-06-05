"""Hermetic guards for C-LB1 Learning Brain Outcome Loop.

The loop turns shadow grading results into evidence -> claim -> PersonalizationContextPack
-> study card -> retest plan -> simulated outcome proof. It must never write production
learner truth, never promote shadow evidence to canonical mastery, never build a second
personalization authority, and must keep the full chain explainable + retestable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_learning_brain_outcome_loop_c_line as c1

pytestmark = pytest.mark.skipif(not c1.FULL100.exists(), reason="full100 graded samples absent")


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("c_line")
    result = c1.run_c_line(out_dir=out, live_models=False, n_examples=20)
    return out, result


def test_required_artifacts_exist(run):
    out, _ = run
    for name in (
        "learning_evidence_events_c1.jsonl", "learner_claim_projection_c1.jsonl",
        "personalization_context_pack_c1.json", "learner_visible_study_cards_c1.md",
        "retest_recommendation_plan_c1.jsonl", "simulated_retest_outcome_proofs_c1.jsonl",
        "claim_lifecycle_audit_c1.json", "redaction_and_visibility_audit_c1.json",
        "learning_loop_failure_modes_c1.md", "learning_brain_readiness_c1.json",
        "FINDING_learning_brain_outcome_loop_c_line_20260604.md",
    ):
        assert (out / name).exists(), name


def test_workflow_ledger_has_six_patterns_with_evidence(run):
    out, _ = run
    ledger = _j(out / "workflow_ledger_c1.json")
    assert set(ledger) == {
        "classify_and_act", "fanout_and_synthesize", "generate_and_filter",
        "tournament", "adversarial_verification", "loop_until_done",
    }
    for spec in ledger.values():
        assert (out / spec["evidence_file"]).exists()


def test_no_live_model_calls_by_default(run):
    out, _ = run
    plan = _j(out / "model_usage_plan_c1.json")
    assert plan["live_calls_performed"] is False
    assert plan["deterministic_loop_is_authority"] is True
    assert all(v == 0 for v in plan["actual_calls"].values())
    assert all(m["is_learning_authority"] is False for m in plan["models"])


def test_gate_counts_meet_c_line_minimums(run):
    out, result = run
    counts = result["counts"]
    assert counts["evidence_events"] >= 20
    assert counts["claims"] >= 20
    assert counts["packs"] >= 10
    assert counts["study_cards"] >= 10
    assert counts["retest_plans"] >= 10
    assert counts["outcome_proofs"] >= 5
    assert counts["negative_controls"] >= 5


def test_verdict_and_invariants(run):
    out, result = run
    readiness = _j(out / "learning_brain_readiness_c1.json")
    assert result["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert result["verdict"] == "GO"
    assert result["invariants_all_pass"] is True
    inv = readiness["invariants"]
    assert inv["shadow_not_promoted_to_mastery"] is True
    assert inv["production_write_zero"] is True
    assert inv["no_second_personalization_authority"] is True
    assert inv["no_improved_without_retest"] is True
    assert readiness["production_write_count"] == 0


def test_no_production_write_anywhere(run):
    out, _ = run
    for ev in _jsonl(out / "learning_evidence_events_c1.jsonl"):
        assert ev["production_write_performed"] is False
    for cl in _jsonl(out / "learner_claim_projection_c1.jsonl"):
        assert cl["production_write_performed"] is False
        assert cl["promoted_to_canonical_mastery"] is False
    for pr in _jsonl(out / "simulated_retest_outcome_proofs_c1.jsonl"):
        assert pr["production_write_performed"] is False
        assert pr["is_canonical_truth"] is False


def test_personalization_pack_is_the_only_contract(run):
    out, _ = run
    pack_doc = _j(out / "personalization_context_pack_c1.json")
    assert pack_doc["contract"] == c1.PERSONALIZATION_CONTRACT
    assert pack_doc["second_authority"] is False
    assert pack_doc["production_write_count"] == 0
    for pack in pack_doc["packs"].values():
        assert pack["contract"] == c1.PERSONALIZATION_CONTRACT
        assert pack["is_second_authority"] is False
        assert pack["canonical_mastery_claims"] == []  # shadow data yields no canonical mastery


def test_build_personalization_context_pack_is_pure_and_bounded():
    claims = [
        {"user_id": "S1", "subject_id": c1.SUBJECT_ID, "claim_id": "a",
         "lifecycle_state": c1.CLAIM_NEEDS_RETEST},
        {"user_id": "S1", "subject_id": c1.SUBJECT_ID, "claim_id": "b",
         "lifecycle_state": c1.CLAIM_READY_RETEST},
        {"user_id": "S2", "subject_id": c1.SUBJECT_ID, "claim_id": "c",
         "lifecycle_state": c1.CLAIM_READY_RETEST},
    ]
    pack = c1.build_personalization_context_pack("S1", claims)
    assert pack["user_id"] == "S1"
    assert pack["needs_retest_count"] == 1
    assert pack["ready_retest_count"] == 1
    assert pack["canonical_mastery_claims"] == []
    assert pack["dry_run"] is True
    assert "c" not in pack["next_focus_claim_ids"]  # S2 claim not leaked into S1 pack
