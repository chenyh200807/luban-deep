from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal

TutorBotResponseMode = Literal["smart", "fast", "deep"]
ResponseDensity = Literal["short", "balanced", "detailed"]
KnowledgeStrategy = Literal["kb_first"]
ModeWorkflow = Literal["single_shot_with_prefetch", "full_agent_loop"]


@dataclass(frozen=True)
class ModeExecutionPolicy:
    requested_mode: TutorBotResponseMode
    selected_mode: Literal["fast", "deep"]
    effective_mode: TutorBotResponseMode
    max_tool_rounds: int
    allow_deep_stage: bool
    response_density: ResponseDensity
    latency_budget_ms: int
    knowledge_strategy: KnowledgeStrategy
    workflow: ModeWorkflow
    model_fallback_allowed: bool
    web_search_allowed: bool
    execution_path: str
    preferred_model: str = ""
    response_mode_degrade_reason: str = ""
    selection_reason: str = ""


def normalize_requested_response_mode(value: Any) -> TutorBotResponseMode:
    if value is None:
        return "smart"

    normalized = str(value).strip().lower()
    if normalized in {"fast", "deep"}:
        return normalized
    return "smart"


def resolve_requested_response_mode(
    chat_mode: Any,
    interaction_hints: dict[str, Any] | None,
) -> TutorBotResponseMode:
    hints = interaction_hints or {}

    if chat_mode is not None and str(chat_mode).strip():
        return normalize_requested_response_mode(chat_mode)

    if "requested_response_mode" in hints:
        return normalize_requested_response_mode(
            hints.get("requested_response_mode"),
        )

    return "smart"


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    normalized = str(text or "").strip().lower()
    return any(marker in normalized for marker in markers)


def _looks_like_deep_query(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    strong_markers = (
        "案例",
        "对比",
        "比较",
        "详细",
        "分步",
        "规划",
        "计划",
        "批改",
        "讲评",
        "沿用",
        "同一个案例",
        "考试标准",
        "风险",
        "多问",
    )
    weak_markers = (
        "分析",
        "为什么",
        "怎么做",
    )
    if _contains_any(text, strong_markers):
        return True
    weak_marker_hits = sum(1 for marker in weak_markers if marker in text)
    if weak_marker_hits >= 2:
        return True
    return text.count("？") + text.count("?") >= 2


def looks_like_explicit_brevity_request(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return _contains_any(
        text,
        (
            "简要",
            "一句话",
            "简短",
            "快速",
            "快一点",
            "概括",
            "别展开",
            "不要展开",
            "不用展开",
            "少废话",
            "只说结论",
            "只给结论",
            "只说答案",
            "只给答案",
            "直接说",
            "简单解释",
            "简单讲",
            "one sentence",
            "briefly",
            "short answer",
        ),
    )


def _looks_like_fast_query(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return bool(
        looks_like_explicit_brevity_request(text)
        or _contains_any(
            text,
            (
                "简单说",
                "简单解释",
                "简单讲",
                "概括",
                "是什么",
            ),
        ),
    )


def _looks_like_structured_submission_followup(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    if not _contains_any(text, ("我答", "我选", "批改", "判分", "打分", "订正", "改一下")):
        return False
    return re.search(r"第\s*[0-9一二两三四五六七八九十]+\s*[题问]", text) is not None


def select_response_mode(
    requested_mode: Any,
    *,
    user_message: str,
    interaction_hints: dict[str, Any] | None,
    has_active_object: bool,
) -> tuple[Literal["fast", "deep"], str]:
    normalized_requested = normalize_requested_response_mode(requested_mode)
    hints = interaction_hints or {}

    if normalized_requested == "fast":
        return "fast", "requested_mode_explicit"
    if normalized_requested == "deep":
        return "deep", "requested_mode_explicit"

    from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request

    if _looks_like_structured_submission_followup(user_message):
        return "fast", "structured_submission"

    if looks_like_practice_generation_request(user_message):
        return "fast", "practice_generation"

    if looks_like_explicit_brevity_request(user_message):
        return "fast", "explicit_brevity"

    deep_reasons: list[str] = []
    if has_active_object:
        deep_reasons.append("active_object")
    if bool(hints.get("current_info_required")):
        deep_reasons.append("current_info_required")
    if _looks_like_deep_query(user_message):
        deep_reasons.append("deep_query_shape")
    if deep_reasons:
        return "deep", ",".join(deep_reasons)

    fast_reasons: list[str] = []
    if _looks_like_fast_query(user_message):
        fast_reasons.append("simple_explainer")
    if not fast_reasons:
        fast_reasons.append("default_fast")
    return "fast", ",".join(fast_reasons)


def build_mode_execution_policy(
    requested_mode: Any,
    *,
    selected_mode: Any | None = None,
    selection_reason: str = "",
) -> ModeExecutionPolicy:
    normalized_requested = normalize_requested_response_mode(requested_mode)
    normalized_selected = normalize_requested_response_mode(selected_mode)
    if normalized_selected not in {"fast", "deep"}:
        normalized_selected = "deep" if normalized_requested == "deep" else "fast"

    if normalized_selected == "fast":
        return ModeExecutionPolicy(
            requested_mode=normalized_requested,
            selected_mode="fast",
            effective_mode="fast",
            max_tool_rounds=1,
            allow_deep_stage=False,
            response_density="short",
            latency_budget_ms=6000,
            knowledge_strategy="kb_first",
            workflow="single_shot_with_prefetch",
            model_fallback_allowed=True,
            web_search_allowed=True,
            execution_path="tutorbot_kb_first_fast_policy",
            selection_reason=selection_reason,
        )

    return ModeExecutionPolicy(
        requested_mode=normalized_requested,
        selected_mode="deep",
        effective_mode="deep",
        max_tool_rounds=4,
        allow_deep_stage=True,
        response_density="detailed",
        latency_budget_ms=20000,
        knowledge_strategy="kb_first",
        workflow="full_agent_loop",
        model_fallback_allowed=True,
        web_search_allowed=True,
        execution_path="tutorbot_kb_first_full_agent_policy",
        selection_reason=selection_reason,
    )
