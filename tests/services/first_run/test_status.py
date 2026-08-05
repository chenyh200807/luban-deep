from __future__ import annotations

from deeptutor.services.first_run.status import (
    project_first_run_completion,
    project_first_run_gate,
    project_pass_readiness_completion,
)


def test_projects_completed_only_from_canonical_learner_profile() -> None:
    projection = project_first_run_completion(
        {
            "learning_preferences": {
                "first_run": {
                    "script_version": "first_run_script.v1@abc",
                    "completed_at": "2026-07-11T02:00:00+00:00",
                    "source": "explicit_first_run_v1",
                }
            }
        }
    )

    assert projection == {
        "completed": True,
        "script_version": "first_run_script.v1@abc",
        "completed_at": "2026-07-11T02:00:00+00:00",
        "source": "learner_state.learning_preferences.first_run",
    }


def test_incomplete_or_untrusted_profile_fails_closed() -> None:
    assert project_first_run_completion({})["completed"] is False
    assert project_first_run_completion(
        {"learning_preferences": {"first_run": {"script_version": "first_run_script.v1@abc"}}}
    )["completed"] is False
    assert project_first_run_completion(
        {
            "learning_preferences": {
                "first_run": {
                    "script_version": "first_run_script.v1@abc",
                    "completed_at": "2026-07-11T02:00:00+00:00",
                    "source": "some_other_writer",
                }
            }
        }
    )["completed"] is False


def _scored_pass_readiness_session(*, with_evidence: bool = True) -> dict:
    return {
        "quiz_id": "quiz_pr_1",
        "assessment_type": "pass_readiness",
        "status": "scored",
        "scored_at": "2026-08-05T12:00:00Z",
        "learning_event_refs": (
            [{"event_id": "evt_1", "question_id": "q1"}] if with_evidence else []
        ),
    }


def test_pass_readiness_completion_requires_scored_session_with_landed_evidence() -> None:
    completed = project_pass_readiness_completion(_scored_pass_readiness_session())
    assert completed == {
        "completed": True,
        "quiz_id": "quiz_pr_1",
        "scored_at": "2026-08-05T12:00:00Z",
        "source": "assessment_sessions.pass_readiness",
    }

    # Evidence not landed yet → not completed (§5.2: evidence migration must succeed).
    assert project_pass_readiness_completion(_scored_pass_readiness_session(with_evidence=False))[
        "completed"
    ] is False
    # Other assessment types never suppress First Run.
    other = _scored_pass_readiness_session()
    other["assessment_type"] = "topic_diagnostic"
    assert project_pass_readiness_completion(other)["completed"] is False
    assert project_pass_readiness_completion(None)["completed"] is False


def test_first_run_gate_suppresses_only_on_positive_pass_readiness_evidence() -> None:
    incomplete_first_run = project_first_run_completion({})
    pass_readiness_done = project_pass_readiness_completion(_scored_pass_readiness_session())
    pass_readiness_missing = project_pass_readiness_completion(None)

    suppressed = project_first_run_gate(incomplete_first_run, pass_readiness_done)
    assert suppressed["required"] is False
    assert suppressed["suppressed_by_pass_readiness"] is True
    assert suppressed["completed"] is False  # suppression never fakes completion

    still_required = project_first_run_gate(incomplete_first_run, pass_readiness_missing)
    assert still_required["required"] is True
    assert still_required["suppressed_by_pass_readiness"] is False

    completed_first_run = project_first_run_completion(
        {
            "learning_preferences": {
                "first_run": {
                    "script_version": "first_run_script.v1@abc",
                    "completed_at": "2026-07-11T02:00:00+00:00",
                    "source": "explicit_first_run_v1",
                }
            }
        }
    )
    already_done = project_first_run_gate(completed_first_run, pass_readiness_done)
    assert already_done["required"] is False
    assert already_done["suppressed_by_pass_readiness"] is False
    assert already_done["completed"] is True
