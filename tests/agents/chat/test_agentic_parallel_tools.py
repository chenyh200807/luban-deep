from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline, ToolTrace
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.trace import build_trace_metadata
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.tool_protocol import ToolResult


async def _collect_bus_events(bus: StreamBus) -> tuple[list[StreamEvent], asyncio.Task[Any]]:
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    return events, consumer  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_native_tool_loop_executes_parallel_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def __init__(self) -> None:
            self.inflight = 0
            self.max_inflight = 0

        def build_openai_schemas(self, _enabled_tools):
            return [{"type": "function", "function": {"name": "web_search"}}]

        def build_prompt_text(self, enabled_tools, **_kwargs):
            return "\n".join(enabled_tools)

        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        async def execute(self, name: str, **kwargs):
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            await asyncio.sleep(0.05)
            self.inflight -= 1
            return ToolResult(
                content=f"{name} => {kwargs.get('query', '') or kwargs.get('context', '')}".strip(),
                sources=[{"tool": name}],
                metadata={"tool": name},
                success=True,
            )

    registry = FakeRegistry()
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.get_tool_registry", lambda: registry)

    class FakeObservability:
        def __init__(self) -> None:
            self.updated: list[dict[str, Any]] = []

        def estimate_usage_details(self, **_kwargs):
            return {"input": 10.0, "output": 3.0, "total": 13.0}

        def estimate_cost_details(self, **_kwargs):
            return {"input": 0.0, "output": 0.0, "total": 0.0}

        def start_observation(self, **_kwargs):
            class _Manager:
                def __enter__(self_inner):
                    return object()

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Manager()

        def update_observation(self, _observation, **kwargs):
            self.updated.append(kwargs)

    fake_observability = FakeObservability()
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.observability", fake_observability)

    pipeline = AgenticChatPipeline(language="en")
    pipeline.registry = registry

    class FakeCreate:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    usage=SimpleNamespace(prompt_tokens=41, completion_tokens=9, total_tokens=50),
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="",
                                tool_calls=[
                                    SimpleNamespace(
                                        id="tool-call-1",
                                        function=SimpleNamespace(
                                            name="web_search",
                                            arguments='{"query":"first"}',
                                        ),
                                    ),
                                    SimpleNamespace(
                                        id="tool-call-2",
                                        function=SimpleNamespace(
                                            name="reason",
                                            arguments='{"context":"second"}',
                                        ),
                                    ),
                                ],
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="No more tools needed.",
                            tool_calls=[],
                        )
                    )
                ]
            )

    fake_create = FakeCreate()
    monkeypatch.setattr(
        pipeline,
        "_build_openai_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=fake_create),
            )
        ),
    )

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-1",
        user_message="compare two sources",
        enabled_tools=["web_search", "reason"],
        language="en",
        metadata={"turn_id": "turn-1"},
    )

    traces = await pipeline._run_native_tool_loop(
        context=context,
        enabled_tools=["web_search", "reason"],
        thinking_text="Need outside evidence and a reasoning cross-check.",
        stream=bus,
    )
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    assert fake_create.calls == 1
    assert registry.max_inflight >= 2
    assert [trace.name for trace in traces] == ["web_search", "reason"]
    assert fake_observability.updated[0]["usage_source"] == "provider"
    assert fake_observability.updated[0]["usage_details"] == {
        "input": 41.0,
        "output": 9.0,
        "total": 50.0,
    }

    tool_result_events = [event for event in events if event.type.value == "tool_result"]
    assert len(tool_result_events) == 2
    assert tool_result_events[0].metadata["tool_call_id"] == "tool-call-1"
    assert tool_result_events[1].metadata["tool_call_id"] == "tool-call-2"
    assert tool_result_events[0].metadata["tool_index"] == 0
    assert tool_result_events[1].metadata["tool_index"] == 1
    acting_thinking_events = [
        event for event in events
        if event.type == StreamEventType.THINKING and event.stage == "acting"
    ]
    assert acting_thinking_events == []


@pytest.mark.asyncio
async def test_execute_tool_call_streams_retrieve_progress_for_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        async def execute(self, name: str, **kwargs):
            event_sink = kwargs.get("event_sink")
            if event_sink is not None:
                await event_sink("status", "Selecting provider: llamaindex", {"provider": "llamaindex"})
                await event_sink("status", "Retrieving chunks...", {"mode": "hybrid"})
            return ToolResult(
                content=f"{name} => grounded answer",
                sources=[{"tool": name}],
                metadata={"tool": name},
                success=True,
            )

    registry = FakeRegistry()
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.get_tool_registry", lambda: registry)

    pipeline = AgenticChatPipeline(language="en")
    pipeline.registry = registry

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-1",
        user_message="what is a transformer",
        enabled_tools=["rag"],
        knowledge_bases=["demo-kb"],
        language="en",
        metadata={"turn_id": "turn-1"},
    )
    trace_meta = build_trace_metadata(
        call_id="chat-react-1",
        phase="acting",
        label="Round 1",
        call_kind="react_round",
        trace_id="chat-react-1",
        trace_role="thought",
        trace_group="react_round",
        round=1,
    )
    retrieve_meta = pipeline._retrieve_trace_metadata(
        trace_meta,
        context=context,
        tool_call_id="tool-call-rag",
        tool_name="rag",
        tool_index=0,
        tool_args={"query": "transformer model", "kb_name": "demo-kb"},
    )

    result = await pipeline._execute_tool_call(
        "rag",
        {"query": "transformer model", "kb_name": "demo-kb"},
        stream=bus,
        retrieve_meta=retrieve_meta,
    )
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    assert result["success"] is True
    retrieve_events = [
        event
        for event in events
        if event.type == StreamEventType.PROGRESS and event.metadata.get("trace_role") == "retrieve"
    ]
    assert [event.content for event in retrieve_events] == [
        "Query: transformer model",
        "Selecting provider: llamaindex",
        "Retrieving chunks...",
        "Retrieve complete (22 chars)",
    ]


def test_augment_tool_kwargs_fills_rag_query_from_user_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        session_id="session-rag-query",
        user_message="请分析这道建筑案例题",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        language="zh",
        metadata={"turn_id": "turn-rag-query"},
    )

    kwargs = pipeline._augment_tool_kwargs("rag", {}, context, "需要知识召回")

    assert kwargs["kb_name"] == "construction-exam"
    assert kwargs["mode"] == "hybrid"
    assert kwargs["query"] == "请分析这道建筑案例题"


@pytest.mark.asyncio
async def test_native_tool_loop_forces_rag_for_grounded_tutorbot_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def build_openai_schemas(self, _enabled_tools):
            return [{"type": "function", "function": {"name": "rag"}}]

        def build_prompt_text(self, enabled_tools, **_kwargs):
            return "\n".join(enabled_tools)

        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        async def execute(self, name: str, **kwargs):
            return ToolResult(
                content=f"{name} => grounded",
                sources=[{"tool": name, "kb_name": kwargs.get("kb_name")}],
                metadata={"tool": name, "kb_name": kwargs.get("kb_name")},
                success=True,
            )

    registry = FakeRegistry()
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.get_tool_registry", lambda: registry)

    pipeline = AgenticChatPipeline(language="zh")
    pipeline.registry = registry

    async def _no_tool_call(**_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="不需要额外工具。",
                        tool_calls=[],
                    )
                )
            ]
        )

    monkeypatch.setattr(
        pipeline,
        "_build_openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_no_tool_call))),
    )

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-grounded",
        user_message="请分析这道建筑案例题并回答全部问题",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        language="zh",
        metadata={
            "turn_id": "turn-grounded",
            "bot_id": "construction-exam-coach",
        },
        config_overrides={"interaction_profile": "tutorbot"},
    )

    traces = await pipeline._run_native_tool_loop(
        context=context,
        enabled_tools=["rag"],
        thinking_text="这是一道案例题，需要先找真题。",
        stream=bus,
    )
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    assert [trace.name for trace in traces] == ["rag"]
    assert traces[0].arguments["kb_name"] == "construction-exam"
    assert any(event.type == StreamEventType.TOOL_CALL for event in events)
    assert any(event.type == StreamEventType.TOOL_RESULT for event in events)


@pytest.mark.asyncio
async def test_react_fallback_forces_rag_for_grounded_tutorbot_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="anthropic", model="claude-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def build_prompt_text(self, enabled_tools, **_kwargs):
            return "\n".join(enabled_tools)

        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        async def execute(self, name: str, **kwargs):
            return ToolResult(
                content=f"{name} => grounded",
                sources=[{"tool": name, "kb_name": kwargs.get("kb_name")}],
                metadata={"tool": name, "kb_name": kwargs.get("kb_name")},
                success=True,
            )

    registry = FakeRegistry()
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.get_tool_registry", lambda: registry)
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.llm_stream",
        lambda **_kwargs: iter(['{"action":"done","action_input":{}}']),
    )

    pipeline = AgenticChatPipeline(language="zh")
    pipeline.registry = registry

    async def _stream_wrapper():
        yield '{"action":"done","action_input":{}}'

    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.llm_stream", lambda **_kwargs: _stream_wrapper())

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-react-grounded",
        user_message="请按考点解释这道案例题",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        language="zh",
        metadata={
            "turn_id": "turn-react-grounded",
            "bot_id": "construction-exam-coach",
        },
        config_overrides={"interaction_profile": "tutorbot"},
    )

    traces = await pipeline._run_react_fallback(
        context=context,
        enabled_tools=["rag"],
        thinking_text="需要知识召回。",
        stream=bus,
    )
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    assert [trace.name for trace in traces] == ["rag"]
    assert traces[0].arguments["kb_name"] == "construction-exam"
    assert any(event.type == StreamEventType.TOOL_CALL for event in events)
    assert any(event.type == StreamEventType.TOOL_RESULT for event in events)


@pytest.mark.asyncio
async def test_native_tool_loop_caps_parallel_tool_calls_at_eight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )

    class FakeRegistry:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def build_openai_schemas(self, _enabled_tools):
            return [{"type": "function", "function": {"name": "web_search"}}]

        def build_prompt_text(self, enabled_tools, **_kwargs):
            return "\n".join(enabled_tools)

        def get_enabled(self, selected):
            return [SimpleNamespace(name=name) for name in selected]

        async def execute(self, name: str, **kwargs):
            self.calls.append(f"{name}:{kwargs.get('query', '')}")
            return ToolResult(
                content=f"{name} => {kwargs.get('query', '')}",
                sources=[{"tool": name}],
                metadata={"tool": name},
                success=True,
            )

    registry = FakeRegistry()
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.get_tool_registry", lambda: registry)

    pipeline = AgenticChatPipeline(language="en")
    pipeline.registry = registry

    tool_calls = [
        SimpleNamespace(
            id=f"tool-call-{index}",
            function=SimpleNamespace(
                name="web_search",
                arguments=f'{{"query":"q{index}"}}',
            ),
        )
        for index in range(10)
    ]

    async def fake_create(**_kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Use multiple tools in parallel.",
                        tool_calls=tool_calls,
                    )
                )
            ]
        )

    monkeypatch.setattr(
        pipeline,
        "_build_openai_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=fake_create),
            )
        ),
    )

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-1",
        user_message="collect broad evidence",
        enabled_tools=["web_search"],
        language="en",
        metadata={"turn_id": "turn-1"},
    )

    traces = await pipeline._run_native_tool_loop(
        context=context,
        enabled_tools=["web_search"],
        thinking_text="Need multiple web sources.",
        stream=bus,
    )
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    assert len(traces) == 8
    assert len(registry.calls) == 8
    assert registry.calls[-1] == "web_search:q7"
    progress_events = [event.content for event in events if event.type == StreamEventType.PROGRESS]
    assert any("8 can run in parallel" in content for content in progress_events)


def test_infer_answer_type_detects_knowledge_explainer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    assert pipeline._infer_answer_type("什么是流水施工，怎么区分流水步距和流水节拍？") == "knowledge_explainer"


def test_missing_teaching_elements_requires_exact_zh_section_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    content = """
## 核心结论
先看组织节奏。

## 踩分点
- 写清相邻专业队投入间隔。

## 易错点
- 不要把流水步距当成流水节拍。

## 记忆口诀
步距看“队与队之间的间隔”。

## 心得
看到“相邻专业队”就优先判断步距。
"""
    assert pipeline._missing_teaching_elements(content) == []


def test_missing_teaching_elements_requires_explicit_section_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    content = """
结论先行：流水步距是相邻专业队开始时间差。

拿分关键：
- 先看相邻专业队是否错开投入。

常见误区：
- 不要把流水步距当成流水节拍。

口诀：
- 步距看邻居，节拍看自己。

考试技巧：
- 题干一出现“相邻专业队”，先判步距。
"""
    assert pipeline._missing_teaching_elements(content) == [
        "核心结论",
        "踩分点",
        "易错点",
        "记忆口诀",
        "心得",
    ]


def test_teaching_contract_only_enforced_when_rag_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    assert pipeline._should_enforce_teaching_contract("knowledge_explainer", []) is False
    trace = ToolTrace(
        name="rag",
        arguments={"query": "流水施工"},
        result="kb result",
        success=True,
        sources=[],
        metadata={"call_kind": "rag_retrieval"},
    )
    assert pipeline._should_enforce_teaching_contract("knowledge_explainer", [trace]) is True


def test_extract_exact_question_authority_from_rag_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    trace = ToolTrace(
        name="rag",
        arguments={"query": "单选题"},
        result="kb result",
        success=True,
        sources=[],
        metadata={
            "exact_question": {
                "id": "15156",
                "stem": "确定屋面防水工程的防水等级应根据（ ）。",
                "correct_answer": "ACE",
                "analysis": "正确答案: ACE",
                "confidence": 1.0,
            }
        },
    )

    authority = pipeline._extract_exact_question_authority([trace])

    assert authority is not None
    assert authority["authoritative_answer"] == "ACE"
    assert authority["stem"] == "确定屋面防水工程的防水等级应根据（ ）。"


def test_extract_case_exact_question_authority_from_rag_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    trace = ToolTrace(
        name="rag",
        arguments={"query": "案例题"},
        result="kb result",
        success=True,
        sources=[],
        metadata={
            "exact_question": {
                "id": "9717",
                "stem": "某旧城改造工程案例题",
                "question_type": "case_study",
                "answer_kind": "case_study",
                "covered_subquestions": [
                    {
                        "display_index": "1",
                        "prompt": "通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                        "authoritative_answer": "①潜在投标人数量较多；②大型、技术复杂项目；合格制、有限数量制。",
                        "analysis": "第1问标准答案。",
                    }
                ],
                "missing_subquestions": [
                    {"display_index": "2", "prompt": "管理策划内容还有哪些？"},
                ],
                "coverage_state": "single_subquestion_only",
                "coverage_ratio": 0.2,
                "confidence": 0.98,
            }
        },
    )

    authority = pipeline._extract_exact_question_authority([trace])

    assert authority is not None
    assert authority["authority_kind"] == "case_study"
    assert authority["covered_subquestions"][0]["display_index"] == "1"
    assert authority["missing_subquestions"][0]["display_index"] == "2"


@pytest.mark.asyncio
async def test_apply_exact_question_authority_rewrites_mismatched_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        session_id="session-1",
        user_message="单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积",
        language="zh",
    )
    trace = ToolTrace(
        name="rag",
        arguments={"query": "单选题"},
        result="kb result",
        success=True,
        sources=[],
        metadata={
            "exact_question": {
                "id": "15156",
                "stem": "确定屋面防水工程的防水等级应根据（ ）。",
                "correct_answer": "ACE",
                "analysis": "正确答案: ACE",
                "options": ["A. 建筑物的类别", "B. 建筑物的面积", "C. 建筑物的重要程度"],
                "confidence": 1.0,
            }
        },
    )

    async def _fake_rewrite(**kwargs):
        _ = kwargs
        return "【最终答案】ACE\n依据题库原题，应该选建筑物的类别、重要程度和使用功能。"

    monkeypatch.setattr(pipeline, "_rewrite_exact_question_response", _fake_rewrite)

    corrected = await pipeline._apply_exact_question_authority(
        context=context,
        answer_type="problem_solving",
        content="【最终答案】B\n因为建筑物面积决定防水等级。",
        tool_traces=[trace],
        max_tokens=800,
    )

    assert corrected.startswith("【最终答案】ACE")
    assert "建筑物面积决定防水等级" not in corrected


@pytest.mark.asyncio
async def test_apply_case_exact_question_authority_rewrites_whole_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        session_id="session-case",
        user_message="背景资料：某旧城改造工程。问题：1. 资格预审特点和方法？2. 计算施工项目成本。",
        language="zh",
    )
    trace = ToolTrace(
        name="rag",
        arguments={"query": "案例题"},
        result="kb result",
        success=True,
        sources=[],
        metadata={
            "exact_question": {
                "id": "9717",
                "stem": "某旧城改造工程案例题",
                "question_type": "case_study",
                "answer_kind": "case_study",
                "case_bundle": {
                    "coverage_state": "single_subquestion_only",
                    "covered_subquestions": [
                        {
                            "display_index": "1",
                            "prompt": "通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                            "authoritative_answer": "①潜在投标人数量较多；②大型、技术复杂项目；合格制、有限数量制。",
                            "analysis": "第1问标准答案。",
                        }
                    ],
                    "missing_subquestions": [
                        {"display_index": "2", "prompt": "按照完全成本法计算的工程施工项目成本是多少亿元？"}
                    ],
                    "coverage_ratio": 0.5,
                },
            }
        },
    )

    async def _fake_rewrite(**kwargs):
        _ = kwargs
        return (
            "1. 通常进行资格预审的工程特点：潜在投标人数量较多、大型且技术复杂；方法包括合格制和有限数量制。\n"
            "2. 工程施工项目成本应按已召回证据和计算结果作答。"
        )

    monkeypatch.setattr(pipeline, "_rewrite_exact_question_response", _fake_rewrite)

    corrected = await pipeline._apply_exact_question_authority(
        context=context,
        answer_type="problem_solving",
        content="1. 资格预审方法只有合格制。\n2. 成本约10.07亿元。",
        tool_traces=[trace],
        max_tokens=800,
    )

    assert "有限数量制" in corrected
    assert "10.07亿元" not in corrected


@pytest.mark.asyncio
async def test_apply_case_exact_question_authority_renders_full_exact_bundle_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        session_id="session-case-full",
        user_message="某旧城改造工程案例题，请按标准答案作答。",
        language="zh",
    )
    trace = ToolTrace(
        name="rag",
        arguments={"query": "案例题"},
        result="kb result",
        success=True,
        sources=[],
        metadata={
            "exact_question": {
                "id": "9717",
                "stem": "某旧城改造工程案例题",
                "question_type": "case_study",
                "answer_kind": "case_study",
                "coverage_ratio": 1.0,
                "covered_subquestions": [
                    {
                        "display_index": "1",
                        "prompt": "通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                        "authoritative_answer": "①潜在投标人数量较多的项目；②大型、技术复杂的项目。①合格制；②有限数量制。",
                    },
                    {
                        "display_index": "4",
                        "prompt": "按照完全成本法计算的工程施工项目成本是多少亿元？",
                        "authoritative_answer": "12.10-0.72-1.10=10.28 亿元。工程投标、施工准备、施工过程、竣工验收。",
                    },
                ],
                "missing_subquestions": [],
            }
        },
    )

    async def _unexpected_rewrite(**_kwargs):
        raise AssertionError("full exact case bundle should not call llm rewrite")

    monkeypatch.setattr(pipeline, "_rewrite_exact_question_response", _unexpected_rewrite)

    corrected = await pipeline._apply_exact_question_authority(
        context=context,
        answer_type="problem_solving",
        content="1. 特点不详。4. 成本约10.07亿元。",
        tool_traces=[trace],
        max_tokens=800,
    )

    assert corrected == (
        "1. ①潜在投标人数量较多的项目；②大型、技术复杂的项目。①合格制；②有限数量制。\n\n"
        "4. 12.10-0.72-1.10=10.28 亿元。工程投标、施工准备、施工过程、竣工验收。"
    )


@pytest.mark.asyncio
async def test_apply_case_exact_question_authority_ignores_answer_type_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")
    context = UnifiedContext(
        session_id="session-case-full-knowledge",
        user_message="某旧城改造工程案例题，请按标准答案作答。",
        language="zh",
    )
    trace = ToolTrace(
        name="rag",
        arguments={"query": "案例题"},
        result="kb result",
        success=True,
        sources=[],
        metadata={
            "exact_question": {
                "id": "9717",
                "stem": "某旧城改造工程案例题",
                "question_type": "case_study",
                "answer_kind": "case_study",
                "coverage_ratio": 1.0,
                "covered_subquestions": [
                    {
                        "display_index": "2",
                        "prompt": "管理策划内容还有哪些？",
                        "authoritative_answer": "（1）计划、组织、协调方案。",
                    },
                    {
                        "display_index": "4",
                        "prompt": "按照完全成本法计算的工程施工项目成本是多少亿元？",
                        "authoritative_answer": "（1）12.10-0.72-1.10=10.28 亿元。",
                    },
                ],
                "missing_subquestions": [],
            }
        },
    )

    async def _unexpected_rewrite(**_kwargs):
        raise AssertionError("full exact case bundle should not call llm rewrite")

    monkeypatch.setattr(pipeline, "_rewrite_exact_question_response", _unexpected_rewrite)

    corrected = await pipeline._apply_exact_question_authority(
        context=context,
        answer_type="knowledge_explainer",
        content="2. 组织方案、合同管理方案。4. 10.07亿元。",
        tool_traces=[trace],
        max_tokens=800,
    )

    assert corrected == "2. （1）计划、组织、协调方案。\n\n4. （1）12.10-0.72-1.10=10.28 亿元。"


@pytest.mark.asyncio
async def test_run_short_circuits_to_exact_case_authority_before_observing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")

    trace = ToolTrace(
        name="rag",
        arguments={"query": "案例题"},
        result="kb result",
        success=True,
        sources=[{"type": "rag", "title": "case-study"}],
        metadata={
            "exact_question": {
                "id": "9717",
                "stem": "某旧城改造工程案例题",
                "question_type": "case_study",
                "answer_kind": "case_study",
                "coverage_ratio": 1.0,
                "covered_subquestions": [
                    {
                        "display_index": "1",
                        "prompt": "通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                        "authoritative_answer": "（1）①潜在投标人数量较多的项目；②大型、技术复杂的项目。\n（2）①合格制；②有限数量制。",
                    },
                    {
                        "display_index": "4",
                        "prompt": "按照完全成本法计算的工程施工项目成本是多少亿元？",
                        "authoritative_answer": "（1）12.10-0.72-1.10=10.28 亿元。\n（2）工程投标、施工准备、施工过程、竣工验收。",
                    },
                ],
                "missing_subquestions": [],
            }
        },
    )

    async def _fake_retrieval_first(*_args, **_kwargs):
        return [trace]

    async def _unexpected_thinking(*_args, **_kwargs):
        raise AssertionError("full exact case authority should short-circuit before thinking")

    async def _unexpected_acting(*_args, **_kwargs):
        raise AssertionError("full exact case authority should short-circuit before acting")

    async def _unexpected_observing(*_args, **_kwargs):
        raise AssertionError("full exact case authority should short-circuit before observing")

    async def _unexpected_responding(*_args, **_kwargs):
        raise AssertionError("full exact case authority should short-circuit before llm responding")

    monkeypatch.setattr(pipeline, "_stage_retrieval_first", _fake_retrieval_first)
    monkeypatch.setattr(pipeline, "_stage_thinking", _unexpected_thinking)
    monkeypatch.setattr(pipeline, "_stage_acting", _unexpected_acting)
    monkeypatch.setattr(pipeline, "_stage_observing", _unexpected_observing)
    monkeypatch.setattr(pipeline, "_stage_responding", _unexpected_responding)

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-case-run",
        user_message="某旧城改造工程案例题，请按标准答案作答。",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        language="zh",
        metadata={"turn_id": "turn-case-run", "bot_id": "construction-exam-coach"},
        config_overrides={"interaction_profile": "tutorbot"},
    )

    await pipeline.run(context, bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    result_events = [event for event in events if event.type == StreamEventType.RESULT]
    assert len(result_events) == 1
    response = result_events[0].metadata["response"]
    assert "10.28 亿元" in response
    assert "合格制" in response
    assert "10.07" not in response
    assert result_events[0].metadata["observation"] == ""
    stage_starts = [event.stage for event in events if event.type == StreamEventType.STAGE_START]
    assert stage_starts == ["responding"]


@pytest.mark.asyncio
async def test_run_uses_retrieval_first_grounding_without_thinking_when_rag_has_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")

    trace = ToolTrace(
        name="rag",
        arguments={"query": "案例题"},
        result="标准答案片段",
        success=True,
        sources=[{"type": "rag", "title": "case-study"}],
        metadata={"exact_question": {"id": "9717", "answer_kind": "case_study", "coverage_ratio": 0.4, "covered_subquestions": [{"display_index": "1", "prompt": "Q1", "authoritative_answer": "A1"}], "missing_subquestions": [{"display_index": "2", "prompt": "Q2"}]}},
    )

    async def _fake_retrieval_first(*_args, **_kwargs):
        return [trace]

    async def _unexpected_thinking(*_args, **_kwargs):
        raise AssertionError("grounded retrieval-first path should not call thinking when rag already has evidence")

    async def _unexpected_acting(*_args, **_kwargs):
        raise AssertionError("grounded retrieval-first path should not call acting twice")

    async def _fake_observing(*_args, **_kwargs):
        return "已根据 rag 结果整理观察。"

    async def _fake_responding(*_args, **_kwargs):
        return "基于召回结果整理后的答案。", {"label": "Final response", "trace_kind": "stage"}

    monkeypatch.setattr(pipeline, "_stage_retrieval_first", _fake_retrieval_first)
    monkeypatch.setattr(pipeline, "_stage_thinking", _unexpected_thinking)
    monkeypatch.setattr(pipeline, "_stage_acting", _unexpected_acting)
    monkeypatch.setattr(pipeline, "_stage_observing", _fake_observing)
    monkeypatch.setattr(pipeline, "_stage_responding", _fake_responding)

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-case-retrieval-first",
        user_message="某旧城改造工程案例题，请结合知识库作答。",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        language="zh",
        metadata={"turn_id": "turn-case-retrieval-first", "bot_id": "construction-exam-coach"},
        config_overrides={"interaction_profile": "tutorbot"},
    )

    await pipeline.run(context, bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["response"] == "基于召回结果整理后的答案。"
    assert result_event.metadata["observation"] == "已根据 rag 结果整理观察。"


@pytest.mark.asyncio
async def test_run_short_circuits_social_greeting_for_grounded_tutorbot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(binding="openai", model="gpt-test", api_key="k", base_url="u", api_version=None),
    )
    pipeline = AgenticChatPipeline(language="zh")

    async def _unexpected(*_args, **_kwargs):
        raise AssertionError("social greeting should short-circuit before tool or llm stages")

    monkeypatch.setattr(pipeline, "_stage_smart_responding", _unexpected)
    monkeypatch.setattr(pipeline, "_stage_retrieval_first", _unexpected)
    monkeypatch.setattr(pipeline, "_stage_thinking", _unexpected)
    monkeypatch.setattr(pipeline, "_stage_acting", _unexpected)
    monkeypatch.setattr(pipeline, "_stage_observing", _unexpected)
    monkeypatch.setattr(pipeline, "_stage_responding", _unexpected)

    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    context = UnifiedContext(
        session_id="session-greeting",
        user_message="你好",
        enabled_tools=["rag"],
        knowledge_bases=["construction-exam"],
        language="zh",
        metadata={"turn_id": "turn-greeting", "bot_id": "construction-exam-coach"},
        config_overrides={"interaction_profile": "tutorbot", "chat_mode": "smart"},
    )

    await pipeline.run(context, bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert "你好，我是" in response
    assert "考我一道题" in response
    assert "正确答案" not in response
    assert "题目" not in response
    assert result_event.metadata["tool_traces"] == []
    stage_starts = [event.stage for event in events if event.type == StreamEventType.STAGE_START]
    assert stage_starts == ["responding"]
