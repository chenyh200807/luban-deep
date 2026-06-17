from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

secure_router_mod = importlib.import_module("deeptutor.api._secure_router")
ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
submission_grader_agent_mod = importlib.import_module(
    "deeptutor.agents.question.agents.submission_grader_agent"
)


def _build_ws_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ws_module.router, prefix="/api/v1")
    return app


def _auth_ctx(user_id: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id, "canonical_uid": user_id},
        is_admin=False,
    )


class _FakeContextBuilder:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def build(self, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            conversation_history=[],
            conversation_summary="",
            context_text="",
            token_count=0,
            budget=0,
        )


class _FakeMemoryService:
    def build_memory_context(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    async def refresh_from_turn(self, **_kwargs: Any) -> None:
        return None


class _FakeLearnerStateService:
    def build_context(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    def read_compiled_learning_truth(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}


class _FakeSubmissionGraderAgent:
    def __init__(self, **_kwargs: Any) -> None:
        self._trace_callback = None

    def set_trace_callback(self, callback: Any) -> None:
        self._trace_callback = callback

    async def process(self, **_kwargs: Any) -> str:
        return "得分：1分（满分3分）。"


def _install_runtime_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    user_id: str,
    shadow_builder: Any | None = None,
    patch_shadow_builder: bool = True,
    patch_engine_fixture: bool = True,
) -> tuple[TurnRuntimeManager, list[dict[str, Any]], list[dict[str, Any]]]:
    from deeptutor.services.construction_grading import runtime_shadow_adapter
    from deeptutor.runtime.orchestrator import ChatOrchestrator

    runtime = TurnRuntimeManager(SQLiteSessionStore(tmp_path / "ws-shadow-smoke.db"))
    write_calls: list[dict[str, Any]] = []
    shadow_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _auth_ctx(user_id))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: runtime)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", _FakeContextBuilder)
    monkeypatch.setattr("deeptutor.services.memory.get_memory_service", lambda: _FakeMemoryService())
    monkeypatch.setattr("deeptutor.services.learner_state.get_learner_state_service", lambda: _FakeLearnerStateService())
    monkeypatch.setattr(submission_grader_agent_mod, "SubmissionGraderAgent", _FakeSubmissionGraderAgent)
    async def _select_deep_question(self: Any, context: Any) -> str:
        return "deep_question"

    monkeypatch.setattr(ChatOrchestrator, "_select_capability", _select_deep_question)

    def _write_grading_error_events(**kwargs: Any) -> int:
        write_calls.append(kwargs)
        return 1

    monkeypatch.setattr(
        "deeptutor.capabilities.deep_question.write_grading_error_events",
        _write_grading_error_events,
    )

    if patch_engine_fixture:
        from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

        def _build_best_quality_draft(**kwargs: Any) -> dict[str, Any]:
            shadow_calls.append(dict(kwargs))
            question = kwargs["question"]
            points = list(question.get("scoring_points") or [])
            point = points[0]
            return build_ai_draft(
                question,
                kwargs["student_answer"],
                [
                    {
                        "point_id": point["point_id"],
                        "hit": "hit",
                        "score": point.get("max_score") or 1,
                        "evidence_span": "专用开关箱",
                        "rationale": "deterministic smoke fixture",
                    }
                ],
                points=[point],
                student_id=kwargs.get("student_id"),
                artifact_gate=kwargs.get("artifact_gate"),
            )

        monkeypatch.setattr(runtime_shadow_adapter, "_build_best_quality_draft", _build_best_quality_draft)

    if patch_shadow_builder:
        if shadow_builder is not None:
            monkeypatch.setattr(runtime_shadow_adapter, "build_runtime_shadow_result", shadow_builder)
    return runtime, write_calls, shadow_calls


def _start_turn_frame(
    *,
    question_id: str = "Q1-NA",
    flag: bool,
    engine: str = "best_quality_4model",
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "followup_question_context": {
            "question_id": question_id,
            "question_type": "case",
            "question": "指出事件二中临时用电管理的不妥之处。",
            "correct_answer": (
                "共用一个开关箱不妥，应采用专用开关箱；"
                "未编制临时用电施工组织设计；插座插头不得活动连接。"
            ),
        }
    }
    if flag:
        config["grading_engine_runtime_shadow"] = True
        config["grading_engine_runtime_shadow_engine"] = engine
    return {
        "type": "start_turn",
        "content": "共用一个开关箱不妥，应采用专用开关箱。",
        "capability": "deep_question",
        "language": "zh",
        "config": config,
    }


def _receive_result_event(client: TestClient, frame: dict[str, Any]) -> dict[str, Any]:
    with client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json(frame)
        for _ in range(80):
            message = websocket.receive_json()
            if message.get("type") == "result":
                return message
            if message.get("type") == "error":
                raise AssertionError(message)
    raise AssertionError("result event not received")


def test_ws_turn_smoke_flag_off_has_no_shadow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _runtime, write_calls, shadow_calls = _install_runtime_fakes(
        monkeypatch,
        tmp_path,
        user_id="qa_ws_shadow_smoke_001",
        shadow_builder=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("shadow must not run")),
    )

    with TestClient(_build_ws_app()) as client:
        result = _receive_result_event(client, _start_turn_frame(flag=False))

    metadata = result["metadata"]
    assert metadata["construction_grading_result"]["authority"] == "construction_grading"
    assert "luban_grading_engine_shadow" not in metadata
    assert shadow_calls == []
    assert len(write_calls) == 1
    assert write_calls[0]["grading_result"]["authority"] == "construction_grading"


def test_ws_turn_smoke_qa_flag_on_client_receives_shadow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _runtime, write_calls, shadow_calls = _install_runtime_fakes(
        monkeypatch,
        tmp_path,
        user_id="qa_ws_shadow_smoke_002",
    )

    with TestClient(_build_ws_app()) as client:
        result = _receive_result_event(client, _start_turn_frame(flag=True))

    metadata = result["metadata"]
    legacy = metadata["construction_grading_result"]
    shadow = metadata["luban_grading_engine_shadow"]
    assert legacy["authority"] == "construction_grading"
    assert legacy["score_awarded"] == 1.0
    assert legacy["max_score"] == 3.0
    assert shadow["authority"] == "luban_grading_engine_shadow"
    assert shadow["not_production_grade"] is True
    assert shadow["writeback_performed"] is False
    assert shadow["point_results"][0]["evidence_span"] == "专用开关箱"
    assert shadow_calls[0]["question"]["case_id"] == "Q1-NA"
    assert shadow_calls[0]["student_id"] == "qa_ws_shadow_smoke_002"
    assert len(write_calls) == 1


def test_ws_turn_smoke_non_qa_user_fails_closed_without_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    _runtime, write_calls, _shadow_calls = _install_runtime_fakes(
        monkeypatch,
        tmp_path,
        user_id="real_student_123",
        patch_shadow_builder=False,
        patch_engine_fixture=False,
    )
    monkeypatch.setattr(
        runtime_shadow_adapter,
        "_build_best_quality_draft",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("engine must not run")),
    )

    with TestClient(_build_ws_app()) as client:
        result = _receive_result_event(client, _start_turn_frame(flag=True))

    metadata = result["metadata"]
    assert metadata["construction_grading_result"]["authority"] == "construction_grading"
    shadow = metadata["luban_grading_engine_shadow"]
    assert shadow["shadow_status"] == "qa_student_required"
    assert shadow["writeback_performed"] is False
    assert shadow["point_results"] == []
    assert len(write_calls) == 1


def test_ws_turn_smoke_adapter_exception_keeps_legacy_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _runtime, write_calls, _shadow_calls = _install_runtime_fakes(
        monkeypatch,
        tmp_path,
        user_id="qa_ws_shadow_smoke_003",
        shadow_builder=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("adapter boom")),
    )

    with TestClient(_build_ws_app()) as client:
        result = _receive_result_event(client, _start_turn_frame(flag=True))

    metadata = result["metadata"]
    assert metadata["construction_grading_result"]["authority"] == "construction_grading"
    shadow = metadata["luban_grading_engine_shadow"]
    assert shadow["shadow_status"] == "engine_unavailable"
    assert shadow["writeback_performed"] is False
    assert len(write_calls) == 1
