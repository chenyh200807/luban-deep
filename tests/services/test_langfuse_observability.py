"""Tests for Langfuse observability adapter compatibility behavior."""

from __future__ import annotations

from contextlib import contextmanager
from types import ModuleType

import pytest

from deeptutor.services.construction_grading.case_output_policy import (
    CASE_GRADING_AUTHORITY_EXPORT_KEYS,
)
from deeptutor.services.observability.langfuse_adapter import (
    _METADATA_NESTED_KEY_LIMIT,
    _METADATA_TOP_LEVEL_KEY_LIMIT,
    LangfuseObservability,
    _NoopObservation,
    _normalize_langfuse_host,
)


class _FakeObservation:
    def __init__(self, trace_id: str = "") -> None:
        self.trace_id = trace_id
        self.updates: list[dict] = []
        self.events: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)
        return None

    def create_event(
        self,
        *,
        name: str,
        metadata=None,
        level=None,
        status_message=None,
    ) -> None:
        self.events.append(
            {
                "name": name,
                "metadata": metadata,
                "level": level,
                "status_message": status_message,
            }
        )
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


def test_observation_trace_id_reads_langfuse_observation_identity() -> None:
    adapter = LangfuseObservability()

    assert adapter.observation_trace_id(_FakeObservation(trace_id="trace-direct-1")) == (
        "trace-direct-1"
    )


def test_observation_trace_id_ignores_missing_or_noop_observation() -> None:
    adapter = LangfuseObservability()

    assert adapter.observation_trace_id(None) == ""
    assert adapter.observation_trace_id(_FakeObservation()) == ""


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


def test_sanitize_metadata_preserves_trace_identity_fields_when_pii_masking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_MASK_PII", "1")
    adapter = LangfuseObservability()

    sanitized = adapter.sanitize_metadata(
        {
            "session_id": "tb_af037a7ee6f847c5b6b4d72d",
            "turn_id": "turn_1777698668043_1c9a67b18b",
            "trace_id": "7500df48ad329927093d5c1d6aa0fca8",
            "request_id": "codex-feedback-log-smoke",
            "user_phone": "13800001234",
        }
    )

    assert sanitized["session_id"] == "tb_af037a7ee6f847c5b6b4d72d"
    assert sanitized["turn_id"] == "turn_1777698668043_1c9a67b18b"
    assert sanitized["trace_id"] == "7500df48ad329927093d5c1d6aa0fca8"
    assert sanitized["request_id"] == "codex-feedback-log-smoke"
    assert sanitized["user_phone"] == "[PHONE]"


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


def test_record_usage_keeps_charged_provider_and_api_base() -> None:
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger

    adapter.record_usage(
        usage_details={"input": 10.0, "output": 2.0, "total": 12.0},
        cost_details={"total": 0.001},
        source="provider",
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "charged_provider_name": "deepseek",
            "requested_provider_name": "deepseek",
            "api_base": "https://api.deepseek.com",
            "effective_url": "https://api.deepseek.com",
            "api_key_fingerprint": "sha256:synthetic",  # pragma: allowlist secret
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
            "billable_unit": "conversation_turn",
            "billable_turn_id": "turn-1",
            "raw_model": "deepseek-v4-flash",
            "pricing_model": "deepseek-v4-flash",
        },
    )

    assert fake_ledger.calls[0]["metadata"]["provider_name"] == "deepseek"
    assert fake_ledger.calls[0]["metadata"]["charged_provider_name"] == "deepseek"
    assert fake_ledger.calls[0]["metadata"]["cost_center"] == "prod_user_chat"
    assert fake_ledger.calls[0]["metadata"]["billable_turn_id"] == "turn-1"
    assert fake_ledger.calls[0]["metadata"]["api_base"] == "https://api.deepseek.com"


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
        "estimated_input_tokens": 12,
        "estimated_output_tokens": 0,
        "estimated_total_tokens": 12,
        "total_cost_usd": 0.0016,
        "estimated_total_cost_usd": 0.00001,
    }

    assert adapter.usage_details_from_summary(summary) == {
        "input": 140.0,
        "output": 32.0,
        "total": 172.0,
    }
    assert adapter.cost_details_from_summary(summary) == {
        "input": 0.0,
        "output": 0.0,
        "total": 0.00161,
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
        "usage_rollup": "tokens=172; cost=0.00161; accuracy=mixed",
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


def test_estimated_usage_is_exported_to_langfuse_payload() -> None:
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

    assert client.start_calls[-1]["usage_details"] == {
        "input": 50.0,
        "output": 10.0,
        "total": 60.0,
    }
    assert client.start_calls[-1]["cost_details"] == {
        "input": 0.001,
        "output": 0.002,
        "total": 0.003,
    }
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

    assert client.observation.updates[-1]["usage_details"] == {
        "input": 50.0,
        "output": 10.0,
        "total": 60.0,
    }
    assert client.observation.updates[-1]["cost_details"] == {
        "input": 0.001,
        "output": 0.002,
        "total": 0.003,
    }
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


# ----------------------------------------------------------------------------------
# Battle2 S3-T1: completion_start_time passthrough (Langfuse timeToFirstToken)
# ----------------------------------------------------------------------------------
def test_update_observation_passes_completion_start_time_through() -> None:
    from datetime import datetime, timezone

    adapter = LangfuseObservability()
    observation = _FakeObservation()
    first_chunk_at = datetime(2026, 7, 12, 3, 4, 5, tzinfo=timezone.utc)

    adapter.update_observation(
        observation,
        output_payload="hello",
        completion_start_time=first_chunk_at,
    )

    assert observation.updates[-1]["completion_start_time"] == first_chunk_at


def test_update_observation_defaults_completion_start_time_to_none() -> None:
    adapter = LangfuseObservability()
    observation = _FakeObservation()

    adapter.update_observation(observation, output_payload="hello")

    assert observation.updates[-1]["completion_start_time"] is None


def test_update_observation_completion_start_time_noop_observation_does_not_raise() -> None:
    from datetime import datetime, timezone

    from deeptutor.services.observability.langfuse_adapter import _NoopObservation

    adapter = LangfuseObservability()
    adapter.update_observation(
        _NoopObservation(),
        output_payload="hello",
        completion_start_time=datetime.now(timezone.utc),
    )  # must not raise (fail-open)


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


def test_deepseek_v4_flash_pricing_uses_official_cache_miss_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_MODEL_PRICING_JSON", raising=False)
    adapter = LangfuseObservability()

    assert adapter.estimate_cost_details(
        model="deepseek-v4-flash",
        usage_details={"input": 1_000_000.0, "output": 1_000_000.0, "total": 2_000_000.0},
    ) == {
        "input": 0.14,
        "output": 0.28,
        "total": 0.42,
    }


def test_deepseek_v4_flash_cost_uses_cache_hit_and_miss_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_MODEL_PRICING_JSON", raising=False)
    adapter = LangfuseObservability()

    assert adapter.estimate_cost_details(
        model="deepseek-v4-flash",
        usage_details={
            "input": 1_000_000.0,
            "input_cache_hit": 800_000.0,
            "input_cache_miss": 200_000.0,
            "output": 100_000.0,
            "total": 1_100_000.0,
        },
    ) == {
        "input": 0.03024,
        "output": 0.028,
        "total": 0.05824,
    }


def test_update_observation_writes_pricing_metadata_to_usage_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_MODEL_PRICING_JSON", raising=False)
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger

    adapter.update_observation(
        _FakeObservation(),
        metadata={"provider_name": "deepseek"},
        usage_details={"input": 1.0, "output": 1.0, "total": 2.0},
        cost_details={"input": 0.0, "output": 0.0, "total": 0.0},
        usage_source="provider",
        model="deepseek-v4-flash",
    )

    metadata = fake_ledger.calls[0]["metadata"]
    assert metadata["provider_name"] == "deepseek"
    assert metadata["pricing_currency"] == "USD"
    assert metadata["billing_currency"] == "USD"
    assert metadata["pricing_source"] == "deepseek-official-2026-06-03"
    assert metadata["pricing_source_checked_at"] == "2026-06-03"


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


def test_normalize_langfuse_host_strips_public_api_suffixes() -> None:
    assert _normalize_langfuse_host("http://localhost:3001/api/public") == "http://localhost:3001"
    assert (
        _normalize_langfuse_host("https://langfuse.example.com/base/api/public/ingestion")
        == "https://langfuse.example.com/base"
    )


def test_get_client_normalizes_langfuse_host_before_sdk_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("langfuse")
    captured: dict[str, object] = {}

    class _CapturingLangfuse:
        def __init__(
            self,
            *,
            public_key=None,
            secret_key=None,
            host=None,
            base_url=None,
            timeout=None,
            httpx_client=None,
            debug=None,
            tracing_enabled=None,
            flush_at=None,
            flush_interval=None,
            environment=None,
        ) -> None:
            captured.update(
                {
                    "public_key": public_key,
                    "secret_key": secret_key,
                    "host": host,
                    "base_url": base_url,
                    "timeout": timeout,
                    "httpx_client": httpx_client,
                    "debug": debug,
                    "tracing_enabled": tracing_enabled,
                    "flush_at": flush_at,
                    "flush_interval": flush_interval,
                    "environment": environment,
                }
            )

        def start_as_current_observation(self, **_kwargs):
            raise AssertionError("observation should not start in client init test")

        def auth_check(self) -> bool:
            return True

    module.Langfuse = _CapturingLangfuse
    monkeypatch.setitem(__import__("sys").modules, "langfuse", module)
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3001/api/public")

    adapter = LangfuseObservability()

    assert adapter._get_client() is not None
    assert captured["host"] == "http://localhost:3001"
    assert captured["base_url"] == "http://localhost:3001"


# --- task#19 终点黑洞：终态 marker 必须真的到达 Langfuse ------------------------


def _terminal_marker_family() -> dict[str, str]:
    """判分权威族 + 两个终态判别位，取值带哨兵前缀便于断言。"""
    family = {key: f"v::{key}" for key in CASE_GRADING_AUTHORITY_EXPORT_KEYS}
    family["execution_path"] = "v::execution_path"
    family["score_authority"] = "v::score_authority"
    return family


def test_sanitize_metadata_keeps_terminal_markers_past_the_first_twenty_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """终点黑洞根因回归：顶层 metadata 曾被静默砍成前 20 个键。

    真实的 turn 终态 metadata 里，skill_metadata + usage 汇总先占满 20 个位置，
    判分权威族排在它们之后 —— 于是每一轮都被剥光，Langfuse 只剩 start 指纹。
    这个断言就是那条线：前置 20 个填充键之后的整族 marker 必须一个不少。
    """
    monkeypatch.setenv("LANGFUSE_MASK_PII", "0")
    adapter = LangfuseObservability()

    family = _terminal_marker_family()
    metadata = {f"usage_filler_{index:02d}": index for index in range(20)}
    metadata.update(family)
    assert len(metadata) > 20

    sanitized = adapter.sanitize_metadata(metadata)

    assert sanitized is not None
    missing = [key for key in family if key not in sanitized]
    assert missing == []
    for key, value in family.items():
        assert sanitized[key] == value
    assert "metadata_truncated_key_count" not in sanitized


def test_sanitize_metadata_declares_truncation_instead_of_dropping_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """截断仍然可能发生（OTel 128 属性硬顶），但绝不允许再静默。"""
    monkeypatch.setenv("LANGFUSE_MASK_PII", "0")
    adapter = LangfuseObservability()

    over_limit = _METADATA_TOP_LEVEL_KEY_LIMIT + 7
    metadata = {f"k{index:04d}": index for index in range(over_limit)}

    sanitized = adapter.sanitize_metadata(metadata)

    assert sanitized is not None
    kept = [key for key in sanitized if key.startswith("k")]
    assert len(kept) == _METADATA_TOP_LEVEL_KEY_LIMIT
    assert sanitized["metadata_truncated_key_count"] == 7
    assert sanitized["metadata_truncated_keys"] == [
        f"k{index:04d}" for index in range(_METADATA_TOP_LEVEL_KEY_LIMIT, over_limit)
    ]


def test_sanitize_metadata_still_bounds_nested_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """顶层放宽不等于嵌套放宽：单个大 payload 不能把 span 属性预算撑爆。"""
    monkeypatch.setenv("LANGFUSE_MASK_PII", "0")
    adapter = LangfuseObservability()

    sanitized = adapter.sanitize_metadata(
        {"nested": {f"n{index:03d}": index for index in range(60)}}
    )

    assert sanitized is not None
    assert len(sanitized["nested"]) == _METADATA_NESTED_KEY_LIMIT


def test_record_turn_terminal_state_emits_event_carrying_full_marker_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """终态 marker 族要能在 Langfuse 上按 name='turn.terminal_state' 一行查到。"""
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_MASK_PII", "0")
    adapter = LangfuseObservability()
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True
    observation = _FakeObservation(trace_id="trace-terminal-1")

    family = _terminal_marker_family()
    emitted = adapter.record_turn_terminal_state(
        observation,
        metadata={"turn_status": "completed", **family},
    )

    assert emitted is True
    assert len(observation.events) == 1
    event = observation.events[0]
    assert event["name"] == "turn.terminal_state"
    assert event["metadata"]["turn_status"] == "completed"
    for key, value in family.items():
        assert event["metadata"][key] == value


def test_record_turn_terminal_state_forwards_error_level_for_failed_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    adapter = LangfuseObservability()
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True
    observation = _FakeObservation()

    adapter.record_turn_terminal_state(
        observation,
        metadata={"turn_status": "failed"},
        level="ERROR",
        status_message="turn terminal status=failed",
    )

    assert observation.events[0]["level"] == "ERROR"
    assert observation.events[0]["status_message"] == "turn terminal status=failed"


def test_record_turn_terminal_state_is_a_safe_noop_without_langfuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """best-effort：关闭/未接通/观测缺失时静默返回 False，永不抛。"""
    monkeypatch.setenv("LANGFUSE_ENABLED", "0")
    adapter = LangfuseObservability()
    adapter._client = _FakeClient()
    adapter._init_attempted = True

    assert adapter.record_turn_terminal_state(_FakeObservation(), metadata={"a": 1}) is False

    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    assert adapter.record_turn_terminal_state(None, metadata={"a": 1}) is False
    assert (
        adapter.record_turn_terminal_state(_NoopObservation(), metadata={"a": 1}) is False
    )

    class _ObservationWithoutEvents:
        pass

    assert (
        adapter.record_turn_terminal_state(_ObservationWithoutEvents(), metadata={"a": 1})
        is False
    )


def test_record_turn_terminal_state_swallows_sdk_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    adapter = LangfuseObservability()
    adapter._client = _FakeClient()
    adapter._init_attempted = True

    class _ExplodingObservation:
        def create_event(self, *, name: str, metadata=None, level=None, status_message=None):
            raise RuntimeError("langfuse exporter down")

    assert (
        adapter.record_turn_terminal_state(_ExplodingObservation(), metadata={"a": 1}) is False
    )


def test_record_usage_stamps_call_site_from_enclosing_observation_name() -> None:
    """效率画像 §6 插桩缺口：llm_usage_events 的 call_site 此前 683 条全空。"""
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True

    with adapter.start_observation(name="llm.complete", as_type="generation") as observation:
        adapter.update_observation(
            observation,
            usage_details={"input": 10.0, "output": 5.0, "total": 15.0},
            usage_source="provider",
            model="deepseek-v3.2",
            metadata={"provider_name": "dashscope"},
        )

    assert fake_ledger.calls
    assert fake_ledger.calls[-1]["metadata"]["call_site"] == "llm.complete"


def test_explicit_call_site_overrides_the_observation_name() -> None:
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True

    with adapter.start_observation(
        name="llm.complete",
        as_type="generation",
        call_site="case_rubric_batch_judge",
    ) as observation:
        adapter.update_observation(
            observation,
            usage_details={"input": 10.0, "output": 5.0, "total": 15.0},
            usage_source="provider",
            model="deepseek-v3.2",
        )

    assert fake_ledger.calls[-1]["metadata"]["call_site"] == "case_rubric_batch_judge"


def test_call_site_does_not_leak_outside_the_observation_scope() -> None:
    adapter = LangfuseObservability()
    fake_ledger = _FakeUsageLedger()
    adapter._usage_ledger = fake_ledger
    client = _FakeClient()
    adapter._client = client
    adapter._init_attempted = True

    with adapter.start_observation(name="llm.complete", as_type="generation"):
        pass

    adapter.record_usage(
        usage_details={"input": 1.0, "output": 1.0, "total": 2.0},
        source="provider",
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
    )

    assert "call_site" not in fake_ledger.calls[-1]["metadata"]
