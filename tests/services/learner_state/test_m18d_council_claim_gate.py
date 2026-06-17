"""Unit tests for M18D AI-council claim-gate protocol (pure, non-human, fail-closed).

The council is a non-human review authority over a REAL retest proof: available seats apply
a deterministic role protocol, unavailable providers fail closed (never fabricated), and the
verdict never writes human/teacher/PO truth nor replaces source authority.
"""
from __future__ import annotations

import scripts.run_luban_learning_brain_real_retest_canonical_gate_m18d as m18d


def _proof(valid=True, regression=False, fp=0, new_auto=("P1",), weak_on_claim=False,
           evidence=("Q::P1",), laundering=False):
    return {
        "proof_valid": valid, "regression": regression, "false_positive": fp,
        "improved_new_auto_points": list(new_auto), "weak_round_autocertified_claim": weak_on_claim,
        "evidence_refs": list(evidence), "source_laundering": laundering,
    }


def test_unavailable_gpt55_seat_fails_closed_without_fabrication():
    vote = m18d._council_vote("gpt55", "claim_promotion_reviewer", _proof(), available=False)
    assert vote["available"] is False
    assert vote["vote"] is None
    assert "fail_closed" in vote["status"]
    assert vote["is_human"] is False


def test_opus_is_in_session_protocol_judge_not_human():
    vote = m18d._council_vote("opus48", "protocol_judge_adversarial_auditor", _proof(), available=False)
    assert vote["kind"] == "in_session_self_judge"
    assert vote["vote"] == "accept"          # valid proof + no regression + fp=0
    assert vote["is_human"] is False
    assert vote["human_reviewed"] is False


def test_evidence_prosecutor_rejects_weak_only_proof():
    # a proof whose weak round already auto-certified the claim is not an improvement
    vote = m18d._council_vote("deepseek_v4", "strict_evidence_prosecutor",
                              _proof(weak_on_claim=True), available=True)
    assert vote["vote"] == "needs_more_retest"


def test_evidence_prosecutor_accepts_genuine_improvement():
    vote = m18d._council_vote("deepseek_v4", "strict_evidence_prosecutor", _proof(), available=True)
    assert vote["vote"] == "accept"
    assert vote["kind"] == "deterministic_role_protocol_over_real_proof"


def test_semantics_reviewer_rejects_laundered_source():
    vote = m18d._council_vote("qwen37", "chinese_domain_semantics_reviewer",
                              _proof(laundering=True), available=True)
    assert vote["vote"] == "needs_more_retest"


def test_all_seats_never_write_human_or_teacher_fields():
    for seat, role, _env in m18d.COUNCIL_SEATS:
        v = m18d._council_vote(seat, role, _proof(), available=True)
        assert v["human_reviewed"] is False
        assert v["po_reviewed"] is False
        assert v["teacher_reviewed"] is False
        assert v["review_authority"] == "ai_expert_council_final"
