from __future__ import annotations

import importlib
import sys
import types

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
WebSocketDenialResponse = pytest.importorskip("starlette.testclient").WebSocketDenialResponse

from deeptutor.api.dependencies import AuthContext, get_current_user

fake_chat_module = types.ModuleType("deeptutor.agents.chat")
fake_chat_module.__path__ = []  # type: ignore[attr-defined]
fake_chat_pipeline_module = types.ModuleType("deeptutor.agents.chat.agentic_pipeline")


class _FakeSessionManager:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


class _FakeChatAgent:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


class _FakeAgenticChatPipeline:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


fake_chat_module.ChatAgent = _FakeChatAgent
fake_chat_module.SessionManager = _FakeSessionManager
fake_chat_pipeline_module.AgenticChatPipeline = _FakeAgenticChatPipeline
sys.modules.setdefault("deeptutor.agents.chat", fake_chat_module)
sys.modules.setdefault("deeptutor.agents.chat.agentic_pipeline", fake_chat_pipeline_module)

chat_module = importlib.import_module("deeptutor.api.routers.chat")
router = chat_module.router


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


def test_chat_sessions_require_admin() -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/chat/sessions")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_chat_websocket_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=False)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDenialResponse):
            with client.websocket_connect("/api/v1/chat"):
                pass
