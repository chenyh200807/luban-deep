from __future__ import annotations

import pytest

from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
)


def _candidate(index: int, *, stem: str | None = None, source_id: str | None = None) -> QuestionCandidate:
    return QuestionCandidate(
        source_question_id=source_id or f"waterproof_{index}",
        question_stem=stem or f"防水工程第 {index} 题，关于卷材搭接和节点处理的正确做法是？",
        question_type="single_choice" if index % 3 else "multi_choice",
        chapter="防水工程",
        options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
        answer="A" if index % 3 else "AB",
        difficulty="medium",
        source_type="REAL_EXAM",
        node_code="1A414010",
        source_meta={"topic": "防水", "semantic_signature": f"waterproof_sig_{index}"},
    )


def test_p0a_blueprint_delivers_exact_signed_off_count() -> None:
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider([_candidate(index) for index in range(30)]),
    )

    payload = service.create_session(
        user_id="student_demo",
        count=12,
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=("waterproof",),
    )

    assert payload["assessment_type"] == "topic_diagnostic"
    assert payload["subject_id"] == "construction_exam"
    assert payload["topic_ids"] == ["waterproof"]
    assert payload["blueprint_version"] == "topic_waterproof_v1"
    assert payload["requested_count"] == 12
    assert payload["delivered_count"] == 12
    assert payload["scored_count"] == 12
    assert payload["profile_count"] == 0
    assert all(question["scored"] for question in payload["questions"])
    assert "answer" not in payload["questions"][0]
    assert "answer" in payload["session_questions"][0]


def test_p0a_blueprint_fails_closed_when_topic_candidates_short() -> None:
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider([_candidate(index) for index in range(6)]),
    )

    with pytest.raises(AssessmentBlueprintUnavailable):
        service.create_session(
            user_id="student_demo",
            count=12,
            assessment_type="topic_diagnostic",
            subject_id="construction_exam",
            topic_ids=("waterproof",),
        )


def test_p0a_does_not_silently_use_generic_topic_candidates() -> None:
    generic = [
        QuestionCandidate(
            source_question_id=f"generic_{index}",
            question_stem=f"主体结构第 {index} 题，关于混凝土浇筑的正确做法是？",
            question_type="single_choice",
            chapter="主体结构",
            options=(("A", "正确做法"), ("B", "错误做法"), ("C", "干扰项"), ("D", "干扰项")),
            answer="A",
            difficulty="medium",
            source_type="REAL_EXAM",
            node_code="1A413000",
            source_meta={"topic": "主体结构"},
        )
        for index in range(30)
    ]
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider(generic),
    )

    with pytest.raises(AssessmentBlueprintUnavailable):
        service.create_session(
            user_id="student_demo",
            count=12,
            assessment_type="topic_diagnostic",
            subject_id="construction_exam",
            topic_ids=("waterproof",),
        )


def test_p0a_dedupes_semantic_signature_when_available() -> None:
    candidates = [_candidate(index, source_id=f"same_semantic_{index}") for index in range(20)]
    candidates[1] = _candidate(1, source_id="same_semantic_duplicate")
    candidates[1].source_meta["semantic_signature"] = candidates[0].source_meta["semantic_signature"]
    service = AssessmentBlueprintService(
        blueprint=get_assessment_blueprint("topic_waterproof_v1"),
        provider=StaticAssessmentQuestionProvider(candidates),
    )

    payload = service.create_session(
        user_id="student_demo",
        count=12,
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=("waterproof",),
    )

    signatures = [
        question["provenance"]["source_meta"].get("semantic_signature")
        for question in payload["session_questions"]
    ]
    assert len(signatures) == len(set(signatures))
