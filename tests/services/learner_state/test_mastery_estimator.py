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


# ─── Batch B Task 5: recency-aware confidence + forgetting risk ───────────


def test_old_positive_evidence_has_forgetting_risk() -> None:
    """Plan's literal failing test: a single correct attempt from ~50 days
    ago must mark forgetting_risk > 0.5 and needs_revalidation=True. The
    level can be 'unstable' or 'needs_revalidation' — both honest options."""
    estimate = estimate_mastery(
        attempts=[
            {"score_ratio": 1.0, "created_at": "2026-04-01T00:00:00+08:00"},
        ],
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert estimate["level"] in {"unstable", "needs_revalidation"}
    assert estimate["forgetting_risk"] > 0.5
    assert estimate["needs_revalidation"] is True


def test_recent_revalidation_lowers_forgetting_risk() -> None:
    """Plan's literal failing test: a recent successful revalidation
    (within decay half-life) drops forgetting_risk < 0.4 and lifts
    level into improving/stable."""
    estimate = estimate_mastery(
        attempts=[
            {"score_ratio": 0.0, "created_at": "2026-05-01T00:00:00+08:00"},
            {"score_ratio": 1.0, "created_at": "2026-05-22T00:00:00+08:00"},
        ],
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert estimate["level"] in {"improving", "stable"}
    assert estimate["forgetting_risk"] < 0.4


def test_code_application_decays_faster_than_transfer() -> None:
    """ability_dimension picks a decay profile. code_application has the
    shortest half-life (10d) and transfer the longest (28d); given the
    same 14-day stale positive, code_application must produce a higher
    forgetting_risk than transfer."""
    base_attempts = [
        {"score_ratio": 1.0, "created_at": "2026-05-08T00:00:00+08:00"}
    ]
    now = "2026-05-22T00:00:00+08:00"

    code_estimate = estimate_mastery(
        attempts=base_attempts, now_iso=now, ability_dimension="code_application"
    )
    transfer_estimate = estimate_mastery(
        attempts=base_attempts, now_iso=now, ability_dimension="transfer"
    )

    assert code_estimate["forgetting_risk"] > transfer_estimate["forgetting_risk"]
    assert code_estimate["decay_profile_days"] == 10
    assert transfer_estimate["decay_profile_days"] == 28


def test_unknown_ability_dimension_falls_back_to_default_profile() -> None:
    """A dimension outside the canonical six gets the default 14-day
    profile, never raises."""
    estimate = estimate_mastery(
        attempts=[{"score_ratio": 1.0, "created_at": "2026-05-15T00:00:00+08:00"}],
        now_iso="2026-05-22T00:00:00+08:00",
        ability_dimension="not_in_registry",
    )

    assert estimate["decay_profile_days"] == 14  # default
    assert "forgetting_risk" in estimate


def test_no_attempts_reports_insufficient_evidence_level() -> None:
    """Empty attempts must produce ``level='insufficient_evidence'`` with
    a non-stale ``forgetting_risk=0`` (nothing to forget)."""
    estimate = estimate_mastery(
        attempts=[],
        legacy_score=80,
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert estimate["level"] == "insufficient_evidence"
    assert estimate["forgetting_risk"] == 0
    assert estimate["needs_revalidation"] is False


def test_repeated_recent_negatives_become_weak_not_stable() -> None:
    """Two recent misses → ``level='weak'``; forgetting_risk is moderate
    (the events ARE recent, but the level is driven by correctness)."""
    estimate = estimate_mastery(
        attempts=[
            {"score_ratio": 0.0, "created_at": "2026-05-20T00:00:00+08:00"},
            {"score_ratio": 0.0, "created_at": "2026-05-22T00:00:00+08:00"},
        ],
        now_iso="2026-05-22T00:00:00+08:00",
        ability_dimension="code_application",
    )

    assert estimate["level"] == "weak"
    assert estimate["needs_revalidation"] is True


def test_conversation_only_attempts_do_not_change_level_from_insufficient() -> None:
    """conversation_synthesis events MUST NOT prove mastery; the level
    stays ``insufficient_evidence`` even when many such events are
    passed."""
    chat_events = [
        {
            "evidence_source": "conversation_synthesis",
            "score_ratio": 1.0,
            "created_at": "2026-05-22T00:00:00+08:00",
            "quality": {"progress_countable": False},
        }
        for _ in range(5)
    ]

    estimate = estimate_mastery(
        attempts=chat_events,
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert estimate["level"] == "insufficient_evidence"
    assert estimate["needs_revalidation"] is False


def test_legacy_status_field_still_present_for_backward_compat() -> None:
    """Existing consumers read 'status'; Task 5 must NOT remove it."""
    estimate = estimate_mastery(
        attempts=[{"score_ratio": 1.0, "created_at": "2026-05-22T00:00:00+08:00"}],
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert "status" in estimate
    assert "score" in estimate
    assert "confidence" in estimate

