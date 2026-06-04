"""Integration guard for C-LB1 claim lifecycle + outcome proof safety.

Proves: claims never regress, shadow evidence never becomes canonical mastery,
duplicate grading writes are idempotent, and a retest that did not happen can never
be written as "improved".
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
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("c_line_lifecycle")
    c1.run_c_line(out_dir=d, live_models=False)
    return d


def test_claims_never_regress(out):
    audit = _j(out / "claim_lifecycle_audit_c1.json")
    assert audit["any_regression"] is False
    for t in audit["transitions"]:
        assert t["regressed"] is False
        assert t["valid"] is True


def test_shadow_evidence_never_becomes_canonical_mastery(out):
    audit = _j(out / "claim_lifecycle_audit_c1.json")
    assert audit["any_shadow_promoted_to_mastery"] is False
    claims = _jsonl(out / "learner_claim_projection_c1.jsonl")
    assert claims
    assert all(c["promoted_to_canonical_mastery"] is False for c in claims)
    # full100 is entirely ai_draft_shadow -> every claim must carry the shadow flag
    assert all(c["is_shadow"] is True for c in claims)


def test_needs_and_ready_retest_claims_are_distinguished(out):
    claims = _jsonl(out / "learner_claim_projection_c1.jsonl")
    states = {c["lifecycle_state"] for c in claims}
    assert c1.CLAIM_NEEDS_RETEST in states or c1.CLAIM_READY_RETEST in states
    # ready_retest claims must be source-backed; needs_retest carries high_risk/unsupported
    for c in claims:
        if c["lifecycle_state"] == c1.CLAIM_READY_RETEST:
            assert c["source_backed_point_ids"]


def test_outcome_proof_only_improves_after_a_real_retest(out):
    proofs = _jsonl(out / "simulated_retest_outcome_proofs_c1.jsonl")
    assert len(proofs) >= 5
    for p in proofs:
        assert p["is_simulation"] is True
        if p["claim_after"] == "improving":
            assert p["retest_happened"] is True and p["retest_passed"] is True
        assert p["transition_valid"] is True


def test_retest_absent_improved_is_blocked(out):
    controls = _jsonl(out / "negative_controls_c1.jsonl")
    absent = next(c for c in controls if c["control"] == "retest_absent_improved")
    assert absent["wrote_improved"] is False
    assert absent["blocked"] is True


def test_duplicate_grading_write_is_idempotent(out):
    controls = _jsonl(out / "negative_controls_c1.jsonl")
    dup = next(c for c in controls if c["control"] == "duplicate_grading_write")
    assert dup["idempotent"] is True
    assert dup["second_write_performed"] is False
