"""Guards for M14E AI-council final + real retest canonical pilot.

The AI council is a NON-HUMAN review authority: it must never claim to be human, never
replace source authority, and never let a simulated/fake retest count as a real proof.
Real retests must carry runtime provenance or be marked BLOCKED. Nothing is written to
production. Runs deterministically (--live-council 0) for reproducibility.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_learning_brain_ai_council_retest_canonical_pilot_m14e as m14e

pytestmark = pytest.mark.skipif(
    not (m14e.M13E_DIR / "canonical_claim_candidate_proposals_m13e.jsonl").exists(),
    reason="M13E claim proposals absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _run_m14e():
    subprocess.run([sys.executable,
                    str(m14e.REPO / "scripts/run_luban_learning_brain_ai_council_retest_canonical_pilot_m14e.py"),
                    "--live-council", "0"], cwd=m14e.REPO, check=True, capture_output=True)
    return m14e.OUT_DIR


def test_all_three_m13e_proposals_are_read():
    proposals = _jsonl(m14e.OUT_DIR / "m13e_claim_proposal_inventory_m14e.jsonl")
    assert len(proposals) == 3


def test_ai_council_never_claims_to_be_human():
    votes = _jsonl(m14e.OUT_DIR / "ai_expert_council_review_votes_m14e.jsonl")
    assert votes
    for v in votes:
        assert v["is_human"] is False
    adj = _j(m14e.OUT_DIR / "ai_expert_council_adjudication_m14e.json")
    assert adj["any_human_claimed"] is False
    for f in adj["finals"]:
        assert f["human_reviewed"] is False
        assert f["teacher_reviewed"] is False
        assert f["review_authority"] == "ai_expert_council_final"


def test_council_never_replaces_source_authority():
    adj = _j(m14e.OUT_DIR / "ai_expert_council_adjudication_m14e.json")
    assert adj["any_source_replaced"] is False
    for f in adj["finals"]:
        assert f["source_authority_replaced"] is False
        # a source-weak point can never be council-accepted to canonical
        if not f["source_backed"]:
            assert f["council_final"] != "accept"


def test_simulated_retest_never_becomes_real_proof():
    proofs = _jsonl(m14e.OUT_DIR / "retest_proof_verification_m14e.jsonl")
    for pr in proofs:
        assert pr["is_simulation"] is False
        if pr["real_retest_proof_valid"]:
            assert pr["runtime_provenance"] is True  # real proof needs runtime provenance


def test_real_retest_requires_runtime_provenance_or_is_blocked():
    events = _jsonl(m14e.OUT_DIR / "real_retest_runtime_events_m14e.jsonl")
    assert events
    for e in events:
        assert e["status"] in ("REAL_RUNTIME_GRADED", "BLOCKED_REAL_RETEST_ENTRY")
        if e["status"] == "BLOCKED_REAL_RETEST_ENTRY":
            assert e.get("reason")  # must record why it was blocked, not fabricate


def test_canonical_candidate_requires_council_final_and_real_retest():
    dryrun = _jsonl(m14e.OUT_DIR / "canonical_write_dryrun_candidates_m14e.jsonl")
    for d in dryrun:
        if d["outcome"] == "canonical_write_candidate":
            assert d["council_final"] == "accept"
            assert d["real_retest_proof_valid"] is True


def test_all_safety_attacks_zero():
    audit = _j(m14e.OUT_DIR / "adversarial_canonical_safety_audit_m14e.json")
    assert audit["all_attacks_zero"] is True
    c = audit["checks"]
    for k in ("ai_claimed_human", "council_replaced_source_authority", "simulated_retest_as_real_proof",
              "fake_manual_retest_passed", "cross_user_leak", "subject_leak", "teacher_only_leak",
              "regression_promoted", "source_laundering", "human_reviewed_written"):
        assert c[k] == 0


def test_production_never_written_and_canonical_truth_false():
    guard = _j(m14e.OUT_DIR / "production_write_guard_m14e.json")
    assert guard["production_write_count"] == 0
    assert guard["canonical_truth_written"] is False
    assert guard["human_reviewed_written"] == 0
    dryrun = _jsonl(m14e.OUT_DIR / "canonical_write_dryrun_candidates_m14e.jsonl")
    for d in dryrun:
        assert d["dry_run"] is True
        assert d["production_write_performed"] is False


def test_personalization_context_pack_remains_only_contract():
    audit = _j(m14e.OUT_DIR / "adversarial_canonical_safety_audit_m14e.json")
    assert audit["personalization_contract_is_only"] is True
    delta = _jsonl(m14e.OUT_DIR / "personalization_context_pack_delta_m14e.jsonl")
    for d in delta:
        assert d["uses_contract"] == "PersonalizationContextPack"
        assert d["second_authority_created"] is False
        assert d["production_personalization_written"] is False
        assert "how_to_prove_next" in d  # learner-visible: how to prove progress next


def test_verdict_is_weak_go_or_go_not_no_go():
    m = _j(m14e.OUT_DIR / "m14e_manifest.json")
    assert m["verdict"] in ("GO", "WEAK-GO")  # NO-GO would mean a safety breach
