from __future__ import annotations

from deeptutor.services.learner_state.mastery_estimator import estimate_mastery


def _attempt(
    *,
    correct: bool,
    difficulty: str = "medium",
    question_id: str = "q1",
    created_at: str = "2026-05-21T10:00:00+08:00",
    evidence_source: str = "construction_grading",
    progress_countable: bool = True,
) -> dict:
    return {
        "question_id": question_id,
        "difficulty": difficulty,
        "created_at": created_at,
        "score_awarded": 1 if correct else 0,
        "max_score": 1,
        "evidence_source": evidence_source,
        "quality": {"progress_countable": progress_countable},
    }


def test_one_easy_correct_attempt_has_low_confidence_and_cap() -> None:
    result = estimate_mastery(
        attempts=[_attempt(correct=True, difficulty="easy")],
        legacy_score=100,
    )

    assert result["score"] <= 60
    assert result["confidence"] < 0.4
    assert result["status"] == "insufficient_evidence"
    assert result["sample_count"] == 1


def test_mixed_difficulty_repeated_correct_promotes_stable_mastery() -> None:
    result = estimate_mastery(
        attempts=[
            _attempt(correct=True, difficulty="easy", question_id="q1"),
            _attempt(correct=True, difficulty="medium", question_id="q2"),
            _attempt(correct=True, difficulty="hard", question_id="q3"),
            _attempt(correct=True, difficulty="medium", question_id="q4"),
            _attempt(correct=True, difficulty="hard", question_id="q5"),
        ],
        legacy_score=80,
    )

    assert result["score"] >= 75
    assert result["confidence"] >= 0.65
    assert result["status"] in {"emerging", "stable"}
    assert result["sample_count"] == 5
    assert result["coverage_ratio"] == 1
    assert result["last_practiced_at"] == "2026-05-21T10:00:00+08:00"


def test_conversation_synthesis_does_not_promote_stable_mastery() -> None:
    result = estimate_mastery(
        attempts=[
            _attempt(
                correct=True,
                difficulty="hard",
                question_id=f"conv-{index}",
                evidence_source="conversation_synthesis",
                progress_countable=False,
            )
            for index in range(6)
        ],
        legacy_score=95,
    )

    assert result["sample_count"] == 0
    assert result["confidence"] < 0.4
    assert result["status"] == "insufficient_evidence"


def test_no_attempts_caps_legacy_score_as_insufficient_evidence() -> None:
    result = estimate_mastery(attempts=[], legacy_score=80)

    assert result["score"] <= 60
    assert result["confidence"] < 0.4
    assert result["status"] == "insufficient_evidence"


def test_conflicting_evidence_needs_confirmation_or_remains_unstable() -> None:
    result = estimate_mastery(
        attempts=[
            _attempt(correct=True, difficulty="medium", question_id="q1"),
            _attempt(correct=False, difficulty="medium", question_id="q2"),
            _attempt(correct=True, difficulty="hard", question_id="q3"),
            _attempt(correct=False, difficulty="hard", question_id="q4"),
        ],
        legacy_score=90,
    )

    assert result["status"] == "needs_confirmation" or result["status"] != "stable"
    assert result["confidence"] < 0.7 or result["status"] == "needs_confirmation"


def test_repeated_wrong_attempts_do_not_become_stable_mastery() -> None:
    result = estimate_mastery(
        attempts=[
            _attempt(correct=False, difficulty="easy", question_id="q1"),
            _attempt(correct=False, difficulty="medium", question_id="q2"),
            _attempt(correct=False, difficulty="hard", question_id="q3"),
            _attempt(correct=False, difficulty="medium", question_id="q4"),
            _attempt(correct=False, difficulty="hard", question_id="q5"),
        ],
        legacy_score=70,
    )

    assert result["confidence"] >= 0.65
    assert result["score"] < 60
    assert result["status"] != "stable"
