"""Agentic chat capability."""

from __future__ import annotations

from typing import Any

from deeptutor.agents.chat import ChatAgent
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.agents.chat.agentic_pipeline import CHAT_OPTIONAL_TOOLS, AgenticChatPipeline
from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.capabilities.request_contracts import get_capability_request_schema

CHAT_FAST_TOOLS = {"rag", "web_search"}


def _flatten_sources(raw_sources: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(raw_sources, dict):
        return []
    flattened: list[dict[str, Any]] = []
    for source_type, items in raw_sources.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                flattened.append({"source_type": source_type, **item})
            elif item:
                flattened.append({"source_type": source_type, "content": str(item)})
    return flattened


class ChatCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="chat",
        description="Chat with selectable fast or deep execution modes.",
        stages=["responding", "thinking", "acting", "observing"],
        tools_used=CHAT_OPTIONAL_TOOLS,
        cli_aliases=["chat"],
        request_schema=get_capability_request_schema("chat"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        mode = str(context.config_overrides.get("chat_mode") or get_default_chat_mode()).strip().lower()
        if mode == "fast":
            await self._run_fast(context, stream)
            return
        pipeline = AgenticChatPipeline(language=context.language)
        await pipeline.run(context, stream)

    async def _run_fast(self, context: UnifiedContext, stream: StreamBus) -> None:
        enabled_tools = {tool for tool in context.enabled_tools or [] if tool in CHAT_FAST_TOOLS}
        kb_name = context.knowledge_bases[0] if context.knowledge_bases else None
        history = [
            {"role": msg.get("role", ""), "content": str(msg.get("content", "") or "")}
            for msg in context.conversation_history
            if msg.get("role") in {"user", "assistant"}
        ]
        agent = ChatAgent(language=context.language)

        async with stream.stage("responding", source=self.name):
            await stream.progress(
                "快速回答中..." if context.language.lower().startswith("zh") else "Answering quickly...",
                source=self.name,
                stage="responding",
            )
            result = await agent.process(
                message=context.user_message,
                history=history,
                kb_name=kb_name,
                enable_rag="rag" in enabled_tools,
                enable_web_search="web_search" in enabled_tools,
                stream=True,
                attachments=context.attachments,
            )
            full_response = ""
            final_sources: dict[str, Any] = {"rag": [], "web": []}
            truncated_history: list[dict[str, str]] = history
            async for item in result:
                item_type = str(item.get("type") or "")
                if item_type == "chunk":
                    chunk = str(item.get("content") or "")
                    if not chunk:
                        continue
                    full_response += chunk
                    await stream.content(chunk, source=self.name, stage="responding")
                    continue
                if item_type == "complete":
                    final_sources = item.get("sources") if isinstance(item.get("sources"), dict) else final_sources
                    candidate_history = item.get("truncated_history")
                    if isinstance(candidate_history, list):
                        truncated_history = candidate_history

            flattened_sources = _flatten_sources(final_sources)
            if flattened_sources:
                await stream.sources(flattened_sources, source=self.name, stage="responding")
            await stream.result(
                {
                    "response": full_response,
                    "chat_mode": "fast",
                    "sources": final_sources,
                    "truncated_history": truncated_history,
                },
                source=self.name,
            )
