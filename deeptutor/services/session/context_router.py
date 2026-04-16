from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Sequence


class ContextRouteLabel(str, Enum):
    LOW_SIGNAL_SOCIAL = "low_signal_social"
    SESSION_FOLLOWUP = "session_followup"
    ACTIVE_QUESTION_FOLLOWUP = "active_question_followup"
    GUIDED_PLAN_CONTINUATION = "guided_plan_continuation"
    NOTEBOOK_FOLLOWUP = "notebook_followup"
    PERSONAL_RECALL = "personal_recall"
    CROSS_SESSION_RECALL = "cross_session_recall"
    GENERAL_LEARNING_QUERY = "general_learning_query"
    TOOL_OR_GROUNDING_NEEDED = "tool_or_grounding_needed"


class TaskAnchorType(str, Enum):
    NONE = "none"
    SESSION = "session"
    ACTIVE_QUESTION = "active_question"
    GUIDED_PLAN = "guided_plan"
    NOTEBOOK = "notebook"
    PERSONAL = "personal"
    CROSS_SESSION = "cross_session"
    GENERAL = "general"
    GROUNDING = "grounding"


class ContextRouteReason(str, Enum):
    LOW_SIGNAL_TEXT = "low_signal_text"
    SOCIAL_GREETING = "social_greeting"
    SHORT_ACK = "short_ack"
    SESSION_CONTINUATION_HINT = "session_continuation_hint"
    ACTIVE_QUESTION_PRESENT = "active_question_present"
    GUIDED_PLAN_PRESENT = "guided_plan_present"
    NOTEBOOK_REFERENCE_PRESENT = "notebook_reference_present"
    PERSONAL_RECALL_REQUEST = "personal_recall_request"
    CROSS_SESSION_REFERENCE_PRESENT = "cross_session_reference_present"
    GROUNDING_REQUEST = "grounding_request"
    GENERAL_LEARNING_QUERY = "general_learning_query"
    QUESTION_FORM = "question_form"


@dataclass(frozen=True, slots=True)
class ContextRouteInput:
    user_message: str
    has_active_question: bool = False
    has_active_plan: bool = False
    notebook_references: Sequence[str] = ()
    history_references: Sequence[str] = ()
    memory_references: Sequence[str] = ()
    explicit_grounding: bool = False
    session_followup_hint: bool = False
    personal_recall_hint: bool = False


@dataclass(frozen=True, slots=True)
class ContextRouteDecision:
    primary_route: ContextRouteLabel
    secondary_flags: tuple[str, ...] = ()
    task_anchor_type: TaskAnchorType = TaskAnchorType.NONE
    route_reasons: tuple[ContextRouteReason, ...] = ()
    confidence: float = 1.0

    @property
    def route_label(self) -> str:
        return self.primary_route.value


_LOW_SIGNAL_PATTERNS = (
    re.compile(r"^(hi|hello|hey|ok|okay|thanks|thank you|thx|yo)[!.?\s]*$", re.IGNORECASE),
    re.compile(r"^(你好|您好|哈喽|hello|hi|在吗|在嘛|在不在|谢谢|多谢|好的|好呀|收到|嗯嗯?|行|可以|ok|okay)[。！？!?，,。\s]*$"),
    re.compile(r"^(还有多少|还有几|剩多少|点数|积分|余额|账户余额)"),
)
_SOCIAL_MARKERS = ("你好", "您好", "在吗", "在嘛", "hello", "hi", "thanks", "谢谢", "好的", "收到")
_FOLLOWUP_MARKERS = ("继续", "接着", "然后", "这个题", "刚才", "上面", "前面", "那我", "那这个", "再说")
_PLAN_MARKERS = ("计划", "学习计划", "page", "页面", "进度", "继续上次", "继续学习", "下一步", "按计划")
_NOTEBOOK_MARKERS = ("笔记", "notebook", "记到笔记", "写进笔记", "我笔记里", "笔记里")
_PERSONAL_MARKERS = ("我偏好", "我喜欢", "记得我", "我叫什么", "我的目标", "我的进度", "我之前", "我上次")
_HISTORY_MARKERS = ("上次", "之前", "前几天", "刚刚那次", "之前的对话", "历史", "history", "上回", "回顾")
_GROUNDING_MARKERS = ("根据", "资料", "来源", "原文", "引用", "证据", "查一下", "搜索", "规范", "依据", "文档")
_QUESTION_PREFIXES = ("什么", "为什么", "怎么", "如何", "是否", "能否", "能不能", "请问", "解释", "讲解")
_CURRENT_OVERRIDE_MARKERS = ("别管上次", "先回答我现在", "先答我现在", "先回答这句", "只回答我现在", "ignore last time")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _has_any(text: str, markers: Sequence[str]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _is_question(text: str) -> bool:
    normalized = _normalize_text(text)
    return "?" in text or "？" in text or normalized.startswith(_QUESTION_PREFIXES)


def _looks_like_session_followup(text: str) -> bool:
    normalized = _normalize_text(text)
    return _has_any(normalized, _FOLLOWUP_MARKERS) or _has_any(normalized, _CURRENT_OVERRIDE_MARKERS)


def _looks_like_grounding_request(text: str) -> bool:
    normalized = _normalize_text(text)
    return _has_any(normalized, _GROUNDING_MARKERS)


def _is_low_signal_social(message: str) -> bool:
    text = _normalize_text(message)
    if not text:
        return False
    if len(text) <= 18 and _has_any(text, _SOCIAL_MARKERS):
        return True
    return any(pattern.match(text) for pattern in _LOW_SIGNAL_PATTERNS)


def _build_decision(
    route: ContextRouteLabel,
    *,
    anchor: TaskAnchorType,
    reasons: Sequence[ContextRouteReason],
    secondary_flags: Sequence[str] = (),
    confidence: float = 1.0,
) -> ContextRouteDecision:
    return ContextRouteDecision(
        primary_route=route,
        task_anchor_type=anchor,
        route_reasons=tuple(reasons),
        secondary_flags=tuple(flag for flag in secondary_flags if flag),
        confidence=confidence,
    )


def decide_context_route(route_input: ContextRouteInput) -> ContextRouteDecision:
    text = _normalize_text(route_input.user_message)
    notebook_refs = tuple(ref for ref in route_input.notebook_references if str(ref).strip())
    history_refs = tuple(ref for ref in route_input.history_references if str(ref).strip())
    memory_refs = tuple(ref for ref in route_input.memory_references if str(ref).strip())

    if _is_low_signal_social(text):
        return _build_decision(
            ContextRouteLabel.LOW_SIGNAL_SOCIAL,
            anchor=TaskAnchorType.NONE,
            reasons=(
                ContextRouteReason.LOW_SIGNAL_TEXT,
                ContextRouteReason.SOCIAL_GREETING if _has_any(text, _SOCIAL_MARKERS) else ContextRouteReason.SHORT_ACK,
            ),
        )

    if notebook_refs or _has_any(text, _NOTEBOOK_MARKERS):
        reasons = [ContextRouteReason.NOTEBOOK_REFERENCE_PRESENT]
        if _has_any(text, _FOLLOWUP_MARKERS):
            reasons.append(ContextRouteReason.SESSION_CONTINUATION_HINT)
        return _build_decision(
            ContextRouteLabel.NOTEBOOK_FOLLOWUP,
            anchor=TaskAnchorType.NOTEBOOK,
            reasons=reasons,
            secondary_flags=("notebook_reference",),
        )

    if _has_any(text, _CURRENT_OVERRIDE_MARKERS):
        if route_input.has_active_question:
            return _build_decision(
                ContextRouteLabel.ACTIVE_QUESTION_FOLLOWUP,
                anchor=TaskAnchorType.ACTIVE_QUESTION,
                reasons=(ContextRouteReason.ACTIVE_QUESTION_PRESENT, ContextRouteReason.SESSION_CONTINUATION_HINT),
                secondary_flags=("active_question", "current_override"),
            )
        return _build_decision(
            ContextRouteLabel.SESSION_FOLLOWUP,
            anchor=TaskAnchorType.SESSION,
            reasons=(ContextRouteReason.SESSION_CONTINUATION_HINT,),
            secondary_flags=("current_override",),
        )

    if history_refs or _has_any(text, _HISTORY_MARKERS):
        return _build_decision(
            ContextRouteLabel.CROSS_SESSION_RECALL,
            anchor=TaskAnchorType.CROSS_SESSION,
            reasons=(ContextRouteReason.CROSS_SESSION_REFERENCE_PRESENT,),
            secondary_flags=("history_reference",),
        )

    if memory_refs or _has_any(text, _PERSONAL_MARKERS) or (
        route_input.personal_recall_hint and _has_any(text, _PERSONAL_MARKERS)
    ):
        return _build_decision(
            ContextRouteLabel.PERSONAL_RECALL,
            anchor=TaskAnchorType.PERSONAL,
            reasons=(ContextRouteReason.PERSONAL_RECALL_REQUEST,),
            secondary_flags=("memory_reference",),
        )

    if route_input.has_active_plan or _has_any(text, _PLAN_MARKERS):
        reasons = [ContextRouteReason.GUIDED_PLAN_PRESENT]
        if _has_any(text, _FOLLOWUP_MARKERS):
            reasons.append(ContextRouteReason.SESSION_CONTINUATION_HINT)
        return _build_decision(
            ContextRouteLabel.GUIDED_PLAN_CONTINUATION,
            anchor=TaskAnchorType.GUIDED_PLAN,
            reasons=reasons,
            secondary_flags=("active_plan",),
        )

    if route_input.has_active_question and (_is_question(text) or _has_any(text, _FOLLOWUP_MARKERS)):
        return _build_decision(
            ContextRouteLabel.ACTIVE_QUESTION_FOLLOWUP,
            anchor=TaskAnchorType.ACTIVE_QUESTION,
            reasons=(ContextRouteReason.ACTIVE_QUESTION_PRESENT, ContextRouteReason.QUESTION_FORM),
            secondary_flags=("active_question",),
        )

    if (
        route_input.session_followup_hint and _looks_like_session_followup(text)
    ) or (
        _looks_like_session_followup(text)
        and not _is_question(text)
        and not _looks_like_grounding_request(text)
        and not route_input.has_active_plan
        and not route_input.has_active_question
    ):
        return _build_decision(
            ContextRouteLabel.SESSION_FOLLOWUP,
            anchor=TaskAnchorType.SESSION,
            reasons=(ContextRouteReason.SESSION_CONTINUATION_HINT,),
            secondary_flags=("session_followup",),
        )

    if _looks_like_grounding_request(text) or (
        route_input.explicit_grounding and _looks_like_grounding_request(text)
    ):
        return _build_decision(
            ContextRouteLabel.TOOL_OR_GROUNDING_NEEDED,
            anchor=TaskAnchorType.GROUNDING,
            reasons=(ContextRouteReason.GROUNDING_REQUEST,),
            secondary_flags=("grounding",),
        )

    return _build_decision(
        ContextRouteLabel.GENERAL_LEARNING_QUERY,
        anchor=TaskAnchorType.GENERAL,
        reasons=(
            ContextRouteReason.GENERAL_LEARNING_QUERY,
            ContextRouteReason.QUESTION_FORM if _is_question(text) else ContextRouteReason.LOW_SIGNAL_TEXT,
        ),
    )


def route_context(user_message: str, **kwargs: object) -> ContextRouteDecision:
    return decide_context_route(ContextRouteInput(user_message=user_message, **kwargs))


__all__ = [
    "ContextRouteDecision",
    "ContextRouteInput",
    "ContextRouteLabel",
    "ContextRouteReason",
    "TaskAnchorType",
    "decide_context_route",
    "route_context",
]
