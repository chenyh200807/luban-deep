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


_PASS_READINESS_SOURCE = "assessment_sessions.pass_readiness"


def project_pass_readiness_completion(session: dict[str, Any] | None) -> dict[str, Any]:
    """Project canonical pass-readiness completion from an assessment session row.

    Completion = a scored ``pass_readiness`` session whose evidence writeback
    landed (non-empty ``learning_event_refs``). Pure read projection — no flag,
    no new state.
    """

    row = session if isinstance(session, dict) else {}
    completed = bool(
        str(row.get("assessment_type") or "") == "pass_readiness"
        and str(row.get("status") or "") == "scored"
        and list(row.get("learning_event_refs") or [])
    )
    return {
        "completed": completed,
        "quiz_id": str(row.get("quiz_id") or "") if completed else "",
        "scored_at": str(row.get("scored_at") or "") if completed else "",
        "source": _PASS_READINESS_SOURCE,
    }


def project_first_run_gate(
    first_run: dict[str, Any],
    pass_readiness: dict[str, Any],
) -> dict[str, Any]:
    """Suppression projection (过线体检 §5.2): a learner whose pass-readiness
    diagnostic produced canonical learning evidence is not asked to repeat the
    legacy four-question First Run.

    Pure function over the two canonical projections; the legacy completion
    truth is passed through untouched (suppression never fakes completion).
    """

    first_run_completed = bool(dict(first_run or {}).get("completed"))
    pass_readiness_completed = bool(dict(pass_readiness or {}).get("completed"))
    suppressed = (not first_run_completed) and pass_readiness_completed
    return {
        **dict(first_run or {}),
        "required": not first_run_completed and not pass_readiness_completed,
        "suppressed_by_pass_readiness": suppressed,
    }


__all__ = [
    "project_first_run_completion",
    "project_first_run_gate",
    "project_pass_readiness_completion",
]
