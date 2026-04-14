from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
router = mobile_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_mobile_chat_start_turn_returns_ws_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_1",
                    "title": "New conversation",
                    "created_at": 1_700_000_000.0,
                },
                {
                    "id": "turn_1",
                    "status": "running",
                    "capability": "",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "考我一道流水施工的题",
                "mode": "AUTO",
                "language": "zh",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation"]["id"] == "session_1"
    assert body["turn"]["id"] == "turn_1"
    assert body["stream"]["transport"] == "websocket"
    assert body["stream"]["subscribe"]["turn_id"] == "turn_1"
    assert captured["payload"]["capability"] is None
    assert captured["payload"]["config"]["interaction_hints"]["profile"] == "mini_tutor"
    assert captured["payload"]["config"]["billing_context"] == {
        "source": "wx_miniprogram",
        "user_id": "student_demo",
    }


def test_mobile_chat_start_turn_passes_chat_mode_and_followup_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_2",
                    "title": "流水步距",
                    "created_at": 1_700_000_010.0,
                },
                {
                    "id": "turn_2",
                    "status": "running",
                    "capability": "chat",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "为什么我这题做错了？",
                "conversation_id": "session_2",
                "mode": "DEEP",
                "followup_question_context": {
                    "question_id": "q_1",
                    "question": "流水步距描述什么？",
                    "question_type": "choice",
                },
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["chat_mode"] == "deep"
    assert config["followup_question_context"]["question_id"] == "q_1"
    assert config["interaction_hints"]["profile"] == "mini_tutor"


def test_mobile_chat_start_turn_accepts_custom_interaction_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_3",
                    "title": "学习会话",
                    "created_at": 1_700_000_020.0,
                },
                {
                    "id": "turn_3",
                    "status": "running",
                    "capability": "",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "考我一道题",
                "interaction_profile": "mini_tutor",
                "interaction_hints": {
                    "preferred_question_type": "written",
                    "allow_general_chat_fallback": False,
                },
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["interaction_hints"]["profile"] == "mini_tutor"
    assert config["interaction_hints"]["preferred_question_type"] == "written"
    assert config["interaction_hints"]["allow_general_chat_fallback"] is False


def test_get_conversation_messages_includes_interactive_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_mcq",
        "title": "防水工程练习",
        "preferences": {},
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "### Question 1\n某防水工程题目",
                "created_at": 1_700_000_030.0,
                "events": [
                    {
                        "type": "result",
                        "metadata": {
                            "summary": {
                                "results": [
                                    {
                                        "qa_pair": {
                                            "question_id": "q_1",
                                            "question": "某防水工程题目",
                                            "question_type": "choice",
                                            "options": {
                                                "A": "方案A",
                                                "B": "方案B",
                                            },
                                            "correct_answer": "B",
                                            "explanation": "B 更符合规范。",
                                            "difficulty": "medium",
                                            "concentration": "地下防水",
                                        }
                                    }
                                ]
                            }
                        },
                    }
                ],
            }
        ],
    }

    async def _fake_get_session_with_messages(_conversation_id: str):
        return session_payload

    monkeypatch.setattr(mobile_module.session_store, "get_session_with_messages", _fake_get_session_with_messages)
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/session_mcq/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[0]["interactive"]["type"] == "mcq_interactive"
    assert messages[0]["interactive"]["questions"][0]["question_id"] == "q_1"
    assert messages[0]["interactive"]["hidden_contexts"][0]["correct_answer"] == "B"


def test_wechat_login_route_maps_service_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _failing_login(_code: str):
        raise RuntimeError("WeChat code2Session failed")

    monkeypatch.setattr(mobile_module.member_service, "login_with_wechat_code", _failing_login)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/wechat/mp/login", json={"code": "abc"})

    assert response.status_code == 502
    assert "code2Session" in response.json()["detail"]


def test_wechat_bind_phone_uses_bound_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "wx_user_1")
    
    async def _fake_bind_phone(user_id, phone_code):
        return {
            "bound": True,
            "user_id": user_id,
            "phone": phone_code,
        }

    monkeypatch.setattr(
        mobile_module.member_service,
        "bind_phone_for_wechat",
        _fake_bind_phone,
    )

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/wechat/mp/bind-phone", json={"phone_code": "13800001234"})

    assert response.status_code == 200
    assert response.json()["bound"] is True
    assert response.json()["user_id"] == "wx_user_1"


def test_list_conversations_exposes_cost_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSessionStore:
        async def list_sessions(self, limit: int = 200, offset: int = 0):
            return [
                {
                    "id": "session_1",
                    "title": "会话一",
                    "last_message": "最后一条",
                    "message_count": 6,
                    "status": "completed",
                    "capability": "chat",
                    "created_at": 1_700_000_000.0,
                    "updated_at": 1_700_000_100.0,
                    "preferences": {
                        "archived": False,
                        "source": "wx_miniprogram",
                        "user_id": "student_demo",
                    },
                    "cost_summary": {
                        "scope_id": "session:session_1",
                        "session_id": "session_1",
                        "total_input_tokens": 320,
                        "total_output_tokens": 120,
                        "total_tokens": 440,
                        "total_calls": 4,
                        "measured_calls": 2,
                        "estimated_calls": 2,
                        "usage_accuracy": "mixed",
                        "usage_sources": {"provider": 2, "tiktoken": 2},
                        "models": {"deepseek-v3.2": 4},
                        "total_cost_usd": 0.023,
                    },
                }
            ]

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations")

    assert response.status_code == 200
    conversation = response.json()["conversations"][0]
    assert conversation["id"] == "session_1"
    assert conversation["cost_summary"]["total_tokens"] == 440
    assert conversation["cost_summary"]["usage_accuracy"] == "mixed"
