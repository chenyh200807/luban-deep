"""Guards for M13E Learning Brain canonical claim gate.

Only teacher-reviewed or real-retest-proof evidence may form a canonical claim proposal,
nothing is written to production, shadow events never become canonical mastery, and a
simulated retest never produces a canonical 'improved' claim.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_learning_brain_canonical_claim_gate_m13e as m13e

pytestmark = pytest.mark.skipif(
    not (m13e.C_DIR / "learner_claim_projection_c1.jsonl").exists(),
    reason="C-LB1 preview supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _run_m13e():
    subprocess.run([sys.executable, str(m13e.REPO / "scripts/run_luban_learning_brain_canonical_claim_gate_m13e.py")],
                   cwd=m13e.REPO, check=True, capture_output=True)
    return m13e.OUT_DIR


def test_every_preview_event_has_final_disposition():
    events = _jsonl(m13e.OUT_DIR / "preview_event_inventory_m13e.jsonl")
    assert events
    for e in events:
        assert e["disposition"] in m13e.DISPOSITIONS


def test_shadow_only_never_promoted_to_canonical_mastery():
    events = _jsonl(m13e.OUT_DIR / "preview_event_inventory_m13e.jsonl")
    shadow = [e for e in events if e["disposition"] == "shadow_only_blocked"]
    assert shadow
    for e in shadow:
        assert e.get("promoted_to_canonical_mastery") is False


def test_only_teacher_reviewed_forms_a_claim_proposal():
    proposals = _jsonl(m13e.OUT_DIR / "canonical_claim_candidate_proposals_m13e.jsonl")
    for p in proposals:
        assert p["gate_basis"] in ("teacher_reviewed", "retest_proof")
        assert p["mastery_granted"] is True


def test_qa_simulated_proposals_block_canonical_write_until_real_signoff():
    proposals = _jsonl(m13e.OUT_DIR / "canonical_claim_candidate_proposals_m13e.jsonl")
    for p in proposals:
        if p.get("requires_real_teacher_signoff"):
            assert p["canonical_write_allowed_now"] is False


def test_improvement_proposal_requires_retest_proof_ready():
    dm = _j(m13e.OUT_DIR / "claim_gate_decision_matrix_m13e.json")
    # improvement proposals must equal retest_proof_ready dispositions (0 when all retests simulated)
    assert dm["retest_proof_gate_holds"] is True
    assert dm["improvement_proposals"] == dm["disposition_counts"].get("retest_proof_ready", 0)


def test_simulated_retest_never_canonical_improved():
    audit = _j(m13e.OUT_DIR / "adversarial_claim_safety_audit_m13e.json")
    c = audit["checks"]
    assert c["simulated_retest_marked_canonical"] == 0
    assert c["improvement_proposal_from_simulation"] == 0


def test_no_cross_user_subject_or_teacher_only_leak():
    audit = _j(m13e.OUT_DIR / "adversarial_claim_safety_audit_m13e.json")
    c = audit["checks"]
    assert c["cross_user_leak"] == 0
    assert c["subject_leak"] == 0
    assert c["teacher_only_leak"] == 0
    # independent: no proposal carries a teacher-only / answer-key field
    proposals = _jsonl(m13e.OUT_DIR / "canonical_claim_candidate_proposals_m13e.jsonl")
    for p in proposals:
        for k in m13e.TEACHER_ONLY_FIELDS:
            assert k not in p


def test_duplicate_replay_is_idempotent():
    audit = _j(m13e.OUT_DIR / "adversarial_claim_safety_audit_m13e.json")
    assert audit["checks"]["duplicate_replay_idempotent"] is True


def test_personalization_context_pack_is_only_contract():
    pcp = _j(m13e.OUT_DIR / "adversarial_claim_safety_audit_m13e.json")
    assert pcp["personalization_contract_is_only"] is True
    cands = _jsonl(m13e.OUT_DIR / "personalization_context_pack_candidates_m13e.jsonl")
    for c in cands:
        assert c["second_authority_created"] is False
        assert c["production_personalization_written"] is False


def test_no_production_write_and_no_canonical_truth_written():
    audit = _j(m13e.OUT_DIR / "adversarial_claim_safety_audit_m13e.json")
    assert audit["production_write_count"] == 0
    assert audit["canonical_truth_written"] is False
    dryrun = _jsonl(m13e.OUT_DIR / "canonical_write_dryrun_m13e.jsonl")
    for d in dryrun:
        assert d["dry_run"] is True
        assert d["canonical_truth_written"] is False
        assert d["production_write_performed"] is False


def test_verdict_is_weak_go_or_go_with_safety():
    dm = _j(m13e.OUT_DIR / "claim_gate_decision_matrix_m13e.json")
    assert dm["verdict"] in ("GO", "WEAK-GO")  # NO-GO would mean a safety breach
