"""Failover wrapper for TutorBot LLM providers."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse


class FailoverProvider(LLMProvider):
    """Try a configured backup provider when the primary yields no visible answer.

    Battle1 W4-T4 model-tiering interaction (decided, not changed): a per-call
    ``model`` override (e.g. the light "fast" tier) is honored by the PRIMARY only.
    On failover the backup is always called with ``self.fallback_model`` -- the
    per-call override is deliberately NOT forwarded. A persistently failing light
    tier is fixed at the config layer (change LLM_FAST_MODEL or turn the fast-turn
    flag off), NOT by an automatic "light -> primary" mid-hop, which would add a
    decider and hide the regression while making cost unpredictable.
    """

    def __init__(
        self,
        *,
        primary: LLMProvider,
        fallback: LLMProvider,
        fallback_model: str,
    ) -> None:
        super().__init__()
        self.primary = primary
        self.fallback = fallback
        self.fallback_model = fallback_model
        self.generation = primary.generation

    @staticmethod
    def _visible_text(content: str | None) -> str:
        if not content:
            return ""
        return re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

    @classmethod
    def _should_failover(cls, response: LLMResponse) -> bool:
        if response.completion_failure_kind and response.finish_reason == "error":
            return True
        if not response.is_complete:
            # A truncated primary may already have streamed provisional deltas.
            # Reusing the callback for a fallback would concatenate two answers;
            # preserve the typed incomplete result for the terminal consumer.
            return False
        if response.has_tool_calls:
            return False
        return not cls._visible_text(response.content)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        primary_public_delta_emitted = False

        async def _capture_primary_delta(text: str) -> None:
            nonlocal primary_public_delta_emitted
            if text:
                primary_public_delta_emitted = True
            if on_content_delta is not None:
                await on_content_delta(text)

        primary_response = await self.primary.chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            on_content_delta=(
                _capture_primary_delta if on_content_delta is not None else None
            ),
        )
        if primary_public_delta_emitted or not self._should_failover(primary_response):
            return primary_response

        logger.warning(
            "Primary LLM provider returned no usable answer; failing over to {}",
            self.fallback_model,
        )
        return await self.fallback.chat(
            messages=messages,
            tools=tools,
            model=self.fallback_model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            on_content_delta=on_content_delta,
        )

    def get_default_model(self) -> str:
        return self.primary.get_default_model()
