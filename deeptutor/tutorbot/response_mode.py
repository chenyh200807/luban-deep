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


def _case_question_paste_signals(text: str) -> bool:
    """案例试卷粘贴的结构信号（纯形状谓词，非独立判定门——消费方是两个既有
    baselined gate：deep 形状加分、提交门拒接）。

    生产 trace 87ad350f（2026-07-29）：549 字案例题面+单小问，恰好不含任何
    strong marker、零问号，落进 default_fast 后 fast 单发 3 次空答案收场。
    trace 51df5b03：`【问题】`括号形不匹配旧 `问题[:：]` 正则。长题面 +
    「问题:」/「【问题】」小问段 = 试卷/案例粘贴；纯长粘贴本身也是深意图——
    fast 的定位是"快答速讲"，几百字题面不是速讲对象。误判方向不对称：
    错进 deep 只多花几秒，错进 fast 是整轮失败。
    """
    if len(text) >= 120 and re.search(r"问题\s*[:：]|【问题】", text):
        return True
    return len(text) >= 300


def _looks_like_deep_query(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    if _case_question_paste_signals(text):
        return True
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
    # 长案例试卷粘贴不归简答门：题面里偶含"简要说明"类字样（考题原文常见）
    # 不代表用户要一句话快答——fast 单发接不住案例题（trace 51df5b03 实证，
    # 该题面正文命中简答词后被抢进 fast）。
    if _case_question_paste_signals(text):
        return False
    return _contains_any(
        text,
        (
            "简要",
            "一句话",
            "简短",
            "字以内",
            "个字以内",
            "10字",
            "10个字",
            "十字以内",
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
    # 提交快答门只接短结构化提交（"第3题我选B"）。长案例试卷粘贴即使带
    # "批改/我答"话术也不归它——fast 单发接不住案例题（P0 2026-07-29，
    # trace 51df5b03 实证），该形状归 deep（_looks_like_deep_query 同谓词加分）。
    if _case_question_paste_signals(text):
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


def active_object_requires_deep_mode(
    *,
    active_object: dict[str, Any] | None,
    followup_context: dict[str, Any] | None,
    user_message: str,
) -> bool:
    """Single authority (control-plane S3a): does the active question object
    require DEEP mode-selection?

    Both ``start_turn`` mode-selection and ``TutorBotCapability._mode_policy``
    smart fallback call this. It carries the FINE semantics (the more correct
    of the two legacy implementations): an active question with an answer
    submission / practice-generation / grading followup is demoted to FAST;
    a pure explanation request (or any active object without such a followup)
    stays DEEP.

    This decides the fast/deep response mode and intentionally lives in
    ``response_mode`` rather than QTPK — fast/deep is a response-mode policy,
    not a question-turn fact.
    """
    from deeptutor.services.active_object_builder import (
        extract_question_context_from_active_object,
        normalize_active_object,
    )
    from deeptutor.services.question_followup import (
        normalize_question_followup_context,
        resolve_submission_attempt,
    )
    from deeptutor.services.semantic_router import is_question_active_object_type
    from deeptutor.tutorbot.teaching_modes import (
        looks_like_practice_generation_request,
    )

    normalized = normalize_active_object(active_object)
    if not isinstance(normalized, dict):
        return False
    object_type = str(normalized.get("object_type") or "").strip()
    if object_type in {"", "open_chat_topic"}:
        return False

    resolved_followup = normalize_question_followup_context(followup_context)
    if not resolved_followup:
        resolved_followup = extract_question_context_from_active_object(normalized)

    # Family-first: the FAST-demote (submission / practice / grading) branch applies
    # only to question (题型) objects — including open_world_question, which the old
    # hand-listed {question_set, single_question} silently dropped. Non-question objects
    # keep their pre-existing DEEP fall-through unchanged.
    if is_question_active_object_type(object_type) and resolved_followup:
        if looks_like_practice_generation_request(user_message):
            return False
        _, submission = resolve_submission_attempt(user_message, resolved_followup)
        if submission:
            return False
        text = str(user_message or "").strip()
        if any(marker in text for marker in ("我答", "我选", "批改", "判分", "打分")) and re.search(
            r"第\s*[0-9一二两三四五六七八九十]+\s*[题问]", text
        ):
            return False
    return True


def build_mode_execution_policy(
    requested_mode: Any,
    *,
    selected_mode: Any | None = None,
    selection_reason: str = "",
    fast_preferred_model: str = "",
) -> ModeExecutionPolicy:
    normalized_requested = normalize_requested_response_mode(requested_mode)
    normalized_selected = normalize_requested_response_mode(selected_mode)
    if normalized_selected not in {"fast", "deep"}:
        normalized_selected = "deep" if normalized_requested == "deep" else "fast"

    if normalized_selected == "fast":
        # 产品口径（主控裁决 2026-08-01）：**任何档位都不降判分质量**。fast 只压
        # 主 agent 循环的 tool 轮数与时延预算（max_tool_rounds=1 / 6s），
        # **不跳判分链**——案例判分永远跑完整 rubric + judge，且被钉在主模型上
        # （capabilities/tutorbot.py 的 grading_turn 闸清空 fast_preferred_model）。
        # 效率画像 §3.3 记录的"快速档≈没有体感差别"由**渐进吐字**兑现（判分正文
        # 之前的顺序发射，contracts/turn.md「渐进发射不改变终态」），不是靠少判。
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
            preferred_model=str(fast_preferred_model or "").strip(),
            selection_reason=selection_reason,
        )

    # DEEP branch intentionally never fills preferred_model: deep / grading
    # paths always run the primary model (hard invariant). fast_preferred_model
    # is ignored here on purpose.
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
