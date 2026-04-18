"""
Anthropic LLM provider implementation.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Callable, Protocol, TypeVar, cast

import anthropic

from deeptutor.services.observability import get_langfuse_observability

from ..config import LLMConfig
from ..http_client import get_shared_http_client
from ..registry import register_provider
from ..telemetry import track_llm_call
from ..types import AsyncStreamGenerator, TutorResponse, TutorStreamChunk
from .base_provider import BaseLLMProvider

_DISALLOWED_KWARGS = {
    "api_version",
    "base_url",
    "binding",
    "logit_bias",
    "max_retries",  # Handled by factory retry mechanism
    "response_format",
    "seed",
    "stream",
    "stream_options",
}

F = TypeVar("F", bound=Callable[..., object])
observability = get_langfuse_observability()


class AnthropicDelta(Protocol):
    """Protocol for Anthropic delta payloads."""

    text: str | None


class AnthropicUsage(Protocol):
    """Protocol for Anthropic usage payloads."""

    input_tokens: int
    output_tokens: int


class AnthropicChunk(Protocol):
    """Protocol for Anthropic streaming chunks."""

    type: str
    delta: AnthropicDelta
    usage: AnthropicUsage | None


class AnthropicStream(Protocol):
    """Protocol for Anthropic streaming responses."""

    def __aiter__(self) -> AsyncIterator[AnthropicChunk]: ...


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _typed_track_llm_call(provider: str) -> Callable[[F], F]:
    return cast(Callable[[F], F], track_llm_call(provider))


def _normalize_usage_details(usage: object) -> dict[str, float] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = float(usage.get("input_tokens") or usage.get("prompt_tokens") or 0.0)
    output_tokens = float(usage.get("output_tokens") or usage.get("completion_tokens") or 0.0)
    total_tokens = float(usage.get("total_tokens") or (input_tokens + output_tokens))
    if total_tokens <= 0:
        return None
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
    }


def _sanitize_kwargs(kwargs: dict[str, object]) -> dict[str, object]:
    """
    Remove OpenAI-only and factory-specific kwargs before Anthropic calls.

    Args:
        kwargs: Raw kwargs passed to the provider.

    Returns:
        Sanitized kwargs safe for the Anthropic SDK.
    """
    import logging

    sanitized = dict(kwargs)
    removed_keys = []
    for key in _DISALLOWED_KWARGS:
        if key in sanitized:
            removed_keys.append(key)
            sanitized.pop(key)

    if removed_keys:
        logging.getLogger("AnthropicProvider").warning(
            "Ignoring unsupported Anthropic kwargs (handled upstream): %s",
            removed_keys,
        )

    return sanitized


@register_provider("anthropic")
class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Provider with shared HTTP client."""

    def __init__(self, config: LLMConfig) -> None:
        """
        Initialize the Anthropic provider.

        Args:
            config: Provider configuration object.

        Returns:
            None.

        Raises:
            Exception: Propagates client initialization failures.
        """
        super().__init__(config)
        self.client: anthropic.AsyncAnthropic | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> anthropic.AsyncAnthropic:
        if self.client is None:
            async with self._client_lock:
                if self.client is None:
                    http_client = await get_shared_http_client()
                    self.client = anthropic.AsyncAnthropic(
                        api_key=self.api_key,
                        http_client=http_client,
                    )
        return self.client

    @_typed_track_llm_call("anthropic")
    async def complete(self, prompt: str, **kwargs: object) -> TutorResponse:
        """
        Generate a completion using Anthropic.

        Args:
            prompt: User prompt content.
            **kwargs: Provider-specific options.

        Returns:
            TutorResponse containing the completion result.

        Raises:
            Exception: Propagates SDK or execution errors.
        """
        model_raw = kwargs.pop("model", None)
        model = (
            model_raw
            if isinstance(model_raw, str) and model_raw
            else self.config.model or "claude-3-sonnet-20240229"
        )
        kwargs.pop("max_retries", None)
        kwargs.pop("stream", None)

        async def _call_api() -> TutorResponse:
            client = await self._get_client()
            request_kwargs = _sanitize_kwargs(kwargs)
            response = await client.messages.create(  # type: ignore[call-overload]
                model=model,
                max_tokens=_coerce_int(request_kwargs.pop("max_tokens", 1024), 1024),
                messages=[{"role": "user", "content": prompt}],
                **request_kwargs,
            )

            content = response.content[0].text if response.content else ""
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

            return TutorResponse(
                content=content,
                raw_response=response.model_dump(),
                usage=usage,
                provider="anthropic",
                model=model,
                finish_reason=response.stop_reason,
                cost_estimate=self.calculate_cost(usage),
            )

        with observability.start_observation(
            name="provider.anthropic.complete",
            as_type="generation",
            input_payload=prompt,
            metadata={
                "provider_name": self.provider_name,
                "provider_mode": "legacy_provider",
                "base_url": self.base_url,
            },
            model=model,
        ) as observation:
            try:
                result = await self.execute_with_retry(_call_api)
            except Exception as exc:
                observability.update_observation(
                    observation,
                    metadata={
                        "provider_name": self.provider_name,
                        "provider_mode": "legacy_provider",
                    },
                    level="ERROR",
                    status_message=str(exc),
                )
                raise

            usage_details = _normalize_usage_details(result.usage)
            usage_source = "provider"
            if usage_details is None:
                usage_details = observability.estimate_usage_details(
                    input_payload=prompt,
                    output_payload=result.content,
                )
                usage_source = "tiktoken"
            observability.update_observation(
                observation,
                output_payload=result.content,
                metadata={
                    "provider_name": self.provider_name,
                    "provider_mode": "legacy_provider",
                },
                usage_details=usage_details,
                usage_source=usage_source,
                model=model,
                cost_details=observability.estimate_cost_details(
                    model=model,
                    usage_details=usage_details,
                ),
            )
            return result

    @_typed_track_llm_call("anthropic")
    def stream(self, prompt: str, **kwargs: object) -> AsyncStreamGenerator:
        """
        Stream a completion from Anthropic.

        Args:
            prompt: User prompt content.
            **kwargs: Provider-specific options.

        Returns:
            AsyncStreamGenerator yielding TutorStreamChunk items.

        Raises:
            Exception: Propagates SDK or execution errors.
        """
        model_raw = kwargs.pop("model", None)
        model = (
            model_raw
            if isinstance(model_raw, str) and model_raw
            else self.config.model or "claude-3-sonnet-20240229"
        )
        max_tokens = kwargs.pop("max_tokens", 1024)
        kwargs.pop("max_retries", None)

        async def _create_stream() -> AnthropicStream:
            client = await self._get_client()
            request_kwargs = _sanitize_kwargs(kwargs)
            return cast(
                AnthropicStream,
                await client.messages.create(  # type: ignore[call-overload]
                    model=model,
                    max_tokens=_coerce_int(max_tokens, 1024),
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    **request_kwargs,
                ),
            )

        async def _stream() -> AsyncStreamGenerator:
            with observability.start_observation(
                name="provider.anthropic.stream",
                as_type="generation",
                input_payload=prompt,
                metadata={
                    "provider_name": self.provider_name,
                    "provider_mode": "legacy_provider",
                    "base_url": self.base_url,
                },
                model=model,
            ) as observation:
                try:
                    stream = cast(AnthropicStream, await self.execute_with_retry(_create_stream))
                except Exception as exc:
                    observability.update_observation(
                        observation,
                        metadata={
                            "provider_name": self.provider_name,
                            "provider_mode": "legacy_provider",
                        },
                        level="ERROR",
                        status_message=str(exc),
                    )
                    raise

                accumulated_content = ""
                usage = None

                try:
                    async for chunk in stream:
                        if chunk.type == "content_block_delta" and chunk.delta.text:
                            delta = chunk.delta.text
                            accumulated_content += delta

                            yield TutorStreamChunk(
                                content=accumulated_content,
                                delta=delta,
                                provider="anthropic",
                                model=model,
                                is_complete=False,
                            )
                        elif chunk.type == "message_delta" and chunk.usage is not None:
                            usage = {
                                "input_tokens": chunk.usage.input_tokens,
                                "output_tokens": chunk.usage.output_tokens,
                            }
                except Exception as exc:
                    observability.update_observation(
                        observation,
                        metadata={
                            "provider_name": self.provider_name,
                            "provider_mode": "legacy_provider",
                        },
                        level="ERROR",
                        status_message=str(exc),
                    )
                    raise

                usage_details = _normalize_usage_details(usage)
                usage_source = "provider"
                if usage_details is None:
                    usage_details = observability.estimate_usage_details(
                        input_payload=prompt,
                        output_payload=accumulated_content,
                    )
                    usage_source = "tiktoken"
                observability.update_observation(
                    observation,
                    output_payload=accumulated_content,
                    metadata={
                        "provider_name": self.provider_name,
                        "provider_mode": "legacy_provider",
                    },
                    usage_details=usage_details,
                    usage_source=usage_source,
                    model=model,
                    cost_details=observability.estimate_cost_details(
                        model=model,
                        usage_details=usage_details,
                    ),
                )

                yield TutorStreamChunk(
                    content=accumulated_content,
                    delta="",
                    provider="anthropic",
                    model=model,
                    is_complete=True,
                    usage=usage,
                )

        return _stream()
