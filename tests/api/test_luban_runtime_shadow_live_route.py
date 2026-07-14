from __future__ import annotations

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext
from deeptutor.capabilities import deep_question as deep_question_module
from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus

secure_router_mod = importlib.import_module("deeptutor.api._secure_router")
ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
mobile_module = importlib.import_module("deeptutor.api.routers.mobile")


def _build_ws_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ws_module.router, prefix="/api/v1")
    return app


def _auth_ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id, "canonical_uid": user_id},
        is_admin=is_admin,
    )


class _FakeRuntime:
    def __init__(self) -> None:
        self.started_payload: dict[str, Any] | None = None

    async def start_turn(self, payload: dict[str, Any]):
        self.started_payload = dict(payload)
        return {"id": str(payload.get("session_id") or "session_live_route")}, {"id": "turn_live_route"}

    async def subscribe_turn(self, turn_id: str, after_seq: int = 0):
        yield {
            "type": "done",
            "source": "test",
            "stage": "",
            "content": "",
            "metadata": {"status": "completed", "after_seq": after_seq},
            "session_id": "session_live_route",
            "turn_id": turn_id,
            "seq": 1,
            "timestamp": 0,
        }


class _DeepQuestionRuntime:
    def __init__(self) -> None:
        self.started_payload: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []

    async def start_turn(self, payload: dict[str, Any]):
        self.started_payload = dict(payload)
        config = dict(payload.get("config") or {})
        billing_context = (
            config.get("billing_context")
            if isinstance(config.get("billing_context"), dict)
            else {}
        )
        user_id = str(billing_context.get("user_id") or "").strip()
        followup = (
            config.get("followup_question_context")
            if isinstance(config.get("followup_question_context"), dict)
            else {}
        )
        raw_answer = str(payload.get("content") or "").strip()
        context = UnifiedContext(
            session_id=str(payload.get("session_id") or "session_live_route"),
            user_message=f"[History Context]\n用户刚做完题。\n\n[User Question]\n{raw_answer}",
            language=str(payload.get("language") or "zh"),
            config_overrides=config,
            metadata={
                "user_id": user_id,
                "billing_context": dict(billing_context),
                "raw_user_message": raw_answer,
                "conversation_context_text": "用户刚做完一道建筑实务案例题。",
                "turn_semantic_decision": {"next_action": "route_to_grading"},
                "question_followup_action": {
                    "intent": "answer_questions",
                    "answers": [{"question_id": followup.get("question_id"), "answer": raw_answer}],
                },
                "question_followup_context": dict(followup),
            },
        )
        events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
        self.events = [event.to_dict() for event in events]
        for idx, event in enumerate(self.events, start=1):
            event["session_id"] = context.session_id
            event["turn_id"] = "turn_live_route"
            event["seq"] = idx
        return {"id": context.session_id}, {"id": "turn_live_route", "capability": "deep_question"}

    async def subscribe_turn(self, _turn_id: str, after_seq: int = 0):
        for event in self.events:
            if int(event.get("seq") or 0) > after_seq:
                yield event


def test_ws_start_turn_accepts_runtime_shadow_config_from_external_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _FakeRuntime()
    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _auth_ctx("qa_ws_shadow_user"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_ws_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "请批改我的案例题答案",
                    "capability": "deep_question",
                    "language": "zh",
                    "config": {
                        "grading_engine_runtime_shadow": True,
                        "grading_engine_runtime_shadow_engine": "deepseek_fast",
                        "followup_question_context": {
                            "question_id": "Q17-1A433000",
                            "question_type": "case",
                            "question": "写出施工现场消防安全管理要点。",
                        },
                    },
                }
            )
            message = websocket.receive_json()

    assert message["type"] == "done"
    assert fake_runtime.started_payload is not None
    config = fake_runtime.started_payload["config"]
    assert config["grading_engine_runtime_shadow"] is True
    assert config["grading_engine_runtime_shadow_engine"] == "deepseek_fast"
    assert config["followup_question_context"]["question_id"] == "Q17-1A433000"
    assert config["billing_context"]["user_id"] == "qa_ws_shadow_user"


def test_ws_client_receives_luban_shadow_result_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    _install_deep_question_fakes(monkeypatch)
    fake_runtime = _DeepQuestionRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _auth_ctx("qa_ws_shadow_user"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)
    monkeypatch.setattr(
        runtime_shadow_adapter,
        "build_runtime_shadow_result",
        lambda **kwargs: {
            "authority": "luban_grading_engine_shadow",
            "engine": kwargs["engine"],
            "not_production_grade": True,
            "writeback_performed": False,
            "shadow_status": "ok",
            "artifact_gate": {"artifact_status": "published"},
            "scores": {"model_draft_score": 1, "auto_certified_score": 0, "pending_review_score": 1},
            "point_results": [{"point_id": "P1", "evidence_span": "专用开关箱"}],
            "teacher_review_required": True,
        },
    )

    result_message: dict[str, Any] | None = None
    with TestClient(_build_ws_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "共用一个开关箱不妥，应采用专用开关箱。",
                    "capability": "deep_question",
                    "language": "zh",
                    "config": {
                        "grading_engine_runtime_shadow": True,
                        "grading_engine_runtime_shadow_engine": "deepseek_fast",
                        "followup_question_context": {
                            "question_id": "case-live-ws",
                            "question_type": "case",
                            "question": "指出事件二中临时用电管理的不妥之处。",
                            "correct_answer": "共用一个开关箱不妥，应采用专用开关箱。",
                        },
                    },
                }
            )
            for _ in range(20):
                message = websocket.receive_json()
                if message.get("type") == "result":
                    result_message = message
                    break

    assert result_message is not None
    metadata = result_message["metadata"]
    assert metadata["construction_grading_result"]["authority"] == "construction_grading"
    shadow = metadata["luban_grading_engine_shadow"]
    assert shadow["authority"] == "luban_grading_engine_shadow"
    assert shadow["writeback_performed"] is False
    assert shadow["not_production_grade"] is True


def test_mobile_start_turn_can_carry_runtime_shadow_flag_to_runtime_config() -> None:
    body = mobile_module.MobileStartTurnRequest(
        query="请批改我的案例题答案",
        capability="deep_question",
        grading_engine_runtime_shadow=True,
        grading_engine_runtime_shadow_engine="best_quality_4model",
        followup_question_context={
            "question_id": "Q17-1A433000",
            "question_type": "case",
            "question": "写出施工现场消防安全管理要点。",
        },
    )

    payload = mobile_module.build_mobile_turn_payload(
        body=body,
        authenticated_user_id="qa_mobile_shadow_user",
        wallet_user_id="qa_mobile_shadow_user",
        query=body.query,
    )

    config = payload["config"]
    assert config["grading_engine_runtime_shadow"] is True
    assert config["grading_engine_runtime_shadow_engine"] == "best_quality_4model"
    assert config["followup_question_context"]["question_id"] == "Q17-1A433000"
    assert config["billing_context"]["user_id"] == "qa_mobile_shadow_user"


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> None:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, pkg_name, pkg)
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)

    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, fullname, module)
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        monkeypatch.setattr(parent, parts[-1], module, raising=False)


async def _collect_events(run_coro) -> list[StreamEvent]:
    bus = StreamBus()
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    await run_coro(bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


def _install_deep_question_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **_kwargs: Any) -> str:
            return "得分：1分（满分3分）。"

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )


def _case_context(
    *,
    user_id: str = "qa_live_route_user",
    flag: bool,
    engine: str = "deepseek_fast",
) -> UnifiedContext:
    raw_answer = "我的答案：共用一个开关箱不妥，应采用专用开关箱。请按案例题阅卷标准批改。"
    return UnifiedContext(
        user_message=f"[History Context]\n用户刚做完题。\n\n[User Question]\n{raw_answer}",
        language="zh",
        config_overrides={
            "grading_engine_runtime_shadow": flag,
            "grading_engine_runtime_shadow_engine": engine,
        },
        metadata={
            "user_id": user_id,
            "raw_user_message": raw_answer,
            "conversation_context_text": "用户刚做完一道建筑实务案例题。",
            "turn_semantic_decision": {"next_action": "route_to_grading"},
            "question_followup_action": {
                "intent": "answer_questions",
                "answers": [{"question_id": "case-live-route", "answer": "E"}],
            },
            "question_followup_context": {
                "question_id": "case-live-route",
                "question": "指出事件二中临时用电管理的不妥之处。",
                "question_type": "case",
                "correct_answer": (
                    "不妥之处：1.未编制临时用电施工组织设计；2.共用一个开关箱；"
                    "3.插座插头活动连接。正确做法：1.应编制单项施工用电方案；"
                    "2.应采用专用开关箱；3.插头和插座应配套使用，不得活动连接。"
                ),
                "concentration": "临时用电",
            },
        },
    )


async def _run_deep_question_result(
    monkeypatch: pytest.MonkeyPatch,
    context: UnifiedContext,
) -> dict[str, Any]:
    _install_deep_question_fakes(monkeypatch)
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    return next(event.metadata for event in events if event.type == StreamEventType.RESULT)


@pytest.mark.asyncio
async def test_result_event_has_legacy_only_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    monkeypatch.setattr(
        runtime_shadow_adapter,
        "build_runtime_shadow_result",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("shadow adapter must not run")),
    )

    result = await _run_deep_question_result(monkeypatch, _case_context(flag=False))

    assert result["construction_grading_result"]["authority"] == "construction_grading"
    assert "luban_grading_engine_shadow" not in result


@pytest.mark.asyncio
async def test_result_event_appends_shadow_when_config_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    captured: dict[str, Any] = {}

    def _shadow(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "authority": "luban_grading_engine_shadow",
            "engine": kwargs["engine"],
            "not_production_grade": True,
            "writeback_performed": False,
            "shadow_status": "ok",
            "artifact_gate": {"artifact_status": "published"},
            "scores": {"model_draft_score": 1, "auto_certified_score": 0, "pending_review_score": 1},
            "point_results": [{"point_id": "P1"}],
            "teacher_review_required": True,
        }

    monkeypatch.setattr(runtime_shadow_adapter, "build_runtime_shadow_result", _shadow)

    result = await _run_deep_question_result(monkeypatch, _case_context(flag=True, engine="best_quality_4model"))

    legacy = result["construction_grading_result"]
    shadow = result["luban_grading_engine_shadow"]
    assert legacy["authority"] == "construction_grading"
    assert legacy["score_awarded"] == 1.0
    assert shadow["authority"] == "luban_grading_engine_shadow"
    assert shadow["not_production_grade"] is True
    assert shadow["writeback_performed"] is False
    assert captured["student_id"] == "qa_live_route_user"
    assert captured["question_id"] == "case-live-route"
    assert captured["engine"] == "best_quality_4model"


@pytest.mark.asyncio
async def test_non_qa_user_keeps_legacy_and_shadow_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    result = await _run_deep_question_result(
        monkeypatch,
        _case_context(user_id="real_student_123", flag=True),
    )

    assert result["construction_grading_result"]["authority"] == "construction_grading"
    shadow = result["luban_grading_engine_shadow"]
    assert shadow["shadow_status"] == "qa_student_required"
    assert shadow["writeback_performed"] is False
    assert shadow["point_results"] == []


@pytest.mark.asyncio
async def test_adapter_exception_keeps_legacy_and_returns_shadow_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    monkeypatch.setattr(
        runtime_shadow_adapter,
        "build_runtime_shadow_result",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("adapter boom")),
    )

    result = await _run_deep_question_result(monkeypatch, _case_context(flag=True))

    assert result["construction_grading_result"]["authority"] == "construction_grading"
    shadow = result["luban_grading_engine_shadow"]
    assert shadow["shadow_status"] == "engine_unavailable"
    assert shadow["writeback_performed"] is False


@pytest.mark.asyncio
async def test_shadow_path_does_not_add_learning_brain_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    write_calls: list[dict[str, Any]] = []

    def _write_grading_error_events(**kwargs: Any) -> int:
        write_calls.append(kwargs)
        return 1

    monkeypatch.setattr(deep_question_module, "write_grading_error_events", _write_grading_error_events)
    monkeypatch.setattr(
        runtime_shadow_adapter,
        "build_runtime_shadow_result",
        lambda **kwargs: {
            "authority": "luban_grading_engine_shadow",
            "engine": kwargs["engine"],
            "not_production_grade": True,
            "writeback_performed": False,
            "shadow_status": "ok",
            "artifact_gate": {"artifact_status": "published"},
            "scores": {"model_draft_score": 1, "auto_certified_score": 0, "pending_review_score": 1},
            "point_results": [{"point_id": "P1"}],
            "teacher_review_required": True,
        },
    )

    result = await _run_deep_question_result(monkeypatch, _case_context(flag=True))

    assert result["luban_grading_engine_shadow"]["writeback_performed"] is False
    assert len(write_calls) == 1
