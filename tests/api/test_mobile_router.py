from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
_SH_TZ = timezone(timedelta(hours=8))


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


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/chat/start-turn",
        "/api/v1/mobile/chat/start-turn",
        "/api/v1/mobile/chat/start",
    ],
)
def test_mobile_chat_start_turn_returns_ws_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
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
            path,
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


def test_mobile_feedback_attachment_upload_returns_bi_visible_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/feedback/attachments",
            data={"kind": "image"},
            files={"file": ("screen.png", b"image-bytes", "image/png")},
        )

    assert response.status_code == 200
    attachment = response.json()["attachment"]
    assert attachment["kind"] == "image"
    assert attachment["filename"] == "screen.png"
    assert attachment["size"] == len(b"image-bytes")
    assert attachment["url"].startswith("/api/attachments/feedback-student_demo/")


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
                "prompt_intent": {
                    "source": "home_dashboard",
                    "concept_label": "主体结构",
                    "error_label": "多选漏选",
                    "training_intent_id": "lti_chat",
                },
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
    assert config["learning_prompt_intent"]["training_intent_id"] == "lti_chat"
    assert "learning_training_intent" not in config
    assert config["interaction_hints"]["profile"] == "tutorbot"


def test_mobile_chat_start_turn_can_regenerate_without_repersisting_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_retry_1",
                    "title": "监理考试时间",
                    "created_at": 1_700_000_020.0,
                },
                {
                    "id": "turn_retry_2",
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
                "query": "2026年监理工程师考试时间是什么时候",
                "conversation_id": "session_retry_1",
                "mode": "AUTO",
                "persist_user_message": False,
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert captured["payload"]["content"] == "2026年监理工程师考试时间是什么时候"
    assert config["_persist_user_message"] is False
    assert config["billing_context"] == {
        "source": "wx_miniprogram",
        "user_id": "student_demo",
        "wallet_user_id": "wallet_demo",
        "learning_user_id": "student_demo",
    }


def test_mobile_chat_start_turn_keeps_deep_question_config_schema_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_dq_1",
                    "title": "案例批改",
                    "created_at": 1_700_000_012.0,
                },
                {
                    "id": "turn_dq_1",
                    "status": "running",
                    "capability": "deep_question",
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
                "query": "我的答案：共用一个开关箱不妥。请批改。",
                "conversation_id": "session_dq_1",
                "capability": "deep_question",
                "mode": "DEEP",
                "prompt_intent": {
                    "source": "learning_report",
                    "concept_label": "主体结构",
                    "error_label": "多选漏选",
                    "training_intent_id": "lti_deep_question",
                    "question_count": 3,
                },
                "followup_question_context": {
                    "question_id": "case_1",
                    "question": "指出临时用电中的不妥之处。",
                    "question_type": "case",
                },
            },
        )

    assert response.status_code == 200
    payload = captured["payload"]
    config = payload["config"]
    assert payload["capability"] == "deep_question"
    assert "chat_mode" not in config
    assert "bot_id" not in config
    assert config["followup_question_context"]["question_id"] == "case_1"
    assert config["learning_training_intent"]["training_intent_id"] == "lti_deep_question"
    assert "learning_prompt_intent" not in config
    assert config["interaction_hints"]["requested_response_mode"] == "deep"
    assert config["billing_context"]["user_id"] == "student_demo"


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
                "client_turn_id": "surface_turn_1",
                "mode": "DEEP",
            },
        )

    assert response.status_code == 200
    config = captured["payload"]["config"]
    assert config["chat_mode"] == "deep"
    assert config["client_turn_id"] == "surface_turn_1"
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


def test_mobile_chat_start_turn_enables_web_search_for_current_info_queries(
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
    monkeypatch.setattr(mobile_module, "is_web_search_runtime_available", lambda: True)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "2026一建考试时间",
                "mode": "AUTO",
                "language": "zh",
            },
        )

    assert response.status_code == 200
    assert "web_search" in captured["payload"]["tools"]
    assert captured["payload"]["config"]["interaction_hints"]["current_info_required"] is True


def test_mobile_chat_start_turn_does_not_enable_web_search_for_personal_learning_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_4_learning_status",
                    "title": "学情",
                    "created_at": 1_700_000_040.2,
                },
                {
                    "id": "turn_4_learning_status",
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
    monkeypatch.setattr(mobile_module, "is_web_search_runtime_available", lambda: True)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "我最近学的怎么样",
                "mode": "AUTO",
                "language": "zh",
            },
        )

    assert response.status_code == 200
    assert "web_search" not in captured["payload"]["tools"]
    assert "current_info_required" not in captured["payload"]["config"]["interaction_hints"]


def test_mobile_chat_start_turn_does_not_treat_web_search_tool_as_current_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_4a",
                    "title": "联网查询",
                    "created_at": 1_700_000_040.5,
                },
                {
                    "id": "turn_4a",
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
    monkeypatch.setattr(mobile_module, "is_web_search_runtime_available", lambda: True)
    monkeypatch.setattr(
        mobile_module,
        "build_grounding_decision",
        lambda **_kwargs: SimpleNamespace(
            current_info_required=False,
            textbook_delta_query=False,
            reasons=[],
        ),
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "帮我批改这道建筑实务题的作答",
                "mode": "AUTO",
                "language": "zh",
                "tools": ["web_search"],
            },
        )

    assert response.status_code == 200
    assert "web_search" not in captured["payload"]["tools"]
    assert "current_info_required" not in captured["payload"]["config"]["interaction_hints"]


def test_mobile_chat_start_turn_treats_explicit_web_search_command_as_current_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {
                    "id": "session_4c",
                    "title": "联网查询",
                    "created_at": 1_700_000_040.8,
                },
                {
                    "id": "turn_4c",
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
    monkeypatch.setattr(mobile_module, "is_web_search_runtime_available", lambda: True)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={
                "query": "你不是能联网的吗，联网查询",
                "mode": "AUTO",
                "language": "zh",
            },
        )

    assert response.status_code == 200
    assert "web_search" in captured["payload"]["tools"]
    assert captured["payload"]["config"]["interaction_hints"]["current_info_required"] is True


def test_mobile_chat_start_turn_marks_current_info_without_disabled_web_search_when_unavailable(
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
    monkeypatch.setattr(mobile_module, "is_web_search_runtime_available", lambda: False)

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
    assert "web_search" not in captured["payload"]["tools"]
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


def test_mobile_chat_start_turn_blocks_when_usage_quota_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, _payload):
            captured["started"] = True
            return {}, {}

    class FakeWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            return mobile_module.WalletSnapshot(
                user_id=user_id,
                balance_micros=100_000_000,
                frozen_micros=0,
                plan_id="advance",
                version=1,
                created_at=mobile_module.datetime.now(mobile_module._BILLING_USAGE_TZ).isoformat(),
            )

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            captured["wallet_user_id"] = user_id
            captured["limit"] = limit
            captured["offset"] = offset
            return [
                mobile_module.WalletLedgerEntry(
                    id="evt_quota_1",
                    user_id=user_id,
                    event_type="debit",
                    delta_micros=-20_000_000,
                    balance_after_micros=80_000_000,
                    frozen_after_micros=0,
                    reference_type="ai_usage",
                    reference_id="turn_quota_1",
                    idempotency_key="capture:turn_quota_1",
                    metadata={"reason": "capture"},
                    created_at=mobile_module.datetime.now(mobile_module._BILLING_USAGE_TZ).isoformat(),
                )
            ]

    monkeypatch.setenv("DEEPTUTOR_BILLING_USAGE_5H_LIMIT_POINTS", "20")
    monkeypatch.setenv("DEEPTUTOR_BILLING_USAGE_WEEKLY_LIMIT_POINTS", "20")
    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(mobile_module, "wallet_service", FakeWalletService())
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

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={"query": "继续讲这道题"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "billing_quota_exceeded"
    assert detail["message"] == "Usage quota exceeded."
    assert detail["limited_by"] in {"five_hour", "weekly"}
    assert isinstance(detail["quota"], list)
    assert captured["wallet_user_id"] == "wallet_demo"
    assert captured["limit"] == mobile_module._BILLING_USAGE_LEDGER_WINDOW
    assert captured["offset"] == 0
    assert "started" not in captured


def test_billing_usage_defaults_follow_two_plan_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_BILLING_USAGE_5H_LIMIT_POINTS", raising=False)
    monkeypatch.delenv("DEEPTUTOR_BILLING_USAGE_WEEKLY_LIMIT_POINTS", raising=False)

    advance = mobile_module._build_billing_usage_payload([], plan_id="advance")
    sprint = mobile_module._build_billing_usage_payload([], plan_id="sprint")

    assert advance["display"]["plan_id"] == "advance"
    assert sprint["display"]["plan_id"] == "sprint"
    assert [row["label"] for row in advance["quota"]["rows"]] == ["5 小时保护额度", "本周额度"]

    advance_rows = {row["key"]: row for row in advance["quota"]["rows"]}
    sprint_rows = {row["key"]: row for row in sprint["quota"]["rows"]}
    assert advance_rows["five_hour"]["remaining_percent"] == 100
    assert sprint_rows["five_hour"]["remaining_percent"] == 100
    assert mobile_module._billing_usage_limit_for_plan("advance", "weekly") == 4400
    assert mobile_module._billing_usage_limit_for_plan("sprint", "weekly") == 9000


def test_mobile_chat_start_turn_skips_quota_gate_when_billing_storage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return (
                {"id": "session_quota_degraded", "title": "New conversation", "created_at": 1_700_000_030.0},
                {"id": "turn_quota_degraded", "status": "running", "capability": ""},
            )

    class FailingWalletService:
        is_configured = True

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            raise RuntimeError("supabase payment required")

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(mobile_module, "wallet_service", FailingWalletService())
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

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={"query": "继续讲这道题"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json()["turn"]["id"] == "turn_quota_degraded"
    assert captured["payload"]["config"]["billing_context"]["wallet_user_id"] == "wallet_demo"


def test_billing_usage_returns_degraded_payload_when_billing_storage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            return mobile_module.WalletSnapshot(
                user_id=user_id,
                balance_micros=100_000_000,
                frozen_micros=0,
                plan_id="advance",
                version=1,
                created_at=mobile_module.datetime.now(mobile_module._BILLING_USAGE_TZ).isoformat(),
            )

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            raise RuntimeError("supabase payment required")

    monkeypatch.setattr(mobile_module, "wallet_service", FailingWalletService())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_wallet_lookup_user_id",
        lambda *_args, **_kwargs: "wallet_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get(
            "/api/v1/billing/usage",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["display"]["primary_label"] == "额度同步中"
    assert body["quota"]["rows"] == []


def test_billing_ledger_returns_degraded_empty_page_when_billing_storage_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingWalletService:
        is_configured = True

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            raise RuntimeError("supabase payment required")

    monkeypatch.setattr(mobile_module, "wallet_service", FailingWalletService())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_wallet_lookup_user_id",
        lambda *_args, **_kwargs: "wallet_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get(
            "/api/v1/billing/ledger?limit=15",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["entries"] == []
    assert body["degraded"] is True


def test_billing_checkout_creates_wechat_order_shell_without_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPTUTOR_PAYMENT_GATEWAY_URL", raising=False)
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

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/billing/checkout",
            json={"package_id": "sprint", "channel": "wechat"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "payment_config_missing"
    assert body["channel"] == "wechat"
    assert body["wallet_user_id"] == "wallet_demo"
    assert body["package"]["id"] == "sprint"
    assert body["amount_fen"] == 19900
    assert body["payment"]["type"] == "wechat_mp"


def test_billing_checkout_rejects_unknown_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/billing/checkout",
            json={"package_id": "sprint", "channel": "bank_card"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400


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
    monkeypatch.setattr(mobile_module, "get_request_id", lambda: "req_feedback_1")
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
                "feedback_source": "wx_miniprogram_profile_feedback",
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
    assert row["metadata"]["feedback_source"] == "wx_miniprogram_profile_feedback"
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
    monkeypatch.setattr(mobile_module, "get_request_id", lambda: "req_feedback_1")
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


def test_mobile_chat_feedback_persists_canonical_turn_and_message_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
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
    monkeypatch.setattr(mobile_module, "get_request_id", lambda: "req_feedback_1")
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
                    "id": "session_feedback_trace",
                    "preferences": {
                        "interaction_hints": {
                            "requested_response_mode": "smart",
                        },
                    },
                    "messages": [
                        {
                            "id": 99,
                            "role": "assistant",
                            "content": "答案",
                            "events": [
                                {
                                    "type": "result",
                                    "turn_id": "turn_feedback_1",
                                    "metadata": {"trace_id": "trace_feedback_1"},
                                },
                                {
                                    "type": "tool_call",
                                    "turn_id": "turn_feedback_1",
                                    "metadata": {"tool_name": "rag"},
                                },
                            ],
                        }
                    ],
                }
            ),
        ),
    )

    with caplog.at_level("INFO", logger=mobile_module.__name__):
        with TestClient(_build_app()) as client:
            response = client.post(
                "/api/v1/sessions/session_feedback_trace/messages/a3/feedback",
                headers={"X-Request-ID": "req_feedback_1"},
                json={
                    "turn_id": "turn_feedback_1",
                    "rating": -1,
                    "reason_tags": ["逻辑不通"],
                    "comment": "这次推理跳步",
                },
            )

    assert response.status_code == 200
    row = captured["row"]
    assert row["metadata"]["deeptutor_message_id"] == "99"
    assert row["metadata"]["surface_message_id"] == "a3"
    assert row["metadata"]["turn_id"] == "turn_feedback_1"
    assert row["metadata"]["trace_id"] == "trace_feedback_1"
    assert row["metadata"]["request_id"] == "req_feedback_1"
    assert row["metadata"]["actual_tool_rounds"] == 1
    assert "Mobile feedback persisted" in caplog.text
    assert "turn_id=turn_fee...ck_1" in caplog.text
    assert "trace_id=trace_fe...ck_1" in caplog.text
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
    followup = messages[0]["presentation"]["blocks"][0]["questions"][0]["followup_context"]
    assert followup["correct_answer"] == ""
    assert followup["explanation"] == ""


def test_get_conversation_messages_reveals_answers_only_in_review_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_review_mcq",
        "title": "防水工程讲评",
        "preferences": {
            "source": "wx_miniprogram",
            "archived": False,
        },
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "讲评模式",
                "created_at": 1_700_000_031.0,
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
                                                },
                                            }
                                        ],
                                        "submit_hint": "请选择后提交答案",
                                        "receipt": "",
                                        "review_mode": True,
                                    }
                                ],
                                "fallback_text": "讲评模式",
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
        response = client.get("/api/v1/conversations/session_review_mcq/messages")

    assert response.status_code == 200
    followup = response.json()["messages"][0]["presentation"]["blocks"][0]["questions"][0]["followup_context"]
    assert followup["correct_answer"] == "B"
    assert followup["explanation"] == "B 更符合规范。"


def test_get_conversation_messages_preserves_explicit_reveal_flags_from_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_explicit_reveal_mcq",
        "title": "带答案练题",
        "preferences": {
            "source": "wx_miniprogram",
            "archived": False,
        },
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "讲评模式",
                "created_at": 1_700_000_032.0,
                "events": [
                    {
                        "type": "result",
                        "metadata": {
                            "reveal_answers": True,
                            "reveal_explanations": True,
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
                                                },
                                            }
                                        ],
                                        "submit_hint": "请选择后提交答案",
                                        "receipt": "",
                                        "review_mode": False,
                                    }
                                ],
                                "fallback_text": "讲评模式",
                            },
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
        response = client.get("/api/v1/conversations/session_explicit_reveal_mcq/messages")

    assert response.status_code == 200
    followup = response.json()["messages"][0]["presentation"]["blocks"][0]["questions"][0]["followup_context"]
    assert followup["correct_answer"] == "B"
    assert followup["explanation"] == "B 更符合规范。"


def test_get_conversation_messages_suppresses_presentation_for_exact_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_exact_authority",
        "title": "真题讲解",
        "preferences": {
            "source": "wx_miniprogram",
            "archived": False,
        },
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "题干：结构的可靠性包括（　　）\n标准答案：BCE",
                "created_at": 1_700_000_030.0,
                "events": [
                    {
                        "type": "tool_result",
                        "metadata": {
                            "authority_applied": True,
                            "exact_question": {"correct_answer": "BCE"},
                        },
                    },
                    {
                        "type": "result",
                        "metadata": {
                            "authority_applied": True,
                            "presentation": {
                                "schema_version": 1,
                                "blocks": [
                                    {
                                        "type": "mcq",
                                        "questions": [
                                            {
                                                "index": 1,
                                                "question_id": "q_exact",
                                                "stem": "结构的可靠性包括（　　）",
                                                "question_type": "multi_choice",
                                                "options": [
                                                    {"key": "A", "text": "稳定"},
                                                    {"key": "B", "text": "安全性"},
                                                ],
                                            }
                                        ],
                                        "submit_hint": "请选择后提交答案",
                                        "receipt": "",
                                        "review_mode": False,
                                    }
                                ],
                                "fallback_text": "题干：结构的可靠性包括（　　）",
                                "meta": {"streamingMode": "block_finalized"},
                            },
                        },
                    },
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
        response = client.get("/api/v1/conversations/session_exact_authority/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[0]["content"].startswith("题干：结构的可靠性包括")
    assert messages[0]["presentation"] is None


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
                "chat_mode": "deep",
                "interaction_hints": {
                    "requested_response_mode": "deep",
                    "selected_mode": "deep",
                },
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
    conversation = response.json()["conversation"]
    assert conversation["id"] == "tb_123"
    assert conversation["preferences"]["interaction_hints"]["requested_response_mode"] == "deep"


def test_get_conversation_messages_prefers_full_question_over_compact_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compact_question = "\n".join(
        [
            "**第1题**",
            "以上 4 项做法中，存在质量隐患的有几项？",
            "A. 1 项",
            "B. 2 项",
            "C. 3 项",
            "D. 4 项",
            "",
            "答案：D",
            "解析：以上做法均存在质量隐患。",
        ]
    )
    full_question = "\n".join(
        [
            "好，考你一道跟刚才内容直接相关的题，看你能不能把知识点用上。",
            "",
            "**题目：**",
            "",
            "某办公楼装修工程施工中，质检员发现以下情况：",
            "",
            "1. 内墙抹灰时，混凝土墙面未做任何处理直接抹灰。",
            "2. 外墙不同基层交接处未挂钢丝网。",
            "3. 不上人吊顶的吊杆长度达到 1.8m，未设置反支撑。",
            "4. 纸面石膏板吊顶板缝对接严密，未留缝隙。",
            "",
            "**问题：**",
            "",
            "以上 4 项做法中，存在质量隐患的有几项？",
            "",
            "A. 1 项",
            "B. 2 项",
            "C. 3 项",
            "D. 4 项",
        ]
    )
    session_rows = [
        {
            "id": "tb_quality",
            "updated_at": 20.0,
            "created_at": 10.0,
            "preferences": {"source": "wx_miniprogram", "user_id": "student_demo"},
        },
        {
            "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_quality",
            "updated_at": 20.0,
            "created_at": 10.0,
            "preferences": {
                "source": "wx_miniprogram",
                "user_id": "student_demo",
                "conversation_id": "tb_quality",
            },
        },
    ]
    session_payloads = {
        "tb_quality": {
            "id": "tb_quality",
            "preferences": {"source": "wx_miniprogram", "archived": False},
            "messages": [
                {
                    "id": 1,
                    "role": "user",
                    "content": "给我出一道题测试",
                    "created_at": 100.0,
                    "events": [],
                },
                {
                    "id": 4,
                    "role": "assistant",
                    "content": compact_question,
                    "created_at": 101.0,
                    "events": [],
                },
            ],
        },
        "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_quality": {
            "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_quality",
            "preferences": {"source": "wx_miniprogram", "archived": False},
            "messages": [
                {
                    "id": 2,
                    "role": "user",
                    "content": "给我出一道题测试",
                    "created_at": 100.5,
                    "events": [],
                },
                {
                    "id": 3,
                    "role": "assistant",
                    "content": full_question,
                    "created_at": 101.0,
                    "events": [],
                },
            ],
        },
    }

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            return "" if session_id == "tb_quality" else "user:student_demo"

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
        response = client.get("/api/v1/conversations/tb_quality/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert "某办公楼装修工程施工中" in messages[1]["content"]
    assert "内墙抹灰时" in messages[1]["content"]
    assert "答案：D" not in messages[1]["content"]
    assert "解析：" not in messages[1]["content"]
    assert messages[1]["content"] != compact_question


def test_merge_mobile_message_rows_keeps_distinct_questions_with_same_options() -> None:
    compact_question = "\n".join(
        [
            "**第1题**",
            "以上 4 项做法中，存在质量隐患的有几项？",
            "A. 1 项",
            "B. 2 项",
            "C. 3 项",
            "D. 4 项",
        ]
    )
    different_question_with_same_options = "\n".join(
        [
            "某混凝土工程施工中，项目部统计了以下 4 项养护做法。",
            "",
            "**问题：**",
            "以上 4 项做法中，符合规范要求的有几项？",
            "A. 1 项",
            "B. 2 项",
            "C. 3 项",
            "D. 4 项",
        ]
    )

    merged = mobile_module._merge_mobile_message_rows(
        [
            {
                "id": 1,
                "role": "assistant",
                "content": compact_question,
                "created_at": 101.0,
                "events": [],
            },
            {
                "id": 2,
                "role": "assistant",
                "content": different_question_with_same_options,
                "created_at": 101.5,
                "events": [],
            },
        ]
    )

    assert [item["content"] for item in merged] == [
        compact_question,
        different_question_with_same_options,
    ]


def test_get_conversation_messages_drops_internal_context_user_bubbles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_internal_context",
        "preferences": {"source": "wx_miniprogram", "archived": False},
        "messages": [
            {
                "id": 1,
                "role": "user",
                "content": "给出一个监理考试土建进度控制的题目",
                "created_at": 100.0,
                "events": [],
            },
            {
                "id": 2,
                "role": "user",
                "content": (
                    "## 参考证据\n"
                    "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
                    "[Question Follow-up Context]\n"
                    "Question ID: tb_q_1\n"
                    "Question type: choice"
                ),
                "created_at": 111.0,
                "events": [],
            },
            {
                "id": 3,
                "role": "assistant",
                "content": "好的，我来出一道进度控制题。",
                "created_at": 112.0,
                "events": [],
            },
        ],
    }

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            return "user:student_demo" if session_id == "session_internal_context" else ""

        async def get_session_with_messages(self, session_id: str):
            return session_payload if session_id == "session_internal_context" else None

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/session_internal_context/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert [item["content"] for item in messages] == [
        "给出一个监理考试土建进度控制的题目",
        "好的，我来出一道进度控制题。",
    ]
    assert "参考证据" not in str(response.json())
    assert "Question Follow-up Context" not in str(response.json())


def test_get_conversation_messages_dedupes_visible_query_from_internal_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visible_query = "给出一个监理考试土建进度控制的题目"
    session_rows = [
        {
            "id": "tb_progress",
            "updated_at": 20.0,
            "created_at": 10.0,
            "preferences": {
                "source": "wx_miniprogram",
                "user_id": "student_demo",
                "bot_id": "construction-exam-coach",
            },
        },
        {
            "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_progress",
            "updated_at": 21.0,
            "created_at": 11.0,
            "preferences": {
                "source": "wx_miniprogram",
                "user_id": "student_demo",
                "conversation_id": "tb_progress",
                "bot_id": "construction-exam-coach",
            },
        },
    ]
    session_payloads = {
        "tb_progress": {
            "id": "tb_progress",
            "preferences": {"source": "wx_miniprogram", "archived": False},
            "messages": [
                {
                    "id": 1,
                    "role": "user",
                    "content": visible_query,
                    "created_at": 100.0,
                    "events": [],
                },
            ],
        },
        "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_progress": {
            "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_progress",
            "preferences": {"source": "wx_miniprogram", "archived": False},
            "messages": [
                {
                    "id": 10,
                    "role": "user",
                    "content": (
                        "## 参考证据\n"
                        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
                        "## 当前用户问题\n"
                        f"{visible_query}"
                    ),
                    "created_at": 112.0,
                    "events": [],
                    "metadata": {"user_visible_query": visible_query},
                },
                {
                    "id": 11,
                    "role": "assistant",
                    "content": "好的，我来出一道进度控制题。",
                    "created_at": 113.0,
                    "events": [],
                },
            ],
        },
    }

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            return "" if session_id == "tb_progress" else "user:student_demo"

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
        response = client.get("/api/v1/conversations/tb_progress/messages")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [item["content"] for item in messages] == [
        visible_query,
        "好的，我来出一道进度控制题。",
    ]
    assert "参考证据" not in str(response.json())


def test_get_conversation_messages_preserves_repeated_visible_user_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_payload = {
        "id": "session_repeated_visible",
        "preferences": {"source": "wx_miniprogram", "archived": False},
        "messages": [
            {
                "id": 1,
                "role": "user",
                "content": "楼梯平台净高要求是什么？",
                "created_at": 100.0,
                "events": [],
            },
            {
                "id": 2,
                "role": "user",
                "content": "楼梯平台净高要求是什么？",
                "created_at": 130.0,
                "events": [],
            },
            {
                "id": 3,
                "role": "assistant",
                "content": "楼梯平台处净高不应小于 2.0m。",
                "created_at": 131.0,
                "events": [],
            },
        ],
    }

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            return "user:student_demo" if session_id == "session_repeated_visible" else ""

        async def get_session_with_messages(self, session_id: str):
            return session_payload if session_id == "session_repeated_visible" else None

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/session_repeated_visible/messages")

    assert response.status_code == 200
    assert [item["content"] for item in response.json()["messages"]] == [
        "楼梯平台净高要求是什么？",
        "楼梯平台净高要求是什么？",
        "楼梯平台处净高不应小于 2.0m。",
    ]


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


def test_get_conversation_messages_returns_empty_for_existing_mobile_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            assert session_id == "session_empty"
            return "user:student_demo"

        async def get_session_with_messages(self, session_id: str):
            assert session_id == "session_empty"
            return {
                "id": "session_empty",
                "preferences": {"source": "wx_miniprogram", "archived": False},
                "messages": [],
            }

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/session_empty/messages")

    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == []
    assert body["conversation"]["id"] == "session_empty"
    assert body["conversation"]["preferences"]["source"] == "wx_miniprogram"


def test_get_conversation_messages_rejects_existing_non_mobile_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            assert session_id == "session_web"
            return "user:student_demo"

        async def get_session_with_messages(self, session_id: str):
            assert session_id == "session_web"
            return {
                "id": "session_web",
                "preferences": {"source": "web", "archived": False},
                "messages": [],
            }

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/conversations/session_web/messages")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


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
            "points": 360,
            "balance_micros": 360_000_000,
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
            "points": 520,
            "balance_micros": 520_000_000,
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
    assert "points" not in calls[0][2]
    assert "balance_micros" not in calls[0][2]
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


def test_auth_profile_allows_explicit_local_wallet_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK", "1")
    monkeypatch.setattr(
        type(mobile_module.wallet_service),
        "is_configured",
        property(lambda _self: False),
    )
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "wx_demo_user",
    )
    monkeypatch.setattr(
        mobile_module,
        "resolve_auth_context",
        lambda *_args, **_kwargs: SimpleNamespace(user_id="wx_demo_user", is_admin=False),
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
        lambda *_args, **_kwargs: "wx_demo_user",
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/auth/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["points"] == 0
    assert body["wallet"]["plan_id"] == "local"


def test_learning_brain_projection_reads_authenticated_learner_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeLearnerStateService:
        def read_compiled_learning_truth(self, user_id):
            captured["user_id"] = user_id
            return {
                "schema_version": 2,
                "subject": "construction_exam_learning_truth",
                "compiled_objects": {
                    "concept:1A432000": {
                        "object_type": "concept",
                        "object_id": "1A432000",
                        "current_truth": "1A432000 上出现 E02 等错因观察",
                        "evidence_level": "L1_repeated",
                        "confidence": 0.72,
                        "supporting_event_ids": ["evt1", "evt2"],
                        "timeline_refs": [{"event_id": "evt1"}],
                        "decay_state": "active",
                    }
                },
                "weak_points": [
                    {
                        "concept_id": "1A432000",
                        "error_code": "E02",
                        "claim": "1A432000 上出现 E02 错因观察",
                        "evidence_level": "L1_repeated",
                        "supporting_event_ids": ["evt1", "evt2"],
                        "recommended_training": {"mode": "case_repair", "focus": "专家论证程序"},
                    }
                ],
                "typed_graph": {
                    "edges": [
                        {
                            "edge_type": "question_tests_concept",
                            "from": {"type": "question", "id": "case_001"},
                            "to": {"type": "concept", "id": "1A432000"},
                        },
                        {
                            "edge_type": "error_points_to_training",
                            "from": {"type": "error", "id": "1A432000:E02"},
                            "to": {"type": "next_training", "id": "1A432000:E02:case_repair"},
                        }
                    ],
                    "readiness_gaps": [],
                },
                "synthesis_run": {
                    "input_event_count": 2,
                    "created_claim_count": 1,
                    "output_projection_hash": "sha256:test",
                },
            }

        def synthesize_learning_truth(self, *_args, **_kwargs):
            raise AssertionError("mobile projection must not synthesize compiled truth online")

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/learning-brain/projection?event_limit=25")

    assert response.status_code == 200
    body = response.json()
    assert captured == {"user_id": "student_demo"}
    assert body["projection_subject"] == "construction_exam_learning_truth"
    assert body["event_count"] == 2
    assert body["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert body["visible_sections"]["current_truth"][0]["current_truth"].startswith("工程招标投标与合同管理")
    assert body["visible_sections"]["current_truth"][0]["display_meta"] == "知识点：工程招标投标与合同管理"
    assert body["visible_sections"]["evidence_flow"][0]["event_id"] == ""
    assert body["visible_sections"]["evidence_flow"][0]["event_label"] == "最近一次批改"
    assert body["visible_sections"]["next_training"][0]["recommended_training"] == {}
    assert body["visible_sections"]["next_training"][0]["display_meta"] == (
        "知识点：工程招标投标与合同管理；错因：采分点遗漏；案例题补强"
    )
    assert body["typed_graph_edge_count"] == 4
    assert any(edge["edge_type"] == "training_not_improved_error" for edge in body["typed_graph_edges"])
    assert body["graph_chain"]["has_training_uses_question"] is True
    assert body["graph_chain"]["has_training_not_improved_error"] is True


def test_learning_brain_projection_returns_empty_read_model_without_compiled_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLearnerStateService:
        def read_compiled_learning_truth(self, user_id):
            return {}

        def synthesize_learning_truth(self, *_args, **_kwargs):
            raise AssertionError("mobile projection must not synthesize compiled truth online")

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/learning-brain/projection")

    assert response.status_code == 200
    body = response.json()
    assert body["projection_subject"] == "construction_exam_learning_truth"
    assert body["event_count"] == 0
    assert body["visible_sections"] == {
        "current_truth": [],
        "evidence_flow": [],
        "next_training": [],
    }


def test_learning_brain_projection_local_qa_can_fallback_to_dry_run_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeLearnerStateService:
        def read_compiled_learning_truth(self, user_id):
            calls["read_user_id"] = user_id
            return {}

        def synthesize_learning_truth(self, user_id, *, dry_run, event_limit):
            calls["synthesis"] = {
                "user_id": user_id,
                "dry_run": dry_run,
                "event_limit": event_limit,
            }
            return {
                "projection": {
                    "schema_version": 2,
                    "subject": "construction_exam_learning_truth",
                    "compiled_objects": {
                        "concept:1A432000": {
                            "object_type": "concept",
                            "object_id": "1A432000",
                            "current_truth": "1A432000 上出现 E02 错因观察",
                            "evidence_level": "L1_repeated",
                            "supporting_event_ids": ["evt1", "evt2"],
                        }
                    },
                    "weak_points": [
                        {
                            "concept_id": "1A432000",
                            "error_code": "E02",
                            "claim": "1A432000 上出现 E02 错因观察",
                            "evidence_level": "L1_repeated",
                            "supporting_event_ids": ["evt1", "evt2"],
                        }
                    ],
                    "typed_graph": {"edges": []},
                    "synthesis_run": {"input_event_count": 2},
                }
            }

    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.setenv("DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK", "1")
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/learning-brain/projection?event_limit=25")

    assert response.status_code == 200
    body = response.json()
    assert calls == {
        "read_user_id": "student_demo",
        "synthesis": {"user_id": "student_demo", "dry_run": True, "event_limit": 25},
    }
    assert body["event_count"] == 2
    assert body["weak_points"][0]["evidence_level"] == "L1_repeated"


def test_mobile_learning_report_uses_learning_evidence_for_recent_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeMemberService:
        def get_today_progress(self, user_id):
            captured["legacy_today_user_id"] = user_id
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_home_dashboard(self, user_id):
            return {
                "review": {"due_today": 0, "overdue": 0},
                "mastery": {"weak_nodes": []},
                "today": {"hint": "优先补强 建筑构造"},
            }

        def get_assessment_profile(self, user_id):
            return {"level": "beginner", "chapter_mastery": {}}

        def get_mastery_dashboard(self, user_id):
            return {"overall_mastery": 0, "groups": [], "hotspots": [], "review_summary": {"total_due": 0}}

    class FakeLearnerStateService:
        def list_memory_events(self, user_id, limit=100):
            captured["event_user_id"] = user_id
            created_at = datetime.now(_SH_TZ).replace(microsecond=0).isoformat()
            return [
                SimpleNamespace(
                    event_id="evt1",
                    user_id=user_id,
                    source_feature="construction_grading",
                    source_id="turn:evt1",
                    source_bot_id="construction-exam",
                    memory_kind="learning_evidence",
                    dedupe_key="evt1",
                    created_at=created_at,
                    payload_json={
                        "event_type": "learning_evidence",
                        "question_id": "case_001",
                        "score_awarded": 0,
                        "max_score": 1,
                        "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
                        "next_training_signal": {"concept": "1A432000", "mode": "case_repair"},
                    },
                )
            ]

        def read_compiled_learning_truth(self, user_id):
            return {}

        def synthesize_learning_truth(self, user_id, *, dry_run, event_limit):
            return {
                "projection": {
                    "schema_version": 2,
                    "subject": "construction_exam_learning_truth",
                    "compiled_objects": {},
                    "weak_points": [
                        {
                            "concept_id": "1A432000",
                            "error_code": "E02",
                            "claim": "1A432000 上出现 E02 错因观察",
                            "evidence_level": "L0_observed",
                            "supporting_event_ids": ["evt1"],
                        }
                    ],
                    "typed_graph": {"edges": [], "readiness_gaps": []},
                    "synthesis_run": {"input_event_count": 1, "created_claim_count": 0},
                }
            }

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "member_service", FakeMemberService())
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/mobile/learning-report?event_limit=25")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["authority"]["read_model"] == "learning-report-read-model"
    assert body["authority"]["progress_source"] == "learner_memory_events.learning_evidence"
    assert body["authority"]["learning_brain_source"] in {
        "compiled_learning_truth",
        "dry_run_learning_evidence",
    }
    assert body["overview"]["today_done"] == 1
    assert body["overview"]["attempt_count"] == 1
    assert body["overview"]["unique_question_count"] == 1
    assert body["overview"]["today_unique_questions"] == 1
    assert body["progress_feedback"]["cards"][0]["label"] == "近 3 天完成"
    assert body["progress_feedback"]["cards"][0]["value"] == "1题"
    assert body["legacy_compat"]["today_progress"]["today_done"] == 0
    # degraded 契约：所有源 ok → degraded=false / degraded_sources=[]
    assert body["degraded"] is False
    assert body["degraded_sources"] == []
    for status in body["source_status"].values():
        assert status["ok"] in (True, None)
    assert body["freshness"]["window_truncated"] is False
    assert body["freshness"]["unknown_date_count"] == 0


def test_mobile_assessment_topics_returns_catalog_without_chat_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Member:
        def get_assessment_topic_catalog(self, user_id):
            captured["user_id"] = user_id
            captured["catalog_called"] = True
            return {
                "recommendation": {
                    "recommended_mode": "topic",
                    "recommended_topic_id": "waterproof",
                    "recommended_count": 12,
                    "reason": "建议先测防水工程",
                },
                "topics": [
                    {
                        "topic_id": "waterproof",
                        "label": "防水工程",
                        "blueprint_version": "topic_waterproof_v1",
                        "status": "stable",
                        "enabled": True,
                        "form_count": 5,
                        "minimum_form_count": 3,
                        "target_form_count": 5,
                    }
                ]
            }

    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")
    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(
        mobile_module,
        "turn_runtime",
        SimpleNamespace(start_turn=AsyncMock(side_effect=AssertionError("assessment topics must not start a turn"))),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/assessment/topics")

    assert response.status_code == 200
    body = response.json()
    assert captured["catalog_called"] is True
    assert captured["user_id"] == "student_demo"
    assert body["recommendation"]["recommended_topic_id"] == "waterproof"
    assert body["topics"][0]["topic_id"] == "waterproof"
    assert body["topics"][0]["status"] == "stable"
    assert body["topics"][0]["form_count"] == 5


def test_mobile_learning_report_dual_emits_v2_without_breaking_v1_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMemberService:
        def get_today_progress(self, user_id):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_home_dashboard(self, user_id):
            return {
                "review": {"due_today": 1},
                "mastery": {"weak_nodes": []},
                "today": {"hint": "优先补主体结构"},
                "today_focus": {"title": "今日焦点：主体结构"},
                "recommended_prompts": [
                    {
                        "prompt_type": "practice_prompt",
                        "text": "练 3 道主体结构题",
                        "intent": {"source": "home_dashboard"},
                    }
                ],
            }

        def get_assessment_profile(self, user_id):
            return {"level": "beginner", "chapter_mastery": {"主体结构": {"name": "主体结构", "mastery": 30}}}

        def get_mastery_dashboard(self, user_id):
            return {"overall_mastery": 30, "groups": [], "hotspots": [], "review_summary": {"total_due": 1}}

    class FakeLearnerStateService:
        def list_memory_events(self, user_id, limit=100):
            return []

        def read_compiled_learning_truth(self, user_id):
            return {}

        def synthesize_learning_truth(self, user_id, *, dry_run, event_limit):
            return {"projection": {}}

    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")
    monkeypatch.setattr(mobile_module, "member_service", FakeMemberService())
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/mobile/learning-report?schema_version=2")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 2
    assert body["authority"]["conversation_source"] == "learner_memory_events.learning_evidence[evidence_source=conversation_synthesis]"
    assert body["authority"]["attempt_detail_source"] == "attempt-detail-read-model"
    assert body["authority"]["mistake_book_source"] == "learner_mistake_book_items"
    assert body["recent_attempts"] == body["learner_facing"]["recent_attempts"]
    assert body["timeline"] == body["learner_facing"]["evidence_timeline"]
    assert body["training_loop_cards"] == body["learner_facing"]["training_loops"]
    assert body["hero"]["primary_cta"]["intent"]["source"] == "learning_report"
    assert body["home_personalization"]["recommended_prompt_count"] == 1
    assert isinstance(body["mastery"]["overall_mastery"], dict)


def test_mobile_learning_report_accept_header_negotiates_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    class _Member:
        def get_today_progress(self, user_id):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_home_dashboard(self, user_id):
            return {"review": {"due_today": 0}, "mastery": {"weak_nodes": []}, "today": {"hint": ""}}

        def get_assessment_profile(self, user_id):
            return {"level": "beginner", "chapter_mastery": {}}

        def get_mastery_dashboard(self, user_id):
            return {"overall_mastery": 0, "groups": [], "hotspots": [], "review_summary": {"total_due": 0}}

    class _Learner:
        def list_memory_events(self, user_id, limit=100):
            return []

        def read_compiled_learning_truth(self, user_id):
            return {}

        def synthesize_learning_truth(self, user_id, *, dry_run, event_limit):
            return {"projection": {}}

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "learner_state_service", _Learner())

    with TestClient(_build_app()) as client:
        response = client.get(
            "/api/v1/mobile/learning-report",
            headers={"Accept": "application/vnd.deeptutor.learning-report+json;v=2"},
        )

    assert response.status_code == 200
    assert response.json()["schema_version"] == 2


def test_mobile_learning_report_accept_header_does_not_treat_v20_as_v2() -> None:
    assert (
        mobile_module._learning_report_schema_version(
            schema_version=1,
            accept="application/vnd.deeptutor.learning-report+json;v=20",
        )
        == 1
    )


def test_mobile_learning_report_requires_authentication() -> None:
    """无 Authorization → 401，不暴露 user_id。"""
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/mobile/learning-report")
    assert response.status_code == 401
    body = response.json()
    assert "user_id" not in body
    assert body.get("detail")


def test_mobile_learning_attempt_detail_returns_user_facing_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
    from deeptutor.services.learner_state.service import LearnerStateEvent

    event = LearnerStateEvent(
        event_id="evt_mobile_detail",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id="turn:evt_mobile_detail",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="evt_mobile_detail",
        created_at=datetime.now(_SH_TZ).isoformat(),
        payload_json={
            "event_type": "learning_evidence",
            "question_id": "q-mobile",
            "question_stem": "主体结构验收条件是什么？",
            "options": {"A": "先施工后验收", "B": "施工质量验收合格后进入下一步"},
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": {"summary": "先看验收前置条件。"},
            "error_events": [{"error_code": "M06", "concept_tag": "1A432000"}],
        },
    )

    class FakeLearnerStateService:
        def read_learning_evidence_event(self, user_id, event_id, *, max_age_seconds=None):
            assert user_id == "student_demo"
            assert event_id == "evt_mobile_detail"
            return event

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())

    attempt_ref = sign_attempt_ref(user_id="student_demo", event_id="evt_mobile_detail", question_id="q-mobile")
    with TestClient(_build_app()) as client:
        response = client.get(f"/api/v1/mobile/learning-attempts/{attempt_ref}")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["question"]["stem"] == "主体结构验收条件是什么？"
    assert body["answer"]["user_answer"] == "A"
    assert body["explanation"]["summary"] == "先看验收前置条件。"
    assert body["diagnosis"]["error_label"] == "多选漏选"
    assert body["conversation"]["turns"] == [
        {
            "role": "system",
            "label": "系统出题",
            "content": "主体结构验收条件是什么？\nA. 先施工后验收\nB. 施工质量验收合格后进入下一步",
        },
        {"role": "student", "label": "学员作答", "content": "A"},
        {
            "role": "system",
            "label": "系统解析",
            "content": "答错。正确答案：B\n先看验收前置条件。\n错因：多选漏选",
        },
    ]
    assert "evt_mobile_detail" not in str(body)
    assert "M06" not in str(body)


def test_mobile_learning_attempt_detail_uses_history_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
    from deeptutor.services.learner_state.service import LearnerStateEvent

    event = LearnerStateEvent(
        event_id="evt_mobile_history_detail",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id="turn:turn_mobile_history:q1",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="evt_mobile_history_detail",
        created_at=datetime.now(_SH_TZ).isoformat(),
        payload_json={
            "event_type": "learning_evidence",
            "session_id": "tb_mobile_history",
            "turn_id": "turn_mobile_history:q1",
            "question_id": "q-mobile-history",
            "question_stem": "验槽通常主要采用什么方法？",
            "user_answer": "B",
            "correct_answer": "A",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": {"summary": "B 选项不符合标准答案。"},
            "error_events": [{"error_code": "M03", "concept_tag": "验槽方法"}],
        },
    )

    class FakeLearnerStateService:
        def read_learning_evidence_event(self, user_id, event_id, *, max_age_seconds=None):
            assert user_id == "student_demo"
            assert event_id == "evt_mobile_history_detail"
            return event

    class FakeSessionStore:
        async def get_session_with_messages(self, session_id):
            assert session_id == "tb_mobile_history"
            return {
                "id": "tb_mobile_history",
                "messages": [
                    {
                        "role": "assistant",
                        "content": "### 为什么错\n你把辅助手段当成主要方法，混淆了验槽方法的主次关系。",
                        "events": [{"metadata": {"turn_id": "turn_mobile_history"}}],
                    }
                ],
            }

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "learner_state_service", FakeLearnerStateService())
    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())

    attempt_ref = sign_attempt_ref(
        user_id="student_demo", event_id="evt_mobile_history_detail", question_id="q-mobile-history"
    )
    with TestClient(_build_app()) as client:
        response = client.get(f"/api/v1/mobile/learning-attempts/{attempt_ref}")

    assert response.status_code == 200
    body = response.json()
    assert "主次关系" in body["explanation"]["full_text"]
    assert "B 选项不符合标准答案" not in body["conversation"]["turns"][-1]["content"]


def test_mobile_mistake_book_save_list_remove_and_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
    from deeptutor.services.learner_state.mistake_book import InMemoryMistakeBookStore, MistakeBookService

    service = MistakeBookService(store=InMemoryMistakeBookStore())
    monkeypatch.setattr(mobile_module, "mistake_book_service", service)
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", "true")
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", "true")
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    attempt_ref = sign_attempt_ref(user_id="student_demo", event_id="evt_mistake_api", question_id="q1")
    with TestClient(_build_app()) as client:
        save_response = client.post(
            "/api/v1/mobile/mistake-book/items",
            json={
                "attempt_ref": attempt_ref,
                "subject_id": "construction_exam_1",
                "title": "主体结构错题",
            },
        )
        assert save_response.status_code == 200
        saved = save_response.json()
        assert saved["is_bookmarked"] is True
        assert saved["etag"]

        list_response = client.get("/api/v1/mobile/mistake-book?subject_id=construction_exam_1")
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1

        stale_response = client.delete(
            f"/api/v1/mobile/mistake-book/items/{attempt_ref}",
            headers={"If-Match": "stale"},
        )
        assert stale_response.status_code == 409
        assert stale_response.json()["detail"]["latest"]["is_bookmarked"] is True

        delete_response = client.delete(
            f"/api/v1/mobile/mistake-book/items/{attempt_ref}",
            headers={"If-Match": saved["etag"]},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["is_bookmarked"] is False


def test_mobile_mistake_book_flags_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
    from deeptutor.services.learner_state.mistake_book import InMemoryMistakeBookStore, MistakeBookService

    service = MistakeBookService(store=InMemoryMistakeBookStore())
    monkeypatch.setattr(mobile_module, "mistake_book_service", service)
    monkeypatch.delenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", raising=False)
    monkeypatch.delenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", raising=False)
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    attempt_ref = sign_attempt_ref(user_id="student_demo", event_id="evt_disabled", question_id="q1")

    with TestClient(_build_app()) as client:
        list_response = client.get("/api/v1/mobile/mistake-book?subject_id=construction_exam_1")
        assert list_response.status_code == 404
        assert list_response.json()["detail"] == "mistake_book_disabled"

        save_response = client.post(
            "/api/v1/mobile/mistake-book/items",
            json={"attempt_ref": attempt_ref, "subject_id": "construction_exam_1"},
        )
        assert save_response.status_code == 404
        assert save_response.json()["detail"] == "mistake_book_write_disabled"


def test_mobile_mistake_book_mastered_and_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
    from deeptutor.services.learner_state.mistake_book import InMemoryMistakeBookStore, MistakeBookService

    service = MistakeBookService(store=InMemoryMistakeBookStore())
    monkeypatch.setattr(mobile_module, "mistake_book_service", service)
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", "true")
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", "true")
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    attempt_ref = sign_attempt_ref(user_id="student_demo", event_id="evt_review_api", question_id="q1")

    with TestClient(_build_app()) as client:
        saved = client.post(
            "/api/v1/mobile/mistake-book/items",
            json={"attempt_ref": attempt_ref, "subject_id": "construction_exam_1"},
        ).json()
        reviewed_response = client.post(
            f"/api/v1/mobile/mistake-book/items/{attempt_ref}/review",
            headers={"If-Match": saved["etag"]},
        )
        assert reviewed_response.status_code == 200
        reviewed = reviewed_response.json()
        assert reviewed["last_reviewed_at"]
        assert reviewed["review_due_at"]

        mastered_response = client.post(
            f"/api/v1/mobile/mistake-book/items/{attempt_ref}/mastered",
            headers={"If-Match": reviewed["etag"]},
        )
        assert mastered_response.status_code == 200
        assert mastered_response.json()["mastered_at"]


def test_mobile_assessment_testset_routes_delegate_with_auth_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, object]] = []

    class _Member:
        def create_assessment(self, user_id, **kwargs):
            calls.append(("create", user_id, kwargs))
            return {
                "quiz_id": "quiz_p0a",
                "assessment_type": kwargs["assessment_type"],
                "topic_ids": kwargs["topic_ids"],
                "questions": [],
            }

        def get_assessment_session(self, user_id, quiz_id):
            calls.append(("resume", user_id, quiz_id))
            return {"quiz_id": quiz_id, "status": "in_progress", "questions": []}

        def get_assessment_report(self, user_id, quiz_id):
            calls.append(("report", user_id, quiz_id))
            return {"schema_version": "p0a-v1", "quiz_id": quiz_id}

        def submit_assessment(self, user_id, quiz_id, *, answers, time_spent_seconds):
            calls.append(
                (
                    "submit",
                    user_id,
                    {
                        "quiz_id": quiz_id,
                        "answers": answers,
                        "time_spent_seconds": time_spent_seconds,
                    },
                )
            )
            return {
                "schema_version": "p0a-v1",
                "quiz_id": quiz_id,
                "score_summary": {"score_pct": 50},
            }

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        created = client.post(
            "/api/v1/assessment/create",
            json={
                "assessment_type": "topic_diagnostic",
                "subject_id": "construction_exam",
                "topic_ids": ["waterproof"],
                "count": 12,
            },
        )
        resumed = client.get("/api/v1/assessment/quiz_p0a")
        submitted = client.post(
            "/api/v1/assessment/quiz_p0a/submit",
            json={"answers": {"q1": "A"}, "time_spent_seconds": 90},
        )
        report = client.get("/api/v1/assessment/quiz_p0a/report")

    assert created.status_code == 200
    assert resumed.status_code == 200
    assert submitted.status_code == 200
    assert report.status_code == 200
    assert calls[0] == (
        "create",
        "student_demo",
        {
            "assessment_type": "topic_diagnostic",
            "subject_id": "construction_exam",
            "topic_ids": ["waterproof"],
            "count": 12,
            "duration_policy": {},
        },
    )
    assert calls[1] == ("resume", "student_demo", "quiz_p0a")
    assert calls[2] == (
        "submit",
        "student_demo",
        {"quiz_id": "quiz_p0a", "answers": {"q1": "A"}, "time_spent_seconds": 90},
    )
    assert calls[3] == ("report", "student_demo", "quiz_p0a")


def test_mobile_assessment_topics_routes_delegate_with_auth_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class _Member:
        def get_assessment_topic_catalog(self, user_id):
            calls.append(("topics", "student_demo"))
            return {
                "topics": [
                    {
                        "topic_id": "waterproof",
                        "label": "防水工程",
                        "blueprint_version": "topic_waterproof_v1",
                        "status": "stable",
                        "enabled": True,
                        "form_count": 5,
                    }
                ]
            }

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "student_demo")

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/assessment/topics")

    assert response.status_code == 200
    assert response.json()["topics"][0]["topic_id"] == "waterproof"
    assert calls == [("topics", "student_demo")]


def test_mobile_assessment_deep_explanation_delegates_without_chat_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeMemberService:
        async def get_assessment_deep_explanation(self, user_id: str, quiz_id: str, question_id: str):
            calls.append((user_id, quiz_id, question_id))
            return {
                "quiz_id": quiz_id,
                "question_id": question_id,
                "cache_status": "generated",
                "billing": {"status": "captured", "amount_points": 20},
                "explanation": {"summary": "先看防水节点构造。"},
            }

    monkeypatch.setattr(mobile_module, "member_service", FakeMemberService())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "turn_runtime",
        SimpleNamespace(start_turn=AsyncMock(side_effect=AssertionError("assessment explanation must not start a turn"))),
    )

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/assessment/quiz_1/items/q1/explain")

    assert response.status_code == 200
    assert response.json()["explanation"]["summary"] == "先看防水节点构造。"
    assert calls == [("student_demo", "quiz_1", "q1")]


def test_mobile_assessment_deep_explanation_maps_billing_failures_to_402(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMemberService:
        async def get_assessment_deep_explanation(self, user_id: str, quiz_id: str, question_id: str):
            raise RuntimeError("assessment_deep_explanation_insufficient_balance")

    monkeypatch.setattr(mobile_module, "member_service", FakeMemberService())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/assessment/quiz_1/items/q1/explain")

    assert response.status_code == 402
    assert response.json()["detail"] == "assessment_deep_explanation_insufficient_balance"


@pytest.mark.parametrize("event_limit", [0, 501, -1])
def test_mobile_learning_report_rejects_event_limit_out_of_range(
    event_limit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    with TestClient(_build_app()) as client:
        response = client.get(f"/api/v1/mobile/learning-report?event_limit={event_limit}")
    assert response.status_code == 422


@pytest.mark.parametrize("event_limit", [1, 500])
def test_mobile_learning_report_accepts_event_limit_boundaries(
    event_limit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    class _Member:
        def get_today_progress(self, user_id):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_home_dashboard(self, user_id):
            return {"review": {"due_today": 0}, "mastery": {"weak_nodes": []}, "today": {"hint": ""}}

        def get_assessment_profile(self, user_id):
            return {"level": "beginner", "chapter_mastery": {}}

        def get_mastery_dashboard(self, user_id):
            return {"overall_mastery": 0, "groups": [], "hotspots": [], "review_summary": {"total_due": 0}}

    class _Learner:
        def list_memory_events(self, user_id, limit=100):
            return []

        def read_compiled_learning_truth(self, user_id):
            return {}

        def synthesize_learning_truth(self, user_id, *, dry_run, event_limit):
            return {"projection": {}}

    monkeypatch.setattr(mobile_module, "member_service", _Member())
    monkeypatch.setattr(mobile_module, "learner_state_service", _Learner())

    with TestClient(_build_app()) as client:
        response = client.get(f"/api/v1/mobile/learning-report?event_limit={event_limit}")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1


def test_mobile_learning_report_propagates_source_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FlakyMember:
        def get_today_progress(self, user_id):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_home_dashboard(self, user_id):
            return {"review": {"due_today": 0}, "mastery": {"weak_nodes": []}, "today": {"hint": ""}}

        def get_assessment_profile(self, user_id):
            return {"level": "beginner", "chapter_mastery": {}}

        def get_mastery_dashboard(self, user_id):
            raise RuntimeError("mastery offline: simulated outage")

    class _Learner:
        def list_memory_events(self, user_id, limit=100):
            return [
                SimpleNamespace(
                    event_id="evt1",
                    user_id=user_id,
                    source_feature="construction_grading",
                    source_id="turn:evt1",
                    source_bot_id="construction-exam",
                    memory_kind="learning_evidence",
                    dedupe_key="evt1",
                    created_at="2026-05-20T10:00:00+08:00",
                    payload_json={
                        "event_type": "learning_evidence",
                        "question_id": "case_001",
                        "score_awarded": 0,
                        "max_score": 1,
                        "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
                        "next_training_signal": {"concept": "1A432000", "mode": "case_repair"},
                    },
                )
            ]

        def read_compiled_learning_truth(self, user_id):
            return {}

        def synthesize_learning_truth(self, user_id, *, dry_run, event_limit):
            return {"projection": {}}

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )
    monkeypatch.setattr(mobile_module, "member_service", FlakyMember())
    monkeypatch.setattr(mobile_module, "learner_state_service", _Learner())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/mobile/learning-report?event_limit=10")
    assert response.status_code == 200
    body = response.json()
    # degraded / degraded_sources / source_status 三者必须同步
    assert body["degraded"] is True
    assert "mastery_dashboard" in body["degraded_sources"]
    assert body["source_status"]["mastery_dashboard"]["ok"] is False
    assert "RuntimeError" in (body["source_status"]["mastery_dashboard"]["error"] or "")
    # 其它源仍可用，evidence-driven 进度照常输出
    assert body["source_status"]["learner_events"]["ok"] is True
    assert body["overview"]["today_done"] >= 0
    assert body["overview"]["attempt_count"] >= 0


def test_auth_profile_exposes_is_admin_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "admin_demo",
    )
    monkeypatch.setattr(
        mobile_module,
        "resolve_auth_context",
        lambda *_args, **_kwargs: SimpleNamespace(user_id="admin_demo", is_admin=True),
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_profile",
        lambda user_id: {
            "user_id": user_id,
            "display_name": "管理员",
        },
    )
    monkeypatch.setattr(
        mobile_module,
        "resolve_wallet_user_id",
        lambda *_args, **_kwargs: "admin_demo",
    )
    monkeypatch.setattr(mobile_module.wallet_service, "_base_url", "https://example.supabase.co")
    monkeypatch.setattr(mobile_module.wallet_service, "_service_key", "test-service-key")
    monkeypatch.setattr(
        mobile_module.wallet_service,
        "get_wallet",
        lambda _user_id: SimpleNamespace(
            user_id="admin_demo",
            balance_micros=0,
            frozen_micros=0,
            plan_id="",
            version=1,
            created_at="2026-04-23T00:00:00+08:00",
        ),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/auth/profile")

    assert response.status_code == 200
    assert response.json()["is_admin"] is True


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
                        "chat_mode": "deep",
                        "interaction_hints": {
                            "requested_response_mode": "deep",
                            "selected_mode": "deep",
                        },
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
    assert conversations[0]["preferences"]["chat_mode"] == "deep"
    assert conversations[0]["preferences"]["interaction_hints"]["requested_response_mode"] == "deep"
    assert conversations[0]["preferences"]["interaction_hints"]["selected_mode"] == "deep"


def test_list_conversations_sanitizes_internal_context_titles_and_previews(
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
            assert owner_key == "user:student_demo"
            assert source == "wx_miniprogram"
            return [
                {
                    "id": "tb_internal_list",
                    "title": (
                        "## 参考证据\n"
                        "以下内容是辅助证据，不得覆盖当前用户问题。\n\n"
                        "## 当前用户问题\n"
                        "给出一个监理考试土建进度控制的题目"
                    ),
                    "updated_at": 20.0,
                    "created_at": 10.0,
                    "message_count": 2,
                    "last_message": (
                        "## 参考证据\n"
                        "以下内容是辅助证据，不得覆盖当前用户问题。\n\n"
                        "[Question Follow-up Context]\n"
                        "Question ID: tb_q_1"
                    ),
                    "preferences": {"source": "wx_miniprogram"},
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
    conversation = response.json()["conversations"][0]
    assert conversation["title"] == "给出一个监理考试土建进度控制的题目"
    assert conversation["last_message"] == ""
    assert "参考证据" not in str(response.json())
    assert "Question Follow-up Context" not in str(response.json())


def test_list_conversations_exposes_explicit_time_units(
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
                    "id": "session_1",
                    "title": "会话一",
                    "created_at": 1_700_000_000.25,
                    "updated_at": 1_700_000_100.5,
                    "message_count": 1,
                    "preferences": {"source": "wx_miniprogram"},
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
    conversation = response.json()["conversations"][0]
    assert conversation["created_at"] == mobile_module._ts_to_iso(1_700_000_000.25)
    assert conversation["updated_at"] == mobile_module._ts_to_iso(1_700_000_100.5)
    assert conversation["created_at_ms"] == 1_700_000_000_250
    assert conversation["updated_at_ms"] == 1_700_000_100_500


def test_delete_conversation_deletes_direct_and_mirror_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []

    class FakeSessionStore:
        async def get_session_owner_key(self, session_id: str) -> str:
            if session_id == "tb_123":
                return "user:student_demo"
            return ""

        async def list_sessions_by_owner_and_conversation(
            self,
            owner_key: str,
            conversation_id: str,
            source: str | None = None,
            archived: bool | None = None,
            limit: int = 50,
        ):
            assert owner_key == "user:student_demo"
            assert conversation_id == "tb_123"
            return [
                {
                    "id": "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123",
                    "preferences": {
                        "source": "wx_miniprogram",
                        "conversation_id": "tb_123",
                    },
                }
            ]

        async def delete_session(self, session_id: str) -> bool:
            deleted.append(session_id)
            return True

    monkeypatch.setattr(mobile_module, "session_store", FakeSessionStore())
    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda *_args, **_kwargs: "student_demo",
    )

    with TestClient(_build_app()) as client:
        response = client.delete("/api/v1/conversations/tb_123")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert deleted == [
        "tb_123",
        "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_123",
    ]


class _FakeBalanceWalletService:
    """Minimal wallet service stub for the H3 hard balance gate tests."""

    is_configured = True

    def __init__(self, *, balance_micros: int, frozen_micros: int = 0) -> None:
        self._snapshot = mobile_module.WalletSnapshot(
            user_id="wallet_demo",
            balance_micros=balance_micros,
            frozen_micros=frozen_micros,
            plan_id="advance",
            version=1,
            created_at="2026-04-21T10:00:00+08:00",
        )

    def get_wallet(self, user_id: str):
        del user_id
        return self._snapshot

    def list_wallet_ledger(self, user_id: str, *, limit: int = 20, offset: int = 0):
        del user_id, limit, offset
        return []


def _install_start_turn_stubs(monkeypatch: pytest.MonkeyPatch, started: list[object]) -> None:
    class FakeTurnRuntime:
        async def start_turn(self, payload):
            started.append(payload)
            return (
                {"id": "session_1", "title": "New conversation", "created_at": 1_700_000_000.0},
                {"id": "turn_1", "status": "running", "capability": ""},
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(
        mobile_module, "_resolve_authenticated_user_id", lambda *_a, **_k: "student_demo"
    )
    monkeypatch.setattr(
        mobile_module, "_resolve_wallet_lookup_user_id", lambda *_a, **_k: "wallet_demo"
    )
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(get_session_owner_key=AsyncMock(return_value="user:student_demo")),
    )


def test_mobile_chat_start_turn_hard_balance_gate_rejects_when_enforced_and_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "true")
    started: list[object] = []
    _install_start_turn_stubs(monkeypatch, started)
    # Available balance (balance - frozen) below the per-turn minimum charge
    # (20 points = 20_000_000 micros).
    monkeypatch.setattr(
        mobile_module, "wallet_service", _FakeBalanceWalletService(balance_micros=1_000_000)
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={"query": "考我一道题", "mode": "AUTO", "language": "zh"},
        )

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == "billing_quota_exceeded"
    assert detail["limited_by"] == "balance"
    assert detail["required_micros"] == 20_000_000
    # Fail-closed before delivery: no pending turn was ever created.
    assert started == []


def test_mobile_chat_start_turn_hard_balance_gate_allows_when_enforced_and_sufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "true")
    started: list[object] = []
    _install_start_turn_stubs(monkeypatch, started)
    monkeypatch.setattr(
        mobile_module, "wallet_service", _FakeBalanceWalletService(balance_micros=500_000_000)
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={"query": "考我一道题", "mode": "AUTO", "language": "zh"},
        )

    assert response.status_code == 200
    assert response.json()["turn"]["id"] == "turn_1"
    assert len(started) == 1


def test_mobile_chat_start_turn_hard_balance_gate_is_off_during_internal_beta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Enforcement OFF (default): even an empty wallet must not block start-turn.
    monkeypatch.delenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", raising=False)
    started: list[object] = []
    _install_start_turn_stubs(monkeypatch, started)
    monkeypatch.setattr(
        mobile_module, "wallet_service", _FakeBalanceWalletService(balance_micros=0)
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/chat/start-turn",
            json={"query": "考我一道题", "mode": "AUTO", "language": "zh"},
        )

    assert response.status_code == 200
    assert response.json()["turn"]["id"] == "turn_1"
    assert len(started) == 1


def test_mobile_chat_start_turn_rejects_oversized_query() -> None:
    """H9: query above the F5-equivalent char cap is rejected fail-fast (422),
    not silently accepted into an expensive turn."""
    oversized = "x" * (mobile_module._MAX_MOBILE_START_TURN_QUERY_CHARS + 1)
    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/chat/start-turn", json={"query": oversized})
    assert response.status_code == 422


def test_mobile_chat_start_turn_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """H9: the paid HTTP start-turn entry is rate limited (10/60s), closing the
    F5-shaped amplification surface on the mobile HTTP side."""

    class FakeTurnRuntime:
        async def start_turn(self, payload):
            return (
                {"id": "session_1", "title": "c", "created_at": 1_700_000_000.0},
                {"id": "turn_1", "status": "running", "capability": ""},
            )

    monkeypatch.setattr(mobile_module, "turn_runtime", FakeTurnRuntime())
    monkeypatch.setattr(
        mobile_module, "_resolve_authenticated_user_id", lambda *a, **k: "student_demo"
    )
    monkeypatch.setattr(
        mobile_module, "_resolve_wallet_lookup_user_id", lambda *a, **k: "wallet_demo"
    )
    monkeypatch.setattr(
        mobile_module,
        "session_store",
        SimpleNamespace(get_session_owner_key=AsyncMock(return_value="user:student_demo")),
    )

    statuses: list[int] = []
    with TestClient(_build_app()) as client:
        for _ in range(11):
            statuses.append(
                client.post("/api/v1/chat/start-turn", json={"query": "考一道题"}).status_code
            )

    assert statuses[:10] == [200] * 10  # first 10 within the window pass
    assert statuses[10] == 429  # 11th over the limit is rejected
