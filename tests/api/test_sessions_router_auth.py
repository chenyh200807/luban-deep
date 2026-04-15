from __future__ import annotations

import asyncio
import importlib
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.session import SQLiteSessionStore, build_user_owner_key

router = importlib.import_module("deeptutor.api.routers.sessions").router


def _build_app(store: SQLiteSessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/sessions")
    return app


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLiteSessionStore:
    instance = SQLiteSessionStore(db_path=tmp_path / "sessions-router.db")
    monkeypatch.setattr(
        "deeptutor.api.routers.sessions.get_sqlite_session_store",
        lambda: instance,
    )
    return instance


def test_list_sessions_filters_to_current_owner(store: SQLiteSessionStore) -> None:
    asyncio.run(store.create_session(session_id="owned", owner_key=build_user_owner_key("student_demo")))
    asyncio.run(store.create_session(session_id="other", owner_key=build_user_owner_key("student_other")))

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo")

    with TestClient(app) as client:
        response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["sessions"]] == ["owned"]


def test_non_admin_cannot_read_other_session(store: SQLiteSessionStore) -> None:
    asyncio.run(store.create_session(session_id="other", owner_key=build_user_owner_key("student_other")))

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo")

    with TestClient(app) as client:
        response = client.get("/api/v1/sessions/other")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_admin_can_read_any_session(store: SQLiteSessionStore) -> None:
    asyncio.run(store.create_session(session_id="other", owner_key=build_user_owner_key("student_other")))

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=True)

    with TestClient(app) as client:
        response = client.get("/api/v1/sessions/other")

    assert response.status_code == 200
    assert response.json()["id"] == "other"


def test_list_sessions_supports_keyset_cursor(store: SQLiteSessionStore) -> None:
    asyncio.run(store.create_session(session_id="session-a", owner_key=build_user_owner_key("student_demo")))
    asyncio.run(store.create_session(session_id="session-b", owner_key=build_user_owner_key("student_demo")))
    asyncio.run(store.create_session(session_id="session-c", owner_key=build_user_owner_key("student_demo")))

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (300.0, "session-a"))
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (200.0, "session-b"))
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (100.0, "session-c"))
        conn.commit()

    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo")

    with TestClient(app) as client:
        first = client.get("/api/v1/sessions?limit=2")
        assert first.status_code == 200
        first_body = first.json()
        assert [item["id"] for item in first_body["sessions"]] == ["session-a", "session-b"]
        assert first_body["next_cursor"] == {
            "before_updated_at": 200.0,
            "before_session_id": "session-b",
        }

        second = client.get(
            "/api/v1/sessions?limit=2&before_updated_at=200.0&before_session_id=session-b"
        )
        assert second.status_code == 200
        second_body = second.json()
        assert [item["id"] for item in second_body["sessions"]] == ["session-c"]
        assert second_body["next_cursor"] is None


def test_list_sessions_rejects_mixed_offset_and_cursor(store: SQLiteSessionStore) -> None:
    asyncio.run(store.create_session(session_id="owned", owner_key=build_user_owner_key("student_demo")))
    app = _build_app(store)
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo")

    with TestClient(app) as client:
        response = client.get("/api/v1/sessions?offset=1&before_updated_at=100.0")

    assert response.status_code == 400
    assert response.json()["detail"] == "offset cannot be combined with keyset cursor"
