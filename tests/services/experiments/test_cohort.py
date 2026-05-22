from __future__ import annotations

from deeptutor.services.experiments.cohort import current_stage, is_enabled


FLAG = "LEARNING_STATE_INFERENCE_V2"


def test_feature_flag_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv(f"{FLAG}_STAGE", raising=False)

    assert current_stage(FLAG) == "off"
    assert is_enabled(FLAG, user_id="student_demo") is False


def test_internal_stage_requires_allowlisted_user(monkeypatch) -> None:
    monkeypatch.setenv(f"{FLAG}_STAGE", "internal")
    monkeypatch.setenv(f"{FLAG}_INTERNAL_USERS", "teacher_a, student_demo")

    assert is_enabled(FLAG, user_id="student_demo") is True
    assert is_enabled(FLAG, user_id="other_student") is False


def test_cohort_stage_is_deterministic(monkeypatch) -> None:
    monkeypatch.setenv(f"{FLAG}_STAGE", "cohort_10")

    first = is_enabled(FLAG, user_id="student_demo")
    second = is_enabled(FLAG, user_id="student_demo")

    assert first is second


def test_subgate_stage_is_isolated_from_parent(monkeypatch) -> None:
    monkeypatch.setenv(f"{FLAG}_STAGE", "cohort_100")
    monkeypatch.setenv(f"{FLAG}_EVIDENCE_STAGE", "off")
    monkeypatch.setenv(f"{FLAG}_STATE_PROJECTION_STAGE", "cohort_100")

    assert is_enabled(f"{FLAG}.evidence", user_id="student_demo") is False
    assert is_enabled(f"{FLAG}.state_projection", user_id="student_demo") is True


def test_kill_switch_turns_everything_off_immediately(monkeypatch) -> None:
    monkeypatch.setenv(f"{FLAG}_STAGE", "cohort_100")
    assert is_enabled(FLAG, user_id="student_demo") is True

    monkeypatch.setenv(f"{FLAG}_STAGE", "off")

    assert is_enabled(FLAG, user_id="student_demo") is False
