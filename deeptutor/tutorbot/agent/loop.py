"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.query_intent import (
    build_grounding_decision_from_metadata,
)
from deeptutor.services.rag.exact_authority import (
    build_exact_authority_response,
    should_force_exact_authority,
)
from deeptutor.services.rag.pipelines.supabase_strategy import prepare_exact_question_probe
from deeptutor.tutorbot.agent.context import ContextBuilder
from deeptutor.tutorbot.agent.memory import MemoryConsolidator
from deeptutor.tutorbot.agent.team import TeamManager
from deeptutor.tutorbot.agent.team.tools import TeamTool
from deeptutor.tutorbot.agent.subagent import SubagentManager
from deeptutor.tutorbot.agent.tools.cron import CronTool
from deeptutor.tutorbot.agent.tools.message import MessageTool
from deeptutor.tutorbot.agent.tools.registry import ToolRegistry, build_base_tools
from deeptutor.tutorbot.agent.tools.spawn import SpawnTool
from deeptutor.tutorbot.bus.events import InboundMessage, OutboundMessage
from deeptutor.tutorbot.bus.queue import MessageBus
from deeptutor.tutorbot.providers.base import LLMProvider
from deeptutor.tutorbot.session.manager import Session, SessionManager
from deeptutor.tutorbot.teaching_modes import (
    build_continuity_anchor_instruction,
    get_anchor_preservation_instruction,
    get_practice_generation_instruction,
    get_teaching_mode_instruction,
    looks_like_practice_generation_request,
    normalize_anchor_terms_in_response,
)
from deeptutor.tutorbot.markdown_style import get_markdown_style_instruction

if TYPE_CHECKING:
    from deeptutor.tutorbot.config.schema import ChannelsConfig, ExecToolConfig, WebSearchConfig
    from deeptutor.tutorbot.cron.service import CronService

observability = get_langfuse_observability()


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 16_000
    _RAG_STOP_QUERY_SIMILARITY_THRESHOLD = 0.85
    _RAG_STOP_SOURCE_OVERLAP_THRESHOLD = 0.6

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        context_window_tokens: int = 65_536,
        web_search_config: WebSearchConfig | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        team_max_workers: int = 5,
        team_worker_max_iterations: int = 25,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        shared_memory_dir: Path | None = None,
        default_session_key: str | None = None,
    ):
        from deeptutor.tutorbot.config.schema import ExecToolConfig, WebSearchConfig

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.context_window_tokens = context_window_tokens
        self.web_search_config = web_search_config or WebSearchConfig()
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self._shared_memory_dir = shared_memory_dir
        self._default_session_key = default_session_key

        self.context = ContextBuilder(workspace, shared_memory_dir=shared_memory_dir)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_search_config=self.web_search_config,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        self.team = TeamManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            sessions=self.sessions,
            model=self.model,
            temperature=provider.generation.temperature,
            max_tokens=provider.generation.max_tokens,
            reasoning_effort=provider.generation.reasoning_effort,
            web_search_config=self.web_search_config,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            max_workers=team_max_workers,
            worker_max_iterations=team_worker_max_iterations,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._processing_lock = asyncio.Lock()
        self.memory_consolidator = MemoryConsolidator(
            workspace=workspace,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
            shared_memory_dir=shared_memory_dir,
        )
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        self.tools = build_base_tools(
            workspace=self.workspace,
            exec_config=self.exec_config,
            web_search_config=self.web_search_config,
            web_proxy=self.web_proxy,
            restrict_to_workspace=self.restrict_to_workspace,
        )
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        self.tools.register(TeamTool(manager=self.team))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

        from deeptutor.tutorbot.agent.tools.deeptutor_tools import (
            BrainstormAdapterTool,
            CodeExecutionAdapterTool,
            PaperSearchAdapterTool,
            RAGAdapterTool,
            ReasonAdapterTool,
        )
        for tool_cls in (BrainstormAdapterTool, RAGAdapterTool,
                         CodeExecutionAdapterTool, ReasonAdapterTool,
                         PaperSearchAdapterTool):
            self.tools.register(tool_cls())

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from deeptutor.tutorbot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        *,
        session_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron", "team"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))
        runtime_metadata = dict(metadata or {})
        if session_key:
            runtime_metadata.setdefault("session_key", session_key)
        runtime_metadata.setdefault("channel", channel)
        runtime_metadata.setdefault("chat_id", chat_id)
        if message_id:
            runtime_metadata.setdefault("message_id", message_id)
        for tool_name in self.tools.tool_names:
            tool = self.tools.get(tool_name)
            if tool and hasattr(tool, "set_runtime_context"):
                tool.set_runtime_context(metadata=runtime_metadata)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _normalize_query_text(text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
        return normalized

    @classmethod
    def _query_terms(cls, text: str) -> set[str]:
        normalized = cls._normalize_query_text(text)
        if not normalized:
            return set()
        return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalized))

    @staticmethod
    def _jaccard_similarity(left: set[str], right: set[str]) -> float | None:
        if not left or not right:
            return None
        union = left | right
        if not union:
            return None
        return round(len(left & right) / len(union), 4)

    @staticmethod
    def _copy_sources(sources: Any) -> list[dict[str, Any]]:
        if not isinstance(sources, list):
            return []
        copied: list[dict[str, Any]] = []
        for item in sources:
            if isinstance(item, dict):
                copied.append(dict(item))
        return copied

    @classmethod
    def _source_identity(cls, source: dict[str, Any]) -> str:
        for key in ("chunk_id", "id", "source_id"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
        parts: list[str] = []
        for key in ("kb_name", "source_type", "title", "url", "file_path", "path", "page", "page_number"):
            value = str(source.get(key) or "").strip()
            if value:
                parts.append(f"{key}={value}")
        if parts:
            return "|".join(parts)
        return json.dumps(source, ensure_ascii=False, sort_keys=True)

    @classmethod
    def _source_overlap(cls, previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> tuple[float | None, int]:
        previous_ids = {cls._source_identity(item) for item in previous if isinstance(item, dict)}
        current_ids = {cls._source_identity(item) for item in current if isinstance(item, dict)}
        if not previous_ids or not current_ids:
            return None, 0
        union = previous_ids | current_ids
        if not union:
            return None, 0
        overlap = len(previous_ids & current_ids)
        return round(overlap / len(union), 4), overlap

    @classmethod
    def _build_rag_round_metadata(
        cls,
        *,
        preview_args: dict[str, Any],
        tool_trace_metadata: dict[str, Any] | None,
        prior_rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metadata = dict(tool_trace_metadata or {})
        sources = cls._copy_sources(metadata.get("sources"))
        query = str(preview_args.get("query") or "").strip()
        kb_name = str(
            preview_args.get("kb_name")
            or metadata.get("kb_name")
            or ""
        ).strip()

        previous_round = prior_rounds[-1] if prior_rounds else None
        previous_query = (
            str(previous_round.get("query") or "").strip()
            if isinstance(previous_round, dict)
            else ""
        )
        previous_sources = (
            cls._copy_sources(previous_round.get("sources"))
            if isinstance(previous_round, dict)
            else []
        )
        query_similarity = cls._jaccard_similarity(
            cls._query_terms(previous_query),
            cls._query_terms(query),
        )
        source_overlap, shared_source_count = cls._source_overlap(previous_sources, sources)

        round_metadata = {
            "round_index": len(prior_rounds) + 1,
            "query": query,
            "kb_name": kb_name,
            "source_count": len(sources),
            "sources": sources,
            "query_similarity_to_prev": query_similarity,
            "source_overlap_to_prev": source_overlap,
            "shared_source_count_with_prev": shared_source_count,
        }
        return round_metadata

    @classmethod
    def _augment_rag_trace_metadata(
        cls,
        *,
        preview_args: dict[str, Any],
        tool_trace_metadata: dict[str, Any] | None,
        rag_rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        merged_metadata = dict(tool_trace_metadata or {})
        rag_round = cls._build_rag_round_metadata(
            preview_args=preview_args,
            tool_trace_metadata=merged_metadata,
            prior_rounds=rag_rounds,
        )
        rag_rounds.append(dict(rag_round))
        merged_metadata["rag_round"] = dict(rag_round)
        merged_metadata["rag_rounds"] = [dict(item) for item in rag_rounds]
        merged_metadata["rag_round_count"] = len(rag_rounds)
        return merged_metadata

    def _resolve_tool_definitions(self, runtime_metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
        configured = runtime_metadata.get("default_tools") if isinstance(runtime_metadata, dict) else None
        if not isinstance(configured, list):
            return self.tools.get_definitions()

        ordered_names: list[str] = []
        seen: set[str] = set()
        for item in configured:
            name = str(item or "").strip()
            if not name or name in seen or not self.tools.has(name):
                continue
            ordered_names.append(name)
            seen.add(name)

        if not ordered_names:
            return self.tools.get_definitions()
        return self.tools.get_definitions(ordered_names)

    @classmethod
    def _rag_stop_enabled(cls, runtime_metadata: dict[str, Any] | None) -> bool:
        if not isinstance(runtime_metadata, dict):
            return True
        if "enable_rag_saturation_stop" not in runtime_metadata:
            return True
        return bool(runtime_metadata.get("enable_rag_saturation_stop"))

    @classmethod
    def _rag_stop_threshold(
        cls,
        runtime_metadata: dict[str, Any] | None,
        *,
        key: str,
        default: float,
    ) -> float:
        if not isinstance(runtime_metadata, dict):
            return default
        raw = runtime_metadata.get(key)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, value))

    @classmethod
    def _build_rag_saturation(
        cls,
        *,
        rag_round: dict[str, Any],
        runtime_metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not cls._rag_stop_enabled(runtime_metadata):
            return None
        if int(rag_round.get("round_index") or 0) < 2:
            return None

        query_similarity = rag_round.get("query_similarity_to_prev")
        source_overlap = rag_round.get("source_overlap_to_prev")
        if not isinstance(query_similarity, (int, float)):
            return None
        if not isinstance(source_overlap, (int, float)):
            return None

        query_threshold = cls._rag_stop_threshold(
            runtime_metadata,
            key="rag_stop_query_similarity_threshold",
            default=cls._RAG_STOP_QUERY_SIMILARITY_THRESHOLD,
        )
        source_threshold = cls._rag_stop_threshold(
            runtime_metadata,
            key="rag_stop_source_overlap_threshold",
            default=cls._RAG_STOP_SOURCE_OVERLAP_THRESHOLD,
        )
        if query_similarity < query_threshold or source_overlap < source_threshold:
            return None

        return {
            "detected": True,
            "reason": "high_query_similarity_and_source_overlap",
            "round_index": int(rag_round.get("round_index") or 0),
            "query_similarity_to_prev": float(query_similarity),
            "source_overlap_to_prev": float(source_overlap),
            "shared_source_count_with_prev": int(rag_round.get("shared_source_count_with_prev") or 0),
            "query_similarity_threshold": query_threshold,
            "source_overlap_threshold": source_threshold,
        }

    @staticmethod
    def _filter_out_tool_definitions(
        tool_defs: list[dict[str, Any]],
        *,
        disabled_names: set[str],
    ) -> list[dict[str, Any]]:
        if not disabled_names:
            return tool_defs
        filtered: list[dict[str, Any]] = []
        for item in tool_defs:
            function_spec = item.get("function") if isinstance(item, dict) else None
            name = str(function_spec.get("name") or "").strip() if isinstance(function_spec, dict) else ""
            if name and name in disabled_names:
                continue
            filtered.append(item)
        return filtered

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        runtime_metadata: dict[str, Any] | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
        allow_exact_authority_override: bool = False,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop."""
        runtime_metadata = dict(runtime_metadata or {})
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        exact_authority: dict[str, Any] | None = None
        rag_rounds: list[dict[str, Any]] = []
        rag_saturation: dict[str, Any] | None = None
        raw_stream_buffer = ""
        emitted_stream_len = 0
        effective_model = self.model

        def _visible_stream_text(raw_text: str) -> str:
            # Hide completed and in-progress <think> blocks before forwarding deltas.
            visible = re.sub(r"<think>[\s\S]*?</think>", "", raw_text)
            visible = re.sub(r"<think>[\s\S]*$", "", visible)
            visible = re.sub(r"</think>[\s\S]*$", "", visible)
            visible = re.sub(r"<[^>]*$", "", visible)
            return visible

        async def _stream_delta(delta: str) -> None:
            nonlocal raw_stream_buffer, emitted_stream_len
            if not on_content_delta or not delta:
                return
            raw_stream_buffer += delta
            visible = _visible_stream_text(raw_stream_buffer)
            if len(visible) <= emitted_stream_len:
                return
            chunk = visible[emitted_stream_len:]
            emitted_stream_len = len(visible)
            if chunk:
                await on_content_delta(chunk)

        while iteration < self.max_iterations:
            iteration += 1

            tool_defs = self._resolve_tool_definitions(runtime_metadata)
            if rag_saturation:
                tool_defs = self._filter_out_tool_definitions(tool_defs, disabled_names={"rag"})

            response = await self.provider.chat_with_retry(
                messages=messages,
                tools=tool_defs,
                model=effective_model,
                on_content_delta=_stream_delta if on_content_delta else None,
            )

            if response.has_tool_calls:
                if on_progress:
                    thought = self._strip_think(response.content)
                    if thought:
                        await on_progress(thought)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    tc.to_openai_tool_call()
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    preview_args = dict(tool_call.arguments or {})
                    tool = self.tools.get(tool_call.name)
                    if tool is not None:
                        try:
                            preview_args = tool.preview_args(preview_args)
                        except Exception:
                            preview_args = dict(tool_call.arguments or {})
                    args_str = json.dumps(preview_args, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    if on_tool_call:
                        await on_tool_call(tool_call.name, preview_args)
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    tool_trace_metadata: dict[str, Any] | None = None
                    if tool is not None:
                        try:
                            tool_trace_metadata = tool.consume_trace_metadata()
                        except Exception:
                            tool_trace_metadata = None
                    if isinstance(tool_trace_metadata, dict):
                        exact_candidate = (
                            tool_trace_metadata.get("exact_question")
                            if isinstance(tool_trace_metadata.get("exact_question"), dict)
                            else None
                        )
                        if (
                            allow_exact_authority_override
                            and exact_candidate
                            and self._should_force_exact_authority(exact_candidate)
                        ):
                            exact_authority = exact_candidate
                    if tool_call.name == "rag":
                        tool_trace_metadata = self._augment_rag_trace_metadata(
                            preview_args=preview_args,
                            tool_trace_metadata=tool_trace_metadata,
                            rag_rounds=rag_rounds,
                        )
                        current_round = (
                            tool_trace_metadata.get("rag_round")
                            if isinstance(tool_trace_metadata, dict)
                            and isinstance(tool_trace_metadata.get("rag_round"), dict)
                            else None
                        )
                        saturation = (
                            self._build_rag_saturation(
                                rag_round=current_round,
                                runtime_metadata=runtime_metadata,
                            )
                            if current_round
                            else None
                        )
                        if saturation:
                            rag_saturation = saturation
                            tool_trace_metadata["rag_saturation"] = dict(saturation)
                    elif rag_saturation and isinstance(tool_trace_metadata, dict):
                        tool_trace_metadata["rag_saturation"] = dict(rag_saturation)
                    if on_tool_result:
                        await on_tool_result(tool_call.name, result, tool_trace_metadata)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        if allow_exact_authority_override and exact_authority:
            exact_response = self._build_exact_authority_response(exact_authority)
            if exact_response:
                final_content = exact_response
                self._replace_last_assistant_message(messages, exact_response)

        return final_content, tools_used, messages

    @staticmethod
    def _should_force_exact_authority(exact_question: dict[str, Any]) -> bool:
        return should_force_exact_authority(exact_question)

    @staticmethod
    def _build_exact_authority_response(exact_question: dict[str, Any]) -> str:
        return build_exact_authority_response(exact_question)

    @staticmethod
    def _replace_last_assistant_message(messages: list[dict[str, Any]], content: str) -> None:
        for item in reversed(messages):
            if str(item.get("role") or "") == "assistant":
                item["content"] = content
                return

    @classmethod
    def _should_prefetch_grounded_rag(
        cls,
        *,
        current_message: str,
        runtime_metadata: dict[str, Any] | None,
    ) -> bool:
        decision = build_grounding_decision_from_metadata(
            query=current_message,
            runtime_metadata=runtime_metadata,
            rag_enabled=True,
            tutorbot_context=True,
            exact_question_candidate=prepare_exact_question_probe(current_message) is not None,
            practice_generation_request=looks_like_practice_generation_request(current_message),
        )
        if (
            not decision.grounded_construction_exam_runtime
            and str((runtime_metadata or {}).get("bot_id") or "").strip().lower()
            == "construction-exam-coach"
        ):
            return decision.current_info_required or decision.textbook_delta_query
        return decision.should_prefetch_grounded_rag

    @staticmethod
    def _build_rag_preview_args(
        current_message: str,
        runtime_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
        preview_args: dict[str, Any] = {"query": current_message}
        default_kb = str(metadata.get("default_kb") or "").strip()
        if not default_kb:
            knowledge_bases = metadata.get("knowledge_bases")
            if isinstance(knowledge_bases, list):
                for item in knowledge_bases:
                    normalized = str(item or "").strip()
                    if normalized:
                        default_kb = normalized
                        break
        if default_kb:
            preview_args["kb_name"] = default_kb
        intent = str(metadata.get("intent") or "").strip()
        if intent:
            preview_args["intent"] = intent
        question_flow_active = bool(
            metadata.get("question_followup_context") or metadata.get("followup_question_context")
        ) or intent in {"answer_questions", "revise_answers"}
        question_type = str(metadata.get("question_type") or "").strip() if question_flow_active else ""
        if question_type:
            preview_args["question_type"] = question_type
        interaction_hints = (
            metadata.get("interaction_hints")
            if isinstance(metadata.get("interaction_hints"), dict)
            else {}
        )
        routing_metadata = {
            "profile": str(interaction_hints.get("profile") or "").strip(),
            "entry_role": str(interaction_hints.get("entry_role") or "").strip(),
            "subject_domain": str(interaction_hints.get("subject_domain") or "").strip(),
        }
        if any(routing_metadata.values()):
            preview_args["routing_metadata"] = routing_metadata
        return preview_args

    async def _maybe_prefetch_grounded_rag(
        self,
        *,
        initial_messages: list[dict[str, Any]],
        current_message: str,
        runtime_metadata: dict[str, Any] | None,
        on_tool_call: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
    ) -> list[dict[str, Any]]:
        if not self._should_prefetch_grounded_rag(
            current_message=current_message,
            runtime_metadata=runtime_metadata,
        ):
            return initial_messages

        rag_tool = self.tools.get("rag")
        if rag_tool is None:
            return initial_messages

        preview_args = self._build_rag_preview_args(current_message, runtime_metadata)
        try:
            preview_args = rag_tool.preview_args(preview_args)
        except Exception:
            preview_args = dict(preview_args)

        result = await self.tools.execute("rag", preview_args)
        result_text = str(result or "").strip()
        if not result_text:
            return initial_messages

        tool_trace_metadata: dict[str, Any] | None = None
        try:
            tool_trace_metadata = rag_tool.consume_trace_metadata()
        except Exception:
            tool_trace_metadata = None
        merged_metadata = self._augment_rag_trace_metadata(
            preview_args=preview_args,
            tool_trace_metadata=tool_trace_metadata if isinstance(tool_trace_metadata, dict) else None,
            rag_rounds=[],
        )

        if on_tool_call:
            await on_tool_call("rag", preview_args)
        if on_tool_result:
            await on_tool_result("rag", result_text, merged_metadata)

        prefetch_messages = list(initial_messages)
        tool_call_id = "prefetch-rag-1"
        prefetch_messages = self.context.add_assistant_message(
            prefetch_messages,
            None,
            tool_calls=[
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "rag",
                        "arguments": json.dumps(preview_args, ensure_ascii=False),
                    },
                }
            ],
        )
        prefetch_messages = self.context.add_tool_result(
            prefetch_messages,
            tool_call_id,
            "rag",
            result_text,
        )
        prefetch_messages.append(
            {
                "role": "system",
                "content": (
                    "首轮知识召回已完成。请直接基于现有证据回答学员，"
                    "不要复述“我去搜索/我正在查找”这类过程话术；"
                    "只有当前证据仍明显不足时，才继续调用其他工具。"
                ),
            }
        )
        return prefetch_messages

    async def _run_fast_policy_once(
        self,
        initial_messages: list[dict[str, Any]],
        *,
        runtime_metadata: dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        runtime_metadata = dict(runtime_metadata or {})
        effective_model = self.model
        response = await self.provider.chat_with_retry(
            messages=initial_messages,
            tools=None,
            model=effective_model,
            on_content_delta=on_content_delta,
        )
        clean = self._strip_think(response.content)
        if response.finish_reason == "error":
            final_content = clean or "Sorry, I encountered an error calling the AI model."
        else:
            final_content = clean
        messages = self.context.add_assistant_message(
            initial_messages,
            final_content,
            reasoning_content=response.reasoning_content,
            thinking_blocks=response.thinking_blocks,
        )
        return final_content, messages

    async def _maybe_run_exact_rag_fast_path(
        self,
        *,
        current_message: str,
        history: list[dict[str, Any]],
        media: list[str] | None,
        channel: str,
        chat_id: str,
        runtime_instruction: str | None,
        runtime_metadata: dict[str, Any],
        on_tool_call: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None] | None:
        rag_tool = self.tools.get("rag")
        if rag_tool is None:
            return None
        exact_probe = prepare_exact_question_probe(current_message)
        practice_generation_request = looks_like_practice_generation_request(current_message)
        if bool(runtime_metadata.get("suppress_answer_reveal_on_generate")) and practice_generation_request:
            return None
        decision = build_grounding_decision_from_metadata(
            query=current_message,
            runtime_metadata=runtime_metadata,
            rag_enabled=True,
            tutorbot_context=True,
            exact_question_candidate=exact_probe is not None,
            practice_generation_request=practice_generation_request,
        )
        if (
            not decision.should_try_exact_fast_path
            and str((runtime_metadata or {}).get("bot_id") or "").strip().lower()
            != "construction-exam-coach"
        ):
            return None
        if exact_probe is None:
            return None

        preview_args = self._build_rag_preview_args(current_message, runtime_metadata)
        try:
            preview_args = rag_tool.preview_args(preview_args)
        except Exception:
            preview_args = dict(preview_args)

        result = await self.tools.execute("rag", preview_args)
        tool_trace_metadata: dict[str, Any] | None = None
        try:
            tool_trace_metadata = rag_tool.consume_trace_metadata()
        except Exception:
            tool_trace_metadata = None
        exact_candidate = (
            tool_trace_metadata.get("exact_question")
            if isinstance(tool_trace_metadata, dict)
            and isinstance(tool_trace_metadata.get("exact_question"), dict)
            else None
        )
        if not exact_candidate or not self._should_force_exact_authority(exact_candidate):
            return None

        exact_response = self._build_exact_authority_response(exact_candidate)
        if not exact_response:
            return None

        merged_metadata = self._augment_rag_trace_metadata(
            preview_args=preview_args,
            tool_trace_metadata=tool_trace_metadata,
            rag_rounds=[],
        )
        merged_metadata["authority_applied"] = True

        if on_tool_call:
            await on_tool_call("rag", preview_args)
        if on_tool_result:
            await on_tool_result("rag", result, merged_metadata)

        messages = self.context.build_messages(
            history=history,
            current_message=current_message,
            media=media,
            channel=channel,
            chat_id=chat_id,
            runtime_instruction=runtime_instruction,
        )
        messages = self.context.add_assistant_message(messages, exact_response)
        return exact_response, messages, merged_metadata

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            cmd = msg.content.strip().lower()
            if cmd == "/stop":
                await self._handle_stop(msg)
            elif cmd == "/restart":
                await self._handle_restart(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        team_cancelled = await self.team.cancel_by_session(msg.session_key)
        if team_cancelled:
            session = self.sessions.get_or_create(msg.session_key)
            session.metadata.pop("nano_team_active", None)
            self.sessions.save(session)
        total = cancelled + sub_cancelled + team_cancelled
        content = f"Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    async def _handle_restart(self, msg: InboundMessage) -> None:
        """Restart the process in-place via os.execv."""
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        ))

        async def _do_restart():
            await asyncio.sleep(1)
            # Use original sys.argv to preserve entry point (tutorbot runs in-process)
            os.execv(sys.executable, [sys.executable] + sys.argv)

        asyncio.create_task(_do_restart())

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            runtime_metadata = dict(session.metadata or {})
            runtime_metadata.update(msg.metadata or {})
            self._set_tool_context(
                channel,
                chat_id,
                msg.metadata.get("message_id"),
                session_key=key,
                metadata=runtime_metadata,
            )
            history = session.get_history(max_messages=0)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(
                messages,
                runtime_metadata=runtime_metadata,
            )
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or self._default_session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        raw = msg.content.strip()
        cmd = raw.lower()
        if cmd == "/new":
            try:
                if not await self.memory_consolidator.archive_unconsolidated(session):
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Memory archival failed, session not cleared. Please try again.",
                    )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )

            session.clear()
            session.metadata.pop("nano_team_active", None)
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            lines = [
                "🐈 TutorBot commands:",
                "/new — Start a new conversation",
                "/stop — Stop the current task",
                "/restart — Restart the bot",
                "/team <goal> — Start or instruct nano team mode",
                "/team status — Show nano team state",
                "/team log [n] — Show detailed collaboration logs (default 20)",
                "/team approve <task_id> — Approve a pending task",
                "/team reject <task_id> <reason> — Reject a pending task",
                "/team manual <task_id> <instruction> — Send change request",
                "/team stop — Stop nano team mode",
                "/btw <instruction> — Async side task via single subagent",
                "/help — Show available commands",
            ]
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines),
            )
        current_message = msg.content
        if cmd.startswith("/btw"):
            arg = raw[4:].strip()
            if not arg:
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Usage: /btw <instruction>",
                )
            started = await self.subagents.spawn(
                task=arg,
                label="btw",
                origin_channel=msg.channel,
                origin_chat_id=msg.chat_id,
                session_key=key,
            )
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=started)

        if cmd == "/team":
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=(
                    "Usage:\n"
                    "/team <goal>\n"
                    "/team status\n"
                    "/team log [n]\n"
                    "/team approve <task_id>\n"
                    "/team reject <task_id> <reason>\n"
                    "/team manual <task_id> <instruction>\n"
                    "/team stop"
                ),
            )

        if cmd.startswith("/teams "):
            cmd = "/team " + raw[7:].strip().lower()
            raw = "/team " + raw[7:].strip()

        if cmd.startswith("/team "):
            instruction = raw[6:].strip()
            parts = instruction.split(maxsplit=2)
            lowered = (parts[0] if parts else "").lower()
            if lowered == "status":
                content = self.team.status_text(key)
                session.metadata["nano_team_active"] = bool(self.team.has_unfinished_run(key))
                self.sessions.save(session)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata={"team_text": True},
                )
            if lowered == "log":
                n = 20
                if len(parts) > 1:
                    try:
                        n = max(1, min(200, int(parts[1])))
                    except (TypeError, ValueError):
                        n = 20
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=self.team.log_text(key, n=n),
                    metadata={"team_text": True},
                )
            if lowered == "stop":
                if msg.channel == "cli":
                    content = await self.team.stop_mode(key, with_snapshot=True)
                else:
                    content = await self.team.stop_mode(key)
                session.metadata.pop("nano_team_active", None)
                self.sessions.save(session)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata={"team_text": True},
                )
            if lowered == "approve":
                task_id = parts[1] if len(parts) > 1 else ""
                if not task_id:
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Usage: /team approve <task_id>",
                    )
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=self.team.approve_for_session(key, task_id),
                    metadata={"team_text": True},
                )
            if lowered == "reject":
                task_id = parts[1] if len(parts) > 1 else ""
                reason = parts[2] if len(parts) > 2 else ""
                if not task_id or not reason.strip():
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Usage: /team reject <task_id> <reason>",
                    )
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=self.team.reject_for_session(key, task_id, reason.strip()),
                    metadata={"team_text": True},
                )
            if lowered == "manual":
                task_id = parts[1] if len(parts) > 1 else ""
                instruction_text = parts[2] if len(parts) > 2 else ""
                if not task_id or not instruction_text.strip():
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Usage: /team manual <task_id> <instruction>",
                    )
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=self.team.request_changes_for_session(key, task_id, instruction_text.strip()),
                    metadata={"team_text": True},
                )

            content = await self.team.start_or_route_goal(key, instruction)
            session.metadata["nano_team_active"] = self.team.is_active(key)
            self.sessions.save(session)
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
                metadata={"team_text": True},
            )

        if session.metadata.get("nano_team_active"):
            if not self.team.is_active(key):
                session.metadata.pop("nano_team_active", None)
                self.sessions.save(session)
            else:
                if msg.channel != "cli" and self.team.has_pending_approval(key):
                    approval_reply = self.team.handle_approval_reply(key, raw)
                    if approval_reply:
                        return OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=approval_reply,
                            metadata={"team_text": True},
                        )
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=(
                        "Team mode is active. Supported input:\n"
                        "- /team <instruction|status|log|approve|reject|manual|stop>\n"
                        "- /btw <instruction>"
                    ),
                )

        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        runtime_metadata = dict(session.metadata or {})
        runtime_metadata.update(msg.metadata or {})
        self._set_tool_context(
            msg.channel,
            msg.chat_id,
            msg.metadata.get("message_id"),
            session_key=key,
            metadata=runtime_metadata,
        )
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=0)
        response_mode = (
            runtime_metadata.get("effective_response_mode")
            or runtime_metadata.get("requested_response_mode")
        )
        runtime_instruction_parts = [
            get_teaching_mode_instruction(response_mode),
            get_anchor_preservation_instruction(current_message),
            build_continuity_anchor_instruction(
                current_message,
                active_object=runtime_metadata.get("active_object")
                if isinstance(runtime_metadata.get("active_object"), dict)
                else None,
                conversation_context_text=str(
                    runtime_metadata.get("conversation_context_text") or ""
                ).strip(),
            ),
            get_markdown_style_instruction(),
            get_practice_generation_instruction(
                user_message=current_message,
                suppress_answer_reveal_on_generate=bool(
                    runtime_metadata.get("suppress_answer_reveal_on_generate")
                ),
            ),
        ]
        runtime_instruction = "\n\n".join(
            part for part in runtime_instruction_parts if str(part or "").strip()
        )
        fast_path = await self._maybe_run_exact_rag_fast_path(
            current_message=current_message,
            history=history,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            runtime_instruction=runtime_instruction,
            runtime_metadata=runtime_metadata,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )
        if fast_path is not None:
            final_content, all_msgs, fast_path_metadata = fast_path
            final_content = normalize_anchor_terms_in_response(
                user_message=current_message,
                response=final_content,
            ) or final_content
            if all_msgs:
                all_msgs[-1]["content"] = final_content
            self._save_turn(session, all_msgs, 1 + len(history))
            session.metadata["last_exact_fast_path"] = bool(
                fast_path_metadata and fast_path_metadata.get("authority_applied")
            )
            self.sessions.save(session)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
            logger.info("Fast-path exact authority response to {}:{}: {}", msg.channel, msg.sender_id, preview)
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content,
                metadata=msg.metadata or {},
            )

        initial_messages = self.context.build_messages(
            history=history,
            current_message=current_message,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
            runtime_instruction=runtime_instruction,
        )
        initial_messages = await self._maybe_prefetch_grounded_rag(
            initial_messages=initial_messages,
            current_message=current_message,
            runtime_metadata=runtime_metadata,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )
        if response_mode == "fast":
            final_content, all_msgs = await self._run_fast_policy_once(
                initial_messages,
                runtime_metadata=runtime_metadata,
                on_content_delta=on_content_delta,
            )
            if final_content is None:
                final_content = "I've completed processing but have no response to give."
            final_content = normalize_anchor_terms_in_response(
                user_message=current_message,
                response=final_content,
            ) or final_content
            if all_msgs:
                all_msgs[-1]["content"] = final_content
            self._save_turn(session, all_msgs, 1 + len(history))
            session.metadata["last_exact_fast_path"] = False
            self.sessions.save(session)
            await self.memory_consolidator.maybe_consolidate_by_tokens(session)
            preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
            logger.info("Fast policy response to {}:{}: {}", msg.channel, msg.sender_id, preview)
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content,
                metadata=msg.metadata or {},
            )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages,
            runtime_metadata=runtime_metadata,
            on_progress=on_progress or _bus_progress,
            on_content_delta=on_content_delta,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
            allow_exact_authority_override=prepare_exact_question_probe(current_message) is not None,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        final_content = normalize_anchor_terms_in_response(
            user_message=current_message,
            response=final_content,
        ) or final_content
        if all_msgs:
            all_msgs[-1]["content"] = final_content

        self._save_turn(session, all_msgs, 1 + len(history))
        session.metadata["last_exact_fast_path"] = False
        self.sessions.save(session)
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str):
                    stripped = ContextBuilder.strip_runtime_prefixes(content)
                    if stripped is None:
                        continue
                    entry["content"] = stripped
                if isinstance(content, list):
                    filtered = []
                    for c in content:
                        if c.get("type") == "text" and isinstance(c.get("text"), str):
                            text = c["text"]
                            if text.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG) or text.startswith(
                                ContextBuilder._RUNTIME_MODE_TAG,
                            ):
                                continue  # Strip runtime metadata/control from multimodal messages
                        if (c.get("type") == "image_url"
                                and c.get("image_url", {}).get("url", "").startswith("data:image/")):
                            filtered.append({"type": "text", "text": "[image]"})
                        else:
                            filtered.append(c)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content,
            metadata=metadata or {},
        )
        response = await self._process_message(
            msg,
            session_key=session_key,
            on_progress=on_progress,
            on_content_delta=on_content_delta,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )
        return response.content if response else ""
