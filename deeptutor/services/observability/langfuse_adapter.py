"""Thin Langfuse observability adapter with safe no-op fallback."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import inspect
import json
import os
import re
from typing import Any, Iterator

import httpx

from deeptutor.logging import get_logger

logger = get_logger("LangfuseObservability")

_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"1[3-9]\d{9}"), "[PHONE]"),
    (re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"), "[EMAIL]"),
    (re.compile(r"(?i)(sk-|pk-|api[_-]?key)[A-Za-z0-9_\-]{8,}"), "[API_KEY]"),
)
_DEFAULT_MODEL_PRICING = {
    "gpt-4o": {
        "input_per_1m": 2.5,
        "output_per_1m": 10.0,
        "currency": "USD",
        "source": "openai-default",
    },
    "gpt-4o-mini": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
        "currency": "USD",
        "source": "openai-default",
    },
    "gpt-4-turbo": {
        "input_per_1m": 10.0,
        "output_per_1m": 30.0,
        "currency": "USD",
        "source": "openai-default",
    },
    "gpt-4": {
        "input_per_1m": 30.0,
        "output_per_1m": 60.0,
        "currency": "USD",
        "source": "openai-default",
    },
    "gpt-3.5-turbo": {
        "input_per_1m": 0.50,
        "output_per_1m": 1.50,
        "currency": "USD",
        "source": "openai-default",
    },
    "claude-3-5-sonnet": {
        "input_per_1m": 3.0,
        "output_per_1m": 15.0,
        "currency": "USD",
        "source": "anthropic-default",
    },
    "claude-3-haiku": {
        "input_per_1m": 0.25,
        "output_per_1m": 1.25,
        "currency": "USD",
        "source": "anthropic-default",
    },
    "deepseek-v3.2": {
        "input_per_1m": 2.0,
        "output_per_1m": 3.0,
        "currency": "CNY",
        "source": "aliyun-model-pricing-2026-04-12",
    },
    "text-embedding-v3": {
        "input_per_1m": 0.5,
        "output_per_1m": 0.0,
        "currency": "CNY",
        "source": "aliyun-embedding-pricing-2026-04-12",
    },
}
_MODEL_PRICE_ALIASES = {
    "deepseek-chat": "deepseek-v3.2",
    "deepseek-v3.2-exp": "deepseek-v3.2",
}


@dataclass
class _UsageScopeState:
    scope_id: str
    session_id: str = ""
    turn_id: str = ""
    capability: str = ""
    input_tokens: float = 0.0
    output_tokens: float = 0.0
    total_tokens: float = 0.0
    total_cost_usd: float = 0.0
    total_calls: int = 0
    measured_calls: int = 0
    estimated_calls: int = 0
    sources: dict[str, int] = field(default_factory=dict)
    models: dict[str, int] = field(default_factory=dict)

    def add(
        self,
        *,
        usage_details: dict[str, float] | None,
        cost_details: dict[str, float] | None = None,
        source: str = "estimated",
        model: str | None = None,
    ) -> None:
        if not usage_details:
            return

        input_tokens = float(usage_details.get("input") or 0.0)
        output_tokens = float(usage_details.get("output") or 0.0)
        total_tokens = float(usage_details.get("total") or (input_tokens + output_tokens))
        if total_tokens <= 0:
            return

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        self.total_calls += 1

        source_key = str(source or "estimated").strip().lower() or "estimated"
        self.sources[source_key] = int(self.sources.get(source_key) or 0) + 1
        if source_key in {"provider", "measured", "actual"}:
            self.measured_calls += 1
        else:
            self.estimated_calls += 1

        if model:
            model_key = str(model).strip()
            if model_key:
                self.models[model_key] = int(self.models.get(model_key) or 0) + 1

        if cost_details:
            self.total_cost_usd += float(cost_details.get("total") or 0.0)

    def to_summary(self) -> dict[str, Any] | None:
        total_tokens = int(round(self.total_tokens))
        if total_tokens <= 0 and self.total_calls <= 0:
            return None

        sources = {
            key: value
            for key, value in sorted(self.sources.items(), key=lambda item: item[0])
            if value
        }
        models = {
            key: value
            for key, value in sorted(self.models.items(), key=lambda item: item[0])
            if value
        }
        accuracy = (
            "measured"
            if self.estimated_calls == 0 and self.measured_calls > 0
            else "estimated"
            if self.measured_calls == 0 and self.estimated_calls > 0
            else "mixed"
            if self.measured_calls > 0 and self.estimated_calls > 0
            else "unknown"
        )

        return {
            "scope_id": self.scope_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "capability": self.capability,
            "total_input_tokens": int(round(self.input_tokens)),
            "total_output_tokens": int(round(self.output_tokens)),
            "total_tokens": total_tokens,
            "total_calls": int(self.total_calls),
            "measured_calls": int(self.measured_calls),
            "estimated_calls": int(self.estimated_calls),
            "usage_accuracy": accuracy,
            "usage_sources": sources,
            "models": models,
            "total_cost_usd": round(self.total_cost_usd, 8),
        }


_current_usage_scope: ContextVar[_UsageScopeState | None] = ContextVar(
    "langfuse_usage_scope",
    default=None,
)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _truncate_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _mask_text(text: str, enabled: bool) -> str:
    if not enabled:
        return text
    masked = text
    for pattern, replacement in _PII_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


def _safe_json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _estimate_token_count(value: Any) -> int:
    text = _safe_json_text(value)
    if not text:
        return 0
    try:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _sanitize_value(
    value: Any,
    *,
    mask_pii: bool,
    text_limit: int = 4000,
    list_limit: int = 20,
    dict_limit: int = 20,
    depth: int = 0,
) -> Any:
    if value is None:
        return None
    if depth >= 4:
        return _truncate_text(_mask_text(_safe_json_text(value), mask_pii), limit=text_limit)
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_text(_mask_text(value, mask_pii), limit=text_limit)
    if isinstance(value, list):
        return [
            _sanitize_value(
                item,
                mask_pii=mask_pii,
                text_limit=text_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
                depth=depth + 1,
            )
            for item in value[:list_limit]
        ]
    if isinstance(value, tuple):
        return [
            _sanitize_value(
                item,
                mask_pii=mask_pii,
                text_limit=text_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
                depth=depth + 1,
            )
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= dict_limit:
                break
            sanitized[str(key)] = _sanitize_value(
                item,
                mask_pii=mask_pii,
                text_limit=text_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
                depth=depth + 1,
            )
        return sanitized
    return _truncate_text(_mask_text(str(value), mask_pii), limit=text_limit)


class _NoopObservation:
    def update(self, **_: Any) -> None:
        return None


class LangfuseObservability:
    """Langfuse adapter with lazy initialization and no-op fallback."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._init_attempted = False
        self._init_error_logged = False

    def is_enabled(self) -> bool:
        return _env_flag("LANGFUSE_ENABLED", False)

    def is_configured(self) -> bool:
        if not self.is_enabled():
            return False
        public_key = str(os.getenv("LANGFUSE_PUBLIC_KEY", "") or "").strip()
        secret_key = str(os.getenv("LANGFUSE_SECRET_KEY", "") or "").strip()
        return bool(public_key and secret_key)

    def _get_client(self) -> Any | None:
        if self._init_attempted:
            return self._client

        self._init_attempted = True
        if not self.is_configured():
            self._client = None
            return None

        try:
            from langfuse import Langfuse

            host = str(
                os.getenv("LANGFUSE_BASE_URL", "") or os.getenv("LANGFUSE_HOST", "") or ""
            ).strip() or None
            timeout = int(os.getenv("LANGFUSE_TIMEOUT_S", "5"))
            trust_env = _env_flag("LANGFUSE_HTTPX_TRUST_ENV", False)
            candidate_kwargs = {
                "public_key": str(os.getenv("LANGFUSE_PUBLIC_KEY", "") or "").strip(),
                "secret_key": str(os.getenv("LANGFUSE_SECRET_KEY", "") or "").strip(),
                "host": host,
                "base_url": host,
                "timeout": timeout,
                "httpx_client": httpx.Client(trust_env=trust_env, timeout=timeout),
                "debug": _env_flag("LANGFUSE_DEBUG", False),
                "tracing_enabled": True,
                "flush_at": int(os.getenv("LANGFUSE_FLUSH_AT", "64")),
                "flush_interval": float(os.getenv("LANGFUSE_FLUSH_INTERVAL", "2.0")),
                "environment": str(
                    os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "")
                    or os.getenv("LANGFUSE_ENVIRONMENT", "")
                    or "default"
                ).strip(),
            }
            signature = inspect.signature(Langfuse)
            supported_kwargs = {
                key: value
                for key, value in candidate_kwargs.items()
                if key in signature.parameters and value is not None
            }
            self._client = Langfuse(**supported_kwargs)
            if not callable(getattr(self._client, "start_as_current_observation", None)):
                raise RuntimeError(
                    "Installed langfuse SDK does not support start_as_current_observation; "
                    "expected langfuse>=3."
                )
            logger.info("Langfuse observability enabled")
        except Exception as exc:
            self._client = None
            if not self._init_error_logged:
                logger.warning(f"Langfuse initialization skipped: {exc}")
                self._init_error_logged = True

        return self._client

    def sanitize_input(self, value: Any) -> Any:
        if not _env_flag("LANGFUSE_CAPTURE_INPUT", True):
            return None
        return _sanitize_value(value, mask_pii=_env_flag("LANGFUSE_MASK_PII", True))

    def sanitize_output(self, value: Any) -> Any:
        if not _env_flag("LANGFUSE_CAPTURE_OUTPUT", True):
            return None
        return _sanitize_value(value, mask_pii=_env_flag("LANGFUSE_MASK_PII", True))

    def sanitize_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not metadata:
            return None
        return _sanitize_value(metadata, mask_pii=_env_flag("LANGFUSE_MASK_PII", True))

    @contextmanager
    def usage_scope(
        self,
        *,
        scope_id: str,
        session_id: str = "",
        turn_id: str = "",
        capability: str = "",
    ) -> Iterator[_UsageScopeState]:
        scope = _UsageScopeState(
            scope_id=str(scope_id or "").strip() or "usage-scope",
            session_id=str(session_id or "").strip(),
            turn_id=str(turn_id or "").strip(),
            capability=str(capability or "").strip(),
        )
        token: Token[_UsageScopeState | None] = _current_usage_scope.set(scope)
        try:
            yield scope
        finally:
            _current_usage_scope.reset(token)

    def record_usage(
        self,
        *,
        usage_details: dict[str, float] | None,
        cost_details: dict[str, float] | None = None,
        source: str = "estimated",
        model: str | None = None,
    ) -> None:
        scope = _current_usage_scope.get()
        if scope is None:
            return
        scope.add(
            usage_details=usage_details,
            cost_details=cost_details,
            source=source,
            model=model,
        )

    def get_current_usage_summary(self) -> dict[str, Any] | None:
        scope = _current_usage_scope.get()
        if scope is None:
            return None
        return scope.to_summary()

    def _extract_trace_attributes(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        if not metadata:
            return {}

        attributes: dict[str, Any] = {}

        session_id = str(metadata.get("session_id", "") or "").strip()
        if session_id:
            attributes["session_id"] = session_id

        user_id = str(metadata.get("user_id", "") or "").strip()
        if user_id:
            attributes["user_id"] = user_id

        trace_name = str(metadata.get("trace_name", "") or "").strip()
        if trace_name:
            attributes["trace_name"] = trace_name

        raw_tags = metadata.get("tags")
        if isinstance(raw_tags, (list, tuple)):
            tags = [str(item).strip() for item in raw_tags if str(item or "").strip()]
            if tags:
                attributes["tags"] = tags[:20]

        return attributes

    def _filter_supported_kwargs(self, target: Any, candidate_kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            return {
                key: value for key, value in candidate_kwargs.items() if value is not None
            }

        return {
            key: value
            for key, value in candidate_kwargs.items()
            if key in signature.parameters and value is not None
        }

    @contextmanager
    def _propagate_trace_attributes(
        self,
        client: Any,
        trace_attributes: dict[str, Any],
    ) -> Iterator[None]:
        if not trace_attributes:
            yield
            return

        propagate = getattr(client, "propagate_attributes", None)
        if not callable(propagate):
            yield
            return

        propagate_kwargs = self._filter_supported_kwargs(propagate, trace_attributes)
        if not propagate_kwargs:
            yield
            return

        try:
            with propagate(**propagate_kwargs):
                yield
        except Exception as exc:
            logger.debug(f"Langfuse attribute propagation skipped: {exc}", exc_info=True)
            yield

    def estimate_usage_details(
        self,
        *,
        input_payload: Any = None,
        output_payload: Any = None,
    ) -> dict[str, float] | None:
        input_tokens = _estimate_token_count(input_payload) if input_payload is not None else 0
        output_tokens = _estimate_token_count(output_payload) if output_payload is not None else 0
        total_tokens = input_tokens + output_tokens
        if total_tokens <= 0:
            return None
        return {
            "input": float(input_tokens),
            "output": float(output_tokens),
            "total": float(total_tokens),
        }

    def _get_pricing_override(self, model: str) -> dict[str, float] | None:
        raw = str(os.getenv("LANGFUSE_MODEL_PRICING_JSON", "") or "").strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid LANGFUSE_MODEL_PRICING_JSON, skipping pricing overrides")
            return None
        if not isinstance(payload, dict):
            return None
        entry = payload.get(model) or payload.get(model.lower())
        if not isinstance(entry, dict):
            return None
        result: dict[str, float] = {}
        for key in (
            "input",
            "output",
            "total",
            "input_per_1m",
            "output_per_1m",
            "total_per_1m",
        ):
            value = entry.get(key)
            if isinstance(value, (int, float)):
                result[key] = float(value)
        currency = entry.get("currency")
        if isinstance(currency, str) and currency.strip():
            result["currency"] = currency.strip().upper()
        source = entry.get("source")
        if isinstance(source, str) and source.strip():
            result["source"] = source.strip()
        return result or None

    def _get_builtin_pricing(self, model: str) -> dict[str, Any] | None:
        model_lower = str(model or "").strip().lower()
        if not model_lower:
            return None

        canonical = _MODEL_PRICE_ALIASES.get(model_lower, model_lower)
        if canonical in _DEFAULT_MODEL_PRICING:
            return dict(_DEFAULT_MODEL_PRICING[canonical])

        for key, value in _DEFAULT_MODEL_PRICING.items():
            if key in canonical or canonical in key:
                return dict(value)
        return None

    def get_pricing_metadata(self, model: str | None) -> dict[str, Any] | None:
        if not model:
            return None
        pricing = self._get_pricing_override(model) or self._get_builtin_pricing(model)
        if not pricing:
            return None
        metadata = {
            "pricing_currency": pricing.get("currency", "USD"),
            "pricing_unit": "per_1m_tokens",
            "pricing_source": pricing.get("source", "built_in"),
        }
        return {key: value for key, value in metadata.items() if value is not None}

    def estimate_cost_details(
        self,
        *,
        model: str | None,
        usage_details: dict[str, float] | None,
    ) -> dict[str, float] | None:
        if not model or not usage_details:
            return None

        override = self._get_pricing_override(model)
        if override:
            input_units = float(usage_details.get("input") or 0.0)
            output_units = float(usage_details.get("output") or 0.0)
            total_units = float(usage_details.get("total") or (input_units + output_units))
            if "input_per_1m" in override or "output_per_1m" in override or "total_per_1m" in override:
                input_cost = (input_units / 1_000_000.0) * float(override.get("input_per_1m") or 0.0)
                output_cost = (output_units / 1_000_000.0) * float(
                    override.get("output_per_1m") or 0.0
                )
                total_cost = (total_units / 1_000_000.0) * float(
                    override.get("total_per_1m") or 0.0
                )
            else:
                input_cost = (input_units / 1000.0) * float(override.get("input") or 0.0)
                output_cost = (output_units / 1000.0) * float(override.get("output") or 0.0)
                total_cost = (total_units / 1000.0) * float(override.get("total") or 0.0)
            payload = {
                "input": round(input_cost, 8),
                "output": round(output_cost, 8),
                "total": round(
                    total_cost if total_cost > 0 else (input_cost + output_cost),
                    8,
                ),
            }
            return payload

        pricing = self._get_builtin_pricing(model)
        if pricing is None:
            return None

        input_cost = (float(usage_details.get("input") or 0.0) / 1_000_000.0) * float(
            pricing.get("input_per_1m") or 0.0
        )
        output_cost = (float(usage_details.get("output") or 0.0) / 1_000_000.0) * float(
            pricing.get("output_per_1m") or 0.0
        )
        return {
            "input": round(input_cost, 8),
            "output": round(output_cost, 8),
            "total": round(input_cost + output_cost, 8),
        }

    @contextmanager
    def start_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input_payload: Any = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        usage_details: dict[str, float] | None = None,
        cost_details: dict[str, float] | None = None,
        usage_source: str | None = None,
    ) -> Iterator[Any]:
        client = self._get_client()
        self.record_usage(
            usage_details=usage_details,
            cost_details=cost_details,
            source=usage_source or "estimated",
            model=model,
        )
        if client is None:
            yield _NoopObservation()
            return

        safe_input = self.sanitize_input(input_payload)
        merged_metadata = dict(metadata or {})
        pricing_metadata = self.get_pricing_metadata(model)
        if pricing_metadata:
            merged_metadata.update(pricing_metadata)
        safe_metadata = self.sanitize_metadata(merged_metadata)
        trace_attributes = self._extract_trace_attributes(merged_metadata)
        start_method = getattr(client, "start_as_current_observation", None)
        if not callable(start_method):
            yield _NoopObservation()
            return
        try:
            start_kwargs = self._filter_supported_kwargs(
                start_method,
                {
                    "name": name,
                    "as_type": as_type,
                    "input": safe_input,
                    "metadata": safe_metadata,
                    "model": model,
                    "model_parameters": model_parameters,
                    "usage_details": usage_details,
                    "cost_details": cost_details,
                    "session_id": trace_attributes.get("session_id"),
                    "user_id": trace_attributes.get("user_id"),
                    "trace_name": trace_attributes.get("trace_name"),
                    "tags": trace_attributes.get("tags"),
                },
            )
            with start_method(**start_kwargs) as observation:
                with self._propagate_trace_attributes(client, trace_attributes):
                    yield observation
        except Exception as exc:
            logger.debug(f"Langfuse observation skipped for {name}: {exc}", exc_info=True)
            yield _NoopObservation()

    def update_observation(
        self,
        observation: Any,
        *,
        output_payload: Any = None,
        metadata: dict[str, Any] | None = None,
        usage_details: dict[str, float] | None = None,
        cost_details: dict[str, float] | None = None,
        usage_source: str | None = None,
        model: str | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        self.record_usage(
            usage_details=usage_details,
            cost_details=cost_details,
            source=usage_source or "estimated",
            model=model,
        )
        if observation is None or isinstance(observation, _NoopObservation):
            return
        try:
            observation.update(
                output=self.sanitize_output(output_payload),
                metadata=self.sanitize_metadata(metadata),
                usage_details=usage_details,
                cost_details=cost_details,
                level=level,
                status_message=status_message,
            )
        except Exception as exc:
            logger.debug(f"Langfuse observation update skipped: {exc}", exc_info=True)

    def flush(self) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.flush()
        except Exception as exc:
            logger.debug(f"Langfuse flush skipped: {exc}", exc_info=True)


_adapter: LangfuseObservability | None = None


def get_langfuse_observability() -> LangfuseObservability:
    global _adapter
    if _adapter is None:
        _adapter = LangfuseObservability()
    return _adapter
