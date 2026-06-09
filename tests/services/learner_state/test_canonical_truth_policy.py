from __future__ import annotations

from deeptutor.services.learner_state.canonical_truth_policy import (
    canonical_truth_promotion_decision,
    trusted_adjudication_from_quality,
)


def test_production_non_cohort_requires_broad_trusted_adjudication(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED", "1")
    monkeypatch.setenv("LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_COHORT", "qa_,operator_")
    monkeypatch.delenv("LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_TRUSTED_ADJUDICATION_ENABLED", raising=False)
    monkeypatch.delenv("LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_AI_ADJUDICATION_ENABLED", raising=False)

    decision = canonical_truth_promotion_decision(
        user_id="real_student_1",
        projection={"subject": "construction_exam_learning_truth"},
    )

    assert decision.allowed is False
    assert decision.reason == "production_cohort_required"


def test_broad_ai_jury_requires_confident_resolved_adjudication(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED", "1")
    monkeypatch.setenv("LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_AI_ADJUDICATION_ENABLED", "1")

    low_confidence = canonical_truth_promotion_decision(
        user_id="real_student_1",
        projection={
            "synthesis_run": {
                "trusted_adjudication": {
                    "source": "llm_jury",
                    "confidence": 0.62,
                    "conflict_status": "resolved",
                    "requires_human": False,
                }
            }
        },
    )
    unresolved = canonical_truth_promotion_decision(
        user_id="real_student_1",
        projection={
            "synthesis_run": {
                "trusted_adjudication": {
                    "source": "llm_jury",
                    "confidence": 0.95,
                    "conflict_status": "unresolved",
                    "requires_human": False,
                }
            }
        },
    )
    resolved = canonical_truth_promotion_decision(
        user_id="real_student_1",
        projection={
            "synthesis_run": {
                "trusted_adjudication": {
                    "source": "llm_jury",
                    "confidence": 0.95,
                    "conflict_status": "resolved",
                    "requires_human": False,
                }
            }
        },
    )

    assert low_confidence.allowed is False
    assert low_confidence.reason == "ai_adjudication_confidence_too_low"
    assert unresolved.allowed is False
    assert unresolved.reason == "ai_adjudication_conflict_unresolved"
    assert resolved.allowed is True
    assert resolved.reason == "trusted_adjudication_authorized"


def test_legacy_teacher_final_quality_maps_to_trusted_adjudication() -> None:
    trusted = trusted_adjudication_from_quality(
        {
            "teacher_reviewed": True,
            "teacher_review_authority": "trusted_adjudication",
        },
    )

    assert trusted["source"] == "teacher_final"
    assert trusted["confidence"] == 1.0
    assert trusted["conflict_status"] == "resolved"
