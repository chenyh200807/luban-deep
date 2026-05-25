from __future__ import annotations

import pytest

from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    AssessmentBlueprintUnavailable,
    QuestionCandidate,
    StaticAssessmentQuestionProvider,
    SupabaseAssessmentQuestionProvider,
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


class _StrictTopicSparsePageProvider(SupabaseAssessmentQuestionProvider):
    def _supabase_config(self) -> tuple[str, str]:
        return ("https://example.supabase.co", "test-key")

    def _query(self, base_url: str, api_key: str, filters: dict[str, str]) -> list[dict[str, object]]:
        offset = int(filters.get("offset") or 1000)
        if offset == 2000:
            return [_supabase_row(2000 + index, stem=f"防水施工缝节点补采题 {index}") for index in range(4)]
        rows = [
            _supabase_row(1000 + index, stem=f"主体结构普通题 {index}", node_code="1A413040")
            for index in range(20)
        ]
        rows.extend(_supabase_row(1200 + index, stem=f"防水施工缝节点题 {index}") for index in range(3))
        return rows


def _supabase_row(source_id: int, *, stem: str, node_code: str = "1A413050") -> dict[str, object]:
    return {
        "id": str(source_id),
        "question_stem": stem,
        "question_type": "single_choice",
        "source_type": "REAL_EXAM",
        "node_code": node_code,
        "options": {"A": "正确做法", "B": "错误做法", "C": "干扰项", "D": "干扰项"},
        "correct_answer": "A",
        "difficulty": "medium",
        "source_meta": {},
    }


def test_supabase_provider_backfills_after_strict_topic_filtering() -> None:
    section = get_assessment_blueprint("topic_waterproof_v1").sections[1]
    provider = _StrictTopicSparsePageProvider()

    candidates = provider.get_candidates(
        section,
        limit=4,
        exclude_source_ids=set(),
        selection_seed="",
        avoid_chapters=set(),
    )

    assert len(candidates) == 4
    assert all("防水" in candidate.question_stem for candidate in candidates)
