from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities import deep_question as deep_question_module
from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


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


def _install_grading_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _case_context(*, user_id: str = "qa_runtime_shadow_20260604", shadow: bool = False) -> UnifiedContext:
    raw_answer = "我的答案：共用一个开关箱不妥，应采用专用开关箱。请按案例题阅卷标准批改。"
    metadata: dict[str, Any] = {
        "user_id": user_id,
        "raw_user_message": raw_answer,
        "conversation_context_text": "用户刚做完一道建筑实务案例题。",
        "turn_semantic_decision": {"next_action": "route_to_grading"},
        "question_followup_action": {
            "intent": "answer_questions",
            "answers": [{"question_id": "case-9006", "answer": "E"}],
        },
        "question_followup_context": {
            "question_id": "case-9006",
            "question": "指出事件二中临时用电管理的不妥之处。",
            "question_type": "case",
            "correct_answer": (
                "不妥之处：1.未编制临时用电施工组织设计；2.共用一个开关箱；"
                "3.插座插头活动连接。正确做法：1.应编制单项施工用电方案；"
                "2.应采用专用开关箱；3.插头和插座应配套使用，不得活动连接。"
            ),
            "concentration": "临时用电",
        },
    }
    if shadow:
        metadata["grading_engine_runtime_shadow"] = True
        metadata["grading_engine_runtime_shadow_mode"] = "luban_best_quality_shadow"
    return UnifiedContext(
        user_message=f"[History Context]\n用户刚做完题。\n\n[User Question]\n{raw_answer}",
        language="zh",
        metadata=metadata,
    )


async def _run_case(monkeypatch: pytest.MonkeyPatch, context: UnifiedContext) -> dict[str, Any]:
    _install_grading_fakes(monkeypatch)
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    return next(event.metadata for event in events if event.type == StreamEventType.RESULT)


@pytest.mark.asyncio
async def test_luban_runtime_shadow_absent_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    monkeypatch.setattr(
        runtime_shadow_adapter,
        "build_runtime_shadow_result",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("shadow adapter must not run")),
    )

    result = await _run_case(monkeypatch, _case_context(shadow=False))

    assert result["construction_grading_result"]["authority"] == "construction_grading"
    assert "luban_grading_engine_shadow" not in result


@pytest.mark.asyncio
async def test_luban_runtime_shadow_appends_for_qa_flag(monkeypatch: pytest.MonkeyPatch) -> None:
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

    result = await _run_case(monkeypatch, _case_context(shadow=True))

    legacy = result["construction_grading_result"]
    shadow = result["luban_grading_engine_shadow"]
    assert legacy["authority"] == "construction_grading"
    assert legacy["score_awarded"] == 1.0
    assert legacy["max_score"] == 3.0
    assert shadow["authority"] == "luban_grading_engine_shadow"
    assert shadow["not_production_grade"] is True
    assert shadow["writeback_performed"] is False
    assert captured["student_id"] == "qa_runtime_shadow_20260604"
    assert captured["question_id"] == "case-9006"
    assert captured["engine"] == "luban_best_quality_shadow"


@pytest.mark.asyncio
async def test_luban_runtime_shadow_non_qa_student_fails_closed_without_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    monkeypatch.setattr(
        runtime_shadow_adapter,
        "_build_best_quality_draft",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("engine must not run")),
    )

    result = await _run_case(monkeypatch, _case_context(user_id="real_student_123", shadow=True))

    assert result["construction_grading_result"]["authority"] == "construction_grading"
    shadow = result["luban_grading_engine_shadow"]
    assert shadow["shadow_status"] == "qa_student_required"
    assert shadow["writeback_performed"] is False
    assert shadow["point_results"] == []


@pytest.mark.asyncio
async def test_luban_runtime_shadow_adapter_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter

    monkeypatch.setattr(
        runtime_shadow_adapter,
        "build_runtime_shadow_result",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("adapter boom")),
    )

    result = await _run_case(monkeypatch, _case_context(shadow=True))

    assert result["construction_grading_result"]["authority"] == "construction_grading"
    shadow = result["luban_grading_engine_shadow"]
    assert shadow["authority"] == "luban_grading_engine_shadow"
    assert shadow["shadow_status"] == "engine_unavailable"
    assert shadow["writeback_performed"] is False


@pytest.mark.asyncio
async def test_luban_runtime_shadow_does_not_add_learning_brain_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    result = await _run_case(monkeypatch, _case_context(shadow=True))

    assert result["luban_grading_engine_shadow"]["writeback_performed"] is False
    assert len(write_calls) == 1
    assert write_calls[0]["grading_result"]["authority"] == "construction_grading"
