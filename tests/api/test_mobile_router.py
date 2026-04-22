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
auth_dependency_module = importlib.import_module("deeptutor.api.dependencies.auth")
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
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "_resolve_wallet_lookup_user_id",
        lambda *_args, **_kwargs: "wallet_demo",
    )
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
    assert captured["payload"]["config"]["interaction_hints"]["suppress_answer_reveal_on_generate"] is True
    assert captured["payload"]["config"]["bot_id"] == "construction-exam-coach"
    assert captured["payload"]["config"]["billing_context"] == {
        "source": "wx_miniprogram",
        "user_id": "student_demo",
        "wallet_user_id": "wallet_demo",
        "learning_user_id": "student_demo",
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
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "_resolve_wallet_lookup_user_id",
        lambda *_args, **_kwargs: "wallet_demo",
    )
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


def test_mobile_chat_start_turn_writes_requested_response_mode_and_legacy_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_mode_1",
                    "title": "模式归一",
                    "created_at": 1_700_000_011.0,
                },
                {
                    "id": "turn_mode_1",
                    "status": "running",
                    "capability": "chat",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
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
                "query": "请详细讲一下流水步距",
                "conversation_id": "session_mode_1",
                "mode": "DEEP",
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["chat_mode"] == "deep"
    assert config["interaction_hints"]["requested_response_mode"] == "deep"
    assert "teaching_mode" not in config["interaction_hints"]


def test_mobile_chat_start_turn_overrides_conflicting_legacy_teaching_mode_with_canonical_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_mode_2",
                    "title": "模式冲突归一",
                    "created_at": 1_700_000_012.0,
                },
                {
                    "id": "turn_mode_2",
                    "status": "running",
                    "capability": "chat",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
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
                "query": "请展开讲解流水步距",
                "conversation_id": "session_mode_2",
                "mode": "DEEP",
                "interaction_hints": {
                    "teaching_mode": "fast",
                },
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["chat_mode"] == "deep"
    assert config["interaction_hints"]["requested_response_mode"] == "deep"
    assert "teaching_mode" not in config["interaction_hints"]


def test_mobile_chat_start_turn_preserves_legacy_teaching_mode_when_mode_is_implicit_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_mode_legacy",
                    "title": "模式兼容",
                    "created_at": 1_700_000_013.0,
                },
                {
                    "id": "turn_mode_legacy",
                    "status": "running",
                    "capability": "chat",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
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
                "query": "请按旧版深度模式讲解",
                "conversation_id": "session_mode_legacy",
                "interaction_hints": {
                    "teaching_mode": "deep",
                },
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["chat_mode"] == "deep"
    assert config["interaction_hints"]["requested_response_mode"] == "deep"
    assert "teaching_mode" not in config["interaction_hints"]


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
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

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
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

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


def test_mobile_chat_start_turn_auto_enables_web_search_for_textbook_delta_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_4b",
                    "title": "教材变化",
                    "created_at": 1_700_000_041.0,
                },
                {
                    "id": "turn_4b",
                    "status": "running",
                    "capability": "chat",
                },
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "2026年的教材有什么不一样",
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


def test_mobile_chat_feedback_persists_structured_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeFeedbackClient:
        def __init__(self, *args, **kwargs) -> None:
            self.is_configured = True

        async def insert_feedback(self, row):
            captured["row"] = dict(row)
            return dict(row)

        async def aclose(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(mobile_module, "MobileFeedbackSupabaseClient", FakeFeedbackClient)
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(
            get_session_owner_key=AsyncMock(return_value="user:student_demo")
        ),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/sessions/session_feedback_1/messages/42/feedback",
            json={
                "rating": -1,
                "reason_tags": ["事实错误", "逻辑不通", "事实错误"],
                "comment": "这里的规范引用不对",
                "answer_mode": "fast",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    row = captured["row"]
    assert row["user_id"] is None
    assert row["conversation_id"] is None
    assert row["message_id"] is None
    assert row["rating"] == -1
    assert row["reason_tags"] == ["事实错误", "逻辑不通"]
    assert row["comment"] == "这里的规范引用不对"
    assert row["metadata"]["answer_mode"] == "FAST"
    assert row["metadata"]["feedback_source"] == "wx_miniprogram_message_actions"
    assert row["metadata"]["surface"] == "wx_miniprogram"
    assert row["metadata"]["deeptutor_user_id"] == "student_demo"
    assert row["metadata"]["deeptutor_session_id"] == "session_feedback_1"
    assert row["metadata"]["deeptutor_message_id"] == "42"
    assert captured["closed"] is True


def test_mobile_chat_feedback_legacy_alias_reuses_same_persistence_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeFeedbackClient:
        def __init__(self, *args, **kwargs) -> None:
            self.is_configured = True

        async def insert_feedback(self, row):
            captured["row"] = dict(row)
            return dict(row)

        async def aclose(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(mobile_module, "MobileFeedbackSupabaseClient", FakeFeedbackClient)
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(
            get_session_owner_key=AsyncMock(return_value="user:student_demo")
        ),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/feedback",
            json={
                "message_id": "42",
                "conversation_id": "session_feedback_legacy",
                "rating": 1,
                "reason_tags": ["有帮助"],
                "comment": "这个解释清楚",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    row = captured["row"]
    assert row["conversation_id"] is None
    assert row["message_id"] is None
    assert row["rating"] == 1
    assert row["reason_tags"] == ["有帮助"]
    assert row["metadata"]["deeptutor_session_id"] == "session_feedback_legacy"
    assert row["metadata"]["deeptutor_message_id"] == "42"
    assert captured["closed"] is True


def test_mobile_chat_feedback_infers_response_mode_metadata_from_session_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeFeedbackClient:
        def __init__(self, *args, **kwargs) -> None:
            self.is_configured = True

        async def insert_feedback(self, row):
            captured["row"] = dict(row)
            return dict(row)

        async def aclose(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(mobile_module, "MobileFeedbackSupabaseClient", FakeFeedbackClient)
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(
            get_session_owner_key=AsyncMock(return_value="user:student_demo"),
            get_session_with_messages=AsyncMock(
                return_value={
                    "id": "session_feedback_modes",
                    "preferences": {
                        "chat_mode": "fast",
                        "interaction_hints": {
                            "requested_response_mode": "deep",
                            "response_mode_degrade_reason": "tool_budget",
                        },
                    },
                    "messages": [
                        {
                            "id": 42,
                            "role": "assistant",
                            "content": "答案",
                            "events": [
                                {"type": "tool_call", "metadata": {"tool_name": "rag"}},
                                {"type": "tool_call", "metadata": {"tool_name": "web_search"}},
                            ],
                        }
                    ],
                }
            ),
        ),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/sessions/session_feedback_modes/messages/42/feedback",
            json={
                "rating": 1,
                "reason_tags": ["有帮助"],
                "comment": "这次模式判断对了",
                "answer_mode": "smart",
            },
        )

    assert response.status_code == 200
    row = captured["row"]
    assert row["metadata"]["answer_mode"] == "SMART"
    assert row["metadata"]["requested_response_mode"] == "DEEP"
    assert row["metadata"]["effective_response_mode"] == "FAST"
    assert row["metadata"]["response_mode_degrade_reason"] == "tool_budget"
    assert row["metadata"]["actual_tool_rounds"] == 2
    assert captured["closed"] is True


def test_mobile_chat_feedback_returns_503_when_storage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeFeedbackClient:
        def __init__(self, *args, **kwargs) -> None:
            self.is_configured = False

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(mobile_module, "MobileFeedbackSupabaseClient", FakeFeedbackClient)
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/feedback",
            json={
                "message_id": "42",
                "rating": 1,
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Feedback storage unavailable"


def test_get_conversation_messages_include_presentation_payload(
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
                            "presentation": {
                                "schema_version": 1,
                                "blocks": [
                                    {
                                        "type": "mcq",
                                        "questions": [
                                            {
                                                "index": 1,
                                                "question_id": "q_1",
                                                "stem": "某防水工程题目",
                                                "question_type": "single_choice",
                                                "options": [
                                                    {"key": "A", "text": "方案A"},
                                                    {"key": "B", "text": "方案B"},
                                                ],
                                                "followup_context": {
                                                    "question_id": "q_1",
                                                    "question": "某防水工程题目",
                                                    "question_type": "choice",
                                                    "options": {"A": "方案A", "B": "方案B"},
                                                    "correct_answer": "B",
                                                    "explanation": "B 更符合规范。",
                                                    "difficulty": "medium",
                                                    "concentration": "地下防水",
                                                },
                                            }
                                        ],
                                        "submit_hint": "请选择后提交答案",
                                        "receipt": "",
                                        "review_mode": False,
                                    }
                                ],
                                "fallback_text": "### Question 1\n某防水工程题目",
                                "meta": {"streamingMode": "block_finalized"},
                            }
                        },
                    }
                ],
            }
        ],
    }

    async def _fake_get_session_with_messages(_conversation_id: str):
        return session_payload

    async def _fake_list_sessions_by_owner(*_args, **_kwargs):
        return [session_payload]

    monkeypatch.setattr(mobile_module.session_store, "list_sessions_by_owner", _fake_list_sessions_by_owner)
    monkeypatch.setattr(mobile_module.session_store, "get_session_with_messages", _fake_get_session_with_messages)
    monkeypatch.setattr(mobile_module.session_store, "get_session_owner_key", AsyncMock(return_value="user:student_demo"))
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/session_mcq/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[0]["presentation"]["blocks"][0]["type"] == "mcq"
    assert messages[0]["presentation"]["blocks"][0]["questions"][0]["question_id"] == "q_1"


def test_get_conversation_messages_merges_internal_tutorbot_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_rows = [
        {
            "id": "tb_123",
            "updated_at": 20.0,
            "created_at": 10.0,
            "preferences": {
                "source": "wx_miniprogram",
                "user_id": "student_demo",
                "bot_id": "construction-exam-coach",
            },
        },
        {
            "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123",
            "updated_at": 21.0,
            "created_at": 11.0,
            "preferences": {
                "source": "wx_miniprogram",
                "user_id": "student_demo",
                "conversation_id": "tb_123",
                "bot_id": "construction-exam-coach",
            },
        },
    ]

    session_payloads = {
        "tb_123": {
            "id": "tb_123",
            "preferences": {"source": "wx_miniprogram", "archived": False},
            "messages": [
                {
                    "id": 1,
                    "role": "user",
                    "content": "建筑构造是什么？",
                    "created_at": 100.0,
                    "events": [],
                },
                {
                    "id": 2,
                    "role": "assistant",
                    "content": "我来帮你梳理建筑构造的核心概念。",
                    "created_at": 101.0,
                    "events": [],
                },
            ],
        },
        "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123": {
            "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123",
            "preferences": {"source": "wx_miniprogram", "archived": False},
            "messages": [
                {
                    "id": 10,
                    "role": "assistant",
                    "content": "标准答案：CDE",
                    "created_at": 102.0,
                    "events": [
                        {
                            "type": "result",
                            "metadata": {
                                "presentation": {
                                    "schema_version": 1,
                                    "blocks": [
                                        {
                                            "type": "mcq",
                                            "questions": [
                                                {
                                                    "index": 1,
                                                    "question_id": "q_1",
                                                    "stem": "防火门设置要求有（ ）。",
                                                    "question_type": "multi_choice",
                                                    "options": [
                                                        {"key": "A", "text": "方案A"},
                                                        {"key": "B", "text": "方案B"},
                                                    ],
                                                }
                                            ],
                                            "submit_hint": "请选择后提交答案",
                                            "receipt": "",
                                            "review_mode": False,
                                        }
                                    ],
                                    "fallback_text": "",
                                    "meta": {"streamingMode": "block_finalized"},
                                }
                            },
                        }
                    ],
                }
            ],
        },
    }

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            if session_id == "tb_123":
                return ""
            if session_id in session_payloads:
                return "user:student_demo"
            return ""

        async def list_sessions_by_owner(
            self,
            owner_key: str,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 500,
            offset: int = 0,
        ):
            assert owner_key == "user:student_demo"
            assert source == "wx_miniprogram"
            return session_rows

        async def get_session_with_messages(self, session_id: str):
            return session_payloads.get(session_id)

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/tb_123/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [item["content"] for item in messages] == [
        "建筑构造是什么？",
        "我来帮你梳理建筑构造的核心概念。",
        "标准答案：CDE",
    ]
    assert messages[-1]["presentation"]["blocks"][0]["questions"][0]["stem"] == "防火门设置要求有（ ）。"


def test_get_conversation_messages_pages_past_first_500_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_batch = [
        {
            "id": f"session_{index}",
            "updated_at": float(1000 - index),
            "created_at": float(index),
            "preferences": {"source": "wx_miniprogram", "user_id": "student_demo"},
        }
        for index in range(500)
    ]
    target_row = {
        "id": "tb_target",
        "updated_at": 1.0,
        "created_at": 1.0,
        "preferences": {"source": "wx_miniprogram", "user_id": "student_demo"},
    }
    target_payload = {
        "id": "tb_target",
        "preferences": {"source": "wx_miniprogram", "archived": False},
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "命中了第 501 条之后的会话。",
                "created_at": 1.0,
                "events": [],
            }
        ],
    }

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            if session_id == "tb_target":
                return ""
            return "user:student_demo"

        async def list_sessions_by_owner(
            self,
            owner_key: str,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 500,
            offset: int = 0,
        ):
            assert owner_key == "user:student_demo"
            assert source == "wx_miniprogram"
            if offset == 0:
                return first_batch
            if offset == 500:
                return [target_row]
            return []

        async def get_session_with_messages(self, session_id: str):
            if session_id == "tb_target":
                return target_payload
            return None

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/tb_target/messages")

    assert response.status_code == 200
    assert response.json()["messages"][0]["content"] == "命中了第 501 条之后的会话。"


def test_wechat_login_route_maps_service_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _failing_login(_code: str):
        raise RuntimeError("WeChat code2Session failed")

    monkeypatch.setattr(mobile_module.member_service, "login_with_wechat_code", _failing_login)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/wechat/mp/login", json={"code": "abc"})

    assert response.status_code == 502
    assert "code2Session" in response.json()["detail"]


def test_wechat_bind_phone_uses_bound_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "wx_user_1",
    )
    
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


def test_wechat_bind_phone_rate_limits_by_route_and_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "mobile_wechat_bind_phone": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "wx_user_1",
    )

    async def _fake_bind_phone(_user_id: str, _phone_code: str) -> dict[str, object]:
        return {"bound": True}

    monkeypatch.setattr(mobile_module.member_service, "bind_phone_for_wechat", _fake_bind_phone)

    with TestClient(_build_app()) as client:
        first = client.post("/api/v1/wechat/mp/bind-phone", json={"phone_code": "13800001234"})
        second = client.post("/api/v1/wechat/mp/bind-phone", json={"phone_code": "13800001234"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


def test_bi_radar_self_uses_authenticated_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[auth_dependency_module.get_current_user] = lambda: SimpleNamespace(
        user_id="student_demo",
        is_admin=False,
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_radar_data",
        lambda user_id: {"user_id": user_id, "dimensions": []},
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/radar/self")

    assert response.status_code == 200
    assert response.json()["user_id"] == "student_demo"


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


def test_auth_login_exposes_is_admin_without_profile_followup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mobile_module.member_service,
        "login_with_password",
        lambda _username, _password: {
            "user_id": "admin_demo",
            "token": "token-1",
            "expires_at": 123,
            "is_admin": True,
            "user": {
                "user_id": "admin_demo",
                "display_name": "管理员",
                "is_admin": True,
            },
        },
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin_demo", "password": "good-password"},
        )

    assert response.status_code == 200
    assert response.json()["is_admin"] is True
    assert response.json()["user"]["is_admin"] is True


def test_auth_register_maps_validation_error_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    def _failing_register(_username: str, _password: str, _phone: str):
        raise ValueError("用户名已存在")

    monkeypatch.setattr(mobile_module.member_service, "register_with_external_auth", _failing_register)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "student_demo", "password": "StrongPass123", "phone": "13800000000"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "用户名已存在"


def test_auth_register_seeds_learner_state_when_user_id_present(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        mobile_module.member_service,
        "register_with_external_auth",
        lambda _username, _password, _phone: {"user_id": "student_demo", "token": "ok"},
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "read_snapshot",
        lambda user_id: calls.append(user_id) or {"user_id": user_id},
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "student_demo", "password": "StrongPass123", "phone": "13800000000"},
        )

    assert response.status_code == 200
    assert calls == ["student_demo"]


def test_auth_register_seeds_learner_state_when_user_id_is_nested_under_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        mobile_module.member_service,
        "register_with_external_auth",
        lambda _username, _password, _phone: {
            "token": "ok",
            "user": {"user_id": "student_demo"},
        },
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "read_snapshot",
        lambda user_id: calls.append(user_id) or {"user_id": user_id},
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "student_demo", "password": "StrongPass123", "phone": "13800000000"},
        )

    assert response.status_code == 200
    assert calls == ["student_demo"]


def test_auth_profile_settings_syncs_learner_profile_and_goals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_profile",
        lambda user_id: {
            "user_id": user_id,
            "display_name": "旧昵称",
            "difficulty_preference": "medium",
            "review_reminder": True,
        },
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "update_profile",
        lambda user_id, patch: {
            "user_id": user_id,
            "display_name": "小陈",
            "difficulty_preference": patch.get("difficulty_preference", "medium"),
            "review_reminder": patch.get("review_reminder", True),
        },
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "read_profile",
        lambda user_id: {"user_id": user_id, "display_name": "旧昵称"},
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "read_goals",
        lambda _user_id: [],
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "write_profile_strict",
        lambda user_id, profile: calls.append(("profile", user_id, dict(profile))) or dict(profile),
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "sync_goals_strict",
        lambda user_id, goals: [
            calls.append(("goal", user_id, dict(goal))) or dict(goal)
            for goal in goals
        ],
    )

    with TestClient(_build_app()) as client:
        response = client.patch(
            "/api/v1/auth/profile/settings",
            json={
                "difficulty_preference": "hard",
                "heartbeat_preferences": {
                    "enabled": True,
                    "quiet_hours": ["22:00", "08:00"],
                },
                "consent": {"heartbeat": True},
                "goal": {
                    "goal_type": "study",
                    "title": "本周完成 20 道案例题",
                    "target_question_count": 20,
                },
            },
        )

    assert response.status_code == 200
    assert calls[0][0] == "profile"
    assert calls[0][1] == "student_demo"
    assert calls[0][2]["difficulty_preference"] == "hard"
    assert calls[0][2]["heartbeat_preferences"]["enabled"] is True
    assert calls[0][2]["consent"]["heartbeat"] is True
    assert calls[1] == (
        "goal",
        "student_demo",
        {
            "goal_type": "study",
            "title": "本周完成 20 道案例题",
            "target_question_count": 20,
        },
    )


def test_auth_profile_surfaces_wallet_service_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "wx_demo_user",
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_profile",
        lambda user_id: {
            "user_id": user_id,
            "display_name": "微信学员",
        },
    )
    monkeypatch.setattr(
        mobile_module,
        "resolve_wallet_user_id",
        lambda *_args, **_kwargs: "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
    )
    monkeypatch.setattr(
        mobile_module.wallet_service,
        "get_wallet",
        lambda _user_id: (_ for _ in ()).throw(RuntimeError("wallet unavailable")),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/auth/profile")

    assert response.status_code == 503
    assert response.json()["detail"] == "Wallet service unavailable"


def test_auth_refresh_reissues_token_for_valid_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {"authorization": None}

    def _refresh_access_token(authorization: str | None) -> dict[str, Any]:
        captured["authorization"] = authorization
        return {
            "user_id": "student_demo",
            "token": "dtm.refreshed.signature",
            "token_type": "Bearer",
            "expires_at": 1_800_000_000,
            "expires_in": 2_592_000,
            "user": {"user_id": "student_demo"},
        }

    monkeypatch.setattr(mobile_module.member_service, "refresh_access_token", _refresh_access_token)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": "Bearer old-token"},
        )

    assert response.status_code == 200
    assert captured["authorization"] == "Bearer old-token"
    assert response.json()["token"] == "dtm.refreshed.signature"
    assert response.json()["expires_at"] == 1_800_000_000


def test_auth_refresh_returns_401_for_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_invalid(_authorization: str | None) -> dict[str, Any]:
        raise ValueError("Invalid or expired token")

    monkeypatch.setattr(mobile_module.member_service, "refresh_access_token", _raise_invalid)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": "Bearer expired-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_auth_profile_settings_rolls_back_member_and_learner_state_on_sync_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_calls: list[dict[str, Any]] = []
    profile_sync_calls: list[dict[str, Any]] = []
    goal_sync_calls: list[list[dict[str, Any]]] = []

    previous_profile = {
        "user_id": "student_demo",
        "display_name": "旧昵称",
        "difficulty_preference": "medium",
        "review_reminder": True,
    }
    previous_learner_profile = {"user_id": "student_demo", "display_name": "旧昵称", "consent": {"heartbeat": False}}
    previous_goals = [
        {
            "id": "goal_existing",
            "goal_type": "study",
            "title": "旧目标",
            "target_question_count": 10,
        }
    ]

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module.member_service, "get_profile", lambda _user_id: dict(previous_profile))

    def _update_profile(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        update_calls.append(dict(patch))
        if patch.get("display_name") == previous_profile["display_name"]:
            return dict(previous_profile)
        return {
            "user_id": user_id,
            "display_name": "新昵称",
            "difficulty_preference": patch.get("difficulty_preference", "hard"),
            "review_reminder": patch.get("review_reminder", False),
        }

    monkeypatch.setattr(mobile_module.member_service, "update_profile", _update_profile)
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "read_profile",
        lambda _user_id: dict(previous_learner_profile),
    )
    monkeypatch.setattr(
        mobile_module.learner_state_service,
        "read_goals",
        lambda _user_id: [dict(item) for item in previous_goals],
    )

    def _write_profile_strict(user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        profile_sync_calls.append({"user_id": user_id, **dict(profile)})
        return dict(profile)

    def _sync_goals_strict(user_id: str, goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        goal_sync_calls.append([dict(item) for item in goals])
        if goals and goals[0].get("title") != "旧目标":
            raise RuntimeError("supabase unavailable")
        return [dict(item) for item in goals]

    monkeypatch.setattr(mobile_module.learner_state_service, "write_profile_strict", _write_profile_strict)
    monkeypatch.setattr(mobile_module.learner_state_service, "sync_goals_strict", _sync_goals_strict)

    with TestClient(_build_app()) as client:
        response = client.patch(
            "/api/v1/auth/profile/settings",
            json={
                "display_name": "新昵称",
                "difficulty_preference": "hard",
                "review_reminder": False,
                "goal": {
                    "goal_type": "study",
                    "title": "新目标",
                    "target_question_count": 20,
                },
            },
        )

    assert response.status_code == 503
    assert "Failed to sync learner state" in response.json()["detail"]
    assert update_calls == [
        {
            "display_name": "新昵称",
            "difficulty_preference": "hard",
            "review_reminder": False,
            "goal": {
                "goal_type": "study",
                "title": "新目标",
                "target_question_count": 20,
            },
        },
        {
            "display_name": "旧昵称",
            "difficulty_preference": "medium",
            "review_reminder": True,
        },
    ]
    assert profile_sync_calls[0]["display_name"] == "新昵称"
    assert profile_sync_calls[1]["display_name"] == "旧昵称"
    assert goal_sync_calls == [
        [
            {
                "goal_type": "study",
                "title": "新目标",
                "target_question_count": 20,
            }
        ],
        previous_goals,
    ]


def test_auth_register_rate_limits_by_route_and_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "mobile_auth_register": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "register_with_external_auth",
        lambda _username, _password, _phone: {"token": "ok"},
    )

    with TestClient(_build_app()) as client:
        first = client.post(
            "/api/v1/auth/register",
            json={"username": "student_demo", "password": "StrongPass123", "phone": "13800000000"},
        )
        second = client.post(
            "/api/v1/auth/register",
            json={"username": "student_demo", "password": "StrongPass123", "phone": "13800000000"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


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


def test_auth_send_code_returns_400_for_invalid_phone_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_value_error(_phone: str) -> dict[str, object]:
        raise ValueError("手机号格式不正确")

    monkeypatch.setattr(mobile_module.member_service, "send_phone_code", _raise_value_error)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/auth/send-code", json={"phone": "dev-phone-code"})

    assert response.status_code == 400
    assert response.json()["detail"] == "手机号格式不正确"


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
    class FakeSessionStore:
        async def list_sessions_by_owner_and_conversation(
            self,
            owner_key: str,
            conversation_id: str,
            *,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 50,
        ):
            assert owner_key == "user:student_demo"
            assert conversation_id == "session_other"
            assert source == "wx_miniprogram"
            assert archived is None
            assert limit == 50
            return []

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())

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
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

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


def test_create_conversation_initializes_mobile_tutorbot_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSessionStore:
        async def ensure_session(self, session_id: str, owner_key: str):
            captured["ensure_session"] = {
                "session_id": session_id,
                "owner_key": owner_key,
            }
            return {
                "id": session_id,
                "created_at": 1_700_000_000.0,
            }

        async def update_session_title(self, session_id: str, title: str):
            captured["title"] = {
                "session_id": session_id,
                "title": title,
            }

        async def update_session_preferences(self, session_id: str, preferences: dict[str, object]):
            captured["preferences"] = {
                "session_id": session_id,
                "preferences": preferences,
            }

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/conversations")

    assert response.status_code == 200
    body = response.json()
    conversation = body["conversation"]
    assert conversation["id"].startswith("tb_")
    assert conversation["title"] == "新对话"
    assert captured["ensure_session"] == {
        "session_id": conversation["id"],
        "owner_key": "user:student_demo",
    }
    assert captured["title"] == {
        "session_id": conversation["id"],
        "title": "新对话",
    }
    assert captured["preferences"] == {
        "session_id": conversation["id"],
        "preferences": {
            "source": "wx_miniprogram",
            "user_id": "student_demo",
            "archived": False,
            "bot_id": "construction-exam-coach",
        },
    }


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
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

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


def test_list_conversations_merges_internal_tutorbot_mirror_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSessionStore:
        async def list_sessions_by_owner(
            self,
            owner_key: str,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 200,
            offset: int = 0,
        ):
            return [
                {
                    "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123",
                    "title": "建筑构造是什么？",
                    "updated_at": 20.0,
                    "created_at": 10.0,
                    "message_count": 8,
                    "last_message": "标准答案：CDE",
                    "status": "idle",
                    "active_turn_id": "",
                    "capability": "tutorbot",
                    "cost_summary": {"total_tokens": 88},
                    "preferences": {
                        "source": "wx_miniprogram",
                        "conversation_id": "tb_123",
                        "session_id": "tb_123",
                        "bot_id": "construction-exam-coach",
                    },
                },
                {
                    "id": "tb_123",
                    "title": "新对话",
                    "updated_at": 18.0,
                    "created_at": 9.0,
                    "message_count": 2,
                    "last_message": "",
                    "status": "completed",
                    "active_turn_id": "",
                    "capability": "tutorbot",
                    "cost_summary": {"total_tokens": 44},
                    "preferences": {
                        "source": "wx_miniprogram",
                        "bot_id": "construction-exam-coach",
                    },
                },
            ]

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations")

    assert response.status_code == 200
    conversations = response.json()["conversations"]
    assert len(conversations) == 1
    assert conversations[0]["id"] == "tb_123"
    assert conversations[0]["title"] == "建筑构造是什么？"
    assert conversations[0]["message_count"] == 8
    assert conversations[0]["last_message"] == "标准答案：CDE"
    assert conversations[0]["cost_summary"]["total_tokens"] == 88
