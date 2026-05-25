from __future__ import annotations

import importlib
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.services.member_console.service import MemberConsoleService
from deeptutor.services.path_service import PathService
from deeptutor.services.assessment import AssessmentBlueprintUnavailable


FORBIDDEN_PRE_SUBMIT_KEYS = {
    "answer",
    "answer_key",
    "correct_answer",
    "grading_key",
    "scoring_points",
    "minimal_rationale",
    "rubric",
    "official_answer",
    "option_reasoning",
}

FORBIDDEN_PRE_SUBMIT_KEY_SUBSTRINGS = (
    "answer",
    "grading",
    "rubric",
    "scoring_point",
    "correct",
)

_ALLOWED_PRE_SUBMIT_SUBSTRING_KEYS = {
    # Metadata only: source IDs are needed for provenance/debugging but do not
    # reveal correctness or grading artifacts.
    "source_answer_table",
}


def _assert_no_forbidden_pre_submit_keys(payload: Any, path: str = "$") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            key_lower = key_text.lower()
            current_path = f"{path}.{key_text}"
            assert key_lower not in FORBIDDEN_PRE_SUBMIT_KEYS, f"forbidden key leaked at {current_path}"
            if key_lower not in _ALLOWED_PRE_SUBMIT_SUBSTRING_KEYS:
                for substring in FORBIDDEN_PRE_SUBMIT_KEY_SUBSTRINGS:
                    assert substring not in key_lower, f"forbidden key substring leaked at {current_path}"
            _assert_no_forbidden_pre_submit_keys(value, current_path)
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, item in enumerate(payload):
            _assert_no_forbidden_pre_submit_keys(item, f"{path}[{index}]")


def _build_mobile_app() -> FastAPI:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    app = FastAPI()
    app.include_router(mobile_module.router, prefix="/api/v1")
    return app


def test_member_service_create_assessment_payload_is_redacted(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("redaction_user", count=20)

    _assert_no_forbidden_pre_submit_keys(payload)


def test_mobile_create_assessment_payload_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    user_data_dir = Path(tempfile.mkdtemp(prefix="deeptutor-assessment-redaction-")) / "user"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    path_service = PathService.get_instance()
    original_user_data_dir = path_service._user_data_dir
    path_service._user_data_dir = user_data_dir
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    replacement_service = MemberConsoleService()
    replacement_service._data_path = user_data_dir / "member_console.json"
    monkeypatch.setattr(mobile_module, "member_service", replacement_service)
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "redaction_user")

    try:
        with TestClient(_build_mobile_app()) as client:
            response = client.post(
                "/api/v1/assessment/create",
                json={"assessment_type": "diagnostic", "count": 20},
            )
    finally:
        path_service._user_data_dir = original_user_data_dir

    assert response.status_code == 200
    _assert_no_forbidden_pre_submit_keys(response.json())


def test_redaction_guard_fails_on_hidden_answer_fixture() -> None:
    with pytest.raises(AssertionError, match="forbidden key leaked"):
        _assert_no_forbidden_pre_submit_keys(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "answer": "A",
                    }
                ]
            }
        )


def test_redaction_guard_fails_on_structural_grading_fixture() -> None:
    with pytest.raises(AssertionError, match="forbidden key substring leaked"):
        _assert_no_forbidden_pre_submit_keys(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "gradingArtifact": {"expected_choice": "A"},
                    }
                ]
            }
        )


def test_mobile_create_accepts_topic_diagnostic_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    captured: dict[str, Any] = {}

    class _Member:
        def create_assessment(self, user_id: str, **kwargs):
            captured["user_id"] = user_id
            captured.update(kwargs)
            return {
                "quiz_id": "quiz_p0a",
                "assessment_type": kwargs["assessment_type"],
                "subject_id": kwargs["subject_id"],
                "topic_ids": kwargs["topic_ids"],
                "blueprint_version": "topic_waterproof_v1",
                "questions": [],
            }

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_mobile_app()) as client:
        response = client.post(
            "/api/v1/assessment/create",
            json={
                "assessment_type": "topic_diagnostic",
                "subject_id": "construction_exam",
                "topic_ids": ["waterproof"],
                "count": 12,
                "duration_policy": {"mode": "one_shot"},
            },
        )

    assert response.status_code == 200
    assert captured["assessment_type"] == "topic_diagnostic"
    assert captured["subject_id"] == "construction_exam"
    assert captured["topic_ids"] == ["waterproof"]
    assert captured["count"] == 12


def test_mobile_assessment_topics_route_is_not_captured_by_quiz_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")

    class _Member:
        def get_assessment_topic_catalog(self):
            return {"topics": [{"topic_id": "waterproof", "status": "stable", "enabled": True}]}

        def get_assessment_session(self, user_id: str, quiz_id: str):
            raise AssertionError(f"topics route was captured as quiz_id={quiz_id}")

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_mobile_app()) as client:
        response = client.get("/api/v1/assessment/topics")

    assert response.status_code == 200
    assert response.json()["topics"][0]["topic_id"] == "waterproof"


def test_mobile_create_maps_unavailable_blueprint_to_controlled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")

    class _Member:
        def create_assessment(self, user_id: str, **kwargs):
            raise AssessmentBlueprintUnavailable("requires 4 scored questions, found 3")

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_mobile_app()) as client:
        response = client.post(
            "/api/v1/assessment/create",
            json={
                "assessment_type": "topic_diagnostic",
                "subject_id": "construction_exam",
                "topic_ids": ["waterproof"],
                "count": 12,
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "assessment_blueprint_unavailable"


def test_mobile_resume_payload_is_redacted_before_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")

    class _Member:
        def get_assessment_session(self, user_id: str, quiz_id: str, **kwargs):
            return {
                "quiz_id": quiz_id,
                "status": "in_progress",
                "questions": [{"question_id": "q1", "question_stem": "防水题"}],
            }

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_mobile_app()) as client:
        response = client.get("/api/v1/assessment/quiz_p0a")

    assert response.status_code == 200
    _assert_no_forbidden_pre_submit_keys(response.json())


def test_mobile_report_endpoint_replays_submitted_report(monkeypatch: pytest.MonkeyPatch) -> None:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")

    class _Member:
        def get_assessment_report(self, user_id: str, quiz_id: str):
            return {
                "schema_version": "p0a-v1",
                "quiz_id": quiz_id,
                "score_title": "本次专题测评得分",
                "score_summary": {"score_pct": 50},
                "wrong_items": [{"question_id": "q2", "correct_answer": "A"}],
                "session_local_next_action": {"authority": "session_local_deterministic"},
                "deep_explanation": {"available": False},
            }

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_mobile_app()) as client:
        response = client.get("/api/v1/assessment/quiz_p0a/report")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "p0a-v1"
    assert body["score_title"].startswith("本次")
    assert body["session_local_next_action"]["authority"] == "session_local_deterministic"
    assert body["deep_explanation"]["available"] is False
