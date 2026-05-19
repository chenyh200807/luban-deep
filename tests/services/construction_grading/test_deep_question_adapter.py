from __future__ import annotations

from deeptutor.services.construction_grading.deep_question_adapter import (
    build_deep_question_grading_result,
)
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.question_followup import normalize_question_followup_context


def test_case_grading_preserves_followup_rag_evidence_for_learning_truth_promotion() -> None:
    question_context = normalize_question_followup_context(
        {
            "question_id": "case_1",
            "question": "某危大工程专项方案应如何组织论证？",
            "question_type": "case",
            "correct_answer": "应组织专家论证，并编制专项施工方案后按规定审批。",
            "grading_keywords": ["专家论证", "专项施工方案", "审批"],
            "node_code": "1A432000",
            "testing_focus": "危险性较大工程专项方案程序",
            "evidence_refs": [
                {
                    "source": "evidence_bundle",
                    "field": "kb_chunks",
                    "content": "危大工程应编制专项施工方案，超过一定规模的应组织专家论证。",
                }
            ],
        }
    )
    assert question_context is not None

    events: list[LearnerStateEvent] = []
    for index in range(2):
        result = build_deep_question_grading_result(
            question_context,
            user_answer="加强管理，落实责任。",
        )
        assert result is not None
        payload = build_learning_evidence_payload(
            grading_result=result,
            turn_id=f"turn-{index}",
        )
        assert payload["rag_evidence_refs"]
        assert "missing_rag_evidence" not in payload["quality"]["evidence_cap_reasons"]
        events.append(
            LearnerStateEvent(
                event_id=f"evt{index}",
                user_id="student_demo",
                source_feature="construction_grading",
                source_id=f"turn-{index}",
                source_bot_id="construction-exam",
                memory_kind="learning_evidence",
                dedupe_key=f"evt{index}",
                created_at=f"2026-05-18T10:0{index}:00+08:00",
                payload_json=payload,
            )
        )

    projection = synthesize_learning_truth(events)

    assert projection["weak_points"]
    assert projection["weak_points"][0]["evidence_level"] == "L1_repeated"
