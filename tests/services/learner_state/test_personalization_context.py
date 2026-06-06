from __future__ import annotations

from deeptutor.services.learner_state.personalization_context import (
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.training_intent import build_learning_training_intent


def test_personalization_context_pack_is_read_only_view_over_claims_and_training_intent() -> None:
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A432000",
        concept_label="工程招标投标与合同管理",
        error_code="M06",
        error_label="多选漏选",
        evidence_refs=["evt_claim_1", "evt_claim_2"],
        training_mode="case_repair",
    )
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "claim_confirmed",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A432000",
                    "label": "工程招标投标与合同管理：多选漏选",
                    "supporting_event_ids": ["evt_claim_1", "evt_claim_2"],
                    "confidence": 0.82,
                },
                {
                    "object_id": "claim_stale",
                    "object_type": "error",
                    "claim_status": "stale",
                    "label": "旧的薄弱点",
                    "evidence_refs": ["evt_old"],
                    "confidence": 0.51,
                },
            ]
        },
        active_training_intent=intent,
        recent_events=[{"event_id": "evt_recent"}],
    )

    assert pack["schema_version"] == 1
    assert pack["source"] == "PersonalizationContextPack"
    assert pack["authority"]["claims"] == "learning_synthesis"
    assert pack["authority"]["prescription"] == "training_intent"
    assert pack["top_claims"][0]["claim_id"] == "claim_confirmed"
    assert pack["top_claims"][0]["evidence_refs"] == ["evt_claim_1", "evt_claim_2"]
    assert pack["recent_evidence_refs"] == ["evt_recent", "evt_claim_1", "evt_claim_2"]
    assert pack["active_training_intent"]["training_intent_id"] == intent["training_intent_id"]
    assert pack["next_best_action_candidates"][0]["training_intent_id"] == intent["training_intent_id"]
    assert pack["next_best_action_candidates"][0]["prescription_authority"] == "training_intent"
    assert pack["gaps"] == [{"claim_id": "claim_stale", "reason": "claim_stale"}]


def test_personalization_context_treats_string_evidence_ref_as_single_ref() -> None:
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "claim_string_ref",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A432000",
                    "label": "防水工程薄弱",
                    "evidence_refs": "evt_string",
                }
            ]
        },
    )

    assert pack["top_claims"][0]["evidence_refs"] == ["evt_string"]
