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
from deeptutor.services.question_followup import (
    apply_followup_action_to_context,
    detect_answer_reveal_preference,
    detect_requested_question_type,
    interpret_question_followup_action,
    looks_like_question_followup,
    resolve_submission_attempt,
)
from deeptutor.services.semantic_router import (
    build_active_object_from_question_context,
    normalize_active_object,
    question_context_from_active_object,
    resolve_question_semantic_routing,
    turn_semantic_decision_route,
)
from deeptutor.services.runtime_env import env_flag
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request

logger = logging.getLogger(__name__)


def _coerce_flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    return raw not in {"0", "false", "no", "off"}


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

        cap_name = await self._select_capability(context)
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

    async def _select_capability(self, context: UnifiedContext) -> str:
        routing_user_message = self._routing_user_message(context)
        if context.active_capability:
            return context.active_capability

        semantic_router_enabled = self._semantic_router_enabled(context)
        semantic_router_shadow_mode = self._semantic_router_shadow_mode(context)

        if semantic_router_shadow_mode:
            shadow_decision = await self._preview_turn_semantic_decision(context, routing_user_message)
            context.metadata["semantic_router_mode"] = "shadow"
            context.metadata["semantic_router_shadow_decision"] = shadow_decision or {}
            context.metadata["semantic_router_shadow_route"] = (
                turn_semantic_decision_route(shadow_decision) or ""
            )
            cap_name = self._select_legacy_capability(context, routing_user_message)
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name

        if semantic_router_enabled:
            turn_decision = await self._resolve_turn_semantic_decision(context, routing_user_message)
            context.metadata["semantic_router_mode"] = "primary"
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            semantic_route = turn_semantic_decision_route(turn_decision)
            if semantic_route == "deep_question":
                next_action = str((turn_decision or {}).get("next_action") or "").strip()
                if next_action == "route_to_grading":
                    self._prepare_question_submission_context(
                        context,
                        context.metadata.get("question_followup_action"),
                    )
                elif next_action == "route_to_generation":
                    self._prepare_practice_request_context(context, routing_user_message)
                context.metadata["semantic_router_selected_capability"] = "deep_question"
                return "deep_question"
            if semantic_route == "chat":
                context.metadata["semantic_router_selected_capability"] = "chat"
                return "chat"

        context.metadata["semantic_router_mode"] = "disabled"
        context.metadata["semantic_router_shadow_decision"] = {}
        context.metadata["semantic_router_shadow_route"] = ""
        cap_name = self._select_legacy_capability(context, routing_user_message)
        context.metadata["semantic_router_selected_capability"] = cap_name
        return cap_name

    @staticmethod
    def _semantic_router_enabled(context: UnifiedContext) -> bool:
        override = _coerce_flag(context.config_overrides.get("semantic_router_enabled"))
        if override is not None:
            return override
        return env_flag("DEEPTUTOR_SEMANTIC_ROUTER_ENABLED", default=True)

    @staticmethod
    def _semantic_router_shadow_mode(context: UnifiedContext) -> bool:
        override = _coerce_flag(context.config_overrides.get("semantic_router_shadow_mode"))
        if override is not None:
            return override
        return env_flag("DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE", default=False)

    @staticmethod
    def _routing_user_message(context: UnifiedContext) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        raw = str(metadata.get("raw_user_message") or "").strip()
        return raw or str(context.user_message or "").strip()

    async def _resolve_turn_semantic_decision(
        self,
        context: UnifiedContext,
        message: str,
    ) -> dict[str, Any] | None:
        routing = await self._resolve_semantic_routing(context, message, metadata=context.metadata)
        if routing.active_object is not None:
            context.metadata["active_object"] = routing.active_object
        if routing.question_context is not None:
            context.metadata["question_followup_context"] = routing.question_context
        context.metadata["turn_semantic_decision"] = routing.turn_semantic_decision
        context.metadata["suspended_object_stack"] = routing.suspended_object_stack
        if routing.followup_action:
            context.metadata["question_followup_action"] = routing.followup_action
        return routing.turn_semantic_decision

    async def _preview_turn_semantic_decision(
        self,
        context: UnifiedContext,
        message: str,
    ) -> dict[str, Any] | None:
        preview_metadata = dict(context.metadata or {})
        routing = await self._resolve_semantic_routing(context, message, metadata=preview_metadata)
        return routing.turn_semantic_decision

    async def _resolve_semantic_routing(
        self,
        context: UnifiedContext,
        message: str,
        *,
        metadata: dict[str, Any],
    ):
        active_object = normalize_active_object(metadata.get("active_object")) or (
            build_active_object_from_question_context(
                metadata.get("question_followup_context"),
                source_turn_id=str(metadata.get("turn_id") or "").strip(),
            )
        )
        if active_object is not None:
            metadata["active_object"] = active_object

        return await resolve_question_semantic_routing(
            user_message=message,
            metadata=metadata,
            history_context=str(metadata.get("conversation_context_text", "") or "").strip(),
            interpret_followup_action=lambda message_text, question_context: interpret_question_followup_action(
                message_text,
                question_context,
                history_context=str(
                    metadata.get("conversation_context_text", "") or ""
                ).strip(),
            ),
            resolve_submission_attempt=resolve_submission_attempt,
            looks_like_question_followup=looks_like_question_followup,
            looks_like_practice_generation_request=looks_like_practice_generation_request,
        )

    def _select_legacy_capability(self, context: UnifiedContext, message: str) -> str:
        if looks_like_practice_generation_request(message):
            self._prepare_practice_request_context(context, message)
            return "deep_question"

        if self._looks_like_question_submission(context, message):
            self._prepare_question_submission_context(context)
            return "deep_question"

        if self._looks_like_question_followup(context, message):
            return "deep_question"

        return "chat"

    def _looks_like_question_submission(self, context: UnifiedContext, message: str) -> bool:
        qctx = question_context_from_active_object(context.metadata.get("active_object")) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        if not isinstance(qctx, dict) or not qctx.get("question"):
            return False
        _target_context, submission = resolve_submission_attempt(message, qctx)
        return submission is not None

    def _prepare_question_submission_context(
        self,
        context: UnifiedContext,
        action: dict[str, Any] | None = None,
    ) -> None:
        active_object = normalize_active_object(context.metadata.get("active_object"))
        qctx = question_context_from_active_object(active_object) or dict(
            context.metadata.get("question_followup_context", {}) or {}
        )
        action_context = apply_followup_action_to_context(qctx, action)
        if action_context:
            context.metadata["question_followup_context"] = action_context
            active_object = build_active_object_from_question_context(
                action_context,
                source_turn_id=str(context.metadata.get("turn_id") or "").strip(),
                previous_active_object=active_object,
            )
            if active_object is not None:
                context.metadata["active_object"] = active_object
            return

        target_context, submission = resolve_submission_attempt(context.user_message, qctx)
        if not target_context or not submission:
            return
        fallback_action = {
            "intent": "answer_questions",
            "answers": (
                submission.get("answers")
                if submission.get("kind") == "batch"
                else [
                    {
                        "index": 1,
                        "question_id": str(target_context.get("question_id") or "").strip(),
                        "user_answer": str(submission.get("answer") or "").strip(),
                    }
                ]
            ),
            "preserve_other_answers": False,
        }
        fallback_context = apply_followup_action_to_context(target_context, fallback_action)
        if fallback_context:
            context.metadata["question_followup_context"] = fallback_context
            active_object = build_active_object_from_question_context(
                fallback_context,
                source_turn_id=str(context.metadata.get("turn_id") or "").strip(),
                previous_active_object=active_object,
            )
            if active_object is not None:
                context.metadata["active_object"] = active_object

    def _looks_like_question_followup(self, context: UnifiedContext, message: str) -> bool:
        qctx = question_context_from_active_object(context.metadata.get("active_object")) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        if not isinstance(qctx, dict) or not qctx.get("question"):
            return False
        return looks_like_question_followup(message, qctx)

    @staticmethod
    def _preferred_question_type(message: str) -> str:
        return detect_requested_question_type(message)[0]

    @staticmethod
    def _infer_question_count(message: str) -> int:
        text = str(message or "").strip().lower()
        if not text:
            return 1
        digit_match = re.search(r"(\d{1,2})\s*(?:道|题|个题目|个小题)", text)
        if digit_match:
            return max(1, min(50, int(digit_match.group(1))))
        zh_num_map = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        zh_match = re.search(r"([一二两三四五六七八九十])\s*(?:道|题|个题目|个小题)", text)
        if zh_match:
            return zh_num_map.get(zh_match.group(1), 1)
        if "几道" in text or "几题" in text:
            return 3
        return 1

    def _prepare_practice_request_context(self, context: UnifiedContext, message: str) -> None:
        if not isinstance(context.config_overrides, dict):
            context.config_overrides = {}
        interaction_hints = (
            context.metadata.get("interaction_hints", {})
            if isinstance(context.metadata, dict)
            else {}
        )
        preferred_question_type = ""
        if isinstance(interaction_hints, dict):
            preferred_question_type = str(
                interaction_hints.get("preferred_question_type", "") or ""
            ).strip().lower()
        explicit_question_type, is_explicit_type = detect_requested_question_type(
            message
        )
        reveal_preference = detect_answer_reveal_preference(message)
        context.config_overrides.setdefault("mode", "custom")
        context.config_overrides.setdefault("topic", message)
        context.config_overrides.setdefault(
            "num_questions",
            self._infer_question_count(message),
        )
        context.config_overrides.setdefault(
            "question_type",
            explicit_question_type
            if is_explicit_type
            else preferred_question_type or explicit_question_type,
        )
        context.config_overrides["force_generate_questions"] = True
        suppress_answer_reveal = True
        if isinstance(interaction_hints, dict):
            suppress_answer_reveal = bool(
                interaction_hints.get("suppress_answer_reveal_on_generate", True)
            )
        if reveal_preference is not None:
            suppress_answer_reveal = not reveal_preference
        context.config_overrides.setdefault("reveal_answers", not suppress_answer_reveal)
        context.config_overrides.setdefault("reveal_explanations", not suppress_answer_reveal)

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
