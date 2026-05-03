"""Failover wrapper for TutorBot LLM providers."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse


class FailoverProvider(LLMProvider):
    """Try a configured backup provider when the primary yields no visible answer."""

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
        if response.finish_reason == "error":
            return True
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
        primary_response = await self.primary.chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            on_content_delta=on_content_delta,
        )
        if not self._should_failover(primary_response):
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
