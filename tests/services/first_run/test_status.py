from __future__ import annotations

from deeptutor.services.first_run.status import project_first_run_completion


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
