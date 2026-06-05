"""M18D — Real Retest Proof + AI Council Canonical Claim Gate guards.

Drives the REAL /api/v1/ws full chain (with the M17A LLM-adjudication flag) to produce real
retest proofs, then a non-human AI council dry-run gate. Proves weak->improved improvement is
real, nothing is written to production / canonical truth, and no safety invariant is violated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_learning_brain_real_retest_canonical_gate_m18d as m18d

pytestmark = pytest.mark.skipif(
    not (m18d.M18C / "claim_lifecycle_projection_m18c.jsonl").exists()
    or not (m18d.REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py").exists(),
    reason="M18C claims or ws harness absent",
)


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m18d")
    result = m18d.run_m18d(out_dir=out, target_claims=24)
    return out, result


def test_required_artifacts_exist(run):
    out, _ = run
    for name in (
        "workflow_ledger_m18d.json", "m18c_claim_inventory_m18d.json",
        "retest_plan_generation_m18d.jsonl", "real_ws_retest_events_m18d.jsonl",
        "real_retest_proofs_m18d.jsonl", "ai_council_claim_votes_m18d.jsonl",
        "ai_council_claim_adjudication_m18d.csv", "canonical_write_dryrun_candidates_m18d.jsonl",
        "blocked_or_retest_again_queue_m18d.jsonl", "safety_attack_results_m18d.json",
        "learning_brain_truth_write_guard_m18d.json",
        "FINDING_learning_brain_real_retest_canonical_gate_m18d_20260604.md",
    ):
        assert (out / name).exists(), name


def test_hard_targets_met(run):
    out, result = run
    assert result["real_retest_proof_valid"] >= 10
    assert result["canonical_write_dryrun_candidates"] >= 5
    assert result["all_safe"] is True
    assert result["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert result["verdict"] == "GO"


def test_real_ws_events_carry_runtime_provenance(run):
    out, _ = run
    events = _jsonl(out / "real_ws_retest_events_m18d.jsonl")
    assert len(events) >= 20
    graded = [e for e in events if e["adjudication_present"]]
    assert graded
    for e in graded:
        assert e["legacy_present"] is True               # real construction_grading_result present
        assert e["packet_hash"]                           # M17A packet provenance
        assert e["registry_content_hash"]                 # registry provenance
        assert e["model_used"]                            # model id provenance
        assert e["adjudicator_failclosed"] is False
        assert (e["false_positive"] or 0) == 0


def test_proof_shows_real_weak_to_improved(run):
    out, _ = run
    proofs = [p for p in _jsonl(out / "real_retest_proofs_m18d.jsonl") if p.get("proof_valid")]
    assert len(proofs) >= 10
    for p in proofs:
        assert p["is_real_ws_proof"] is True
        assert p["is_simulation"] is False
        assert p["improved_new_auto_points"]              # improved round added validator-auto
        assert p["weak_round_autocertified_claim"] is False  # weak round did not certify the claim
        assert p["regression"] is False
        assert p["false_positive"] == 0 and p["source_mismatch"] == 0
        assert p["weak_round"]["turn_id"] and p["improved_round"]["turn_id"]


def test_council_is_non_human_review_authority(run):
    out, _ = run
    votes = _jsonl(out / "ai_council_claim_votes_m18d.jsonl")
    assert votes
    for v in votes:
        assert v["is_human"] is False
        assert v["human_reviewed"] is False
        assert v["po_reviewed"] is False
        assert v["teacher_reviewed"] is False
        assert v["review_authority"] == "ai_expert_council_final"
    # GPT5.5 seat must be fail-closed when OpenAI key absent (never fabricated)
    gpt = [v for v in votes if v["seat"] == "gpt55"]
    if gpt:
        assert all(g["vote"] is None and "fail_closed" in g["status"] for g in gpt)


def test_canonical_candidates_are_dryrun_only(run):
    out, _ = run
    cands = _jsonl(out / "canonical_write_dryrun_candidates_m18d.jsonl")
    assert len(cands) >= 5
    for c in cands:
        assert c["disposition"] == "canonical_write_dryrun_candidate"
        assert c["canonical_truth_written"] is False
        assert c["production_write_performed"] is False
        assert c["promoted_to_canonical_mastery"] is False
        assert c["human_reviewed"] is False and c["teacher_reviewed"] is False and c["po_reviewed"] is False
        assert c["review_authority"] == "ai_expert_council_final"
        assert c["evidence_refs"]
        assert c["real_retest_proof"]["improved_turn"]    # backed by a real WS turn


def test_safety_attacks_all_zero(run):
    out, _ = run
    a = _j(out / "safety_attack_results_m18d.json")
    assert a["all_safe"] is True
    for k in ("simulated_retest_as_real", "shadow_promoted_to_mastery", "unsupported_claim_promoted",
              "regression_promoted", "cross_user_leak", "subject_leak", "teacher_only_leak",
              "weak_round_autocertified_any", "false_positive_total", "source_mismatch_total"):
        assert a[k] == 0
    assert a["all_proofs_from_real_ws"] is True


def test_truth_write_guard(run):
    out, _ = run
    g = _j(out / "learning_brain_truth_write_guard_m18d.json")
    assert g["production_write_count"] == 0
    assert g["canonical_truth_written"] is False
    assert g["any_canonical_write"] is False
    assert g["any_production_write"] is False
    assert g["any_mastery_promoted"] is False
    assert g["any_human_or_teacher_field_true"] is False
    assert g["grading_runtime_touched"] is False
    assert g["new_db_schema"] is False
    assert g["second_memory_authority"] is False
    assert g["personalization_context_pack_unique_contract"] is True
    assert g["prescription_authority"] == "training_intent"


def test_finding_answers_fourteen_questions(run):
    out, _ = run
    finding = (out / "FINDING_learning_brain_real_retest_canonical_gate_m18d_20260604.md").read_text("utf-8")
    for idx in range(1, 15):
        assert f"{idx}." in finding
    assert "ai_expert_council_final" in finding
    assert "canonical" in finding
