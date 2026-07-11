from __future__ import annotations

from typing import Any

_PROFILE_SOURCE = "explicit_first_run_v1"
_PROJECTION_SOURCE = "learner_state.learning_preferences.first_run"


def project_first_run_completion(profile: dict[str, Any] | None) -> dict[str, Any]:
    raw_profile = profile if isinstance(profile, dict) else {}
    preferences = raw_profile.get("learning_preferences")
    first_run = preferences.get("first_run") if isinstance(preferences, dict) else {}
    first_run = first_run if isinstance(first_run, dict) else {}
    script_version = str(first_run.get("script_version") or "").strip()
    completed_at = str(first_run.get("completed_at") or "").strip()
    source = str(first_run.get("source") or "").strip()
    completed = bool(
        script_version.startswith("first_run_script.v1@")
        and completed_at
        and source == _PROFILE_SOURCE
    )
    return {
        "completed": completed,
        "script_version": script_version if completed else "",
        "completed_at": completed_at if completed else "",
        "source": _PROJECTION_SOURCE,
    }


__all__ = ["project_first_run_completion"]
