"""
Chat Orchestrator
=================

Unified entry point that routes user messages to the appropriate capability.
All consumers (CLI, WebSocket, SDK) call the orchestrator.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from types import SimpleNamespace
from typing import Any, AsyncIterator
import uuid

from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.events.event_bus import Event, EventType, get_event_bus
from deeptutor.runtime.registry.capability_registry import get_capability_registry
from deeptutor.runtime.registry.tool_registry import get_tool_registry
from deeptutor.services.question_followup import (
    apply_followup_action_to_context,
    batch_answer_action_for_numbered_single,
    detect_answer_reveal_preference,
    detect_requested_question_type,
    followup_action_route,
    interpret_question_followup_action,
    looks_like_question_followup,
    reset_question_submission_state,
    resolve_submission_attempt,
)
from deeptutor.services.question_lifecycle_skills import (
    build_question_lifecycle_clarification_context,
    looks_like_free_text_mcq_answer_request,
    resolve_question_lifecycle_scene_decision,
    select_question_lifecycle_skill_names,
)
from deeptutor.services.runtime_env import env_flag
from deeptutor.services.semantic_router import (
    build_active_object_from_question_context,
    build_turn_semantic_decision,
    is_unresolved_switch_followup,
    normalize_active_object,
    question_context_from_active_object,
    resolve_question_semantic_routing,
    turn_semantic_decision_route,
)
from deeptutor.tutorbot.teaching_modes import (
    classify_practice_strategy,
    looks_like_practice_generation_request,
)

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


def _coerce_positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    raw = str(value or "").strip()
    if not raw or not re.fullmatch(r"\d+", raw):
        return default
    parsed = int(raw)
    return parsed if parsed > 0 else default


def _should_use_lightweight_generation(
    message: str,
    reveal_preference: bool | None,
) -> bool:
    if reveal_preference is False:
        return True
    text = str(message or "").strip().lower()
    if not text:
        return False
    if not looks_like_practice_generation_request(text):
        return False
    delayed_feedback_patterns = (
        r"(做完|答完|写完).{0,12}(再|然后).{0,12}(分析|讲解|解析|批改)",
        r"(先|先给我).{0,20}(出题|出\d{0,2}道题|出[一二两三四五六七八九十几]+道题|小题).{0,20}(再|然后).{0,12}(分析|讲解|解析|批改)",
    )
    return any(re.search(pattern, text) for pattern in delayed_feedback_patterns)


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
            available = self._cap_registry.list_capabilities()
            raise RuntimeError(f"Unknown capability: {cap_name}. Available: {available}")

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
            completed = False
            try:
                await capability.run(context, bus)
                completed = True
            except Exception as exc:
                logger.error("Capability %s failed: %s", cap_name, exc, exc_info=True)
                raise
            finally:
                if completed:
                    with contextlib.suppress(BaseException):
                        await bus.emit(StreamEvent(type=StreamEventType.DONE, source=cap_name))
                with contextlib.suppress(BaseException):
                    await bus.close()

        stream = bus.subscribe()
        task = asyncio.create_task(_run())
        # plan §Phase 0 Step 0.2 (A4): cancellation propagation.
        # 同时覆盖 turn timeout / client disconnect / normal completion 三条路径，
        # 防止 parent turn deadline 之后内部 capability task 继续烧 LLM。
        try:
            cancel_grace_s = float(os.getenv("DEEPTUTOR_CANCEL_GRACE_S", "2.0") or 2.0)
        except (TypeError, ValueError):
            cancel_grace_s = 2.0

        try:
            async for event in stream:
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            # Outer consumer cancelled or disconnected — propagate to capability task
            # so RAG / LLM calls stop instead of running into ghost completions.
            if not task.done():
                task.cancel()
                with contextlib.suppress(BaseException):
                    await asyncio.wait_for(task, timeout=cancel_grace_s)
            with contextlib.suppress(BaseException):
                await bus.close()
            if isinstance(context.metadata, dict):
                context.metadata["turn_cancel_propagated"] = True
            raise
        else:
            await task
        finally:
            with contextlib.suppress(BaseException):
                await self._publish_completion(context, cap_name)

    async def _select_capability(self, context: UnifiedContext) -> str:
        routing_user_message = self._routing_user_message(context)
        # Additive telemetry (no routing effect): capture the routing message
        # in-place so semantic-router decision analysis never needs the
        # unreliable session+time join. See semantic_router_telemetry.
        context.metadata["semantic_router_captured_input"] = routing_user_message
        if not self._question_lifecycle_decision_authority_enabled(context):
            context.metadata["question_lifecycle_decision_authority_disabled"] = True
            return await self._select_capability_after_lifecycle(context, routing_user_message)

        lifecycle_decision = await resolve_question_lifecycle_scene_decision(
            SimpleNamespace(user_message=routing_user_message, metadata=context.metadata)
        )
        self._record_lifecycle_decision(context, lifecycle_decision)
        lifecycle_scene = lifecycle_decision.scene
        if (
            lifecycle_scene is None
            and self._has_active_lifecycle_context(context)
            and looks_like_free_text_mcq_answer_request(routing_user_message)
        ):
            self._suspend_active_lifecycle_context(context)
            cap_name = self._default_chat_capability(context)
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                "embedded_mcq_answer_request_replaces_active_object"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name
        if lifecycle_scene == "question_review":
            if self._has_active_lifecycle_context(context):
                turn_decision = await self._resolve_turn_semantic_decision(context, routing_user_message)
                semantic_route = turn_semantic_decision_route(turn_decision)
                next_action = str((turn_decision or {}).get("next_action") or "").strip()
                # Context-continuity invariant (contracts/turn.md §跨能力上下文连续性):
                # an unresolved switch/back-reference (learner asked about an EARLIER
                # object we can't resolve to a structured target) depends on prior
                # context that lives in conversation_context_text. Route it to the
                # context-continuous main LLM (TutorBot) to answer from history — never
                # into deep_question's structured switch resolver, which fail-closes
                # ("can't locate that question") = amnesia.
                if is_unresolved_switch_followup(turn_decision):
                    cap_name = self._default_chat_capability(context)
                    context.metadata["semantic_router_mode"] = "question_lifecycle"
                    context.metadata["semantic_router_mode_reason"] = (
                        f"{lifecycle_decision.source}_unresolved_switch_to_context_continuity"
                    )
                    context.metadata["semantic_router_shadow_decision"] = {}
                    context.metadata["semantic_router_shadow_route"] = ""
                    context.metadata["semantic_router_selected_capability"] = cap_name
                    return cap_name
                if semantic_route == "chat" and next_action == "ask_clarifying_question":
                    cap_name = self._default_chat_capability(context)
                    context.metadata["semantic_router_mode"] = "question_lifecycle"
                    context.metadata["semantic_router_mode_reason"] = (
                        f"{lifecycle_decision.source}_question_review_active_object_{next_action}"
                    )
                    context.metadata["semantic_router_shadow_decision"] = {}
                    context.metadata["semantic_router_shadow_route"] = ""
                    context.metadata["semantic_router_selected_capability"] = cap_name
                    return cap_name
                if semantic_route == "deep_question" and next_action in {
                    "route_to_followup_explainer",
                    "route_to_grading",
                }:
                    if next_action == "route_to_grading":
                        self._prepare_question_submission_context(
                            context,
                            context.metadata.get("question_followup_action"),
                        )
                    context.metadata["semantic_router_mode"] = "question_lifecycle"
                    context.metadata["semantic_router_mode_reason"] = (
                        f"{lifecycle_decision.source}_question_review_active_object_{next_action}"
                    )
                    context.metadata["semantic_router_shadow_decision"] = {}
                    context.metadata["semantic_router_shadow_route"] = ""
                    context.metadata["semantic_router_selected_capability"] = "deep_question"
                    return "deep_question"
            if self._should_replace_active_context_for_question_review(
                context,
                routing_user_message,
            ):
                self._suspend_active_lifecycle_context(context)
            self._prepare_free_text_question_review_context(context, routing_user_message)
            # Context-Continuity 真闭包 task #12 step 2 part 2: the no-active-object free-text
            # question_review path routes to deep_question WITHOUT a canonical
            # turn_semantic_decision, so deep_question used to fabricate one
            # (_default_turn_semantic_decision) — a second-authority bypass the step-2
            # observation caught in production. Supply the canonical decision here (the
            # routing authority) instead. The decision-bearing fields match what
            # deep_question fabricated for this path (relation=ask_about_active_object,
            # next_action=route_to_followup_explainer, allowed_patch=no_state_change), so
            # behavior is preserved; deep_question now READS it and no longer fabricates.
            if not context.metadata.get("turn_semantic_decision"):
                context.metadata["turn_semantic_decision"] = build_turn_semantic_decision(
                    relation_to_active_object="ask_about_active_object",
                    next_action="route_to_followup_explainer",
                    allowed_patch="no_state_change",
                    confidence=1.0,
                    reason="orchestrator question_review(无 active object)分支提供 canonical "
                    "decision,避免 deep_question 伪造兜底(turn.md §硬约束 24)。",
                    active_object=context.metadata.get("active_object"),
                )
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                f"{lifecycle_decision.source}_question_review"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = "deep_question"
            return "deep_question"
        if lifecycle_scene == "practice_generation":
            turn_decision = None
            if self._has_active_lifecycle_context(context):
                turn_decision = await self._resolve_turn_semantic_decision(context, routing_user_message)
                semantic_route = turn_semantic_decision_route(turn_decision)
                next_action = str((turn_decision or {}).get("next_action") or "").strip()
                # Context-continuity invariant: unresolved switch/back-reference → the
                # context-continuous main LLM (TutorBot, from conversation_context_text),
                # never the deep_question structured switch resolver (fail-closed amnesia).
                if is_unresolved_switch_followup(turn_decision):
                    cap_name = self._default_chat_capability(context)
                    context.metadata["semantic_router_mode"] = "question_lifecycle"
                    context.metadata["semantic_router_mode_reason"] = (
                        f"{lifecycle_decision.source}_unresolved_switch_to_context_continuity"
                    )
                    context.metadata["semantic_router_shadow_decision"] = {}
                    context.metadata["semantic_router_shadow_route"] = ""
                    context.metadata["semantic_router_selected_capability"] = cap_name
                    return cap_name
                if semantic_route == "chat" and next_action == "ask_clarifying_question":
                    cap_name = self._default_chat_capability(context)
                    context.metadata["semantic_router_mode"] = "question_lifecycle"
                    context.metadata["semantic_router_mode_reason"] = (
                        f"{lifecycle_decision.source}_practice_generation_active_object_{next_action}"
                    )
                    context.metadata["semantic_router_shadow_decision"] = {}
                    context.metadata["semantic_router_shadow_route"] = ""
                    context.metadata["semantic_router_selected_capability"] = cap_name
                    return cap_name
                if semantic_route == "deep_question" and next_action in {
                    "route_to_followup_explainer",
                    "route_to_grading",
                }:
                    if next_action == "route_to_grading":
                        self._prepare_question_submission_context(
                            context,
                            context.metadata.get("question_followup_action"),
                        )
                    context.metadata["semantic_router_mode"] = "question_lifecycle"
                    context.metadata["semantic_router_mode_reason"] = (
                        f"{lifecycle_decision.source}_practice_generation_active_object_{next_action}"
                    )
                    context.metadata["semantic_router_shadow_decision"] = {}
                    context.metadata["semantic_router_shadow_route"] = ""
                    context.metadata["semantic_router_selected_capability"] = "deep_question"
                    return "deep_question"
            self._prepare_practice_request_context(context, routing_user_message)
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                f"{lifecycle_decision.source}_practice_generation"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = "deep_question"
            return "deep_question"
        if lifecycle_scene == "case_grading":
            cap_name = self._case_grading_capability(context)
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                f"{lifecycle_decision.source}_case_grading"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name
        if lifecycle_scene in {"learning_evidence_story", "study_assistant", "learning_support", "exam_catalog_query"}:
            cap_name = self._default_chat_capability(context)
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                f"{lifecycle_decision.source}_{lifecycle_scene}"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name
        if lifecycle_decision.needs_clarification:
            cap_name = self._default_chat_capability(context)
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                lifecycle_decision.business_gate_result or "needs_clarification"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name
        return await self._select_capability_after_lifecycle(context, routing_user_message)

    async def _select_capability_after_lifecycle(
        self,
        context: UnifiedContext,
        routing_user_message: str,
    ) -> str:
        # 2026-06-17 root-cause fix（"做完题没给答案"）：MCQ 作答提交轮（lifecycle
        # scene=mcq_grading）若被一个非判分能力 preselect（微信默认 active_capability
        # =tutorbot），原本会在此 bypass 直接返回 tutorbot，且 _prepare_preselected_
        # capability_context 只为 deep_question 准备提交上下文 → tutorbot 拿不到作答、
        # 判分永不触发、用户"做完题没给答案"。这里让该作答轮 fall through 到下方
        # 判分能力路由（semantic router → deep_question route_to_grading），保证判分入口
        # 必达；score authority 不变（鲁班 V1）。case_grading 已有独立分支不经过此处。
        lifecycle_scene = str(context.metadata.get("question_lifecycle_scene") or "").strip()
        preselected_capability = str(context.active_capability or "").strip().lower()
        mcq_grading_bypass = (
            lifecycle_scene == "mcq_grading" and preselected_capability != "deep_question"
        )
        action = context.metadata.get("question_followup_action")
        turn_decision = context.metadata.get("turn_semantic_decision")
        is_generation_continuation = followup_action_route(action) == "practice_generation" or (
            isinstance(turn_decision, dict)
            and str(turn_decision.get("next_action") or "").strip() == "route_to_generation"
        )
        if (
            preselected_capability == "deep_question"
            and not lifecycle_scene
            and self._has_active_lifecycle_context(context)
            and not is_generation_continuation
            and not self._looks_like_question_submission(context, routing_user_message)
            and not self._looks_like_question_followup(context, routing_user_message)
            and not looks_like_practice_generation_request(routing_user_message)
            and not self._looks_like_free_text_question_review_request(
                context,
                routing_user_message,
            )
        ):
            cap_name = self._default_chat_capability(context)
            context.metadata["semantic_router_mode"] = "question_lifecycle"
            context.metadata["semantic_router_mode_reason"] = (
                "deep_question_preselect_demoted_non_question_turn"
            )
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name
        if context.active_capability and not mcq_grading_bypass:
            self._prepare_preselected_capability_context(context, routing_user_message)
            context.metadata.setdefault("semantic_router_mode", "preselected")
            context.metadata.setdefault("semantic_router_mode_reason", "preselected_capability")
            context.metadata.setdefault(
                "semantic_router_selected_capability",
                str(context.active_capability or "").strip(),
            )
            return context.active_capability
        if mcq_grading_bypass:
            context.metadata["mcq_grading_preselect_bypass_recovered"] = preselected_capability

        semantic_router_enabled = self._semantic_router_enabled(context)
        semantic_router_shadow_mode = self._semantic_router_shadow_mode(context)
        semantic_router_scope = self._semantic_router_scope(context)
        semantic_router_scope_match = self._semantic_router_scope_match(
            context,
            routing_user_message,
            semantic_router_scope,
        )
        context.metadata["semantic_router_scope"] = semantic_router_scope
        context.metadata["semantic_router_scope_match"] = semantic_router_scope_match

        if semantic_router_shadow_mode and semantic_router_scope_match:
            shadow_decision = await self._preview_turn_semantic_decision(context, routing_user_message)
            context.metadata["semantic_router_mode"] = "shadow"
            context.metadata["semantic_router_mode_reason"] = "shadow_compare_only"
            context.metadata["semantic_router_shadow_decision"] = shadow_decision or {}
            context.metadata["semantic_router_shadow_route"] = (
                turn_semantic_decision_route(shadow_decision) or ""
            )
            cap_name = self._select_legacy_capability(context, routing_user_message)
            context.metadata["semantic_router_selected_capability"] = cap_name
            return cap_name

        if semantic_router_enabled and semantic_router_scope_match:
            turn_decision = await self._resolve_turn_semantic_decision(context, routing_user_message)
            context.metadata["semantic_router_mode"] = "primary"
            context.metadata["semantic_router_mode_reason"] = "semantic_router_primary"
            context.metadata["semantic_router_shadow_decision"] = {}
            context.metadata["semantic_router_shadow_route"] = ""
            semantic_route = turn_semantic_decision_route(turn_decision)
            # Context-continuity invariant: an unresolved switch/back-reference depends on
            # prior context (conversation_context_text) → route to the context-continuous
            # main LLM, never the deep_question structured switch resolver (fail-closed).
            if is_unresolved_switch_followup(turn_decision):
                cap_name = self._default_chat_capability(context)
                context.metadata["semantic_router_mode_reason"] = (
                    "unresolved_switch_to_context_continuity"
                )
                context.metadata["semantic_router_selected_capability"] = cap_name
                return cap_name
            if semantic_route == "deep_question":
                next_action = str((turn_decision or {}).get("next_action") or "").strip()
                if next_action == "route_to_grading":
                    self._prepare_question_submission_context(
                        context,
                        context.metadata.get("question_followup_action"),
                    )
                elif next_action == "route_to_generation":
                    self._prepare_practice_request_context(
                        context,
                        self._practice_generation_message(context, routing_user_message),
                    )
                context.metadata["semantic_router_selected_capability"] = "deep_question"
                return "deep_question"
            if semantic_route == "chat":
                cap_name = self._default_chat_capability(context)
                context.metadata["semantic_router_selected_capability"] = cap_name
                return cap_name

        context.metadata["semantic_router_mode"] = "disabled"
        context.metadata["semantic_router_mode_reason"] = (
            "scope_excluded"
            if not semantic_router_scope_match and (semantic_router_enabled or semantic_router_shadow_mode)
            else "flag_disabled"
        )
        context.metadata["semantic_router_shadow_decision"] = {}
        context.metadata["semantic_router_shadow_route"] = ""
        cap_name = self._select_legacy_capability(context, routing_user_message)
        context.metadata["semantic_router_selected_capability"] = cap_name
        return cap_name

    @staticmethod
    def _question_lifecycle_decision_authority_enabled(context: UnifiedContext) -> bool:
        override = _coerce_flag(
            context.config_overrides.get("question_lifecycle_decision_authority")
        )
        if override is not None:
            return override
        return env_flag("QUESTION_LIFECYCLE_DECISION_AUTHORITY", default=True)

    def _prepare_preselected_capability_context(
        self,
        context: UnifiedContext,
        message: str,
    ) -> None:
        capability = str(context.active_capability or "").strip().lower()
        if capability != "deep_question":
            return
        action = context.metadata.get("question_followup_action")
        if followup_action_route(action) == "practice_generation":
            self._prepare_practice_request_context(
                context,
                self._practice_generation_message(context, message),
            )
            return
        if (
            followup_action_route(action) == "submission"
            or self._looks_like_question_submission(context, message)
        ):
            self._prepare_question_submission_context(context, action)
            return
        if looks_like_practice_generation_request(message):
            self._prepare_practice_request_context(context, message)

    @staticmethod
    def _record_lifecycle_decision(
        context: UnifiedContext,
        decision: Any,
    ) -> None:
        scene = decision.scene
        selected_skill_names = list(decision.selected_skill_names or ())
        decision_payload = {
            "scene": scene,
            "decision_source": decision.source,
            "scene_confidence": decision.confidence,
            "reason": decision.reason,
            "required_anchor_status": decision.required_anchor_status,
            "exact_question_blocked_reason": decision.exact_question_blocked_reason,
            "selected_skill_names": selected_skill_names,
            "needs_clarification": decision.needs_clarification,
            "llm_scene_candidate": (
                dict(decision.llm_scene_candidate)
                if isinstance(decision.llm_scene_candidate, dict)
                else None
            ),
            "business_gate_result": decision.business_gate_result,
        }
        context.metadata["question_lifecycle_decision"] = decision_payload
        context.metadata["decision_source"] = decision.source
        context.metadata["scene_confidence"] = decision.confidence
        context.metadata["required_anchor_status"] = decision.required_anchor_status
        context.metadata["selected_skill_names"] = selected_skill_names
        context.metadata["llm_scene_candidate"] = decision_payload["llm_scene_candidate"]
        context.metadata["business_gate_result"] = decision.business_gate_result
        context.metadata["question_lifecycle_scene"] = scene
        context.metadata["question_lifecycle_scene_source"] = decision.source
        context.metadata["question_lifecycle_scene_confidence"] = decision.confidence
        context.metadata["question_lifecycle_scene_reason"] = decision.reason
        if scene is not None:
            context.metadata["question_lifecycle_skill_names"] = selected_skill_names
        else:
            context.metadata.setdefault("question_lifecycle_skill_names", [])
        if decision.exact_question_blocked_reason:
            context.metadata["exact_question_blocked_reason"] = decision.exact_question_blocked_reason
            clarification_context = build_question_lifecycle_clarification_context(
                context.user_message,
                decision.exact_question_blocked_reason,
            )
            if clarification_context:
                previous_active_object = context.metadata.get("active_object")
                if (
                    isinstance(previous_active_object, dict)
                    and str(previous_active_object.get("object_type") or "") != "question_lifecycle_clarification"
                ):
                    existing_stack = context.metadata.get("suspended_object_stack")
                    suspended_stack = list(existing_stack) if isinstance(existing_stack, list) else []
                    suspended_stack.append(dict(previous_active_object))
                    context.metadata["suspended_object_stack"] = suspended_stack
                context.metadata["active_object"] = clarification_context
                snapshot = clarification_context.get("state_snapshot")
                if isinstance(snapshot, dict):
                    context.metadata["question_lifecycle_clarification"] = dict(snapshot)
        else:
            context.metadata.pop("exact_question_blocked_reason", None)
        trace_meta = context.metadata.setdefault("trace_metadata", {})
        if isinstance(trace_meta, dict):
            trace_meta["question_lifecycle_decision"] = dict(decision_payload)
            trace_meta["decision_source"] = decision.source
            trace_meta["scene_confidence"] = decision.confidence
            trace_meta["required_anchor_status"] = decision.required_anchor_status
            trace_meta["selected_skill_names"] = list(selected_skill_names)
            trace_meta["llm_scene_candidate"] = decision_payload["llm_scene_candidate"]
            trace_meta["business_gate_result"] = decision.business_gate_result
            trace_meta["question_lifecycle_scene"] = scene
            trace_meta["question_lifecycle_scene_source"] = decision.source
            trace_meta["question_lifecycle_scene_confidence"] = decision.confidence
            trace_meta["question_lifecycle_scene_reason"] = decision.reason
            if decision.exact_question_blocked_reason:
                trace_meta["exact_question_blocked_reason"] = decision.exact_question_blocked_reason
            else:
                trace_meta.pop("exact_question_blocked_reason", None)

    @staticmethod
    def _has_active_lifecycle_context(context: UnifiedContext) -> bool:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        return bool(metadata.get("active_object") or metadata.get("question_followup_context"))

    def _should_replace_active_context_for_question_review(
        self,
        context: UnifiedContext,
        message: str,
    ) -> bool:
        if not self._has_active_lifecycle_context(context):
            return True
        if looks_like_free_text_mcq_answer_request(message):
            return True
        if self._looks_like_question_submission(context, message):
            return False
        if self._looks_like_current_question_followup(message):
            return False
        return True

    @staticmethod
    def _looks_like_current_question_followup(message: str) -> bool:
        text = str(message or "").strip()
        if not text:
            return False
        current_markers = (
            "这题",
            "这道题",
            "本题",
            "上一题",
            "刚才这题",
            "刚刚这题",
            "当前题",
            "为什么",
            "错在哪",
            "哪里错",
        )
        return any(marker in text for marker in current_markers)

    @staticmethod
    def _suspend_active_lifecycle_context(context: UnifiedContext) -> None:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        existing_stack = metadata.get("suspended_object_stack")
        suspended_stack = list(existing_stack) if isinstance(existing_stack, list) else []
        active_object = normalize_active_object(metadata.get("active_object"))
        if active_object is not None:
            suspended_stack.append(active_object)
        metadata.pop("active_object", None)
        metadata.pop("question_followup_context", None)
        metadata.pop("question_followup_action", None)
        metadata.pop("turn_semantic_decision", None)
        metadata["suspended_object_stack"] = suspended_stack
        metadata["question_review_replaces_active_object"] = True

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
    def _semantic_router_scope(context: UnifiedContext) -> str:
        override = str(context.config_overrides.get("semantic_router_scope") or "").strip().lower()
        value = override or str(os.getenv("DEEPTUTOR_SEMANTIC_ROUTER_SCOPE") or "").strip().lower()
        if value in {"question_only", "question_and_guide", "all"}:
            return value
        return "all"

    @staticmethod
    def _routing_user_message(context: UnifiedContext) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        raw = str(metadata.get("raw_user_message") or "").strip()
        return raw or str(context.user_message or "").strip()

    @staticmethod
    def _practice_generation_message(context: UnifiedContext, fallback: str) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        action = metadata.get("question_followup_action")
        if isinstance(action, dict):
            topic = str(action.get("topic") or action.get("topic_hint") or "").strip()
            if topic:
                return topic
        return fallback

    @staticmethod
    def _default_chat_capability(context: UnifiedContext) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        bot_id = str(context.config_overrides.get("bot_id") or metadata.get("bot_id") or "").strip()
        if bot_id:
            return "tutorbot"
        return "chat"

    def _case_grading_capability(self, context: UnifiedContext) -> str:
        active = str(context.active_capability or "").strip()
        if active in {"deep_question", "tutorbot"}:
            return active
        default_capability = self._default_chat_capability(context)
        if default_capability == "tutorbot":
            return "tutorbot"
        return "deep_question"

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
        if self._looks_like_question_submission(context, message):
            self._prepare_question_submission_context(context)
            return "deep_question"

        if looks_like_practice_generation_request(message):
            self._prepare_practice_request_context(context, message)
            return "deep_question"

        if self._looks_like_free_text_question_review_request(context, message):
            self._prepare_free_text_question_review_context(context, message)
            return "deep_question"

        if self._looks_like_question_followup(context, message):
            return "deep_question"

        return self._default_chat_capability(context)

    def _semantic_router_scope_match(
        self,
        context: UnifiedContext,
        message: str,
        scope: str,
    ) -> bool:
        if scope == "all":
            return True
        domain = self._semantic_router_target_domain(context, message)
        if scope == "question_only":
            return domain == "question"
        if scope == "question_and_guide":
            return domain in {"question", "guide"}
        return True

    def _semantic_router_target_domain(self, context: UnifiedContext, message: str) -> str:
        active_object = normalize_active_object(context.metadata.get("active_object"))
        object_type = str((active_object or {}).get("object_type") or "").strip()
        if object_type in {"question_set", "single_question"}:
            return "question"
        if object_type in {"guide_page", "study_plan", "lesson_topic"}:
            return "guide"
        if object_type == "open_chat_topic":
            return "general"
        if looks_like_practice_generation_request(message):
            return "question"
        if self._looks_like_question_submission(context, message):
            return "question"
        if self._looks_like_question_followup(context, message):
            return "question"
        return "general"

    def _looks_like_question_submission(self, context: UnifiedContext, message: str) -> bool:
        qctx = question_context_from_active_object(context.metadata.get("active_object")) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        if not isinstance(qctx, dict) or not qctx.get("question"):
            return False
        _target_context, submission = resolve_submission_attempt(message, qctx)
        return submission is not None and submission.get("kind") != "ambiguous"

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
            target_context, submission = resolve_submission_attempt(context.user_message, qctx)
            if target_context and submission and submission.get("kind") == "batch":
                fallback_context = apply_followup_action_to_context(
                    target_context,
                    {
                        "intent": "answer_questions",
                        "answers": submission.get("answers"),
                        "preserve_other_answers": False,
                    },
                )
                unmatched_refs = (
                    fallback_context.get("unmatched_answer_refs")
                    if isinstance(fallback_context, dict)
                    else None
                )
                if unmatched_refs:
                    action_context["unmatched_answer_refs"] = unmatched_refs
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
        if not target_context or not submission or submission.get("kind") == "ambiguous":
            return
        # object-continuity (E8 SEV-1, 2026-06-21): grade a numbered single submission
        # WITHIN the full batch set so the other questions survive (single chokepoint =
        # `batch_answer_action_for_numbered_single`; the primary fix is at turn-start in
        # turn_runtime, this is the deep_question-path defense-in-depth on the same helper).
        # Returns None for single-question contexts / out-of-range → keep existing path.
        batch_action = batch_answer_action_for_numbered_single(submission, qctx)
        if batch_action is not None:
            grade_target = qctx
            fallback_action = batch_action
        else:
            grade_target = target_context
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
        fallback_context = apply_followup_action_to_context(grade_target, fallback_action)
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

    def _looks_like_free_text_question_review_request(
        self,
        context: UnifiedContext,
        message: str,
    ) -> bool:
        qctx = question_context_from_active_object(context.metadata.get("active_object")) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        if isinstance(qctx, dict) and qctx.get("question"):
            return False
        return context.metadata.get("question_lifecycle_scene") == "question_review"

    def _prepare_free_text_question_review_context(
        self,
        context: UnifiedContext,
        message: str,
    ) -> None:
        if not isinstance(context.config_overrides, dict):
            context.config_overrides = {}
        context.config_overrides.setdefault("mode", "custom")
        context.config_overrides.setdefault("topic", message)
        context.config_overrides.setdefault("num_questions", 1)
        context.config_overrides.setdefault("question_type", self._preferred_question_type(message))
        skill_names = list(select_question_lifecycle_skill_names("question_review"))
        context.metadata["question_lifecycle_skill_names"] = skill_names
        trace_meta = context.metadata.setdefault("trace_metadata", {})
        if isinstance(trace_meta, dict):
            trace_meta["question_lifecycle_skill_names"] = list(skill_names)
            trace_meta["skill_stack"] = list(skill_names)
            trace_meta["review_mode"] = "question_review"

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
        qctx = question_context_from_active_object(context.metadata.get("active_object")) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        if isinstance(qctx, dict) and qctx.get("question"):
            reset_context = reset_question_submission_state(qctx) or qctx
            context.metadata["question_followup_context"] = reset_context
            active_object = build_active_object_from_question_context(
                reset_context,
                source_turn_id=str(context.metadata.get("turn_id") or "").strip(),
                previous_active_object=normalize_active_object(context.metadata.get("active_object")),
            )
            if active_object is not None:
                context.metadata["active_object"] = active_object
            context.metadata.setdefault(
                "question_followup_action",
                {
                    "intent": "generate_more_questions",
                    "confidence": 1.0,
                    "answers": [],
                    "reason": "question lifecycle routed this turn to practice generation",
                },
            )
            if not context.metadata.get("turn_semantic_decision"):
                decision_active_object = normalize_active_object(
                    context.metadata.get("active_object")
                )
                context.metadata["turn_semantic_decision"] = build_turn_semantic_decision(
                    relation_to_active_object=(
                        "continue_same_learning_flow"
                        if decision_active_object is not None
                        else "switch_to_new_object"
                    ),
                    next_action="route_to_generation",
                    allowed_patch="set_active_object",
                    confidence=1.0,
                    reason="question lifecycle routed this turn to practice generation",
                    active_object=decision_active_object,
                )
                context.metadata["turn_semantic_decision_writer_chain"] = [
                    "orchestrator_practice_context"
                ]
        skill_names = list(select_question_lifecycle_skill_names("practice_generation"))
        context.metadata["question_lifecycle_skill_names"] = skill_names
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
        inferred_question_count = self._infer_question_count(message)
        learning_training_intent = context.config_overrides.get("learning_training_intent")
        learning_prompt_intent = context.config_overrides.get("learning_prompt_intent")
        if not isinstance(learning_training_intent, dict) and isinstance(learning_prompt_intent, dict):
            # Mobile/home dashboard prompts initially arrive as learning_prompt_intent
            # because capability selection has not happened yet. Once this turn is
            # canonically routed to practice generation, deep_question is the
            # training authority and should consume the same intent.
            learning_training_intent = dict(learning_prompt_intent)
            context.config_overrides["learning_training_intent"] = learning_training_intent
        intent_question_count = (
            _coerce_positive_int(learning_training_intent.get("question_count"), default=0)
            if isinstance(learning_training_intent, dict)
            else 0
        )
        resolved_question_type = (
            explicit_question_type
            if is_explicit_type
            else preferred_question_type or explicit_question_type
        )
        if not str(context.config_overrides.get("mode") or "").strip():
            context.config_overrides["mode"] = "custom"
        if not str(context.config_overrides.get("topic") or "").strip():
            context.config_overrides["topic"] = message
        current_question_count = _coerce_positive_int(
            context.config_overrides.get("num_questions"),
            default=1,
        )
        if intent_question_count:
            context.config_overrides["num_questions"] = intent_question_count
        elif current_question_count == 1 and inferred_question_count != 1:
            context.config_overrides["num_questions"] = inferred_question_count
        else:
            context.config_overrides.setdefault("num_questions", inferred_question_count)
        if resolved_question_type and not str(context.config_overrides.get("question_type") or "").strip():
            context.config_overrides["question_type"] = resolved_question_type
        context.config_overrides["force_generate_questions"] = True
        suppress_answer_reveal = True
        if isinstance(interaction_hints, dict):
            suppress_answer_reveal = bool(
                interaction_hints.get("suppress_answer_reveal_on_generate", True)
            )
        if reveal_preference is not None:
            suppress_answer_reveal = not reveal_preference
            context.config_overrides["reveal_answers"] = reveal_preference
            context.config_overrides["reveal_explanations"] = reveal_preference
        else:
            context.config_overrides.setdefault("reveal_answers", not suppress_answer_reveal)
            context.config_overrides.setdefault("reveal_explanations", not suppress_answer_reveal)
        # plan §Phase 1 Step 1.1 (A2/A3): classify_practice_strategy 是 lightweight 的
        # 单一规约函数；上限由原本的 `<= 3` 放宽到 `<= 5`（详见 plan §2.2）。
        effective_count = _coerce_positive_int(
            context.config_overrides.get("num_questions"),
            default=inferred_question_count or 1,
        )
        effective_mode = str(context.config_overrides.get("mode") or "").strip().lower()
        active_object_present = bool(
            isinstance(context.metadata, dict)
            and context.metadata.get("active_object")
        )
        strategy = classify_practice_strategy(
            message=message,
            reveal_preference=reveal_preference,
            mode=effective_mode,
            num_questions=effective_count,
            has_active_object=active_object_present,
        )
        context.config_overrides.setdefault(
            "lightweight_generation", strategy == "lightweight"
        )
        # plan §Phase 0 Step 0.3 (B3): single-writer trace fields.
        # 只有 orchestrator._prepare_practice_request_context 写 strategy / question_count，
        # coordinator 等下游模块只读，不再独立写入避免双源不一致。
        if isinstance(context.metadata, dict):
            trace_meta = context.metadata.setdefault("trace_metadata", {})
            if isinstance(trace_meta, dict):
                trace_meta["question_lifecycle_skill_names"] = list(skill_names)
                trace_meta["skill_stack"] = list(skill_names)
                trace_meta["practice_generation.strategy"] = strategy
                trace_meta["practice_generation.question_count"] = int(effective_count)

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
