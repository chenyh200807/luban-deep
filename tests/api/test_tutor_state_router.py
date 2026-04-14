from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
router = importlib.import_module("deeptutor.api.routers.tutor_state").router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/tutor-state")
    return app


def _make_snapshot():
    return type(
        "Snapshot",
        (),
        {
            "user_id": "student_demo",
            "profile": "## 身份信息\n- 学员ID：student_demo",
            "persona": "## 角色定位\n- 你是该学员的专属 TutorBot。",
            "memory": "## 当前主线\n- 当前聚焦：地基基础承载力",
            "profile_updated_at": "2026-04-14T12:00:00+08:00",
            "persona_updated_at": "2026-04-14T12:01:00+08:00",
            "memory_updated_at": "2026-04-14T12:02:00+08:00",
        },
    )()


def test_tutor_state_router_returns_user_snapshot(monkeypatch) -> None:
    class FakeTutorStateService:
        def read_snapshot(self, user_id: str):
            assert user_id == "student_demo"
            return _make_snapshot()

    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_user_tutor_state_service",
        lambda: FakeTutorStateService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/tutor-state/student_demo")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "student_demo"
    assert "专属 TutorBot" in body["persona"]
    assert "地基基础承载力" in body["memory"]


def test_tutor_state_router_returns_rendered_context(monkeypatch) -> None:
    class FakeTutorStateService:
        def build_context(self, user_id: str, *, language: str = "zh", max_chars: int = 5000):
            assert user_id == "student_demo"
            assert language == "en"
            assert max_chars == 2400
            return "## Dedicated Tutor Context\n### Student Profile\n- user: student_demo"

    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_user_tutor_state_service",
        lambda: FakeTutorStateService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/tutor-state/student_demo/context?language=en&max_chars=2400")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "user_id": "student_demo",
        "language": "en",
        "max_chars": 2400,
        "context": "## Dedicated Tutor Context\n### Student Profile\n- user: student_demo",
    }
