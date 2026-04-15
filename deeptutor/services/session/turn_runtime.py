"""
Turn-level runtime manager for unified chat streaming.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.contracts.tutorbot_profiles import resolve_tutorbot_knowledge_chain_profile
from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.path_service import get_path_service
from deeptutor.services.question_followup import normalize_question_followup_context
from deeptutor.services.session.sqlite_store import (
    SQLiteSessionStore,
    build_user_owner_key,
    get_sqlite_session_store,
)

logger = logging.getLogger(__name__)
observability = get_langfuse_observability()
_MINI_PROGRAM_CAPTURE_COST = 20
_CAPTURED_ASSISTANT_CALL_KINDS = {"llm_final_response", "exact_authority_response"}


def _should_capture_assistant_content(event: StreamEvent) -> bool:
    if event.type != StreamEventType.CONTENT:
        return False
    metadata = event.metadata or {}
    call_id = metadata.get("call_id")
    if not call_id:
        return True
    return str(metadata.get("call_kind") or "").strip() in _CAPTURED_ASSISTANT_CALL_KINDS


def _clip_text(value: str, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _extract_followup_question_context(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("followup_question_context", None)
    normalized = normalize_question_followup_context(raw)
    if not normalized:
        return None
    normalized["knowledge_context"] = _clip_text(
        str(normalized.get("knowledge_context", "") or "").strip()
    )
    return normalized


def _extract_interaction_hints(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("interaction_hints", None)
    if not isinstance(raw, dict):
        return None

    profile = str(raw.get("profile", "") or "").strip().lower()
    priorities = raw.get("priorities")
    if not isinstance(priorities, list):
        priorities = []
    normalized_priorities = [
        str(item or "").strip().lower()
        for item in priorities
        if str(item or "").strip()
    ]

    preferred_question_type = str(raw.get("preferred_question_type", "") or "").strip().lower()
    if preferred_question_type not in {"choice", "written", "coding"}:
        preferred_question_type = ""

    hints = {
        "profile": profile,
        "scene": str(raw.get("scene", "") or "").strip().lower(),
        "preferred_question_type": preferred_question_type,
        "suppress_answer_reveal_on_generate": bool(
            raw.get("suppress_answer_reveal_on_generate", False)
        ),
        "prefer_question_context_grading": bool(
            raw.get("prefer_question_context_grading", False)
        ),
        "prefer_concept_teaching_slots": bool(
            raw.get("prefer_concept_teaching_slots", False)
        ),
        "allow_general_chat_fallback": raw.get("allow_general_chat_fallback", True) is not False,
        "priorities": normalized_priorities,
    }

    if profile == "mini_tutor":
        hints["scene"] = hints["scene"] or "wechat_mini_program_learning"
        hints["preferred_question_type"] = hints["preferred_question_type"] or "choice"
        hints["suppress_answer_reveal_on_generate"] = True
        hints["prefer_question_context_grading"] = True
        hints["prefer_concept_teaching_slots"] = True
        if not hints["priorities"]:
            hints["priorities"] = ["practice", "grading", "explain", "review", "plan"]

    meaningful = any(
        [
            hints["profile"],
            hints["scene"],
            hints["preferred_question_type"],
            hints["priorities"],
            hints["suppress_answer_reveal_on_generate"],
            hints["prefer_question_context_grading"],
            hints["prefer_concept_teaching_slots"],
            hints["allow_general_chat_fallback"] is False,
        ]
    )
    return hints if meaningful else None


def _infer_chat_mode_from_interaction_hints(
    hints: dict[str, Any] | None,
) -> str | None:
    if not isinstance(hints, dict):
        return None
    mode = str(hints.get("teaching_mode", "") or "").strip().lower()
    return mode if mode in {"fast", "deep", "smart"} else None


def _extract_persist_user_message(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return True
    raw = config.pop("_persist_user_message", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"false", "0", "no"}
    return bool(raw)


def _extract_billing_context(config: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("billing_context", None)
    if not isinstance(raw, dict):
        return None
    source = str(raw.get("source", "") or "").strip().lower()
    user_id = str(raw.get("user_id", "") or "").strip()
    if not source or not user_id:
        return None
    return {"source": source, "user_id": user_id}


def _normalize_name_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        value = str(item or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
    return normalized


def _resolve_tutorbot_runtime_defaults(
    *,
    bot_id: str,
    interaction_profile: str,
    tools: list[str] | None,
    knowledge_bases: list[str] | None,
) -> dict[str, Any]:
    resolved_tools = _normalize_name_list(tools)
    resolved_knowledge_bases = _normalize_name_list(knowledge_bases)
    profile = resolve_tutorbot_knowledge_chain_profile(
        bot_id=bot_id,
        interaction_profile=interaction_profile,
    )
    if profile is None:
        return {
            "tools": resolved_tools,
            "knowledge_bases": resolved_knowledge_bases,
            "knowledge_chain_profile": "",
            "knowledge_chain_source": "",
        }

    injected = False
    if not resolved_knowledge_bases:
        resolved_knowledge_bases = _normalize_name_list(profile.default_knowledge_bases)
        injected = bool(resolved_knowledge_bases)
    if resolved_knowledge_bases:
        existing_tools = {item.lower() for item in resolved_tools}
        for tool_name in _normalize_name_list(profile.default_tools):
            lowered = tool_name.lower()
            if lowered in existing_tools:
                continue
            resolved_tools.append(tool_name)
            existing_tools.add(lowered)
            injected = True
    return {
        "tools": resolved_tools,
        "knowledge_bases": resolved_knowledge_bases,
        "knowledge_chain_profile": profile.id,
        "knowledge_chain_source": "tutorbot_runtime_defaults" if injected else "explicit",
    }


def _format_followup_question_context(context: dict[str, Any], language: str = "en") -> str:
    options = context.get("options") or {}
    option_lines = []
    if isinstance(options, dict) and options:
        for key, value in options.items():
            if value:
                option_lines.append(f"{key}. {value}")
    correctness = context.get("is_correct")
    correctness_text = (
        "correct"
        if correctness is True
        else "incorrect"
        if correctness is False
        else "unknown"
    )

    if str(language or "en").lower().startswith("zh"):
        lines = [
            "你正在处理一道测验题的后续追问。",
            "下面是本题上下文，请在后续回答中优先围绕这道题进行解释、纠错、延展和追问。",
            "如果用户提出超出本题的内容，也可以正常回答，但要保持和本题的连续性。",
            "",
            "[Question Follow-up Context]",
            f"Question ID: {context.get('question_id') or '(none)'}",
            f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
            f"Question type: {context.get('question_type') or '(none)'}",
            f"Difficulty: {context.get('difficulty') or '(none)'}",
            f"Concentration: {context.get('concentration') or '(none)'}",
            "",
            "Question:",
            context.get("question") or "(none)",
        ]
        if option_lines:
            lines.extend(["", "Options:", *option_lines])
        lines.extend(
            [
                "",
                f"User answer: {context.get('user_answer') or '(not provided)'}",
                f"User result: {correctness_text}",
                f"Reference answer: {context.get('correct_answer') or '(none)'}",
                "",
                "Explanation:",
                context.get("explanation") or "(none)",
            ]
        )
        if context.get("knowledge_context"):
            lines.extend(
                [
                    "",
                    "Knowledge context:",
                    context["knowledge_context"],
                ]
            )
        return "\n".join(lines).strip()

    lines = [
        "You are handling follow-up questions about a single quiz item.",
        "Use the question context below as the primary grounding for future turns in this session.",
        "If the user asks something broader, you may answer normally, but maintain continuity with this quiz item.",
        "",
        "[Question Follow-up Context]",
        f"Question ID: {context.get('question_id') or '(none)'}",
        f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
        f"Question type: {context.get('question_type') or '(none)'}",
        f"Difficulty: {context.get('difficulty') or '(none)'}",
        f"Concentration: {context.get('concentration') or '(none)'}",
        "",
        "Question:",
        context.get("question") or "(none)",
    ]
    if option_lines:
        lines.extend(["", "Options:", *option_lines])
    lines.extend(
        [
            "",
            f"User answer: {context.get('user_answer') or '(not provided)'}",
            f"User result: {correctness_text}",
            f"Reference answer: {context.get('correct_answer') or '(none)'}",
            "",
            "Explanation:",
            context.get("explanation") or "(none)",
        ]
    )
    if context.get("knowledge_context"):
        lines.extend(
            [
                "",
                "Knowledge context:",
                context["knowledge_context"],
            ]
        )
    return "\n".join(lines).strip()


def _format_interaction_hints(hints: dict[str, Any], language: str = "en") -> str:
    profile = str(hints.get("profile", "") or "").strip()
    preferred_question_type = str(hints.get("preferred_question_type", "") or "").strip()

    if str(language or "en").lower().startswith("zh"):
        lines = [
            "你正在一个学习型产品场景中工作。下面是交互策略提示，把它当作类似技能说明的软约束，不要机械套模板：",
        ]
        if profile == "mini_tutor":
            lines.append("- 当前场景偏向微信小程序的学练闭环。")
        if hints.get("priorities"):
            lines.append(
                f"- 优先关注这些交互目标：{', '.join(str(item) for item in hints['priorities'])}。"
            )
        if preferred_question_type:
            lines.append(f"- 用户要求出题但未指定题型时，优先出 `{preferred_question_type}`。")
        if hints.get("suppress_answer_reveal_on_generate"):
            lines.append("- 出题时本回合优先只出题，不主动泄露答案或解析。")
        if hints.get("prefer_question_context_grading"):
            lines.append("- 若已有题目上下文，短答案如 A/B/C/D、我选B，应优先结合题目上下文理解为作答提交。")
        if hints.get("prefer_concept_teaching_slots"):
            lines.append("- 遇到知识讲解且本轮用了知识召回时，优先覆盖核心结论、踩分点、易错点；记忆口诀和心得仅在确有帮助时补充。")
        if hints.get("allow_general_chat_fallback"):
            lines.append("- 如果用户明显转入闲聊、产品问答或开放问题，正常切回通用智能助理模式。")
        else:
            lines.append("- 优先保持学习辅导语境，除非用户明确要求切换话题。")
        return "\n".join(lines).strip()

    lines = [
        "You are operating in a learning-product scenario. Treat the notes below like skill guidance rather than a rigid workflow:",
    ]
    if profile == "mini_tutor":
        lines.append("- The current scene is closer to a WeChat mini-program learning loop.")
    if hints.get("priorities"):
        lines.append(f"- Prioritize these interaction goals: {', '.join(str(item) for item in hints['priorities'])}.")
    if preferred_question_type:
        lines.append(f"- If the learner asks for practice without specifying type, prefer `{preferred_question_type}` questions.")
    if hints.get("suppress_answer_reveal_on_generate"):
        lines.append("- When generating practice, prefer giving only the question first without revealing the answer or explanation.")
    if hints.get("prefer_question_context_grading"):
        lines.append("- If quiz context exists, short replies like A/B/C/D or 'I choose B' should be interpreted as answer submissions when plausible.")
    if hints.get("prefer_concept_teaching_slots"):
        lines.append("- For concept teaching, try to cover conclusion, scoring points, pitfalls, memory hooks, and exam strategy.")
    if hints.get("allow_general_chat_fallback"):
        lines.append("- If the user clearly switches to open-ended chat, product questions, or general conversation, fall back naturally to general assistant behavior.")
    else:
        lines.append("- Stay in tutoring mode unless the user explicitly asks to switch topics.")
    return "\n".join(lines).strip()


@dataclass
class _LiveSubscriber:
    queue: asyncio.Queue[dict[str, Any]]


@dataclass
class _TurnExecution:
    turn_id: str
    session_id: str
    capability: str
    payload: dict[str, Any]
    task: asyncio.Task[None] | None = None
    subscribers: list[_LiveSubscriber] = field(default_factory=list)
    persistence_degraded: bool = False


class TurnRuntimeManager:
    """Run one turn in the background and multiplex persisted/live events."""

    def __init__(self, store: SQLiteSessionStore | None = None) -> None:
        self.store = store or get_sqlite_session_store()
        self._lock = asyncio.Lock()
        self._executions: dict[str, _TurnExecution] = {}
        self._volatile_question_contexts: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _is_persistence_error(exc: Exception) -> bool:
        return isinstance(exc, (sqlite3.Error, OSError))

    def _mark_persistence_degraded(
        self,
        execution: _TurnExecution | None,
        operation: str,
        exc: Exception,
    ) -> None:
        if execution is not None:
            already_degraded = execution.persistence_degraded
            execution.persistence_degraded = True
            log_method = logger.debug if already_degraded else logger.warning
            log_method(
                "Persistence degraded for turn %s during %s: %s",
                execution.turn_id,
                operation,
                exc,
                exc_info=not already_degraded,
            )
            return
        logger.warning("Persistence degraded during %s: %s", operation, exc, exc_info=True)

    async def _safe_store_call(
        self,
        execution: _TurnExecution | None,
        operation: str,
        fn,
        *args,
        default: Any = None,
        swallow_value_error: bool = False,
        **kwargs,
    ) -> Any:
        try:
            return await fn(*args, **kwargs)
        except ValueError as exc:
            if not swallow_value_error:
                raise
            logger.warning("Store call skipped during %s: %s", operation, exc)
            return default
        except Exception as exc:
            if not self._is_persistence_error(exc):
                raise
            self._mark_persistence_degraded(execution, operation, exc)
            return default

    async def _resolve_billing_context(
        self,
        session_id: str,
        request_config: dict[str, Any] | None,
    ) -> dict[str, str] | None:
        billing_context = _extract_billing_context(request_config)
        if billing_context is not None:
            return billing_context
        session = await self._safe_store_call(
            None,
            "get_session_for_billing_context",
            self.store.get_session,
            session_id,
            default=None,
        )
        if session is None:
            return None
        preferences = session.get("preferences") or {}
        source = str(preferences.get("source", "") or "").strip().lower()
        user_id = str(preferences.get("user_id", "") or "").strip()
        if not source or not user_id:
            return None
        return {"source": source, "user_id": user_id}

    async def _resolve_interaction_hints(
        self,
        session_id: str,
        request_config: dict[str, Any] | None,
        *,
        execution: _TurnExecution | None = None,
    ) -> dict[str, Any] | None:
        interaction_hints = _extract_interaction_hints(request_config)
        if interaction_hints is not None:
            return interaction_hints
        session = await self._safe_store_call(
            execution,
            "get_session_for_interaction_hints",
            self.store.get_session,
            session_id,
            default=None,
        )
        if not isinstance(session, dict):
            return None
        preferences = session.get("preferences") if isinstance(session.get("preferences"), dict) else {}
        return _extract_interaction_hints({"interaction_hints": preferences.get("interaction_hints")})

    async def _recover_orphaned_running_turns(
        self,
        session_id: str,
        *,
        reason: str,
    ) -> None:
        active_turns = await self._safe_store_call(
            None,
            "list_active_turns",
            self.store.list_active_turns,
            session_id,
            default=[],
        )
        for turn in active_turns or []:
            turn_id = str(turn.get("id") or turn.get("turn_id") or "").strip()
            if not turn_id:
                continue
            async with self._lock:
                execution = self._executions.get(turn_id)
            if execution is not None and execution.task is not None and not execution.task.done():
                continue
            await self._safe_store_call(
                None,
                "recover_orphaned_turn",
                self.store.update_turn_status,
                turn_id,
                "failed",
                reason,
                default=False,
            )

    def _capture_mobile_points(
        self,
        billing_context: dict[str, str] | None,
        assistant_content: str,
    ) -> None:
        if not billing_context:
            return
        if billing_context.get("source") != "wx_miniprogram":
            return
        user_id = str(billing_context.get("user_id", "") or "").strip()
        if not user_id or not str(assistant_content or "").strip():
            return
        try:
            from deeptutor.services.member_console import get_member_console_service

            member_service = get_member_console_service()
            member_service.capture_points(
                user_id=user_id,
                amount=_MINI_PROGRAM_CAPTURE_COST,
                reason="capture",
            )
        except Exception:
            logger.warning("Failed to capture points for user %s", user_id, exc_info=True)

    def _record_mobile_learning(
        self,
        billing_context: dict[str, str] | None,
        raw_user_content: str,
        assistant_content: str,
    ) -> None:
        if not billing_context:
            return
        if billing_context.get("source") != "wx_miniprogram":
            return
        user_id = str(billing_context.get("user_id", "") or "").strip()
        if not user_id or not str(assistant_content or "").strip():
            return
        try:
            from deeptutor.services.member_console import get_member_console_service

            member_service = get_member_console_service()
            member_service.record_chat_learning(
                user_id=user_id,
                query=raw_user_content,
                assistant_content=assistant_content,
            )
        except Exception:
            logger.warning("Failed to record learning activity for user %s", user_id, exc_info=True)

    async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        requested_capability = str(payload.get("capability") or "").strip() or None
        capability = requested_capability or "chat"
        raw_config = dict(payload.get("config", {}) or {})
        explicit_chat_mode = "chat_mode" in raw_config
        runtime_only_keys = (
            "_persist_user_message",
            "followup_question_context",
            "interaction_hints",
            "billing_context",
            "interaction_profile",
            "chat_mode_explicit",
        )
        runtime_only_config = {
            key: raw_config.pop(key)
            for key in runtime_only_keys
            if key in raw_config
        }
        runtime_interaction_hints = _extract_interaction_hints(
            {"interaction_hints": runtime_only_config.get("interaction_hints")}
        )
        try:
            from deeptutor.capabilities.request_contracts import validate_capability_config

            validated_public_config = validate_capability_config(capability, raw_config)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if capability == "chat" and not explicit_chat_mode:
            hinted_chat_mode = _infer_chat_mode_from_interaction_hints(runtime_interaction_hints)
            if hinted_chat_mode == "smart":
                validated_public_config = {
                    **validated_public_config,
                    "chat_mode": "smart",
                }
        bot_id = str(validated_public_config.get("bot_id") or "").strip()
        interaction_profile = str(
            runtime_only_config.get("interaction_profile")
            or (runtime_interaction_hints or {}).get("profile")
            or ""
        ).strip()
        knowledge_chain_defaults = _resolve_tutorbot_runtime_defaults(
            bot_id=bot_id,
            interaction_profile=interaction_profile,
            tools=payload.get("tools"),
            knowledge_bases=payload.get("knowledge_bases"),
        )
        payload = {
            **payload,
            "capability": requested_capability,
            "_chat_mode_explicit": explicit_chat_mode,
            "tools": knowledge_chain_defaults["tools"],
            "knowledge_bases": knowledge_chain_defaults["knowledge_bases"],
            "config": {
                **validated_public_config,
                **runtime_only_config,
                **(
                    {"knowledge_chain_profile": knowledge_chain_defaults["knowledge_chain_profile"]}
                    if knowledge_chain_defaults["knowledge_chain_profile"]
                    else {}
                ),
                **(
                    {"knowledge_chain_source": knowledge_chain_defaults["knowledge_chain_source"]}
                    if knowledge_chain_defaults["knowledge_chain_source"]
                    else {}
                ),
            },
        }
        billing_context = _extract_billing_context(dict(runtime_only_config)) or {}
        session = await self.store.ensure_session(
            payload.get("session_id"),
            owner_key=build_user_owner_key(billing_context.get("user_id")),
        )
        await self.store.update_session_preferences(
            session["id"],
            {
                "capability": capability,
                "chat_mode": (
                    validated_public_config.get("chat_mode", get_default_chat_mode())
                    if capability == "chat"
                    else raw_config.get("chat_mode", get_default_chat_mode())
                ),
                "tools": list(payload.get("tools") or []),
                "knowledge_bases": list(payload.get("knowledge_bases") or []),
                "language": str(payload.get("language") or "en"),
                **(
                    {"bot_id": str(validated_public_config.get("bot_id") or "").strip()}
                    if str(validated_public_config.get("bot_id") or "").strip()
                    else {}
                ),
                **({"interaction_hints": runtime_interaction_hints} if runtime_interaction_hints else {}),
                **(billing_context or {}),
                **(
                    {"knowledge_chain_profile": knowledge_chain_defaults["knowledge_chain_profile"]}
                    if knowledge_chain_defaults["knowledge_chain_profile"]
                    else {}
                ),
                **(
                    {"knowledge_chain_source": knowledge_chain_defaults["knowledge_chain_source"]}
                    if knowledge_chain_defaults["knowledge_chain_source"]
                    else {}
                ),
            },
        )
        await self._recover_orphaned_running_turns(
            session["id"],
            reason="Recovered orphaned running turn before starting a new turn",
        )
        try:
            turn = await self.store.create_turn(session["id"], capability=capability)
        except RuntimeError as exc:
            if "active turn" not in str(exc).lower():
                raise
            await self._recover_orphaned_running_turns(
                session["id"],
                reason="Recovered orphaned running turn after create_turn conflict",
            )
            turn = await self.store.create_turn(session["id"], capability=capability)
        execution = _TurnExecution(
            turn_id=turn["id"],
            session_id=session["id"],
            capability=capability,
            payload=dict(payload),
        )
        async with self._lock:
            self._executions[turn["id"]] = execution
        await self._persist_and_publish(
            execution,
            StreamEvent(
                type=StreamEventType.SESSION,
                source="turn_runtime",
                metadata={"session_id": session["id"], "turn_id": turn["id"]},
            ),
        )
        async with self._lock:
            execution.task = asyncio.create_task(self._run_turn(execution))
        return session, turn

    async def cancel_turn(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
        if execution is None or execution.task is None or execution.task.done():
            turn = await self._safe_store_call(
                None,
                "get_turn_for_cancel",
                self.store.get_turn,
                turn_id,
                default=None,
            )
            if turn is None or turn.get("status") != "running":
                return False
            updated = await self._safe_store_call(
                None,
                "cancel_turn_without_execution",
                self.store.update_turn_status,
                turn_id,
                "cancelled",
                "Turn cancelled",
                default=False,
            )
            return bool(updated)
        execution.task.cancel()
        return True

    async def subscribe_turn(
        self,
        turn_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        backlog = await self._safe_store_call(
            None,
            "get_turn_backlog",
            self.store.get_turn_events,
            turn_id,
            after_seq,
            default=[],
        )
        last_seq = after_seq
        for item in backlog:
            last_seq = max(last_seq, int(item.get("seq") or 0))
            yield item

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        subscriber = _LiveSubscriber(queue=queue)
        execution: _TurnExecution | None = None
        async with self._lock:
            execution = self._executions.get(turn_id)
            if execution is not None:
                execution.subscribers.append(subscriber)

        catchup = await self._safe_store_call(
            None,
            "get_turn_catchup",
            self.store.get_turn_events,
            turn_id,
            last_seq,
            default=[],
        )
        for item in catchup:
            seq = int(item.get("seq") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            if execution is None:
                yield item
            else:
                queue.put_nowait(item)

        turn = await self._safe_store_call(
            None,
            "get_turn_for_subscribe",
            self.store.get_turn,
            turn_id,
            default=None,
        )
        if execution is None:
            if turn is None or turn.get("status") != "running":
                return
            await self._recover_orphaned_running_turns(
                str(turn.get("session_id") or ""),
                reason=f"Recovered orphaned running turn during subscribe: {turn_id}",
            )
            return
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                seq = int(item.get("seq") or 0)
                if seq <= last_seq:
                    continue
                last_seq = seq
                yield item
        finally:
            async with self._lock:
                execution = self._executions.get(turn_id)
                if execution is not None:
                    execution.subscribers = [sub for sub in execution.subscribers if sub is not subscriber]

    async def subscribe_session(
        self,
        session_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        active_turn = await self._safe_store_call(
            None,
            "get_active_turn_for_session_subscribe",
            self.store.get_active_turn,
            session_id,
            default=None,
        )
        if active_turn is None:
            return
        async for item in self.subscribe_turn(active_turn["id"], after_seq=after_seq):
            yield item

    async def _run_turn(self, execution: _TurnExecution) -> None:
        payload = execution.payload
        session_id = execution.session_id
        capability_name = execution.capability
        turn_id = execution.turn_id
        attachments = []
        attachment_records = []
        assistant_events: list[dict[str, Any]] = []
        assistant_content = ""
        turn_observation: Any | None = None
        trace_metadata = {
            "session_id": session_id,
            "turn_id": turn_id,
            "capability": capability_name or "chat",
            "bot_id": str((payload.get("config", {}) or {}).get("bot_id", "") or "").strip(),
            "interaction_profile": str(
                (payload.get("config", {}) or {}).get("interaction_profile", "") or ""
            ).strip(),
        }

        try:
            from deeptutor.core.context import Attachment, UnifiedContext
            from deeptutor.runtime.orchestrator import ChatOrchestrator
            from deeptutor.agents.notebook import NotebookAnalysisAgent
            from deeptutor.services.memory import get_memory_service
            from deeptutor.services.notebook import notebook_manager
            from deeptutor.services.tutor_state import get_user_tutor_state_service
            from deeptutor.services.llm.config import get_llm_config
            from deeptutor.services.session.context_builder import ContextBuilder

            request_config = dict(payload.get("config", {}) or {})
            followup_question_context = _extract_followup_question_context(request_config)
            interaction_hints = await self._resolve_interaction_hints(
                session_id,
                request_config,
                execution=execution,
            )
            persist_user_message = _extract_persist_user_message(request_config)
            billing_context = await self._resolve_billing_context(session_id, request_config)
            if not followup_question_context:
                followup_question_context = await self._safe_store_call(
                    execution,
                    "get_active_question_context",
                    self.store.get_active_question_context,
                    session_id,
                    default=None,
                )
            if not followup_question_context:
                followup_question_context = self._volatile_question_contexts.get(session_id)
            if followup_question_context:
                self._volatile_question_contexts[session_id] = dict(followup_question_context)
            raw_user_content = str(payload.get("content", "") or "")
            notebook_references = payload.get("notebook_references", []) or []
            history_references = payload.get("history_references", []) or []
            notebook_context = ""
            history_context = ""
            trace_metadata["language"] = payload.get("language", "en")
            trace_metadata["chat_mode"] = str(
                request_config.get("chat_mode")
                or (interaction_hints or {}).get("teaching_mode")
                or ""
            ).strip()
            trace_metadata["source"] = str((billing_context or {}).get("source", "") or "").strip()
            if followup_question_context:
                trace_metadata["question_followup_context"] = dict(followup_question_context)
            user_id = str((billing_context or {}).get("user_id", "") or "").strip()
            if user_id:
                trace_metadata["user_id"] = user_id
            with observability.usage_scope(
                scope_id=turn_id,
                session_id=session_id,
                turn_id=turn_id,
                capability=capability_name or "chat",
            ), observability.start_observation(
                name=f"turn.{capability_name or 'chat'}",
                as_type="chain",
                input_payload={"content": raw_user_content},
                metadata=trace_metadata,
            ) as turn_observation:

                for item in payload.get("attachments", []):
                    record = {
                        "type": item.get("type", "file"),
                        "url": item.get("url", ""),
                        "base64": item.get("base64", ""),
                        "filename": item.get("filename", ""),
                        "mime_type": item.get("mime_type", ""),
                    }
                    attachment_records.append(record)
                    attachments.append(Attachment(**record))

                if followup_question_context:
                    existing_messages = await self._safe_store_call(
                        execution,
                        "get_messages_for_followup_bootstrap",
                        self.store.get_messages_for_context,
                        session_id,
                        default=[],
                    )
                    if not existing_messages:
                        await self._safe_store_call(
                            execution,
                            "add_followup_bootstrap_message",
                            self.store.add_message,
                            session_id=session_id,
                            role="system",
                            content=_format_followup_question_context(
                                followup_question_context,
                                language=str(payload.get("language", "en") or "en"),
                            ),
                            capability=capability_name or "chat",
                            default=None,
                        )

                llm_config = get_llm_config()
                builder = ContextBuilder(self.store)
                try:
                    history_result = await builder.build(
                        session_id=session_id,
                        llm_config=llm_config,
                        language=payload.get("language", "en"),
                        on_event=lambda event: self._persist_and_publish(execution, event),
                    )
                except Exception as exc:
                    if not self._is_persistence_error(exc):
                        raise
                    self._mark_persistence_degraded(execution, "build_context_history", exc)
                    history_result = SimpleNamespace(
                        conversation_history=[],
                        conversation_summary="",
                        context_text="",
                        token_count=0,
                        budget=0,
                    )
                memory_service = get_memory_service()
                tutor_state_service = get_user_tutor_state_service()
                user_id = str((billing_context or {}).get("user_id", "") or "").strip()
                if user_id:
                    try:
                        memory_context = tutor_state_service.build_context(
                            user_id=user_id,
                            language=str(payload.get("language", "en") or "en"),
                        )
                    except Exception:
                        logger.warning(
                            "Failed to build tutor state context for user %s",
                            user_id,
                            exc_info=True,
                        )
                        memory_context = memory_service.build_memory_context()
                else:
                    memory_context = memory_service.build_memory_context()

                if notebook_references:
                    referenced_records = notebook_manager.get_records_by_references(
                        notebook_references
                    )
                    if referenced_records:
                        analysis_agent = NotebookAnalysisAgent(
                            language=str(payload.get("language", "en") or "en")
                        )
                        notebook_context = await analysis_agent.analyze(
                            user_question=raw_user_content,
                            records=referenced_records,
                            emit=lambda event: self._persist_and_publish(execution, event),
                        )

                if history_references:
                    history_records: list[dict[str, Any]] = []
                    for session_ref in history_references:
                        history_session_id = str(session_ref or "").strip()
                        if not history_session_id:
                            continue

                        history_session = await self._safe_store_call(
                            execution,
                            "get_history_reference_session",
                            self.store.get_session,
                            history_session_id,
                            default=None,
                        )
                        if not history_session:
                            continue

                        history_messages = await self._safe_store_call(
                            execution,
                            "get_history_reference_messages",
                            self.store.get_messages_for_context,
                            history_session_id,
                            default=[],
                        )
                        transcript_lines = [
                            f"## {str(message.get('role', '')).title()}\n{message.get('content', '')}"
                            for message in history_messages
                            if str(message.get("content", "") or "").strip()
                        ]
                        if not transcript_lines:
                            continue

                        history_summary = str(
                            history_session.get("compressed_summary", "") or ""
                        ).strip()
                        if not history_summary:
                            history_summary = _clip_text(
                                " ".join(
                                    str(message.get("content", "") or "").strip()
                                    for message in history_messages[-4:]
                                    if str(message.get("content", "") or "").strip()
                                ),
                                limit=400,
                            )
                        if not history_summary:
                            history_summary = f"{len(history_messages)} messages"

                        history_records.append(
                            {
                                "id": history_session_id,
                                "notebook_id": "__history__",
                                "notebook_name": "History",
                                "title": str(
                                    history_session.get("title", "") or "Untitled session"
                                ),
                                "summary": history_summary,
                                "output": "\n\n".join(transcript_lines),
                                "metadata": {
                                    "session_id": history_session_id,
                                    "source": "history",
                                },
                            }
                        )

                    if history_records:
                        analysis_agent = NotebookAnalysisAgent(
                            language=str(payload.get("language", "en") or "en")
                        )
                        history_context = await analysis_agent.analyze(
                            user_question=raw_user_content,
                            records=history_records,
                            emit=lambda event: self._persist_and_publish(execution, event),
                        )
                        if not history_context.strip():
                            max_fallback_chars = 8000
                            parts: list[str] = []
                            total = 0
                            for record in history_records:
                                output = record.get("output")
                                if not output:
                                    continue
                                part = f"## Session: {record.get('title', 'Untitled')}\n{output}"
                                if total + len(part) > max_fallback_chars:
                                    remaining = max_fallback_chars - total
                                    if remaining > 100:
                                        parts.append(part[:remaining] + "\n...(truncated)")
                                    break
                                parts.append(part)
                                total += len(part)
                            history_context = "\n\n".join(parts)

                effective_user_message = raw_user_content
                context_parts: list[str] = []
                if notebook_context:
                    context_parts.append(f"[Notebook Context]\n{notebook_context}")
                if history_context:
                    context_parts.append(f"[History Context]\n{history_context}")
                if context_parts:
                    context_parts.append(f"[User Question]\n{raw_user_content}")
                    effective_user_message = "\n\n".join(context_parts)

                conversation_history = list(history_result.conversation_history)
                conversation_context_text = history_result.context_text

                if persist_user_message:
                    await self._safe_store_call(
                        execution,
                        "add_user_message",
                        self.store.add_message,
                        session_id=session_id,
                        role="user",
                        content=raw_user_content,
                        capability=capability_name,
                        attachments=attachment_records,
                        default=None,
                    )

                context = UnifiedContext(
                    session_id=session_id,
                    user_message=effective_user_message,
                    conversation_history=conversation_history,
                    enabled_tools=payload.get("tools"),
                    active_capability=payload.get("capability"),
                    knowledge_bases=payload.get("knowledge_bases", []),
                    attachments=attachments,
                    config_overrides=request_config,
                    language=payload.get("language", "en"),
                    notebook_context=notebook_context,
                    history_context=history_context,
                    memory_context=memory_context,
                    metadata={
                        "conversation_summary": history_result.conversation_summary,
                        "conversation_context_text": conversation_context_text,
                        "history_token_count": history_result.token_count,
                        "history_budget": history_result.budget,
                        "chat_mode_explicit": bool(payload.get("_chat_mode_explicit", False)),
                        "turn_id": turn_id,
                        "bot_id": str(request_config.get("bot_id", "") or "").strip(),
                        "knowledge_chain_profile": str(
                            execution.payload.get("config", {}).get("knowledge_chain_profile", "")
                            or ""
                        ).strip(),
                        "knowledge_chain_source": str(
                            execution.payload.get("config", {}).get("knowledge_chain_source", "")
                            or ""
                        ).strip(),
                        "question_followup_context": followup_question_context or {},
                        "interaction_hints": interaction_hints or {},
                        "notebook_references": notebook_references,
                        "history_references": history_references,
                        "memory_context": memory_context,
                    },
                )

                orch = ChatOrchestrator()
                async for event in orch.handle(context):
                    if event.type == StreamEventType.SESSION:
                        continue
                    payload_event = await self._persist_and_publish(execution, event)
                    if payload_event.get("type") not in {"done", "session"}:
                        assistant_events.append(payload_event)
                    if _should_capture_assistant_content(event):
                        assistant_content += event.content
                await self._safe_store_call(
                    execution,
                    "add_assistant_message",
                    self.store.add_message,
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    default=None,
                )
                self._capture_mobile_points(billing_context, assistant_content)
                self._record_mobile_learning(
                    billing_context,
                    raw_user_content,
                    assistant_content,
                )
                await self._safe_store_call(
                    execution,
                    "mark_turn_completed",
                    self.store.update_turn_status,
                    turn_id,
                    "completed",
                    default=False,
                )
                observability.update_observation(
                    turn_observation,
                    output_payload={"assistant_content": assistant_content},
                    metadata={
                        **trace_metadata,
                        "assistant_event_count": len(assistant_events),
                    },
                )
                try:
                    if user_id:
                        await tutor_state_service.refresh_from_turn(
                            user_id=user_id,
                            user_message=raw_user_content,
                            assistant_message=assistant_content,
                            session_id=session_id,
                            capability=capability_name or "chat",
                            language=str(payload.get("language", "en") or "en"),
                        )
                    else:
                        await memory_service.refresh_from_turn(
                            user_message=raw_user_content,
                            assistant_message=assistant_content,
                            session_id=session_id,
                            capability=capability_name or "chat",
                            language=str(payload.get("language", "en") or "en"),
                        )
                except Exception:
                    logger.debug("Failed to refresh lightweight tutor memory", exc_info=True)
        except asyncio.CancelledError:
            observability.update_observation(
                turn_observation,
                output_payload={"assistant_content": assistant_content},
                metadata=trace_metadata,
                level="ERROR",
                status_message="Turn cancelled",
            )
            await self._safe_store_call(
                execution,
                "mark_turn_cancelled",
                self.store.update_turn_status,
                turn_id,
                "cancelled",
                "Turn cancelled",
                default=False,
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.ERROR,
                    source=capability_name,
                    content="Turn cancelled",
                    metadata={"turn_terminal": True, "status": "cancelled"},
                ),
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.DONE,
                    source=capability_name,
                    metadata={"status": "cancelled"},
                ),
            )
            raise
        except Exception as exc:
            observability.update_observation(
                turn_observation,
                output_payload={"assistant_content": assistant_content},
                metadata=trace_metadata,
                level="ERROR",
                status_message=str(exc),
            )
            logger.error("Turn %s failed: %s", turn_id, exc, exc_info=True)
            await self._safe_store_call(
                execution,
                "mark_turn_failed",
                self.store.update_turn_status,
                turn_id,
                "failed",
                str(exc),
                default=False,
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.ERROR,
                    source=capability_name,
                    content=str(exc),
                    metadata={"turn_terminal": True, "status": "failed"},
                ),
            )
            await self._persist_and_publish(
                execution,
                StreamEvent(
                    type=StreamEventType.DONE,
                    source=capability_name,
                    metadata={"status": "failed"},
                ),
            )
        finally:
            async with self._lock:
                current = self._executions.get(turn_id)
                if current is not None:
                    for subscriber in current.subscribers:
                        with contextlib.suppress(asyncio.QueueFull):
                            subscriber.queue.put_nowait(None)
                    self._executions.pop(turn_id, None)

    async def _persist_and_publish(
        self,
        execution: _TurnExecution,
        event: StreamEvent,
    ) -> dict[str, Any]:
        metadata = dict(event.metadata or {})
        if event.type == StreamEventType.DONE and not metadata.get("status"):
            metadata["status"] = "completed"
        if event.type == StreamEventType.RESULT:
            usage_summary = observability.get_current_usage_summary()
            if usage_summary:
                nested_metadata = (
                    dict(metadata.get("metadata", {}))
                    if isinstance(metadata.get("metadata"), dict)
                    else {}
                )
                existing_cost_summary = nested_metadata.get("cost_summary")
                if existing_cost_summary and existing_cost_summary != usage_summary:
                    nested_metadata["capability_cost_summary"] = existing_cost_summary
                nested_metadata["cost_summary"] = usage_summary
                metadata["metadata"] = nested_metadata
            question_followup_context = normalize_question_followup_context(
                metadata.get("question_followup_context")
            )
            if question_followup_context is not None:
                self._volatile_question_contexts[execution.session_id] = dict(question_followup_context)
                await self._safe_store_call(
                    execution,
                    "set_active_question_context",
                    self.store.set_active_question_context,
                    execution.session_id,
                    question_followup_context,
                    default=False,
                )
        event.metadata = metadata
        event.session_id = execution.session_id
        event.turn_id = execution.turn_id
        payload = event.to_dict()
        try:
            persisted = await self.store.append_turn_event(execution.turn_id, payload)
        except ValueError as exc:
            # A turn can disappear when the session is deleted while the turn task
            # is still draining events. Avoid cascading failures in the error path.
            if "Turn not found:" not in str(exc):
                raise
            logger.warning(
                "Skip persisting event for missing turn %s (%s)",
                execution.turn_id,
                event.type.value,
            )
            persisted = payload
        except Exception as exc:
            if not self._is_persistence_error(exc):
                raise
            self._mark_persistence_degraded(execution, "append_turn_event", exc)
            persisted = payload
        async with self._lock:
            subscribers = list(self._executions.get(execution.turn_id, execution).subscribers)
        for subscriber in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                subscriber.queue.put_nowait(persisted)
        self._mirror_event_to_workspace(execution, persisted)
        return persisted

    @staticmethod
    def _mirror_event_to_workspace(execution: _TurnExecution, payload: dict[str, Any]) -> None:
        """Mirror turn events to task-local ``events.jsonl`` files under ``data/user/workspace``."""
        try:
            path_service = get_path_service()
            task_dir = path_service.get_task_workspace(execution.capability, execution.turn_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            event_file = task_dir / "events.jsonl"
            with open(event_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Failed to mirror turn event to workspace", exc_info=True)


_runtime_instance: TurnRuntimeManager | None = None


def get_turn_runtime_manager() -> TurnRuntimeManager:
    global _runtime_instance
    if _runtime_instance is None:
        _runtime_instance = TurnRuntimeManager()
    return _runtime_instance


__all__ = ["TurnRuntimeManager", "get_turn_runtime_manager"]
