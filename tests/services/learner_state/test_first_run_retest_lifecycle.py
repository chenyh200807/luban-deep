from __future__ import annotations

from types import SimpleNamespace

from deeptutor.services.learner_state.learning_report_read_model import _truth_sections
from deeptutor.services.learner_state.learning_state_projection import (
    project_three_layer_learning_state,
)
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth


def _event(
    event_id: str,
    *,
    source: str,
    attempt_id: str,
    concept: str,
    correct: bool,
    promotion_allowed: bool,
    mode: str = "",
    evidence_level: str = "",
):
    error_code = "unknown_error"
    return SimpleNamespace(
        event_id=event_id,
        user_id="qa_eval_lifecycle",
        source_feature=source,
        source_id=f"source:{event_id}",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=f"2026-07-{10 + int(event_id[-1])}T10:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": source,
            "completion_id": attempt_id if source == "first_run_diagnostic" else "",
            "retest_completion_id": attempt_id if source == "assessment_testset" else "",
            "practice_mode": mode,
            "question_id": f"q:{event_id}",
            "score_awarded": 1.0 if correct else 0.0,
            "max_score": 1.0,
            "claim_promotion_allowed": promotion_allowed,
            "measurement_confidence": "low" if source == "first_run_diagnostic" else "high",
            "quality": {"evidence_level": evidence_level},
            "error_events": []
            if correct
            else [{"error_code": error_code, "concept_tag": concept}],
            "next_training_signal": {"concept": concept, "error_code": error_code},
        },
    )


def _terminal(event_id: str, *, attempt_id: str, mode: str = "review"):
    return SimpleNamespace(
        event_id=event_id,
        user_id="qa_eval_lifecycle",
        source_feature="assessment_testset",
        source_id=f"{attempt_id}:terminal",
        memory_kind="learning_evidence",
        dedupe_key=f"{attempt_id}:terminal",
        created_at=f"2026-07-{10 + int(event_id[-1])}T10:00:01+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "assessment_testset",
            "retest_completion_id": attempt_id,
            "completion_terminal": True,
            "practice_mode": mode,
            "claim_promotion_allowed": mode == "review",
        },
    )


def test_first_run_and_forward_are_visible_but_capped_at_short_term() -> None:
    events = [
        _event(
            "e1",
            source="first_run_diagnostic",
            attempt_id="first-run-1",
            concept="leaf:F16",
            correct=False,
            promotion_allowed=False,
        ),
        _event(
            "e2",
            source="assessment_testset",
            attempt_id="forward-1",
            concept="pack:F16:rule:diameter",
            correct=False,
            promotion_allowed=False,
            mode="forward",
        ),
    ]

    truth = synthesize_learning_truth(events)
    three_layer = project_three_layer_learning_state(events=events)

    assert truth["weak_points"] == []
    assert {item["concept_id"] for item in truth["observed_candidates"]} == {
        "leaf:F16",
        "pack:F16:rule:diameter",
    }
    assert all(item["state"] == "observed" for item in three_layer["knowledge_state"])
    assert not any(item["state"] == "recurring" for item in three_layer["behavior_state"])


def test_same_attempt_multiple_items_never_counts_as_repeated() -> None:
    events = [
        _event(
            "e1",
            source="assessment_testset",
            attempt_id="review-1",
            concept="pack:F16:rule:diameter",
            correct=False,
            promotion_allowed=True,
            mode="review",
        ),
        _event(
            "e2",
            source="assessment_testset",
            attempt_id="review-1",
            concept="pack:F16:rule:diameter",
            correct=False,
            promotion_allowed=True,
            mode="review",
        ),
        _terminal("e3", attempt_id="review-1"),
    ]

    truth = synthesize_learning_truth(events)
    three_layer = project_three_layer_learning_state(events=events)

    assert truth["weak_points"] == []
    assert three_layer["knowledge_state"][0]["state"] == "observed"
    assert three_layer["knowledge_state"][0]["evidence_count"] == 1
    report_truth = _truth_sections(events)
    assert report_truth["stable_truths"] == []
    assert report_truth["recent_observations"]


def test_second_distinct_attempt_promotes_repeated_error() -> None:
    events = [
        _event(
            "e1",
            source="assessment_testset",
            attempt_id="attempt-1",
            concept="pack:F16:rule:diameter",
            correct=False,
            promotion_allowed=True,
            mode="review",
        ),
        _terminal("e3", attempt_id="attempt-1"),
        _terminal("e4", attempt_id="attempt-2"),
        _event(
            "e2",
            source="assessment_testset",
            attempt_id="attempt-2",
            concept="pack:F16:rule:diameter",
            correct=False,
            promotion_allowed=True,
            mode="review",
        ),
    ]

    truth = synthesize_learning_truth(events)
    three_layer = project_three_layer_learning_state(events=events)

    assert truth["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert three_layer["knowledge_state"][0]["state"] == "weak"
    assert three_layer["knowledge_state"][0]["evidence_count"] == 2


def test_real_retest_can_confirm_or_resolve_only_matching_rule_group() -> None:
    weak = _event(
        "e1",
        source="assessment_testset",
        attempt_id="review-1",
        concept="pack:F16:rule:diameter",
        correct=False,
        promotion_allowed=True,
        mode="review",
        evidence_level="L2_real_retest",
    )
    other = _event(
        "e2",
        source="assessment_testset",
        attempt_id="review-1",
        concept="pack:F16:rule:sequence",
        correct=False,
        promotion_allowed=True,
        mode="review",
        evidence_level="L2_real_retest",
    )
    resolved = _event(
        "e3",
        source="assessment_testset",
        attempt_id="review-2",
        concept="pack:F16:rule:diameter",
        correct=True,
        promotion_allowed=True,
        mode="review",
        evidence_level="L2_real_retest",
    )

    truth = synthesize_learning_truth([
        weak,
        other,
        _terminal("e4", attempt_id="review-1"),
        resolved,
        _terminal("e5", attempt_id="review-2"),
    ])

    assert {(item["concept_id"], item["error_code"]) for item in truth["weak_points"]} == {
        ("pack:F16:rule:sequence", "unknown_error")
    }
    assert {(item["concept_id"], item["error_code"]) for item in truth["improvement_signals"]} == {
        ("pack:F16:rule:diameter", "unknown_error")
    }


def test_real_retest_success_without_prior_weak_is_retained_not_improved() -> None:
    success = _event(
        "e1",
        source="assessment_testset",
        attempt_id="review-clean",
        concept="pack:F16:rule:diameter",
        correct=True,
        promotion_allowed=True,
        mode="review",
        evidence_level="L2_real_retest",
    )
    terminal = _terminal("e2", attempt_id="review-clean")

    truth = synthesize_learning_truth([success, terminal])
    three_layer = project_three_layer_learning_state(events=[success, terminal])

    assert truth["improvement_signals"] == []
    assert truth["weak_points"] == []
    assert three_layer["knowledge_state"][0]["state"] == "observed"
