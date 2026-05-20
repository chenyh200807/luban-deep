"""Agentic chat capability."""

from __future__ import annotations

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.agents.chat.agentic_pipeline import (
    ANSWER_TYPE_KNOWLEDGE,
    CHAT_OPTIONAL_TOOLS,
    AgenticChatPipeline,
)
from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.capabilities.request_contracts import get_capability_request_schema


class ChatCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="chat",
        description="Chat with selectable fast, smart, or deep execution modes.",
        stages=["responding", "thinking", "acting", "observing"],
        tools_used=CHAT_OPTIONAL_TOOLS,
        cli_aliases=["chat"],
        request_schema=get_capability_request_schema("chat"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        mode = str(context.config_overrides.get("chat_mode") or get_default_chat_mode()).strip().lower()
        if self._should_promote_fast_mode(context, mode):
            mode = "deep"
        if mode in {"fast", "smart", "deep"}:
            context.config_overrides["chat_mode"] = mode
        pipeline = AgenticChatPipeline(language=context.language)
        await pipeline.run(context, stream)

    @staticmethod
    def _should_promote_fast_mode(context: UnifiedContext, mode: str) -> bool:
        if mode != "fast":
            return False
        if bool((context.metadata or {}).get("chat_mode_explicit")):
            return False
        if bool((context.config_overrides or {}).get("chat_mode_explicit")):
            return False
        pipeline = AgenticChatPipeline(language=context.language)
        return pipeline._infer_answer_type(context.user_message) == ANSWER_TYPE_KNOWLEDGE
