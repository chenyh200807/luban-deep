from __future__ import annotations

import importlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
from deeptutor.services.path_service import PathService

_TEST_USER_DATA_DIR = Path(tempfile.mkdtemp(prefix="deeptutor-mobile-tests-")) / "user"
_TEST_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
_ORIGINAL_USER_DATA_DIR = PathService.get_instance()._user_data_dir
PathService.get_instance()._user_data_dir = _TEST_USER_DATA_DIR

mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
rate_limit_module = importlib.import_module("deeptutor.api.dependencies.rate_limit")
router = mobile_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture(autouse=True)
def _clear_rate_limit_state() -> None:
    PathService.get_instance()._user_data_dir = _TEST_USER_DATA_DIR
    rate_limit_module.clear_rate_limit_state()
    yield
    rate_limit_module.clear_rate_limit_state()
    PathService.get_instance()._user_data_dir = _ORIGINAL_USER_DATA_DIR


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
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(
            get_session_owner_key=AsyncMock(return_value="user:student_demo")
        ),
    )

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
    assert body["stream"]["url"] == "/api/v1/ws"
    assert body["stream"]["subscribe"]["turn_id"] == "turn_1"
    assert captured["payload"]["capability"] is None
    assert captured["payload"]["content"] == "考我一道流水施工的题"
    assert captured["payload"]["config"]["interaction_hints"]["profile"] == "tutorbot"
    assert captured["payload"]["config"]["bot_id"] == "construction-exam-coach"
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
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(
            get_session_owner_key=AsyncMock(return_value="user:student_demo")
        ),
    )

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
    assert config["interaction_hints"]["profile"] == "tutorbot"


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
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "考我一道题",
                "interaction_profile": "tutorbot",
                "interaction_hints": {
                    "preferred_question_type": "written",
                    "allow_general_chat_fallback": False,
                },
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["interaction_hints"]["profile"] == "tutorbot"
    assert config["interaction_hints"]["preferred_question_type"] == "written"
    assert config["interaction_hints"]["allow_general_chat_fallback"] is False


def test_mobile_chat_start_turn_auto_enables_web_search_for_policy_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_4",
                    "title": "政策解读",
                    "created_at": 1_700_000_040.0,
                },
                {
                    "id": "turn_4",
                    "status": "running",
                    "capability": "chat",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "2025年住建部最新政策有什么变化？",
                "mode": "AUTO",
                "language": "zh",
            },
        )

    assert response.status_code == 200
    assert "web_search" in captured["payload"]["tools"]
    assert captured["payload"]["config"]["interaction_hints"]["current_info_required"] is True


def test_mobile_chat_start_turn_requires_authentication() -> None:
    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "考我一道题",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_get_conversation_messages_includes_interactive_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_mcq",
        "title": "防水工程练习",
        "preferences": {
            "source": "wx_miniprogram",
            "archived": False,
        },
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
    monkeypatch.setattr(mobile_module.session_store, "get_session_owner_key", AsyncMock(return_value="user:student_demo"))
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


def test_auth_login_maps_invalid_password_to_401(monkeypatch: pytest.MonkeyPatch) -> None:
    def _failing_login(_username: str, _password: str):
        raise ValueError("用户名或密码错误")

    monkeypatch.setattr(mobile_module.member_service, "login_with_password", _failing_login)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "student_demo", "password": "bad-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误"


def test_auth_login_rate_limits_by_route_and_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "mobile_auth_login": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "login_with_password",
        lambda _username, _password: {"token": "ok"},
    )

    with TestClient(_build_app()) as client:
        first = client.post(
            "/api/v1/auth/login",
            json={"username": "student_demo", "password": "good-password"},
        )
        second = client.post(
            "/api/v1/auth/login",
            json={"username": "student_demo", "password": "good-password"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


def test_auth_send_code_rate_limits_by_route_and_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "mobile_auth_send_code": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "send_phone_code",
        lambda _phone: {"sent": True, "retry_after": 60, "phone": "13800000000"},
    )

    with TestClient(_build_app()) as client:
        first = client.post("/api/v1/auth/send-code", json={"phone": "13800000000"})
        second = client.post("/api/v1/auth/send-code", json={"phone": "13800000000"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


def test_auth_verify_code_rate_limits_by_route_and_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "mobile_auth_verify_code": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "verify_phone_code",
        lambda _phone, _code, password=None: {"token": "ok", "password": password},
    )

    with TestClient(_build_app()) as client:
        first = client.post(
            "/api/v1/auth/verify-code",
            json={"phone": "13800000000", "code": "123456"},
        )
        second = client.post(
            "/api/v1/auth/verify-code",
            json={"phone": "13800000000", "code": "123456"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


def test_auth_send_code_returns_503_when_sms_debug_fallback_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_runtime(_phone: str) -> dict[str, object]:
        raise RuntimeError("短信服务未配置，生产环境已禁止调试验证码")

    monkeypatch.setattr(mobile_module.member_service, "send_phone_code", _raise_runtime)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/auth/send-code", json={"phone": "13800000000"})

    assert response.status_code == 503
    assert response.json()["detail"] == "短信服务未配置，生产环境已禁止调试验证码"


def test_wechat_login_rate_limits_by_route_and_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "mobile_wechat_login": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )

    async def _fake_login(_code: str) -> dict[str, str]:
        return {"token": "ok"}

    monkeypatch.setattr(mobile_module.member_service, "login_with_wechat_code", _fake_login)

    with TestClient(_build_app()) as client:
        first = client.post("/api/v1/wechat/mp/login", json={"code": "abc"})
        second = client.post("/api/v1/wechat/mp/login", json={"code": "abc"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


def test_mobile_chat_start_turn_rejects_other_users_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_session_owner_key(_conversation_id: str):
        return "user:student_other"

    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")
    monkeypatch.setattr(mobile_module.session_store, "get_session_owner_key", _fake_get_session_owner_key)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "继续刚才的对话",
                "conversation_id": "session_other",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_list_conversations_uses_owner_source_and_archived_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSessionStore:
        async def list_sessions_by_owner(
            self,
            owner_key: str,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 200,
            offset: int = 0,
        ):
            captured["args"] = {
                "owner_key": owner_key,
                "source": source,
                "archived": archived,
                "limit": limit,
                "offset": offset,
            }
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
    assert captured["args"] == {
        "owner_key": "user:student_demo",
        "source": "wx_miniprogram",
        "archived": False,
        "limit": 200,
        "offset": 0,
    }
    conversation = response.json()["conversations"][0]
    assert conversation["id"] == "session_1"
    assert conversation["cost_summary"]["total_tokens"] == 440
    assert conversation["cost_summary"]["usage_accuracy"] == "mixed"


def test_list_conversations_can_request_archived_items(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeSessionStore:
        async def list_sessions_by_owner(
            self,
            owner_key: str,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 200,
            offset: int = 0,
        ):
            captured["args"] = {
                "owner_key": owner_key,
                "source": source,
                "archived": archived,
                "limit": limit,
                "offset": offset,
            }
            return []

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(mobile_module, "_resolve_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations?archived=true")

    assert response.status_code == 200
    assert captured["args"] == {
        "owner_key": "user:student_demo",
        "source": "wx_miniprogram",
        "archived": True,
        "limit": 200,
        "offset": 0,
    }
    assert response.json()["conversations"] == []
