"""M32 Task 5: PersonalizationContextPack is the SINGLE personalization input — it carries
the claim, evidence refs, the active training intent (prescription authority), and one
product-shaped NextBestAction (action_type / target / materials / success_measure /
why_this_now / evidence_refs). A learner with no evidence gets a calibration/diagnostic
action, not fabricated personalization."""
from __future__ import annotations

from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.personalization_context import (
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.training_intent import build_learning_training_intent

CONCEPT = "waterproof_term"


def _intent() -> dict:
    return build_learning_training_intent(
        user_id="qa_m32_waterproof",
        concept_id=CONCEPT,
        concept_label="防水施工规范术语",
        error_code="near_synonym_not_accepted",
        error_label="近义替代原文术语",
        evidence_refs=["attempt_m32_001"],
        training_mode="mixed_review",
    )


def _learning_brain() -> dict:
    return {
        "compiled_objects": [
            {
                "object_id": "claim_waterproof_1",
                "object_type": "error_claim",
                "claim_status": "observed",
                "concept_id": CONCEPT,
                "label": "防水 exact_required 术语近义替代",
                "confidence": 0.6,
                "evidence_refs": ["attempt_m32_001"],
            }
        ]
    }


def _repeated_learning_brain() -> dict:
    return {
        "compiled_objects": [
            {
                "object_id": "claim_waterproof_repeat",
                "object_type": "error_claim",
                "claim_status": "repeated",
                "concept_id": CONCEPT,
                "label": "防水 exact_required 术语近义替代",
                "confidence": 0.82,
                "evidence_refs": ["attempt_m32_001", "attempt_m32_002"],
                "occurrence_timeline": [
                    {
                        "event_id": "attempt_m32_001",
                        "observed_at": "2026-06-07T10:00:00+08:00",
                        "question_id": "waterproof_case_001",
                        "turn_id": "turn_m32_001",
                    },
                    {
                        "event_id": "attempt_m32_002",
                        "observed_at": "2026-06-08T10:00:00+08:00",
                        "question_id": "waterproof_case_002",
                        "turn_id": "turn_m32_002",
                    },
                ],
                "decay_state": "active",
            }
        ]
    }


def _improving_learning_brain() -> dict:
    return {
        "compiled_objects": [
            {
                "object_id": "claim_waterproof_repeat",
                "object_type": "error_claim",
                "claim_status": "stale",
                "concept_id": CONCEPT,
                "label": "防水 exact_required 术语近义替代",
                "confidence": 0.82,
                "evidence_refs": ["attempt_m32_001", "attempt_m32_002"],
                "occurrence_timeline": [
                    {
                        "event_id": "attempt_m32_001",
                        "observed_at": "2026-06-07T10:00:00+08:00",
                        "question_id": "waterproof_case_001",
                        "turn_id": "turn_m32_001",
                    },
                    {
                        "event_id": "attempt_m32_002",
                        "observed_at": "2026-06-08T10:00:00+08:00",
                        "question_id": "waterproof_case_002",
                        "turn_id": "turn_m32_002",
                    },
                ],
                "decay_state": "improving",
            }
        ],
        "improvement_signals": [
            {
                "concept_id": CONCEPT,
                "error_code": "near_synonym_not_accepted",
                "event_id": "retest_m32_001",
                "observed_at": "2026-06-08T12:00:00+08:00",
            }
        ],
    }


def test_next_best_action_has_product_shape() -> None:
    action = build_next_best_actions(user_id="qa_m32_waterproof", training_intents=[_intent()], max_actions=1)[0]
    for field in ("action_type", "target", "materials", "success_measure", "why_this_now", "evidence_refs"):
        assert field in action, f"missing {field}"
    assert action["action_type"] == "retest_or_targeted_practice"  # full intent requires revalidation
    assert action["target"]
    assert isinstance(action["materials"], list) and action["materials"]
    assert action["success_measure"]
    assert action["evidence_refs"] == ["attempt_m32_001"]


def test_pcp_is_single_personalization_input() -> None:
    pcp = build_personalization_context_pack(
        user_id="qa_m32_waterproof",
        learning_brain=_learning_brain(),
        active_training_intent=_intent(),
    )
    # one claim, with its evidence
    assert pcp["top_claims"] and pcp["top_claims"][0]["concept_id"] == CONCEPT
    assert pcp["top_claims"][0]["evidence_refs"] == ["attempt_m32_001"]
    # the active prescription + exactly one next action candidate derived from it
    assert pcp["active_training_intent"]["concept_id"] == CONCEPT
    assert len(pcp["next_best_action_candidates"]) == 1
    nba = pcp["next_best_action_candidates"][0]
    assert nba["action_type"] == "retest_or_targeted_practice"
    # authority: PCP is a read-only view; prescription authority stays training_intent
    assert pcp["authority"]["prescription"] == "training_intent"
    assert nba["prescription_authority"] == "training_intent"


def test_no_evidence_learner_gets_calibration_not_fake_personalization() -> None:
    # No training intent, no claims -> no fabricated recommendation.
    pcp = build_personalization_context_pack(
        user_id="new_learner", learning_brain={"compiled_objects": []}, active_training_intent=None
    )
    assert pcp["top_claims"] == []
    assert pcp["next_best_action_candidates"] == []
    # A bare discovery intent (no evidence) yields a diagnostic action, not personalization.
    discovery = build_learning_training_intent(user_id="new_learner", concept_id="", training_mode="mixed_review")
    action = build_next_best_actions(user_id="new_learner", training_intents=[discovery], max_actions=1)
    if action:
        assert action[0]["action_type"] == "diagnostic_probe"


def test_pcp_projects_repeated_error_trend_into_feedback_guidance() -> None:
    pcp = build_personalization_context_pack(
        user_id="qa_m32_waterproof",
        learning_brain=_repeated_learning_brain(),
        active_training_intent=None,
    )

    claim = pcp["top_claims"][0]
    assert claim["occurrence_count"] == 2
    assert claim["trend_state"] == "repeated_active"
    assert claim["occurrence_timeline"][1]["question_id"] == "waterproof_case_002"

    guidance = pcp["feedback_guidance"]
    assert guidance["authority"] == "PersonalizationContextPack_read_only"
    assert guidance["grading_tone"] == "advanced_repeat_mistake"
    assert guidance["explanation_depth"] == "reference_prior_pattern"
    assert "下一题" in guidance["next_action_hint"]
    assert "canonical_truth_written" not in pcp


def test_pcp_projects_real_retest_improvement_into_followup_guidance() -> None:
    pcp = build_personalization_context_pack(
        user_id="qa_m32_waterproof",
        learning_brain=_improving_learning_brain(),
        active_training_intent=_intent(),
    )

    assert pcp["recent_improvement_signals"][0]["event_id"] == "retest_m32_001"
    guidance = pcp["feedback_guidance"]
    assert guidance["authority"] == "PersonalizationContextPack_read_only"
    assert guidance["grading_tone"] == "retest_improvement_followup"
    assert guidance["explanation_depth"] == "compare_retest_delta"
    assert "复测" in guidance["next_action_hint"]
