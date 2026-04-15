from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext
from deeptutor.services.session import SQLiteSessionStore, build_user_owner_key

ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
router = ws_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


class _FakeRuntime:
    def __init__(self) -> None:
        self.started_payload: dict | None = None

    async def start_turn(self, payload: dict):
        self.started_payload = dict(payload)
        return {"id": str(payload.get("session_id") or "session_new")}, {"id": "turn_new"}

    async def subscribe_turn(self, turn_id: str, after_seq: int = 0):
        yield {
            "type": "done",
            "source": "test",
            "stage": "",
            "content": "",
            "metadata": {"status": "completed", "after_seq": after_seq},
            "session_id": "session_new",
            "turn_id": turn_id,
            "seq": 1,
            "timestamp": 0,
        }

    async def subscribe_session(self, session_id: str, after_seq: int = 0):
        yield {
            "type": "done",
            "source": "test",
            "stage": "",
            "content": "",
            "metadata": {"status": "completed", "after_seq": after_seq},
            "session_id": session_id,
            "turn_id": "",
            "seq": 1,
            "timestamp": 0,
        }

    async def cancel_turn(self, _turn_id: str) -> bool:
        return True


class _BoomRuntime(_FakeRuntime):
    async def start_turn(self, payload: dict):
        raise RuntimeError("database exploded secret")


def test_ws_subscribe_session_rejects_foreign_owned_session(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(ws_module, "resolve_auth_context", lambda _authorization: None)
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="owned_session", owner_key=build_user_owner_key("student_other")))

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "subscribe_session", "session_id": "owned_session"})
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Session not found"


def test_ws_subscribe_session_allows_owner(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(ws_module, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="owned_session", owner_key=build_user_owner_key("student_demo")))

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "subscribe_session", "session_id": "owned_session"})
            message = websocket.receive_json()

    assert message["type"] == "done"
    assert message["session_id"] == "owned_session"


def test_ws_start_turn_binds_authenticated_user_into_billing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(ws_module, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "hello",
                    "config": {},
                }
            )
            message = websocket.receive_json()

    billing_context = fake_runtime.started_payload["config"]["billing_context"]
    assert billing_context["user_id"] == "student_demo"
    assert billing_context["source"] == "authenticated_ws"
    assert message["type"] == "done"


def test_ws_start_turn_runtime_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _BoomRuntime()

    monkeypatch.setattr(ws_module, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "hello",
                    "config": {},
                }
            )
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Unable to start turn. Please try again later."
    assert "database exploded secret" not in message["content"]


def test_ws_invalid_payload_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ws_module, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: _FakeRuntime())

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "cancel_turn"})
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Invalid cancel_turn payload."
