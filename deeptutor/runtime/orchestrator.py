"""
Chat Orchestrator
=================

Unified entry point that routes user messages to the appropriate capability.
All consumers (CLI, WebSocket, SDK) call the orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any, AsyncIterator

from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.events.event_bus import Event, EventType, get_event_bus
from deeptutor.runtime.registry.capability_registry import get_capability_registry
from deeptutor.runtime.registry.tool_registry import get_tool_registry

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    """
    Routes a ``UnifiedContext`` to the correct capability, manages
    the ``StreamBus`` lifecycle, and publishes completion events.
    """

    def __init__(self) -> None:
        self._cap_registry = get_capability_registry()
        self._tool_registry = get_tool_registry()

    async def handle(self, context: UnifiedContext) -> AsyncIterator[StreamEvent]:
        """
        Execute a single user turn and yield streaming events.

        If ``context.active_capability`` is set, the corresponding capability
        handles the turn. Otherwise, the default ``chat`` capability is used.
        """
        if not context.session_id:
            context.session_id = str(uuid.uuid4())

        cap_name = self._select_capability(context)
        capability = self._cap_registry.get(cap_name)

        if capability is None:
            bus = StreamBus()
            await bus.error(
                f"Unknown capability: {cap_name}. "
                f"Available: {self._cap_registry.list_capabilities()}",
                source="orchestrator",
            )
            await bus.close()
            async for event in bus.subscribe():
                yield event
            return

        yield StreamEvent(
            type=StreamEventType.SESSION,
            source="orchestrator",
            metadata={
                "session_id": context.session_id,
                "turn_id": str(context.metadata.get("turn_id", "")),
            },
        )

        bus = StreamBus()

        async def _run() -> None:
            try:
                await capability.run(context, bus)
            except Exception as exc:
                logger.error("Capability %s failed: %s", cap_name, exc, exc_info=True)
                await bus.error(str(exc), source=cap_name)
            finally:
                await bus.emit(StreamEvent(type=StreamEventType.DONE, source=cap_name))
                await bus.close()

        stream = bus.subscribe()
        task = asyncio.create_task(_run())

        async for event in stream:
            yield event

        await task
        await self._publish_completion(context, cap_name)

    def _select_capability(self, context: UnifiedContext) -> str:
        if context.active_capability:
            return context.active_capability

        if self._looks_like_question_submission(context):
            self._prepare_question_submission_context(context)
            return "deep_question"

        if self._looks_like_practice_request(context.user_message):
            self._prepare_practice_request_context(context)
            return "deep_question"

        return "chat"

    @staticmethod
    def _looks_like_practice_request(message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        positive_markers = (
            "出题", "出一道", "来一道", "来一题", "考我", "练习", "刷题", "测我",
            "quiz me", "test me", "give me a question", "give me one question",
        )
        negative_markers = ("不要出题", "别出题", "不想做题")
        if any(marker in text for marker in negative_markers):
            return False
        return any(marker in text for marker in positive_markers)

    @staticmethod
    def _extract_choice_submission(user_message: str) -> str | None:
        raw = str(user_message or "").strip().upper()
        if not raw:
            return None
        compact = re.sub(r"\s+", "", raw)
        patterns = [
            r"^(?:我选|我觉得选|选|答案是|答案|就是|选项)?([ABCD])$",
            r"^(?:我手滑选了|我看错选了|我粗心选了)([ABCD])$",
            r"^(?:OPTION|ANSWER)[:：]?([ABCD])$",
        ]
        for pattern in patterns:
            match = re.fullmatch(pattern, compact)
            if match:
                return match.group(1)
        if re.fullmatch(r"[ABCD]", compact):
            return compact
        return None

    def _looks_like_question_submission(self, context: UnifiedContext) -> bool:
        qctx = context.metadata.get("question_followup_context", {}) or {}
        if not isinstance(qctx, dict) or not qctx.get("question"):
            return False
        question_type = str(qctx.get("question_type", "") or "").strip().lower()
        if question_type != "choice":
            return False
        return self._extract_choice_submission(context.user_message) is not None

    def _prepare_question_submission_context(self, context: UnifiedContext) -> None:
        qctx = dict(context.metadata.get("question_followup_context", {}) or {})
        answer = self._extract_choice_submission(context.user_message)
        if not answer:
            return
        correct_answer = str(qctx.get("correct_answer", "") or "").strip().upper()
        qctx["user_answer"] = answer
        qctx["is_correct"] = bool(correct_answer) and answer == correct_answer
        context.metadata["question_followup_context"] = qctx

    @staticmethod
    def _preferred_question_type(message: str) -> str:
        text = str(message or "").strip().lower()
        if any(marker in text for marker in ("编程", "代码", "伪代码", "algorithm", "coding", "code")):
            return "coding"
        if any(marker in text for marker in ("简答", "论述", "案例", "问答", "written", "essay")):
            return "written"
        return "choice"

    def _prepare_practice_request_context(self, context: UnifiedContext) -> None:
        if not isinstance(context.config_overrides, dict):
            context.config_overrides = {}
        context.config_overrides.setdefault("mode", "custom")
        context.config_overrides.setdefault("topic", context.user_message)
        context.config_overrides.setdefault("num_questions", 1)
        context.config_overrides.setdefault(
            "question_type",
            self._preferred_question_type(context.user_message),
        )
        context.config_overrides.setdefault("reveal_answers", False)
        context.config_overrides.setdefault("reveal_explanations", False)

    async def _publish_completion(self, context: UnifiedContext, cap_name: str) -> None:
        """Publish CAPABILITY_COMPLETE to the global EventBus."""
        try:
            bus = get_event_bus()
            await bus.publish(
                Event(
                    type=EventType.CAPABILITY_COMPLETE,
                    task_id=str(context.metadata.get("turn_id") or context.session_id),
                    user_input=context.user_message,
                    agent_output="",
                    metadata={
                        "capability": cap_name,
                        "session_id": context.session_id,
                        "turn_id": str(context.metadata.get("turn_id", "")),
                    },
                )
            )
        except Exception:
            logger.debug("EventBus publish failed (may not be running)", exc_info=True)

    def list_tools(self) -> list[str]:
        return self._tool_registry.list_tools()

    def list_capabilities(self) -> list[str]:
        return self._cap_registry.list_capabilities()

    def get_capability_manifests(self) -> list[dict[str, Any]]:
        return self._cap_registry.get_manifests()

    def get_tool_schemas(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        return self._tool_registry.build_openai_schemas(names)
