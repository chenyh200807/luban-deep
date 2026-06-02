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


@pytest.mark.asyncio
async def test_deep_question_post_submit_result_appends_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ANSWER_CITATIONS_ENABLED", "true")

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_trace_callback(self, _callback: Any) -> None:
            return None

        async def process(self, **kwargs: Any) -> str:
            response = "双扇防火门应按顺序关闭。\n\n关闭顺序是本题的采分关键。"
            callback = kwargs.get("on_content_chunk")
            if callback is not None:
                await callback(response)
            return response

    async def fake_rag_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "content": "双扇防火门应按顺序关闭。",
            "sources": [
                {
                    "title": "建筑防火门规范考点",
                    "content": "双扇防火门应按顺序关闭。",
                    "source_type": "standard",
                    "chunk_id": "std-fire-door-001",
                    "metadata": {
                        "source_id": "std_fire_door_001",
                        "source_span": {"article": "6.5.1"},
                    },
                },
                {
                    "title": "建筑防火门规范考点",
                    "content": "关闭顺序是本题的采分关键。",
                    "source_type": "standard",
                    "chunk_id": "std-fire-door-002",
                    "metadata": {
                        "source_id": "std_fire_door_002",
                        "source_span": {"article": "6.5.2"},
                    },
                }
            ],
            "evidence_bundle": {
                "sources": [
                    {
                        "title": "建筑防火门规范考点",
                        "content": "双扇防火门应按顺序关闭。",
                        "source_type": "standard",
                        "chunk_id": "std-fire-door-001",
                        "metadata": {
                            "source_id": "std_fire_door_001",
                            "source_span": {"article": "6.5.1"},
                        },
                    },
                    {
                        "title": "建筑防火门规范考点",
                        "content": "关闭顺序是本题的采分关键。",
                        "source_type": "standard",
                        "chunk_id": "std-fire-door-002",
                        "metadata": {
                            "source_id": "std_fire_door_002",
                            "source_span": {"article": "6.5.2"},
                        },
                    }
                ]
            },
        }

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
    monkeypatch.setattr(deep_question_module, "rag_search", fake_rag_search, raising=False)

    context = UnifiedContext(
        user_message="我选C",
        language="zh",
        knowledge_bases=["construction-exam"],
        metadata={
            "selected_mode": "deep",
            "conversation_context_text": "上一轮题目问：双扇防火门关闭顺序。",
            "question_followup_context": {
                "question_id": "q_fire_door",
                "question": "关于双扇防火门关闭要求，下列说法正确的是？",
                "question_type": "choice",
                "options": {
                    "A": "同时关闭",
                    "B": "按顺序关闭",
                    "C": "自动关闭",
                    "D": "手动关闭",
                },
                "correct_answer": "B",
                "explanation": "双扇防火门应按顺序关闭。",
            },
        },
    )

    events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert response == "双扇防火门应按顺序关闭。〔1〕\n\n关闭顺序是本题的采分关键。〔2〕"
    assert "〔1〕" in response
    assert "依据" not in response
    assert result_event.metadata["citation_bundle"]["footer_text"].startswith("依据\n〔1〕建筑防火门规范考点")
    assert result_event.metadata["citation_bundle"]["citation_state"] in {"supported", "partial"}
    content_events = [event for event in events if event.type == StreamEventType.CONTENT]
    assert "".join(str(event.content or "") for event in content_events) == response
