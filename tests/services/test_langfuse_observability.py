"""Tests for Langfuse observability adapter compatibility behavior."""

from __future__ import annotations

from contextlib import contextmanager
from types import ModuleType

import pytest

from deeptutor.services.observability.langfuse_adapter import LangfuseObservability


class _FakeObservation:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.start_calls: list[dict] = []
        self.propagate_calls: list[dict] = []
        self.call_order: list[str] = []
        self.observation = _FakeObservation()

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input=None,
        metadata=None,
        model=None,
        model_parameters=None,
        usage_details=None,
        cost_details=None,
        session_id=None,
        user_id=None,
        trace_name=None,
        bot_id=None,
        turn_id=None,
        capability=None,
        execution_engine=None,
        tags=None,
    ):
        self.call_order.append("start")
        self.start_calls.append(
            {
                "name": name,
                "as_type": as_type,
                "input": input,
                "metadata": metadata,
                "model": model,
                "model_parameters": model_parameters,
                "usage_details": usage_details,
                "cost_details": cost_details,
                "session_id": session_id,
                "user_id": user_id,
                "trace_name": trace_name,
                "bot_id": bot_id,
                "turn_id": turn_id,
                "capability": capability,
                "execution_engine": execution_engine,
                "tags": tags,
            }
        )
        yield self.observation

    @contextmanager
    def propagate_attributes(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_name: str | None = None,
        bot_id: str | None = None,
        turn_id: str | None = None,
        capability: str | None = None,
        execution_engine: str | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ):
        self.call_order.append("propagate")
        self.propagate_calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "trace_name": trace_name,
                "bot_id": bot_id,
                "turn_id": turn_id,
                "capability": capability,
                "execution_engine": execution_engine,
                "metadata": metadata,
                "tags": tags,
            }
        )
        yield


class _FakeUsageLedger:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_usage_event(self, **kwargs) -> None:
        self.calls.append(kwargs)


@contextmanager
def _fake_module_propagate_attributes(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_name: str | None = None,
    bot_id: str | None = None,
    turn_id: str | None = None,
    capability: str | None = None,
    execution_engine: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
):
    _fake_module_propagate_attributes.calls.append(
        {
            "session_id": session_id,
            "user_id": user_id,
            "trace_name": trace_name,
            "bot_id": bot_id,
            "turn_id": turn_id,
            "capability": capability,
            "execution_engine": execution_engine,
            "metadata": metadata,
            "tags": tags,
        }
    )
    yield


_fake_module_propagate_attributes.calls = []


def test_start_observation_propagates_session_id_to_langfuse_trace() -> None:
    adapter = LangfuseObservability()
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True

    with adapter.start_observation(
        name="turn.chat",
        as_type="chain",
        input_payload={"content": "hi"},
        metadata={
            "session_id": "unified_123",
            "turn_id": "turn_456",
            "user_id": "user_789",
            "bot_id": "construction-exam-coach",
            "capability": "tutorbot",
            "execution_engine": "tutorbot_runtime",
            "tags": ["chat", "session"],
        },
    ) as observation:
        assert observation is client.observation

    assert client.start_calls == [
        {
            "name": "turn.chat",
            "as_type": "chain",
            "input": {"content": "hi"},
            "metadata": {
                "session_id": "unified_123",
                "turn_id": "turn_456",
                "user_id": "user_789",
                "bot_id": "construction-exam-coach",
                "capability": "tutorbot",
                "execution_engine": "tutorbot_runtime",
                "tags": ["chat", "session"],
            },
            "model": None,
            "model_parameters": None,
            "usage_details": None,
            "cost_details": None,
            "session_id": "unified_123",
            "user_id": "user_789",
            "trace_name": None,
            "bot_id": "construction-exam-coach",
            "turn_id": "turn_456",
            "capability": "tutorbot",
            "execution_engine": "tutorbot_runtime",
            "metadata": {
                "session_id": "unified_123",
                "turn_id": "turn_456",
                "user_id": "user_789",
                "bot_id": "construction-exam-coach",
                "capability": "tutorbot",
                "execution_engine": "tutorbot_runtime",
                "tags": ["chat", "session"],
            },
            "tags": ["chat", "session"],
        }
    ]
    assert client.propagate_calls == [
        {
            "session_id": "unified_123",
            "user_id": "user_789",
            "trace_name": None,
            "bot_id": "construction-exam-coach",
            "turn_id": "turn_456",
            "capability": "tutorbot",
            "execution_engine": "tutorbot_runtime",
            "metadata": {
                "bot_id": "construction-exam-coach",
                "turn_id": "turn_456",
                "capability": "tutorbot",
                "execution_engine": "tutorbot_runtime",
            },
            "tags": ["chat", "session"],
        }
    ]


def test_sanitize_output_redacts_internal_assistant_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_OUTPUT", "1")
    monkeypatch.setenv("LANGFUSE_MASK_PII", "0")

    adapter = LangfuseObservability()
    sanitized = adapter.sanitize_output(
        {"assistant_content": "我来读取相关技能文件，了解详细的使用说明。"}
    )

    assert sanitized == {"assistant_content": "[INTERNAL_OUTPUT_REDACTED]"}


def test_start_observation_uses_module_level_propagation_when_client_lacks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = LangfuseObservability()

    class _ModuleOnlyClient:
        def __init__(self) -> None:
            self.start_calls: list[dict] = []
            self.observation = _FakeObservation()

        @contextmanager
        def start_as_current_observation(
            self,
            *,
            name: str,
            as_type: str = "span",
            input=None,
            metadata=None,
            model=None,
            model_parameters=None,
            usage_details=None,
            cost_details=None,
        ):
            self.start_calls.append(
                {
                    "name": name,
                    "as_type": as_type,
                    "input": input,
                    "metadata": metadata,
                    "model": model,
                    "model_parameters": model_parameters,
                    "usage_details": usage_details,
                    "cost_details": cost_details,
                }
            )
            yield self.observation

    client = _ModuleOnlyClient()
    adapter._client = client
    adapter._init_attempted = True
    _fake_module_propagate_attributes.calls = []

    module = ModuleType("langfuse")
    module.propagate_attributes = _fake_module_propagate_attributes
    monkeypatch.setitem(__import__("sys").modules, "langfuse", module)

    with adapter.start_observation(
        name="turn.chat",
        as_type="chain",
        metadata={
            "session_id": "session-v4",
            "user_id": "user-v4",
            "bot_id": "construction-exam-coach",
            "turn_id": "turn-v4",
            "capability": "tutorbot",
            "execution_engine": "tutorbot_runtime",
        },
    ) as observation:
        assert observation is client.observation

    assert _fake_module_propagate_attributes.calls == [
        {
            "session_id": "session-v4",
            "user_id": "user-v4",
            "trace_name": None,
            "bot_id": "construction-exam-coach",
            "turn_id": "turn-v4",
            "capability": "tutorbot",
            "execution_engine": "tutorbot_runtime",
            "metadata": {
                "bot_id": "construction-exam-coach",
                "turn_id": "turn-v4",
                "capability": "tutorbot",
                "execution_engine": "tutorbot_runtime",
            },
            "tags": None,
        }
    ]


def test_usage_scope_accumulates_usage_with_sources() -> None:
    adapter = LangfuseObservability()

    with adapter.usage_scope(
        scope_id="turn_123",
        session_id="unified_123",
        turn_id="turn_123",
        capability="chat",
    ):
        adapter.record_usage(
            usage_details={"input": 120.0, "output": 30.0, "total": 150.0},
            source="provider",
            model="gpt-4o",
        )
        adapter.record_usage(
            usage_details={"input": 50.0, "output": 25.0, "total": 75.0},
            source="tiktoken",
            model="gpt-4o",
        )
        summary = adapter.get_current_usage_summary()

    assert summary == {
        "scope_id": "turn_123",
        "session_id": "unified_123",
        "turn_id": "turn_123",
        "capability": "chat",
        "total_input_tokens": 120,
        "total_output_tokens": 30,
        "total_tokens": 150,
        "estimated_input_tokens": 50,
        "estimated_output_tokens": 25,
        "estimated_total_tokens": 75,
        "total_calls": 2,
        "measured_calls": 1,
        "estimated_calls": 1,
        "usage_accuracy": "mixed",
        "usage_sources": {"provider": 1, "tiktoken": 1},
        "models": {"gpt-4o": 2},
        "total_cost_usd": 0.0,
        "estimated_total_cost_usd": 0.0,
    }
    assert adapter.get_current_usage_summary() is None


def test_record_usage_writes_global_usage_ledger_without_scope() -> None:
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger

    adapter.record_usage(
        usage_details={"input": 12.0, "output": 8.0, "total": 20.0},
        cost_details={"total": 0.12},
        source="provider",
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
    )

    assert fake_ledger.calls == [
        {
            "usage_source": "provider",
            "usage_details": {"input": 12.0, "output": 8.0, "total": 20.0},
            "cost_details": {"total": 0.12},
            "model": "deepseek-v3.2",
            "metadata": {"provider_name": "dashscope"},
            "session_id": "",
            "turn_id": "",
            "capability": "",
            "scope_id": "",
        }
    ]


def test_record_usage_skips_summary_for_global_usage_ledger() -> None:
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger

    adapter.record_usage(
        usage_details={"input": 100.0, "output": 20.0, "total": 120.0},
        cost_details={"total": 0.5},
        source="summary",
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
    )

    assert fake_ledger.calls == []


def test_usage_details_and_cost_details_from_summary() -> None:
    adapter = LangfuseObservability()
    summary = {
        "total_input_tokens": 128,
        "total_output_tokens": 32,
        "total_tokens": 160,
        "total_cost_usd": 0.0016,
    }

    assert adapter.usage_details_from_summary(summary) == {
        "input": 128.0,
        "output": 32.0,
        "total": 160.0,
    }
    assert adapter.cost_details_from_summary(summary) == {
        "input": 0.0,
        "output": 0.0,
        "total": 0.0016,
    }


def test_summary_metadata_flattens_usage_summary() -> None:
    adapter = LangfuseObservability()
    summary = {
        "scope_id": "turn_123",
        "total_input_tokens": 128,
        "total_output_tokens": 32,
        "total_tokens": 160,
        "estimated_input_tokens": 12,
        "estimated_output_tokens": 0,
        "estimated_total_tokens": 12,
        "total_calls": 4,
        "measured_calls": 3,
        "estimated_calls": 1,
        "usage_accuracy": "mixed",
        "usage_sources": {"provider": 3, "tiktoken": 1},
        "models": {"deepseek-v3.2": 2, "text-embedding-v3": 1},
        "total_cost_usd": 0.0016,
        "estimated_total_cost_usd": 0.00001,
    }

    assert adapter.summary_metadata(summary) == {
        "usage_rollup": "tokens=160; cost=0.0016; accuracy=mixed",
        "usage_scope_id": "turn_123",
        "usage_total_input_tokens": 128,
        "usage_total_output_tokens": 32,
        "usage_total_tokens": 160,
        "usage_estimated_input_tokens": 12,
        "usage_estimated_output_tokens": 0,
        "usage_estimated_total_tokens": 12,
        "usage_total_calls": 4,
        "usage_measured_calls": 3,
        "usage_estimated_calls": 1,
        "usage_accuracy": "mixed",
        "usage_total_cost": 0.0016,
        "usage_estimated_total_cost": 0.00001,
        "usage_sources": {"provider": 3, "tiktoken": 1},
        "usage_models": {"deepseek-v3.2": 2, "text-embedding-v3": 1},
    }


def test_estimated_usage_is_metadata_only_in_langfuse_payload() -> None:
    adapter = LangfuseObservability()
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True

    with adapter.start_observation(
        name="tool.search",
        metadata={"session_id": "session-1"},
        usage_details={"input": 50.0, "output": 10.0, "total": 60.0},
        cost_details={"input": 0.001, "output": 0.002, "total": 0.003},
        usage_source="tiktoken",
    ) as observation:
        adapter.update_observation(
            observation,
            metadata={"turn_id": "turn-1"},
            usage_details={"input": 50.0, "output": 10.0, "total": 60.0},
            cost_details={"input": 0.001, "output": 0.002, "total": 0.003},
            usage_source="tiktoken",
        )

    assert client.start_calls[-1]["usage_details"] is None
    assert client.start_calls[-1]["cost_details"] is None
    assert client.start_calls[-1]["metadata"]["usage_source"] == "tiktoken"
    assert client.start_calls[-1]["metadata"]["estimated_usage_details"] == {
        "input": 50.0,
        "output": 10.0,
        "total": 60.0,
    }
    assert client.start_calls[-1]["metadata"]["estimated_cost_details"] == {
        "input": 0.001,
        "output": 0.002,
        "total": 0.003,
    }

    assert client.observation.updates[-1]["usage_details"] is None
    assert client.observation.updates[-1]["cost_details"] is None
    assert client.observation.updates[-1]["metadata"]["usage_source"] == "tiktoken"
    assert client.observation.updates[-1]["metadata"]["estimated_usage_details"] == {
        "input": 50.0,
        "output": 10.0,
        "total": 60.0,
    }
    assert client.observation.updates[-1]["metadata"]["estimated_cost_details"] == {
        "input": 0.001,
        "output": 0.002,
        "total": 0.003,
    }


def test_estimate_cost_details_supports_gte_rerank_alias() -> None:
    adapter = LangfuseObservability()

    assert adapter.estimate_cost_details(
        model="gte-rerank",
        usage_details={"input": 1250.0, "output": 0.0, "total": 1250.0},
    ) == {
        "input": 0.001,
        "output": 0.0,
        "total": 0.001,
    }


def test_start_observation_preserves_body_exception() -> None:
    adapter = LangfuseObservability()
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True

    with pytest.raises(RuntimeError, match="boom"):
        with adapter.start_observation(name="turn.chat", metadata={"session_id": "session-1"}):
            raise RuntimeError("boom")


def test_get_client_disables_langfuse_when_auth_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("langfuse")

    class _AuthFailingLangfuse:
        def __init__(self, **_kwargs) -> None:
            return None

        def start_as_current_observation(self, **_kwargs):
            raise AssertionError("observation should not start when auth fails")

        def auth_check(self) -> bool:
            return False

    module.Langfuse = _AuthFailingLangfuse
    monkeypatch.setitem(__import__("sys").modules, "langfuse", module)
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    adapter = LangfuseObservability()

    assert adapter._get_client() is None
