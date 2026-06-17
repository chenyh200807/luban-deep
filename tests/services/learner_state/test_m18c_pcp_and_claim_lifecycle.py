"""Unit tests for M18C PersonalizationContextPack builder + claim lifecycle authority.

Pure-function guards (no DB, no production write): the PCP builder is bounded and
user/subject-isolated, never invents canonical mastery, and next-action prescriptions are
built on the canonical ``training_intent`` authority (not a second authority).
"""
from __future__ import annotations

import scripts.run_luban_learning_brain_dream_cycle_m18c as m18c
from deeptutor.services.learner_state.training_intent import (
    build_learning_training_intent,
    prioritize_training_intents,
)


def _claim(user, subj, state, refs, support):
    return {
        "claim_id": f"{user}:{subj}:{state}", "user_id": user, "subject_id": subj,
        "question_id": "Q", "lifecycle_state": state, "evidence_refs": refs,
        "supporting_event_ids": support, "auto_point_ids": [], "review_point_ids": [],
        "is_shadow": True, "promoted_to_canonical_mastery": False,
    }


def test_pcp_is_user_and_subject_isolated():
    claims = [
        _claim("S1", "construction_case", m18c.NEEDS_RETEST, ["Q::P1"], ["e1"]),
        _claim("S2", "construction_case", m18c.CLAIM_CANDIDATE, ["Q::P2"], ["e2"]),
    ]
    pack = m18c.build_personalization_context_pack("S1", "construction_case", claims, [])
    assert pack["user_id"] == "S1"
    assert pack["evidence_refs"] == ["Q::P1"]          # only S1's refs
    assert pack["supporting_event_ids"] == ["e1"]      # S2's e2 never leaks in
    assert pack["needs_retest_count"] == 1
    assert pack["claim_candidate_count"] == 0


def test_pcp_never_invents_canonical_mastery():
    claims = [_claim("S1", "construction_case", m18c.CLAIM_CANDIDATE, ["Q::P1"], ["e1"])]
    pack = m18c.build_personalization_context_pack("S1", "construction_case", claims, [])
    assert pack["canonical_mastery_claims"] == []
    assert pack["production_write_performed"] is False
    assert pack["canonical_truth_written"] is False
    assert pack["is_second_personalization_authority"] is False
    assert pack["prescription_authority"] == "training_intent"


def test_pcp_is_pure_and_does_not_mutate_inputs():
    claims = [_claim("S1", "construction_case", m18c.NEEDS_RETEST, ["Q::P1"], ["e1"])]
    import copy
    before = copy.deepcopy(claims)
    m18c.build_personalization_context_pack("S1", "construction_case", claims, [])
    assert claims == before


def test_training_intent_is_prescription_authority():
    intent = build_learning_training_intent(
        user_id="qa_x", concept_id="q::Q", evidence_refs=["e1", "e2"],
        question_count=3, source="m18c_test")
    assert intent.get("training_intent_id")
    assert intent.get("prescription_steps")          # the prescription lives in training_intent
    # next_best_action is only a ranking view over training_intent
    ranked = prioritize_training_intents([intent], max_active=1)
    assert ranked and ranked[0]["status"] in {"active", "queued"}
    assert "priority" in ranked[0]


def test_classify_buckets_are_within_taxonomy():
    ev = {"auto_point_ids": ["P1"], "review_point_ids": [], "validator_downgraded": False,
          "provenance": {"kind": "validated_preview"}}
    assert m18c._classify(ev) in m18c.CLASSIFY_BUCKETS
    ev_shadow = {"auto_point_ids": ["P1"], "review_point_ids": ["P2"], "validator_downgraded": False,
                 "provenance": {"kind": "ai_draft_shadow"}}
    assert m18c._classify(ev_shadow) == "shadow_only"
    ev_blocked = {"auto_point_ids": [], "review_point_ids": [], "validator_downgraded": False,
                  "provenance": {"kind": "validated_preview"}}
    assert m18c._classify(ev_blocked) == "blocked_from_claim"
