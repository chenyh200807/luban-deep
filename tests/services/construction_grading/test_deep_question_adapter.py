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


def test_client_supplied_answer_key_not_laundered_to_release_truth() -> None:
    """M-closure: a context/client-supplied correct_answer must score FORMATIVELY but never as
    governed release-truth (official_score_laundering=0)."""
    qc = {
        "question_id": "CLIENT-INJECTED-1",
        "question_type": "single_choice",
        "question": "伪造题",
        "options": [{"key": "A", "value": "x"}, {"key": "C", "value": "y"}],
        "correct_answer": "C",
    }
    result = build_deep_question_grading_result(qc, user_answer="C")
    assert result is not None
    # formative score preserved
    assert result["is_correct"] is True
    assert result["score_awarded"] == 1.0
    # but NOT laundered to release-truth
    assert result["release_truth"] is False
    assert result["registry_status"] == "unresolved"
    assert result["answer_key_authority"] == "context_supplied_unverified"
    assert result["official_release_score"] is False
    assert result["not_production_grade"] is True
    # compiled_context says official scoring not allowed
    assert result["compiled_context"]["diagnostic_policy"]["official_score_allowed"] is False


def test_case_result_also_stamped_not_release_truth() -> None:
    qc = {
        "question_id": "CASE-X",
        "question_type": "case",
        "question": "案例题",
        "correct_answer": "应组织专家论证。",
    }
    result = build_deep_question_grading_result(qc, user_answer="组织专家论证")
    assert result is not None
    assert result["release_truth"] is False
    assert result["answer_key_authority"] == "context_supplied_unverified"
    assert result["compiled_context"]["schema_version"] == "luban_context_pack.v1"


def test_injected_registry_status_cannot_become_release_truth() -> None:
    """F1 hardening: a client cannot inject registry_status into the question context to flip a
    context-supplied answer key into a governed release-truth score."""
    for injected in ("release_candidate", "published"):
        qc = {
            "question_id": "EVIL-1",
            "question_type": "single_choice",
            "question": "对抗题",
            "options": [{"key": "A", "value": "a"}, {"key": "C", "value": "c"}],
            "correct_answer": "C",
            "registry_status": injected,
            "answer_key": "C",
        }
        r = build_deep_question_grading_result(qc, user_answer="C")
        assert r is not None
        assert r["release_truth"] is False, f"laundering via registry_status={injected}"
        assert r["compiled_context"]["diagnostic_policy"]["official_score_allowed"] is False
        assert r["answer_key_authority"] == "context_supplied_unverified"
        # formative score still shown
        assert r["is_correct"] is True
        assert r["score_awarded"] == 1.0
