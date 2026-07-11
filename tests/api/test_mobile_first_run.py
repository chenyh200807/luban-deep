from __future__ import annotations

import importlib
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.services.first_run.manifest import (
    FirstRunAnswerSetInvalid,
    FirstRunManifestUnsigned,
    FirstRunManifestVersionConflict,
    load_first_run_manifest,
)
from deeptutor.services.first_run.writeback import FirstRunIdempotencyConflict

mobile = importlib.import_module("deeptutor.api.routers.mobile")


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(mobile.router, prefix="/api/v1")
    return app


def _valid_body() -> dict[str, Any]:
    manifest = load_first_run_manifest()
    return {
        "completion_id": "completion-http-0001",
        "script_version": manifest["script_version"],
        "completed_at": "2026-07-11T02:00:00Z",
        "answers": [
            {
                "question_id": question["question_id"],
                "selected_key": "A",
                "duration_ms": 10_000,
            }
            for question in manifest["questions"]
        ],
        "declared_preferences": {
            "exam_stage": "second",
            "answer_style": "nopoint",
            "material_version": "y2026",
            "memory_channel": "B",
            "study_slot": "C",
            "motivation": "B",
        },
    }


def test_first_run_complete_requires_auth() -> None:
    with TestClient(_app()) as client:
        response = client.post("/api/v1/first-run/complete", json=_valid_body())

    assert response.status_code == 401


def test_first_run_complete_delegates_only_canonical_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Service:
        def complete(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"sync_status": "synced", "completion_id": kwargs["completion_id"]}

    monkeypatch.setattr(mobile, "first_run_writeback_service", _Service())
    monkeypatch.setattr(mobile, "_resolve_authenticated_user_id", lambda _header: "canonical-user")

    with TestClient(_app()) as client:
        response = client.post("/api/v1/first-run/complete", json=_valid_body())

    assert response.status_code == 200
    assert captured["user_id"] == "canonical-user"
    assert set(captured) == {
        "user_id",
        "completion_id",
        "script_version",
        "completed_at",
        "answers",
        "declared_preferences",
    }
    assert all("score" not in answer for answer in captured["answers"])


def test_first_run_complete_rejects_client_score_and_wrong_answer_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mobile, "_resolve_authenticated_user_id", lambda _header: "canonical-user")
    body = _valid_body()
    body["score"] = 100

    with TestClient(_app()) as client:
        score_response = client.post("/api/v1/first-run/complete", json=body)
        body.pop("score")
        body["answers"] = body["answers"][:3]
        count_response = client.post("/api/v1/first-run/complete", json=body)

    assert score_response.status_code == 422
    assert count_response.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code", "error_code"),
    [
        (FirstRunIdempotencyConflict("c1"), 409, "first_run_idempotency_conflict"),
        (FirstRunManifestUnsigned("q1"), 409, "first_run_content_not_signed"),
        (FirstRunManifestVersionConflict("old"), 409, "first_run_version_conflict"),
        (FirstRunAnswerSetInvalid("answer_set_mismatch"), 422, "first_run_answer_set_invalid"),
        (RuntimeError("storage_down"), 503, "first_run_writeback_unavailable"),
    ],
)
def test_first_run_complete_maps_stable_error_semantics(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    error_code: str,
) -> None:
    class _Service:
        def complete(self, **_kwargs: Any) -> dict[str, Any]:
            raise error

    monkeypatch.setattr(mobile, "first_run_writeback_service", _Service())
    monkeypatch.setattr(mobile, "_resolve_authenticated_user_id", lambda _header: "canonical-user")

    with TestClient(_app()) as client:
        response = client.post("/api/v1/first-run/complete", json=_valid_body())

    assert response.status_code == status_code
    assert response.json()["detail"]["error"] == error_code


def test_assessment_profile_projects_first_run_completion_from_learner_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MemberService:
        def get_assessment_profile(self, user_id: str) -> dict[str, Any]:
            assert user_id == "canonical-user"
            return {"level": "", "chapter_mastery": {}}

    class _LearnerState:
        def read_profile(self, user_id: str) -> dict[str, Any]:
            assert user_id == "canonical-user"
            return {
                "learning_preferences": {
                    "first_run": {
                        "script_version": "first_run_script.v1@abc",
                        "completed_at": "2026-07-11T02:00:00+00:00",
                        "source": "explicit_first_run_v1",
                    }
                }
            }

    monkeypatch.setattr(mobile, "member_service", _MemberService())
    monkeypatch.setattr(mobile, "learner_state_service", _LearnerState())
    monkeypatch.setattr(mobile, "_resolve_authenticated_user_id", lambda _header: "canonical-user")

    with TestClient(_app()) as client:
        response = client.get("/api/v1/assessment/profile", headers={"Authorization": "Bearer qa"})

    assert response.status_code == 200
    assert response.json()["diagnostic_sources"]["first_run"]["completed"] is True
    assert response.json()["level"] == ""
