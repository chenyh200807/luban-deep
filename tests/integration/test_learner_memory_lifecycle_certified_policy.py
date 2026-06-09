from __future__ import annotations

from deeptutor.services.construction_grading.deep_question_adapter import build_deep_question_grading_result
from deeptutor.services.construction_grading.learning_evidence import build_learning_evidence_payload
from deeptutor.services.learner_state.canonical_truth_policy import canonical_truth_promotion_decision
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent


def test_certified_policy_evidence_reaches_stable_claim_and_canonical_gate(monkeypatch) -> None:
    grading_result = build_deep_question_grading_result(
        {
            "question_id": "certified-case-1",
            "question_type": "case",
            "question": "说明专项施工方案专家论证要求。",
            "correct_answer": "应组织专家论证，并按规定审批专项施工方案。",
            "answer_key": "应组织专家论证，并按规定审批专项施工方案。",
            "grading_keywords": ["专家论证", "专项施工方案"],
            "node_code": "1A432000",
            "testing_focus": "专项施工方案专家论证程序",
            "evidence_refs": [
                {
                    "source": "evidence_bundle",
                    "field": "kb_chunks",
                    "content": "超过一定规模的危险性较大的分部分项工程专项施工方案应组织专家论证。",
                }
            ],
        },
        user_answer="仅加强管理。",
        governed_registry_status="published",
        certified_grading_policy={
            "status": "published",
            "policy_id": "policy-case-v1",
            "rubric_hash": "sha256:rubric-v1",
            "grader_version": "rubric-grader-v1",
            "confidence": 0.94,
            "conflict_status": "resolved",
        },
    )
    assert grading_result is not None

    payload = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id="turn-certified-1",
        session_id="session-certified-1",
        governed_certified_authority=True,
    )

    assert payload["memory_lifecycle_stage"] == "stable_learner_claim"
    assert payload["quality"]["evidence_level"] == "L2_confirmed"
    assert payload["quality"]["trusted_adjudication"]["source"] == "certified_grading_policy"
    assert payload["quality"]["trusted_adjudication"]["requires_human"] is False

    event = LearnerStateEvent(
        event_id="evt-certified-1",
        user_id="real_student_1",
        source_feature="construction_grading",
        source_id="turn-certified-1",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="evt-certified-1",
        created_at="2026-06-09T16:00:00+08:00",
        payload_json=payload,
    )
    projection = synthesize_learning_truth([event], synthesis_status="persisted_enqueued")

    weak = projection["weak_points"][0]
    assert weak["memory_lifecycle_stage"] == "stable_learner_claim"
    assert weak["evidence_level"] == "L2_confirmed"
    trusted = projection["synthesis_run"]["trusted_adjudication"]
    assert trusted["source"] == "certified_grading_policy"
    assert trusted["confidence"] == 0.94
    assert trusted["conflict_status"] == "resolved"
    assert trusted["requires_human"] is False

    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED", "1")
    monkeypatch.setenv("LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_TRUSTED_ADJUDICATION_ENABLED", "1")

    decision = canonical_truth_promotion_decision(user_id="real_student_1", projection=projection)

    assert decision.allowed is True
    assert decision.reason == "trusted_adjudication_authorized"
    assert decision.adjudication_source == "certified_grading_policy"
