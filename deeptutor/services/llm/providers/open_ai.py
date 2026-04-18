"""OpenAI provider implementation using shared HTTP client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Callable, Protocol, TypeVar, cast

import httpx
import openai

from deeptutor.logging import get_logger
from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.runtime_env import env_flag, is_production_environment

from ..config import LLMConfig, get_token_limit_kwargs
from ..exceptions import LLMConfigError
from ..registry import register_provider
from ..telemetry import track_llm_call
from ..types import AsyncStreamGenerator, TutorResponse, TutorStreamChunk
from .base_provider import BaseLLMProvider

logger = get_logger(__name__)
observability = get_langfuse_observability()
F = TypeVar("F", bound=Callable[..., object])


class OpenAIChoiceDelta(Protocol):
    """Protocol for OpenAI delta payloads."""

    content: str | None


class OpenAIChoice(Protocol):
    """Protocol for OpenAI choices in streaming responses."""

    delta: OpenAIChoiceDelta


class OpenAIChunk(Protocol):
    """Protocol for OpenAI streaming chunks."""

    choices: list[OpenAIChoice]


class OpenAIStream(Protocol):
    """Protocol for OpenAI streaming responses."""

    def __aiter__(self) -> AsyncIterator[OpenAIChunk]: ...


def _typed_track_llm_call(provider: str) -> Callable[[F], F]:
    return cast(Callable[[F], F], track_llm_call(provider))


def _normalize_usage_details(usage: object) -> dict[str, float] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = float(usage.get("prompt_tokens") or usage.get("input_tokens") or 0.0)
    output_tokens = float(usage.get("completion_tokens") or usage.get("output_tokens") or 0.0)
    total_tokens = float(usage.get("total_tokens") or (input_tokens + output_tokens))
    if total_tokens <= 0:
        return None
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
    }


@register_provider("openai")
class OpenAIProvider(BaseLLMProvider):
    """Production-ready OpenAI Provider with shared HTTP client."""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        http_client = None
        if env_flag("DISABLE_SSL_VERIFY", default=False):
            if is_production_environment():
                raise LLMConfigError("DISABLE_SSL_VERIFY is not allowed in production")
            logger.warning("SSL verification disabled for OpenAI HTTP client")
            http_client = httpx.AsyncClient(verify=False)  # nosec B501
        self.client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or None,
            http_client=http_client,
        )

    @_typed_track_llm_call("openai")
    async def complete(self, prompt: str, **kwargs: object) -> TutorResponse:
        model_raw = kwargs.pop("model", None)
        model = model_raw if isinstance(model_raw, str) and model_raw else self.config.model
        if not model:
            raise LLMConfigError("Model not configured for OpenAI provider")
        kwargs.pop("stream", None)

        requested_max_tokens = (
            kwargs.pop("max_tokens", None)
            or kwargs.pop("max_completion_tokens", None)
            or getattr(self.config, "max_tokens", 4096)
        )
        if isinstance(requested_max_tokens, (int, float, str)):
            max_tokens = int(requested_max_tokens)
        else:
            max_tokens = int(getattr(self.config, "max_tokens", 4096))
        kwargs.update(get_token_limit_kwargs(model, max_tokens))

        async def _call_api() -> TutorResponse:
            request_kwargs: dict[str, object] = dict(kwargs)
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **request_kwargs,
            )

            if not response.choices:
                raise ValueError("API returned no choices in response")
            choice = response.choices[0]
            message = choice.message
            content = message.content or ""
            finish_reason = choice.finish_reason
            usage = response.usage.model_dump() if response.usage else {}
            raw_response = response.model_dump() if hasattr(response, "model_dump") else {}
            provider_label = (
                "azure" if isinstance(self.client, openai.AsyncAzureOpenAI) else "openai"
            )

            return TutorResponse(
                content=content,
                raw_response=raw_response,
                usage=usage,
                provider=provider_label,
                model=model,
                finish_reason=finish_reason,
                cost_estimate=self.calculate_cost(usage),
            )

        with observability.start_observation(
            name="provider.openai.complete",
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

    def stream(self, prompt: str, **kwargs: object) -> AsyncStreamGenerator:
        model_raw = kwargs.pop("model", None)
        model = model_raw if isinstance(model_raw, str) and model_raw else self.config.model
        if not model:
            raise LLMConfigError("Model not configured for OpenAI provider")

        async def _create_stream() -> OpenAIStream:
            request_kwargs: dict[str, object] = dict(kwargs)
            return cast(
                OpenAIStream,
                await self.client.chat.completions.create(  # type: ignore[call-overload]
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    **request_kwargs,
                ),
            )

        async def _stream() -> AsyncStreamGenerator:
            with observability.start_observation(
                name="provider.openai.stream",
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
                    stream = cast(OpenAIStream, await self.execute_with_retry(_create_stream))
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
                provider_label = (
                    "azure" if isinstance(self.client, openai.AsyncAzureOpenAI) else "openai"
                )

                try:
                    async for chunk in stream:
                        delta = ""
                        if chunk.choices and chunk.choices[0].delta.content:
                            delta = chunk.choices[0].delta.content
                            accumulated_content += delta
                            yield TutorStreamChunk(
                                content=accumulated_content,
                                delta=delta,
                                provider=provider_label,
                                model=model,
                                is_complete=False,
                            )
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

                usage_details = observability.estimate_usage_details(
                    input_payload=prompt,
                    output_payload=accumulated_content,
                )
                observability.update_observation(
                    observation,
                    output_payload=accumulated_content,
                    metadata={
                        "provider_name": self.provider_name,
                        "provider_mode": "legacy_provider",
                    },
                    usage_details=usage_details,
                    usage_source="tiktoken",
                    model=model,
                    cost_details=observability.estimate_cost_details(
                        model=model,
                        usage_details=usage_details,
                    ),
                )
                yield TutorStreamChunk(
                    content=accumulated_content,
                    delta="",
                    provider=provider_label,
                    model=model,
                    is_complete=True,
                )

        return _stream()
