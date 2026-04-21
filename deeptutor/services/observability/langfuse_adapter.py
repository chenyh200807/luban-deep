"""Thin Langfuse observability adapter with safe no-op fallback."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import inspect
import json
import os
import re
from typing import Any, Iterator
from urllib.parse import urlparse, urlunparse

import httpx

from deeptutor.logging import get_logger
from deeptutor.services.observability.usage_ledger import get_usage_ledger
from deeptutor.services.user_visible_output import redact_internal_output

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
    "gte-rerank-v2": {
        "input_per_1m": 0.8,
        "output_per_1m": 0.0,
        "currency": "CNY",
        "source": "aliyun-text-rerank-pricing-2026-04-17",
    },
}
_MODEL_PRICE_ALIASES = {
    "deepseek-chat": "deepseek-v3.2",
    "deepseek-v3.2-exp": "deepseek-v3.2",
    "gte-rerank": "gte-rerank-v2",
}
def _normalize_cost_currency(currency: str | None) -> str:
    return str(currency or "").strip().upper()


def _normalize_langfuse_host(raw_host: str | None) -> str | None:
    normalized = str(raw_host or "").strip().rstrip("/")
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized

    path = parsed.path.rstrip("/")
    lowered_path = path.lower()
    for suffix in ("/api/public/ingestion", "/api/public"):
        if lowered_path.endswith(suffix):
            path = path[: -len(suffix)]
            break

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def _get_pricing_override(model: str) -> dict[str, float] | None:
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
    entry = payload.get(model) or payload.get(str(model or "").lower())
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
        result["currency"] = _normalize_cost_currency(currency)
    source = entry.get("source")
    if isinstance(source, str) and source.strip():
        result["source"] = source.strip()
    return result or None


def _get_builtin_pricing(model: str) -> dict[str, Any] | None:
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


def resolve_model_pricing(model: str | None) -> dict[str, Any] | None:
    if not model:
        return None
    return _get_pricing_override(model) or _get_builtin_pricing(model)


def get_model_pricing_metadata(model: str | None) -> dict[str, Any] | None:
    pricing = resolve_model_pricing(model)
    if not pricing:
        return None
    metadata = {
        "pricing_currency": _normalize_cost_currency(pricing.get("currency", "USD")),
        "pricing_unit": "per_1m_tokens",
        "pricing_source": pricing.get("source", "built_in"),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def estimate_model_cost(
    *,
    model: str | None,
    usage_details: dict[str, float] | None,
) -> dict[str, Any] | None:
    if not model or not usage_details:
        return None

    pricing = resolve_model_pricing(model)
    if pricing is None:
        return None

    input_units = float(usage_details.get("input") or 0.0)
    output_units = float(usage_details.get("output") or 0.0)
    total_units = float(usage_details.get("total") or (input_units + output_units))
    if "input_per_1m" in pricing or "output_per_1m" in pricing or "total_per_1m" in pricing:
        input_cost = (input_units / 1_000_000.0) * float(pricing.get("input_per_1m") or 0.0)
        output_cost = (output_units / 1_000_000.0) * float(pricing.get("output_per_1m") or 0.0)
        total_cost = (total_units / 1_000_000.0) * float(pricing.get("total_per_1m") or 0.0)
    else:
        input_cost = (input_units / 1000.0) * float(pricing.get("input") or 0.0)
        output_cost = (output_units / 1000.0) * float(pricing.get("output") or 0.0)
        total_cost = (total_units / 1000.0) * float(pricing.get("total") or 0.0)
    return {
        "input": round(input_cost, 8),
        "output": round(output_cost, 8),
        "total": round(total_cost if total_cost > 0 else (input_cost + output_cost), 8),
        "currency": _normalize_cost_currency(pricing.get("currency", "USD")),
        "source": pricing.get("source", "built_in"),
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
    estimated_input_tokens: float = 0.0
    estimated_output_tokens: float = 0.0
    estimated_total_tokens: float = 0.0
    estimated_total_cost_usd: float = 0.0
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

        self.total_calls += 1

        source_key = str(source or "estimated").strip().lower() or "estimated"
        self.sources[source_key] = int(self.sources.get(source_key) or 0) + 1

        if model:
            model_key = str(model).strip()
            if model_key:
                self.models[model_key] = int(self.models.get(model_key) or 0) + 1

        is_measured = source_key in {"provider", "measured", "actual"}
        if is_measured:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.total_tokens += total_tokens
            self.measured_calls += 1
            if cost_details:
                self.total_cost_usd += float(cost_details.get("total") or 0.0)
            return

        self.estimated_input_tokens += input_tokens
        self.estimated_output_tokens += output_tokens
        self.estimated_total_tokens += total_tokens
        self.estimated_calls += 1
        if cost_details:
            self.estimated_total_cost_usd += float(cost_details.get("total") or 0.0)

    def to_summary(self) -> dict[str, Any] | None:
        total_tokens = int(round(self.total_tokens))
        estimated_total_tokens = int(round(self.estimated_total_tokens))
        if total_tokens <= 0 and estimated_total_tokens <= 0 and self.total_calls <= 0:
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
            "estimated_input_tokens": int(round(self.estimated_input_tokens)),
            "estimated_output_tokens": int(round(self.estimated_output_tokens)),
            "estimated_total_tokens": estimated_total_tokens,
            "total_calls": int(self.total_calls),
            "measured_calls": int(self.measured_calls),
            "estimated_calls": int(self.estimated_calls),
            "usage_accuracy": accuracy,
            "usage_sources": sources,
            "models": models,
            "total_cost_usd": round(self.total_cost_usd, 8),
            "estimated_total_cost_usd": round(self.estimated_total_cost_usd, 8),
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
        self._usage_ledger = get_usage_ledger()

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

        httpx_client: httpx.Client | None = None
        try:
            from langfuse import Langfuse

            host = _normalize_langfuse_host(
                os.getenv("LANGFUSE_BASE_URL", "") or os.getenv("LANGFUSE_HOST", "") or ""
            )
            timeout = int(os.getenv("LANGFUSE_TIMEOUT_S", "5"))
            trust_env = _env_flag("LANGFUSE_HTTPX_TRUST_ENV", False)
            httpx_client = httpx.Client(trust_env=trust_env, timeout=timeout)
            candidate_kwargs = {
                "public_key": str(os.getenv("LANGFUSE_PUBLIC_KEY", "") or "").strip(),
                "secret_key": str(os.getenv("LANGFUSE_SECRET_KEY", "") or "").strip(),
                "host": host,
                "base_url": host,
                "timeout": timeout,
                "httpx_client": httpx_client,
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
            auth_check = getattr(self._client, "auth_check", None)
            if callable(auth_check):
                try:
                    if not bool(auth_check()):
                        raise RuntimeError("Langfuse auth check returned false")
                except Exception as exc:
                    raise RuntimeError(f"Langfuse auth check failed: {exc}") from exc
            logger.info("Langfuse observability enabled")
        except Exception as exc:
            self._client = None
            if httpx_client is not None:
                try:
                    httpx_client.close()
                except Exception:
                    logger.debug("Failed to close Langfuse httpx client", exc_info=True)
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
        return _sanitize_value(
            redact_internal_output(value),
            mask_pii=_env_flag("LANGFUSE_MASK_PII", True),
        )

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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        source_key = self.normalize_usage_source(source)
        if source_key in {"summary", "rollup", "scope"}:
            return
        scope = _current_usage_scope.get()
        if scope is not None:
            scope.add(
                usage_details=usage_details,
                cost_details=cost_details,
                source=source_key,
                model=model,
            )
        try:
            self._usage_ledger.record_usage_event(
                usage_source=source_key,
                usage_details=usage_details,
                cost_details=cost_details,
                model=model,
                metadata=metadata,
                session_id=scope.session_id if scope is not None else "",
                turn_id=scope.turn_id if scope is not None else "",
                capability=scope.capability if scope is not None else "",
                scope_id=scope.scope_id if scope is not None else "",
            )
        except Exception as exc:
            logger.debug(f"Usage ledger write skipped: {exc}", exc_info=True)

    @staticmethod
    def normalize_usage_source(source: str | None) -> str:
        source_key = str(source or "estimated").strip().lower()
        return source_key or "estimated"

    @classmethod
    def is_measured_usage_source(cls, source: str | None) -> bool:
        return cls.normalize_usage_source(source) in {"provider", "measured", "actual"}

    @classmethod
    def should_export_usage_to_langfuse(cls, source: str | None) -> bool:
        source_key = cls.normalize_usage_source(source)
        return source_key not in {"summary", "rollup", "scope"}

    def get_current_usage_summary(self) -> dict[str, Any] | None:
        scope = _current_usage_scope.get()
        if scope is None:
            return None
        return scope.to_summary()

    @staticmethod
    def usage_details_from_summary(summary: dict[str, Any] | None) -> dict[str, float] | None:
        if not isinstance(summary, dict):
            return None
        input_tokens = float(summary.get("total_input_tokens") or 0.0) + float(
            summary.get("estimated_input_tokens") or 0.0
        )
        output_tokens = float(summary.get("total_output_tokens") or 0.0) + float(
            summary.get("estimated_output_tokens") or 0.0
        )
        total_tokens = float(summary.get("total_tokens") or 0.0) + float(
            summary.get("estimated_total_tokens") or 0.0
        )
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        if total_tokens <= 0:
            return None
        return {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        }

    @staticmethod
    def cost_details_from_summary(summary: dict[str, Any] | None) -> dict[str, float] | None:
        if not isinstance(summary, dict):
            return None
        total_cost = float(summary.get("total_cost_usd") or 0.0) + float(
            summary.get("estimated_total_cost_usd") or 0.0
        )
        if total_cost <= 0:
            return None
        return {
            "input": 0.0,
            "output": 0.0,
            "total": total_cost,
        }

    @staticmethod
    def summary_metadata(summary: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(summary, dict):
            return {}

        metadata: dict[str, Any] = {}
        usage_details = LangfuseObservability.usage_details_from_summary(summary)
        cost_details = LangfuseObservability.cost_details_from_summary(summary)
        total_tokens = usage_details.get("total") if usage_details else None
        total_cost = cost_details.get("total") if cost_details else None
        usage_accuracy = summary.get("usage_accuracy")
        rollup_parts: list[str] = []
        if isinstance(total_tokens, (int, float)) and float(total_tokens) > 0:
            rollup_parts.append(f"tokens={int(round(float(total_tokens)))}")
        if isinstance(total_cost, (int, float)) and float(total_cost) > 0:
            rollup_parts.append(f"cost={round(float(total_cost), 8)}")
        if isinstance(usage_accuracy, str) and usage_accuracy.strip():
            rollup_parts.append(f"accuracy={usage_accuracy.strip()}")
        if rollup_parts:
            metadata["usage_rollup"] = "; ".join(rollup_parts)

        scalar_fields = {
            "scope_id": "usage_scope_id",
            "total_input_tokens": "usage_total_input_tokens",
            "total_output_tokens": "usage_total_output_tokens",
            "total_tokens": "usage_total_tokens",
            "estimated_input_tokens": "usage_estimated_input_tokens",
            "estimated_output_tokens": "usage_estimated_output_tokens",
            "estimated_total_tokens": "usage_estimated_total_tokens",
            "total_calls": "usage_total_calls",
            "measured_calls": "usage_measured_calls",
            "estimated_calls": "usage_estimated_calls",
            "usage_accuracy": "usage_accuracy",
        }
        for source_key, target_key in scalar_fields.items():
            value = summary.get(source_key)
            if value in (None, "", [], {}):
                continue
            metadata[target_key] = value

        measured_total_cost = summary.get("total_cost_usd")
        if isinstance(measured_total_cost, (int, float)) and float(measured_total_cost) > 0:
            metadata["usage_total_cost"] = round(float(measured_total_cost), 8)
        estimated_total_cost = summary.get("estimated_total_cost_usd")
        if isinstance(estimated_total_cost, (int, float)) and float(estimated_total_cost) > 0:
            metadata["usage_estimated_total_cost"] = round(float(estimated_total_cost), 8)

        usage_sources = summary.get("usage_sources")
        if isinstance(usage_sources, dict) and usage_sources:
            metadata["usage_sources"] = dict(usage_sources)

        models = summary.get("models")
        if isinstance(models, dict) and models:
            metadata["usage_models"] = dict(models)

        return metadata

    def _build_usage_metadata(
        self,
        *,
        usage_source: str | None,
        usage_details: dict[str, float] | None,
        cost_details: dict[str, float] | None,
    ) -> dict[str, Any]:
        if not usage_details and not cost_details:
            return {}
        source_key = self.normalize_usage_source(usage_source)
        metadata: dict[str, Any] = {"usage_source": source_key}
        if self.is_measured_usage_source(source_key):
            return metadata
        if usage_details:
            metadata["estimated_usage_details"] = dict(usage_details)
        if cost_details:
            metadata["estimated_cost_details"] = dict(cost_details)
        return metadata

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

        bot_id = str(metadata.get("bot_id", "") or "").strip()
        if bot_id:
            attributes["bot_id"] = bot_id

        turn_id = str(metadata.get("turn_id", "") or "").strip()
        if turn_id:
            attributes["turn_id"] = turn_id

        capability = str(metadata.get("capability", "") or "").strip()
        if capability:
            attributes["capability"] = capability

        execution_engine = str(metadata.get("execution_engine", "") or "").strip()
        if execution_engine:
            attributes["execution_engine"] = execution_engine

        raw_tool_calls = metadata.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            attributes["tool_calls"] = _sanitize_value(
                raw_tool_calls,
                mask_pii=_env_flag("LANGFUSE_MASK_PII", True),
            )

        raw_sources = metadata.get("sources")
        if isinstance(raw_sources, list):
            attributes["sources"] = _sanitize_value(
                raw_sources,
                mask_pii=_env_flag("LANGFUSE_MASK_PII", True),
            )

        if "authority_applied" in metadata:
            attributes["authority_applied"] = bool(metadata.get("authority_applied"))

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
            try:
                import langfuse as langfuse_module

                propagate = getattr(langfuse_module, "propagate_attributes", None)
            except Exception:
                propagate = None
        if not callable(propagate):
            yield
            return

        propagation_metadata = {
            key: trace_attributes.get(key)
            for key in (
                "bot_id",
                "turn_id",
                "capability",
                "execution_engine",
                "authority_applied",
            )
            if key in trace_attributes and trace_attributes.get(key) not in (None, "", [], {})
        }
        propagate_kwargs = self._filter_supported_kwargs(
            propagate,
            {
                **trace_attributes,
                "metadata": propagation_metadata or None,
            },
        )
        if not propagate_kwargs:
            yield
            return

        try:
            manager = propagate(**propagate_kwargs)
        except Exception as exc:
            logger.debug(f"Langfuse attribute propagation skipped: {exc}", exc_info=True)
            yield
            return

        with ExitStack() as stack:
            try:
                stack.enter_context(manager)
            except Exception as exc:
                logger.debug(f"Langfuse attribute propagation skipped: {exc}", exc_info=True)
                yield
                return
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

    def get_pricing_metadata(self, model: str | None) -> dict[str, Any] | None:
        return get_model_pricing_metadata(model)

    def estimate_cost_details(
        self,
        *,
        model: str | None,
        usage_details: dict[str, float] | None,
    ) -> dict[str, float] | None:
        estimated = estimate_model_cost(model=model, usage_details=usage_details)
        if not estimated:
            return None
        return {
            "input": float(estimated.get("input") or 0.0),
            "output": float(estimated.get("output") or 0.0),
            "total": float(estimated.get("total") or 0.0),
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
        source_key = self.normalize_usage_source(usage_source)
        merged_metadata = dict(metadata or {})
        merged_metadata.update(
            self._build_usage_metadata(
                usage_source=source_key,
                usage_details=usage_details,
                cost_details=cost_details,
            )
        )
        self.record_usage(
            usage_details=usage_details,
            cost_details=cost_details,
            source=source_key,
            model=model,
            metadata=merged_metadata,
        )
        if client is None:
            yield _NoopObservation()
            return

        safe_input = self.sanitize_input(input_payload)
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
            export_usage = self.should_export_usage_to_langfuse(source_key)
            start_kwargs = self._filter_supported_kwargs(
                start_method,
                {
                    "name": name,
                    "as_type": as_type,
                    "input": safe_input,
                    "metadata": safe_metadata,
                    "model": model,
                    "model_parameters": model_parameters,
                    "usage_details": usage_details if export_usage else None,
                    "cost_details": cost_details if export_usage else None,
                    "session_id": trace_attributes.get("session_id"),
                    "user_id": trace_attributes.get("user_id"),
                    "trace_name": trace_attributes.get("trace_name"),
                    "bot_id": trace_attributes.get("bot_id"),
                    "turn_id": trace_attributes.get("turn_id"),
                    "capability": trace_attributes.get("capability"),
                    "execution_engine": trace_attributes.get("execution_engine"),
                    "tags": trace_attributes.get("tags"),
                },
            )
            observation_manager = start_method(**start_kwargs)
        except Exception as exc:
            logger.debug(f"Langfuse observation skipped for {name}: {exc}", exc_info=True)
            yield _NoopObservation()
            return

        with ExitStack() as stack:
            try:
                stack.enter_context(self._propagate_trace_attributes(client, trace_attributes))
                observation = stack.enter_context(observation_manager)
            except Exception as exc:
                logger.debug(f"Langfuse observation skipped for {name}: {exc}", exc_info=True)
                yield _NoopObservation()
                return
            yield observation

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
        source_key = self.normalize_usage_source(usage_source)
        self.record_usage(
            usage_details=usage_details,
            cost_details=cost_details,
            source=source_key,
            model=model,
            metadata=metadata,
        )
        if observation is None or isinstance(observation, _NoopObservation):
            return
        try:
            export_usage = self.should_export_usage_to_langfuse(source_key)
            merged_metadata = dict(metadata or {})
            merged_metadata.update(
                self._build_usage_metadata(
                    usage_source=source_key,
                    usage_details=usage_details,
                    cost_details=cost_details,
                )
            )
            observation.update(
                output=self.sanitize_output(output_payload),
                metadata=self.sanitize_metadata(merged_metadata),
                usage_details=usage_details if export_usage else None,
                cost_details=cost_details if export_usage else None,
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
