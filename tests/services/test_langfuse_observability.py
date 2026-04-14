"""Tests for Langfuse observability adapter compatibility behavior."""

from __future__ import annotations

from contextlib import contextmanager

from deeptutor.services.observability.langfuse_adapter import LangfuseObservability


class _FakeObservation:
    def update(self, **_kwargs) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.start_calls: list[dict] = []
        self.propagate_calls: list[dict] = []
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

    @contextmanager
    def propagate_attributes(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_name: str | None = None,
        tags: list[str] | None = None,
    ):
        self.propagate_calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "trace_name": trace_name,
                "tags": tags,
            }
        )
        yield


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
                "tags": ["chat", "session"],
            },
            "model": None,
            "model_parameters": None,
            "usage_details": None,
            "cost_details": None,
        }
    ]
    assert client.propagate_calls == [
        {
            "session_id": "unified_123",
            "user_id": "user_789",
            "trace_name": None,
            "tags": ["chat", "session"],
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
        "total_input_tokens": 170,
        "total_output_tokens": 55,
        "total_tokens": 225,
        "total_calls": 2,
        "measured_calls": 1,
        "estimated_calls": 1,
        "usage_accuracy": "mixed",
        "usage_sources": {"provider": 1, "tiktoken": 1},
        "models": {"gpt-4o": 2},
        "total_cost_usd": 0.0,
    }
    assert adapter.get_current_usage_summary() is None
