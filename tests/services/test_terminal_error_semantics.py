"""律4 terminal error semantics — typed failure birth-to-terminal discipline.

Contract (contracts/turn.md §终端产出纪律):
- Failures keep their TYPE from birth (provider / loop budget / cancel): providers
  never write error bodies into the ``content`` channel; the agent loop never
  improvises a surrogate "final answer" for an exhausted tool budget.
- The learner-visible text for ANY terminal state is decided by exactly ONE
  mapper: ``turn_runtime._safe_terminal_assistant_content`` (via
  ``map_turn_failure_to_public_text``).
- A failed turn must never be committed as ``completed`` (no fake-green), and
  the raw error detail lives in ``turns.error`` (internal), never in public
  turn_events.

All assertions read PERSISTED terminal state (messages / turns / turn_events),
never the live stream.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

BUDGET_SURROGATE_MARKER = "maximum number of tool call iterations"
ACCESS_DENIED_DETAIL = (
    "Error: {'message': 'Access denied, please make sure your account is in good "
    "standing.', 'code': 'AccessDenied'}"
)


# ---------------------------------------------------------------------------
# 1. Terminal mapper (single learner-visible text authority)
# ---------------------------------------------------------------------------


def test_terminal_mapper_maps_budget_exhausted_to_recoverable_chinese() -> None:
    from deeptutor.services.session.turn_runtime import map_turn_failure_to_public_text

    text = map_turn_failure_to_public_text("tool_budget_exhausted")
    assert "再发一次" in text
    assert BUDGET_SURROGATE_MARKER not in text


def test_terminal_mapper_maps_provider_failures_to_busy_chinese() -> None:
    from deeptutor.services.session.turn_runtime import map_turn_failure_to_public_text

    for kind in ("provider_error", "provider_timeout"):
        text = map_turn_failure_to_public_text(kind)
        assert "繁忙" in text
        assert "Error" not in text


def test_terminal_mapper_maps_truncation_to_retryable_chinese() -> None:
    from deeptutor.services.session.turn_runtime import map_turn_failure_to_public_text

    text = map_turn_failure_to_public_text("model_output_truncated")
    assert "没有生成完整" in text
    assert "重新发送" in text


def test_terminal_mapper_keeps_cancelled_and_generic_fallbacks() -> None:
    from deeptutor.services.session.turn_runtime import (
        _PUBLIC_CANCELLED_MESSAGE,
        _PUBLIC_FAILED_MESSAGE,
        map_turn_failure_to_public_text,
    )

    assert map_turn_failure_to_public_text(None, status="cancelled") == _PUBLIC_CANCELLED_MESSAGE
    assert map_turn_failure_to_public_text("totally_unknown_kind") == _PUBLIC_FAILED_MESSAGE
    assert map_turn_failure_to_public_text(None) == _PUBLIC_FAILED_MESSAGE


def test_terminal_mapper_orphan_restart_notice_is_chinese() -> None:
    from deeptutor.services.session.turn_runtime import map_turn_failure_to_public_text

    text = map_turn_failure_to_public_text("orphaned_on_restart")
    assert "重启" in text
    assert "再发一次" in text


def test_safe_terminal_content_failure_kind_overrides_partial_content() -> None:
    from deeptutor.services.session.turn_runtime import (
        _safe_terminal_assistant_content,
        map_turn_failure_to_public_text,
    )

    # A typed failure must map deterministically even if partial content leaked in.
    assert _safe_terminal_assistant_content(
        "Error: {'message': 'Access denied'}",
        status="failed",
        failure_kind="provider_error",
    ) == map_turn_failure_to_public_text("provider_error")


def test_safe_terminal_content_never_promotes_partial_on_non_completed_status() -> None:
    from deeptutor.services.session.turn_runtime import (
        _PUBLIC_CANCELLED_MESSAGE,
        _PUBLIC_FAILED_MESSAGE,
        _safe_terminal_assistant_content,
    )

    assert _safe_terminal_assistant_content("", status="cancelled") == _PUBLIC_CANCELLED_MESSAGE
    assert (
        _safe_terminal_assistant_content("已经写好的部分答案。", status="cancelled")
        == _PUBLIC_CANCELLED_MESSAGE
    )
    assert (
        _safe_terminal_assistant_content("异常前的部分答案。", status="failed")
        == _PUBLIC_FAILED_MESSAGE
    )


@pytest.mark.parametrize(
    ("finish_reason", "expected_failure"),
    [
        ("stop", None),
        ("tool_calls", None),
        ("error", "provider_error"),
        ("length", "model_output_truncated"),
        ("max_tokens", "model_output_truncated"),
        ("content_filter", "model_incomplete_response"),
    ],
)
def test_llm_response_is_single_completion_authority(
    finish_reason: str,
    expected_failure: str | None,
) -> None:
    response = LLMResponse(content="partial", finish_reason=finish_reason)

    assert response.completion_failure_kind == expected_failure
    assert response.is_complete is (expected_failure is None)


def test_new_failure_messages_are_not_chargeable() -> None:
    from deeptutor.services.session.turn_runtime import (
        _is_chargeable_mobile_assistant_content,
        map_turn_failure_to_public_text,
    )

    for kind in ("tool_budget_exhausted", "provider_error", "orphaned_on_restart", None):
        public = map_turn_failure_to_public_text(kind)
        assert _is_chargeable_mobile_assistant_content(public, public) is False


# ---------------------------------------------------------------------------
# 2. Typed failure at birth — providers
# ---------------------------------------------------------------------------


def test_openai_compat_handle_error_preserves_failure_type() -> None:
    from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider

    exc = Exception("boom")
    exc.body = "{'message': 'Access denied'}"
    response = OpenAICompatProvider._handle_error(exc)

    assert response.finish_reason == "error"
    assert response.content is None
    assert response.failure_kind == "provider_error"
    assert "Access denied" in (response.error_detail or "")


def test_anthropic_handle_error_preserves_failure_type() -> None:
    from deeptutor.tutorbot.providers.anthropic_provider import AnthropicProvider

    exc = Exception("boom")
    exc.body = "{'message': 'Access denied'}"
    response = AnthropicProvider._handle_error(exc)

    assert response.finish_reason == "error"
    assert response.content is None
    assert response.failure_kind == "provider_error"
    assert "Access denied" in (response.error_detail or "")


class _RaisingProvider(LLMProvider):
    def __init__(self, error_message: str, succeed_after: int | None = None) -> None:
        super().__init__()
        self.calls = 0
        self._error_message = error_message
        self._succeed_after = succeed_after

    _CHAT_RETRY_DELAYS = (0,)

    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        self.calls += 1
        if self._succeed_after is not None and self.calls > self._succeed_after:
            return LLMResponse(content="正常回答")
        raise RuntimeError(self._error_message)

    def get_default_model(self) -> str:
        return "fake-model"


@pytest.mark.asyncio
async def test_chat_with_retry_wraps_exception_as_typed_failure() -> None:
    provider = _RaisingProvider("Access denied for this key")
    response = await provider.chat_with_retry(messages=[{"role": "user", "content": "hi"}])

    assert response.finish_reason == "error"
    assert response.content is None
    assert response.failure_kind == "provider_error"
    assert "Access denied" in (response.error_detail or "")


@pytest.mark.asyncio
async def test_chat_with_retry_still_retries_transient_typed_errors() -> None:
    provider = _RaisingProvider("429 rate limit exceeded", succeed_after=1)
    response = await provider.chat_with_retry(messages=[{"role": "user", "content": "hi"}])

    assert provider.calls == 2
    assert response.finish_reason != "error"
    assert response.content == "正常回答"


# ---------------------------------------------------------------------------
# 3. Provider error-body delta gate (cheap pre-classification, 200-SSE belt)
# ---------------------------------------------------------------------------


def test_error_stream_gate_suppresses_error_body_deltas() -> None:
    from deeptutor.tutorbot.providers.base import ProviderErrorStreamGate

    gate = ProviderErrorStreamGate()
    deltas = [ACCESS_DENIED_DETAIL[i:i + 12] for i in range(0, len(ACCESS_DENIED_DETAIL), 12)]
    forwarded = "".join(gate.feed(delta) for delta in deltas) + gate.flush()
    assert forwarded == ""
    assert gate.suppressed is True


def test_error_stream_gate_normal_stream_is_byte_identical() -> None:
    from deeptutor.tutorbot.providers.base import ProviderErrorStreamGate

    text = (
        "在调试程序时你可能看到 Error 提示，比如 Error: file not found，"
        "这类报错处理思路是先看栈顶。GB/T 50001 图纸规范与此无关。"
    )
    gate = ProviderErrorStreamGate()
    deltas = [text[i:i + 7] for i in range(0, len(text), 7)]
    forwarded = "".join(gate.feed(delta) for delta in deltas) + gate.flush()
    assert forwarded == text
    assert gate.suppressed is False


def test_error_stream_gate_flushes_short_stream_at_end() -> None:
    from deeptutor.tutorbot.providers.base import ProviderErrorStreamGate

    gate = ProviderErrorStreamGate()
    forwarded = gate.feed("Err")
    forwarded += gate.flush()
    assert forwarded == "Err"
    assert gate.suppressed is False


def test_looks_like_provider_error_content_is_high_confidence() -> None:
    from deeptutor.tutorbot.providers.base import looks_like_provider_error_content

    assert looks_like_provider_error_content(ACCESS_DENIED_DETAIL) is True
    assert looks_like_provider_error_content("Error calling LLM: stream stalled") is True
    # Legit teaching content mentioning Error must NOT be classified as failure.
    assert looks_like_provider_error_content("Error: file not found 的意思是文件没找到") is False
    assert looks_like_provider_error_content("在调试时你会看到 Error: {'message': ...} 这样的报错") is False
    assert looks_like_provider_error_content("") is False


def _sse_chunk(text: str | None, finish_reason: str | None = None) -> Any:
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


class _FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _openai_compat_provider_with_chunks(chunks: list[Any]):
    from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider

    provider = OpenAICompatProvider(
        api_key="sk-test",  # pragma: allowlist secret
        api_base="https://example.invalid/v1",
        default_model="fake-model",
    )

    async def _create(**_kwargs):
        return _FakeStream(chunks)

    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    return provider


@pytest.mark.asyncio
async def test_openai_compat_stream_converts_error_body_to_typed_failure() -> None:
    chunks = [
        _sse_chunk(ACCESS_DENIED_DETAIL[i:i + 12])
        for i in range(0, len(ACCESS_DENIED_DETAIL), 12)
    ]
    chunks.append(_sse_chunk(None, finish_reason="stop"))
    provider = _openai_compat_provider_with_chunks(chunks)

    received: list[str] = []

    async def _collect(text: str) -> None:
        received.append(text)

    response = await provider.chat_stream(
        [{"role": "user", "content": "请批改这道真题"}],
        on_content_delta=_collect,
    )

    assert received == []  # the error body never reaches the content channel
    assert response.finish_reason == "error"
    assert response.content is None
    assert response.failure_kind == "provider_error"
    assert "Access denied" in (response.error_detail or "")


@pytest.mark.asyncio
async def test_openai_compat_stream_without_terminal_chunk_is_incomplete() -> None:
    provider = _openai_compat_provider_with_chunks([_sse_chunk("partial answer")])

    response = await provider.chat_stream(
        [{"role": "user", "content": "请完整回答"}],
    )

    assert response.content == "partial answer"
    assert response.finish_reason == "incomplete"
    assert response.completion_failure_kind == "model_incomplete_response"


def test_anthropic_response_without_stop_reason_is_incomplete() -> None:
    from deeptutor.tutorbot.providers.anthropic_provider import AnthropicProvider

    response = AnthropicProvider._parse_response(
        SimpleNamespace(
            content=[SimpleNamespace(type="text", text="partial answer")],
            stop_reason=None,
            usage=None,
        )
    )

    assert response.finish_reason == "incomplete"
    assert response.completion_failure_kind == "model_incomplete_response"


@pytest.mark.asyncio
async def test_openai_compat_stream_normal_answer_is_byte_identical() -> None:
    text = (
        "施工缝留设要点：先看结构受力。调试报错时看到 Error: xxx 不要慌，"
        "按 GB/T 50001 的图纸逻辑逐项对照即可。"
    )
    chunks = [_sse_chunk(text[i:i + 9]) for i in range(0, len(text), 9)]
    chunks.append(_sse_chunk(None, finish_reason="stop"))
    provider = _openai_compat_provider_with_chunks(chunks)

    received: list[str] = []

    async def _collect(chunk: str) -> None:
        received.append(chunk)

    response = await provider.chat_stream(
        [{"role": "user", "content": "施工缝怎么留？"}],
        on_content_delta=_collect,
    )

    assert "".join(received) == text
    assert response.finish_reason == "stop"
    assert response.content == text
    assert response.failure_kind is None


# ---------------------------------------------------------------------------
# 4. Agent loop — no surrogate final answers, typed turn_failure metadata
# ---------------------------------------------------------------------------


class _ToolLoopingProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content="继续调用工具",
            tool_calls=[
                ToolCallRequest(
                    id=f"call_{self.calls}",
                    name="rag",
                    arguments={"topic": f"round-{self.calls}"},
                )
            ],
        )

    def get_default_model(self) -> str:
        return "fake-model"


class _TypedErrorProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        return LLMResponse(
            content=None,
            finish_reason="error",
            failure_kind="provider_error",
            error_detail=ACCESS_DENIED_DETAIL,
        )

    def get_default_model(self) -> str:
        return "fake-model"


class _HealthyProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        return LLMResponse(
            content=(
                "混凝土浇筑中出现 Error 报警属于设备提示，处理时对照 GB/T 50001 逐项排查即可，"
                "不影响结构验收结论。"
            )
        )

    def get_default_model(self) -> str:
        return "fake-model"


class _TruncatedProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        partial = "先把消防用水量代入公式，再计算"
        if on_content_delta is not None:
            await on_content_delta(partial)
        return LLMResponse(content=partial, finish_reason="length")

    def get_default_model(self) -> str:
        return "fake-model"


class _TruncatedToolProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        return LLMResponse(
            content="正在检索",
            finish_reason="length",
            tool_calls=[
                ToolCallRequest(id="partial", name="rag", arguments={"topic": "partial"})
            ],
        )

    def get_default_model(self) -> str:
        return "fake-model"


class _InvisibleProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        return LLMResponse(content="<think>internal only</think>", finish_reason="stop")

    def get_default_model(self) -> str:
        return "fake-model"


def _build_agent_loop(provider: LLMProvider, tmp_path, with_rag_tool: bool = False):
    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus

    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=5,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    if with_rag_tool:
        class DummyTool(Tool):
            @property
            def name(self) -> str:
                return "rag"

            @property
            def description(self) -> str:
                return "dummy tool"

            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                }

            async def execute(self, **kwargs: Any) -> str:
                return f"executed:{kwargs['topic']}"

        loop.tools = TutorBotToolRegistry()
        loop.tools.register(DummyTool())
    return loop


@pytest.mark.asyncio
async def test_agent_loop_budget_exhaustion_is_typed_not_surrogate(tmp_path) -> None:
    provider = _ToolLoopingProvider()
    loop = _build_agent_loop(provider, tmp_path, with_rag_tool=True)
    metadata: dict[str, Any] = {
        "default_tools": ["rag"],
        "mode_execution_policy": {"max_tool_rounds": 2},
    }

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "一直调用工具"}],
        runtime_metadata=metadata,
    )

    # 2 budgeted search rounds + closure round (tool_choice="none") + repair
    # retry. This stubborn provider ignores the closure contract and keeps
    # emitting tool calls with narration content — closure/repair tool calls
    # are never executed and narration is never promoted to an answer.
    assert provider.calls == 4
    assert tools_used == ["rag", "rag"]
    assert metadata["forced_closure_round"] == 3
    # 律4: budget exhaustion must NOT be improvised into a legit final answer.
    assert final_content is None
    failure = metadata.get("turn_failure")
    assert isinstance(failure, dict)
    assert failure["kind"] == "model_empty_answer"
    assert BUDGET_SURROGATE_MARKER not in json.dumps(metadata, ensure_ascii=False)


@pytest.mark.asyncio
async def test_agent_loop_provider_error_is_typed_failure(tmp_path) -> None:
    loop = _build_agent_loop(_TypedErrorProvider(), tmp_path)
    metadata: dict[str, Any] = {}

    final_content, _tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "请判分"}],
        runtime_metadata=metadata,
    )

    assert final_content is None
    failure = metadata.get("turn_failure")
    assert isinstance(failure, dict)
    assert failure["kind"] == "provider_error"
    assert "Access denied" in str(failure.get("detail") or "")


@pytest.mark.asyncio
async def test_agent_loop_truncated_output_is_typed_failure_not_history(tmp_path) -> None:
    loop = _build_agent_loop(_TruncatedProvider(), tmp_path)
    metadata: dict[str, Any] = {}

    final_content, _tools_used, messages = await loop._run_agent_loop(
        [{"role": "user", "content": "请给出完整计算过程"}],
        runtime_metadata=metadata,
    )

    assert final_content is None
    assert messages == [{"role": "user", "content": "请给出完整计算过程"}]
    assert metadata["turn_failure"]["kind"] == "model_output_truncated"
    assert metadata["llm_stream_telemetry"]["calls"][-1]["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_fast_policy_truncated_output_is_typed_failure_not_history(tmp_path) -> None:
    loop = _build_agent_loop(_TruncatedProvider(), tmp_path)
    metadata: dict[str, Any] = {}
    initial = [{"role": "user", "content": "请简答"}]

    final_content, messages, _streamed = await loop._run_fast_policy_once(
        initial,
        runtime_metadata=metadata,
    )

    assert final_content is None
    assert messages == initial
    assert metadata["turn_failure"]["kind"] == "model_output_truncated"


@pytest.mark.asyncio
async def test_truncated_tool_call_is_never_executed(tmp_path, monkeypatch) -> None:
    loop = _build_agent_loop(_TruncatedToolProvider(), tmp_path, with_rag_tool=True)
    executions: list[tuple[str, dict[str, Any]]] = []

    async def _execute(name: str, arguments: dict[str, Any]) -> str:
        executions.append((name, arguments))
        return "must not run"

    monkeypatch.setattr(loop.tools, "execute", _execute)
    metadata: dict[str, Any] = {}
    initial = [{"role": "user", "content": "请检索并计算"}]

    final_content, _tools_used, messages = await loop._run_agent_loop(
        initial,
        runtime_metadata=metadata,
    )

    assert final_content is None
    assert messages == initial
    assert executions == []
    assert metadata["turn_failure"]["kind"] == "model_output_truncated"


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["deep", "fast"])
async def test_invisible_answer_is_typed_failure_not_completed_history(tmp_path, policy) -> None:
    loop = _build_agent_loop(_InvisibleProvider(), tmp_path)
    metadata: dict[str, Any] = {}
    initial = [{"role": "user", "content": "请回答"}]

    if policy == "deep":
        final_content, _tools_used, messages = await loop._run_agent_loop(
            initial,
            runtime_metadata=metadata,
        )
    else:
        final_content, messages, _streamed = await loop._run_fast_policy_once(
            initial,
            runtime_metadata=metadata,
        )

    assert final_content is None
    assert messages == initial
    assert metadata["turn_failure"]["kind"] == "model_empty_answer"


@pytest.mark.asyncio
async def test_agent_loop_normal_answer_untouched_and_unmarked(tmp_path) -> None:
    loop = _build_agent_loop(_HealthyProvider(), tmp_path)
    metadata: dict[str, Any] = {}

    final_content, _tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "混凝土浇筑报警怎么处理？"}],
        runtime_metadata=metadata,
    )

    assert final_content == (
        "混凝土浇筑中出现 Error 报警属于设备提示，处理时对照 GB/T 50001 逐项排查即可，"
        "不影响结构验收结论。"
    )
    assert "turn_failure" not in metadata


@pytest.mark.asyncio
async def test_agent_loop_pops_stale_turn_failure_from_incoming_metadata(tmp_path) -> None:
    loop = _build_agent_loop(_HealthyProvider(), tmp_path)
    metadata: dict[str, Any] = {"turn_failure": {"kind": "provider_error", "detail": "stale"}}

    final_content, _tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "继续讲"}],
        runtime_metadata=metadata,
    )

    assert final_content
    assert "turn_failure" not in metadata


@pytest.mark.asyncio
async def test_process_direct_failure_exports_typed_metadata_without_surrogate(tmp_path) -> None:
    from deeptutor.tutorbot.session.manager import Session

    sessions: dict[str, Session] = {}

    async def _get_or_create(key: str) -> Session:
        if key not in sessions:
            sessions[key] = Session(key=key)
        return sessions[key]

    loop = _build_agent_loop(_TypedErrorProvider(), tmp_path)
    loop.sessions = SimpleNamespace(
        get_or_create=_get_or_create,
        save=lambda session: None,
        invalidate=lambda key: None,
    )

    caller_metadata: dict[str, Any] = {}
    response = await loop.process_direct(
        "你好，介绍一下自己",
        session_key="cli:typed-failure",
        metadata=caller_metadata,
    )

    assert response == ""
    failure = caller_metadata.get("turn_failure")
    assert isinstance(failure, dict)
    assert failure["kind"] == "provider_error"
    # No surrogate learner-visible text is fabricated below the terminal mapper.
    assert "模型调用失败" not in json.dumps(caller_metadata, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 5. Turn runtime end-to-end — persisted terminal truth (messages/turns/events)
# ---------------------------------------------------------------------------


async def _noop_refresh(**_kwargs):
    return None


def _install_runtime_fakes(monkeypatch: pytest.MonkeyPatch, orchestrator_cls) -> None:
    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder
    )
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", orchestrator_cls)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )


async def _drain_turn(runtime: TurnRuntimeManager, turn_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for event in runtime.subscribe_turn(turn_id, after_seq=0):
        events.append(event)
    return events


def _public_events_text(events: list[dict[str, Any]]) -> str:
    public = [
        event for event in events
        if str(event.get("visibility") or "public").strip().lower() != "internal"
    ]
    return json.dumps(public, ensure_ascii=False)


@pytest.mark.asyncio
async def test_turn_runtime_budget_exhaustion_persists_failed_chinese_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class BudgetExhaustedOrchestrator:
        async def handle(self, _context, **_kwargs):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "",
                    "presentation": {"type": "question_card"},
                    "question_followup_context": {"question_id": "partial-q"},
                    "active_object": {
                        "object_type": "question",
                        "object_id": "partial-q",
                        "state_snapshot": {"question_id": "partial-q"},
                    },
                    "suspended_object_stack": [{"object_id": "old"}],
                    "next_best_action": {"action": "practice"},
                    "metadata": {
                        "active_object": {
                            "object_type": "question",
                            "object_id": "nested-partial-q",
                            "state_snapshot": {"question_id": "nested-partial-q"},
                        },
                        "question_followup_context": {"question_id": "nested-partial-q"},
                        "suspended_object_stack": [{"object_id": "nested-old"}],
                        "presentation": {"type": "nested-question-card"},
                        "next_best_action": {"action": "nested-practice"},
                    },
                    "turn_failure": {
                        "kind": "tool_budget_exhausted",
                        "budget": 4,
                        "detail": "agent loop reached max tool rounds (4) without final answer",
                    },
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    _install_runtime_fakes(monkeypatch, BudgetExhaustedOrchestrator)
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请批改这道真题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "language": "zh",
            "config": {},
        }
    )
    events = await _drain_turn(runtime, turn["id"])

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["status"] == "failed"  # 假绿禁令
    assert "max tool rounds" in persisted_turn["error"]

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert "再发一次" in assistant_messages[0]["content"]
    assert BUDGET_SURROGATE_MARKER not in assistant_messages[0]["content"]
    assert assistant_messages[0]["metadata"]["terminal_status"] == "failed"

    result_events = [e for e in events if e.get("type") == "result"]
    assert result_events
    assert result_events[-1]["metadata"]["error_code"] == "tool_budget_exhausted"
    assert "再发一次" in result_events[-1]["metadata"]["response"]
    for forbidden in (
        "presentation",
        "question_followup_context",
        "active_object",
        "suspended_object_stack",
        "next_best_action",
    ):
        assert forbidden not in result_events[-1]["metadata"]
        assert forbidden not in result_events[-1]["metadata"].get("metadata", {})
    persisted_active_object = await store.get_active_object(session["id"])
    assert str((persisted_active_object or {}).get("object_id") or "") != "partial-q"
    assert str((persisted_active_object or {}).get("object_id") or "") != "nested-partial-q"

    done_events = [e for e in events if e.get("type") == "done"]
    assert done_events and done_events[-1]["metadata"]["status"] == "failed"

    persisted_events = await store.get_turn_events(turn["id"])
    assert BUDGET_SURROGATE_MARKER not in _public_events_text(persisted_events)


@pytest.mark.asyncio
async def test_turn_runtime_exception_after_partial_never_commits_partial_as_assistant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.session.turn_runtime import map_turn_failure_to_public_text

    partial = "这是异常发生前尚未完成的半截答案"

    class ExceptionAfterPartialOrchestrator:
        async def handle(self, _context, **_kwargs):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content=partial,
                metadata={"call_kind": "llm_final_response"},
            )
            raise RuntimeError("synthetic terminal failure")

    _install_runtime_fakes(monkeypatch, ExceptionAfterPartialOrchestrator)
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    free_trial_finalize_calls: list[dict[str, Any]] = []
    learning_calls: list[object] = []

    def _spy_finalize(_billing_context, **kwargs):
        free_trial_finalize_calls.append(dict(kwargs))
        return {"status": "released"}

    monkeypatch.setattr(
        runtime,
        "_finalize_free_trial_reservation",
        _spy_finalize,
    )
    monkeypatch.setattr(
        runtime,
        "_record_mobile_learning",
        lambda *args, **kwargs: learning_calls.append((args, kwargs)),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请完整回答",
            "session_id": None,
            "capability": None,
            "tools": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "wallet_user_id": "terminal-failure-user",
                    "free_trial": "reserved",
                    "free_trial_reservation_key": "terminal-failure-reservation",
                }
            },
        }
    )
    events = await _drain_turn(runtime, turn["id"])

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn["status"] == "failed"
    detail = await store.get_session_with_messages(session["id"])
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert partial not in assistant_messages[0]["content"]
    assert assistant_messages[0]["content"] == map_turn_failure_to_public_text(None)
    error_events = [event for event in events if event.get("type") == "error"]
    assert error_events and partial not in str(error_events[-1].get("content") or "")
    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events[-1]["metadata"]["status"] == "failed"
    assert len(free_trial_finalize_calls) == 1
    assert free_trial_finalize_calls[0]["chargeable"] is False
    assert learning_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["provider_error", "provider_timeout"])
async def test_turn_runtime_provider_error_persists_failed_without_leak(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    failure_kind: str,
) -> None:
    class ProviderErrorOrchestrator:
        async def handle(self, _context, **_kwargs):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "",
                    "turn_failure": {"kind": failure_kind, "detail": ACCESS_DENIED_DETAIL},
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    _install_runtime_fakes(monkeypatch, ProviderErrorOrchestrator)
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "老师你好，第一次提问",
            "session_id": None,
            "capability": None,
            "tools": [],
            "language": "zh",
            "config": {},
        }
    )
    events = await _drain_turn(runtime, turn["id"])

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["status"] == "failed"
    assert "Access denied" in persisted_turn["error"]  # raw detail lives in turns.error

    detail = await store.get_session_with_messages(session["id"])
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert "繁忙" in assistant_messages[0]["content"]
    assert "Access denied" not in assistant_messages[0]["content"]

    result_events = [e for e in events if e.get("type") == "result"]
    assert result_events[-1]["metadata"]["error_code"] == failure_kind

    # The raw provider error body never appears in PUBLIC turn events.
    persisted_events = await store.get_turn_events(turn["id"])
    assert "Access denied" not in _public_events_text(persisted_events)


@pytest.mark.asyncio
async def test_turn_runtime_normal_teaching_answer_with_error_word_is_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.user_visible_output import coerce_user_visible_answer
    from deeptutor.tutorbot.markdown_style import normalize_markdown_for_tutorbot

    text = (
        "调试脚本时看到 Error: file not found 不必紧张，先确认路径。"
        "图纸标注按 GB/T 50001 执行，防火墙耐火极限按 GB 50016-2014 判断。"
        "这些报错处理思路都属于正常教学内容。"
    )
    chunk_a, chunk_b = text[:31], text[31:]

    class TeachingOrchestrator:
        async def handle(self, _context, **_kwargs):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content=chunk_a,
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content=chunk_b,
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={"response": text},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    _install_runtime_fakes(monkeypatch, TeachingOrchestrator)
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "调试报错怎么处理？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "language": "zh",
            "config": {},
        }
    )
    events = await _drain_turn(runtime, turn["id"])

    # Counterexample guarantee: the healthy path stays byte-identical.
    content_events = [e for e in events if e.get("type") == "content"]
    assert [e["content"] for e in content_events] == [chunk_a, chunk_b]

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn["status"] == "completed"
    assert persisted_turn["error"] == ""

    detail = await store.get_session_with_messages(session["id"])
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    expected = normalize_markdown_for_tutorbot(coerce_user_visible_answer(text))
    assert assistant_messages[0]["content"] == expected
    assert assistant_messages[0]["metadata"]["terminal_status"] == "completed"

    result_events = [e for e in events if e.get("type") == "result"]
    assert "error_code" not in result_events[-1]["metadata"]
    done_events = [e for e in events if e.get("type") == "done"]
    assert done_events[-1]["metadata"]["status"] == "completed"


@pytest.mark.asyncio
async def test_turn_runtime_terminal_cas_rejects_completed_overwrite_of_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Example C: a cross-worker cancel flips the DB row; the execution holder must
    NOT resurrect the turn to completed, must not publish the assistant message,
    and must not capture billing."""

    release = asyncio.Event()
    started = asyncio.Event()

    class SlowOrchestrator:
        async def handle(self, _context, **_kwargs):
            started.set()
            await release.wait()
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={"response": "迟到的完整回答。"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    _install_runtime_fakes(monkeypatch, SlowOrchestrator)
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    billing_calls: list[dict[str, Any]] = []

    def _spy_capture(_billing_context, _assistant_content, **kwargs):
        billing_calls.append(dict(kwargs))
        return None

    monkeypatch.setattr(runtime, "_capture_mobile_points", _spy_capture)

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一问",
            "session_id": None,
            "capability": None,
            "tools": [],
            "language": "zh",
            "config": {},
        }
    )
    await asyncio.wait_for(started.wait(), timeout=5)

    # Simulate the second worker: cancel is a DB-row flip only.
    assert await store.update_turn_status(turn["id"], "cancelled", "superseded_by_new_turn") is True
    release.set()
    await _drain_turn(runtime, turn["id"])

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn["status"] == "cancelled"  # terminal state absorbs; no resurrection

    detail = await store.get_session_with_messages(session["id"])
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert assistant_messages == []  # superseded assistant output is not published
    assert billing_calls == []  # and billing is never captured


# ---------------------------------------------------------------------------
# 流式覆写的同源后缀豁免（turn.md:144 增补，2026-07-29）
# ---------------------------------------------------------------------------
def test_stream_replacement_keeps_finalized_suffix_response() -> None:
    """finalize 链剥掉开头独白后，终态是流文本的严格后缀——覆写必须让位于
    finalize 权威，不得把已剥离的独白前缀复活。"""
    from deeptutor.core.stream import StreamEvent, StreamEventType
    from deeptutor.services.session.turn_runtime import (
        _replace_public_result_response_with_stream,
    )

    streamed = "现在我有足够的知识库证据来回答第3题。让我来组织完整回答。\n\n## 第3题：临时用水管理"
    finalized = "## 第3题：临时用水管理"
    event = StreamEvent(
        type=StreamEventType.RESULT,
        metadata={"visibility": "public", "response": finalized},
    )

    _replace_public_result_response_with_stream(event, streamed)

    assert event.metadata["response"] == finalized  # 后缀豁免生效


def test_stream_replacement_still_overrides_heterogeneous_response() -> None:
    """turn.md:144 原保护不回退：异源 stale/fallback 文本（非流后缀）仍被
    流文本替换，学生看到什么终态就是什么。"""
    from deeptutor.core.stream import StreamEvent, StreamEventType
    from deeptutor.services.session.turn_runtime import (
        _replace_public_result_response_with_stream,
    )

    streamed = "## 第3题：临时用水管理中的不妥及正确做法"
    event = StreamEvent(
        type=StreamEventType.RESULT,
        metadata={"visibility": "public", "response": "暂时未生成适合直接展示的答案，请重试一次。"},
    )

    _replace_public_result_response_with_stream(event, streamed)

    assert "临时用水管理" in event.metadata["response"]


def test_terminal_mapper_maps_deadline_exceeded_to_typed_chinese() -> None:
    """2026-08-10 F3 钉:deadline 处决不再是无类型静默降级——专属 kind + 专属文案,
    与任意未知失败(_PUBLIC_FAILED_MESSAGE)可区分。"""
    from deeptutor.services.session.turn_runtime import map_turn_failure_to_public_text

    text = map_turn_failure_to_public_text("deadline_exceeded")
    assert "任务量较大" in text
    assert text != map_turn_failure_to_public_text(None)
    assert text != map_turn_failure_to_public_text("tool_budget_exhausted")
