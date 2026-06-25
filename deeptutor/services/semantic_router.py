from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Awaitable, Callable, Literal

from deeptutor.services.question_followup import (
    followup_action_route,
    interpret_question_followup_action,
    looks_like_question_context_exit_request,
    looks_like_question_followup,
    normalize_question_followup_context,
    reset_question_submission_state,
    resolve_submission_attempt,
    submission_confidence,
)
from deeptutor.services.question_lifecycle_skills import looks_like_free_text_mcq_grading_request
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request

_PREVIOUS_OBJECT_MARKERS = (
    "上一题",
    "上一组",
    "上一个",
    "刚才那题",
    "刚才那组",
    "前一题",
    "前一组",
    "回到上一题",
    "回到刚才",
    "不是这题",
    "不是这个题",
    "不是这个",
)
_PREVIOUS_OBJECT_REFERENCE_RE = re.compile(
    r"(?:刚才|之前|前面).{0,24}(?:那道题|那一道|那一题|那道|那题)"
)
_GUIDE_CONTINUATION_MARKERS = (
    "继续",
    "接着",
    "下一步",
    "下一页",
    "继续学习",
    "学习页面",
    "这个页面",
    "这个计划",
    "按计划",
)
_GUIDE_DETOUR_MARKERS = (
    "点数",
    "积分",
    "余额",
    "会员",
    "套餐",
    "充值",
    "支付",
    "你叫什么",
    "你是谁",
)
_LOW_SIGNAL_CONTINUATION_MARKERS = {
    "继续",
    "接着",
    "然后",
    "然后呢",
    "下一步",
    "下一个",
    "那个",
    "这个",
}
_EXPLICIT_PRACTICE_GENERATION_MARKERS = (
    "出题",
    "出一道",
    "来一道",
    "来一题",
    "选择题",
    "单选题",
    "多选题",
    "判断题",
    "案例题",
    "简答题",
    "考我",
    "刷题",
    "测我",
    "摸底测评",
    "继续出",
    "继续来一道",
    "再来一道",
    "再出一道",
    "quiz me",
    "test me",
    "give me a question",
    "give me one question",
)
_EXPLICIT_PRACTICE_GENERATION_PATTERNS = (
    r"(给我|帮我|来|出)\s*(?:\d{0,2}|[一二两三四五六七八九十几]?)\s*(?:道)?(?:题|单选题|多选题|案例题|简答题|选择题|判断题)",
    r"(给我|帮我|来|出).{0,16}(?:\d{1,2}|[一二两三四五六七八九十几]+)\s*(?:道题|题|道)",
    r"(我想|想)\s*(?:刷题|练题|做几道题|做一道题|练几道题|练一道题)",
    r"(?:先|来|做|开始|进行|帮我|给我|帮我做|安排)\s*(?:一次|一轮|个)?\s*(?:入门)?(?:摸底测评|摸底测试|摸底|小测|自测)",
)
_SHORT_PRACTICE_OFFER_ACCEPTANCES = {
    "要",
    "要的",
    "需要",
    "需要的",
    "可以",
    "可以的",
    "好",
    "好的",
    "行",
    "来",
    "来吧",
    "嗯",
    "嗯嗯",
}
_RECENT_PRACTICE_OFFER_RE = re.compile(
    r"(?:需要|要不要|是否|可以|我可以).{0,32}"
    r"(?:出|生成|来|安排).{0,32}"
    r"(?:同考点|类似|相关|巩固|练习|题目|题|自测)",
    re.IGNORECASE,
)
_REPEATED_PRACTICE_OFFER_RE = re.compile(
    r"(?:需要我|可以我|要不要我).{0,32}"
    r"(?:出|生成|来|安排).{0,32}"
    r"(?:同考点|类似|相关|巩固|练习|题目|题|自测)",
    re.IGNORECASE,
)
_ACCEPTED_PRACTICE_OFFER_TOPIC = "继续出同考点题目帮我巩固一下"
_QUESTION_EXPLAINER_MARKERS = (
    "为什么",
    "为啥",
    "解析",
    "讲解",
    "解释",
    "错在哪",
    "哪里错",
    "怎么错",
)
_ORDINAL_INDEX_MAP = {
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


QuestionActiveObjectType = Literal["question_set", "single_question", "open_world_question"]
GuideActiveObjectType = Literal["guide_page", "study_plan"]
SessionActiveObjectType = Literal["open_chat_topic"]
SemanticRelation = Literal[
    "answer_active_object",
    "revise_answer_on_active_object",
    "ask_about_active_object",
    "continue_same_learning_flow",
    "switch_to_new_object",
    "temporary_detour",
    "out_of_scope_chat",
    "uncertain",
]
SemanticNextAction = Literal[
    "route_to_grading",
    "route_to_followup_explainer",
    "route_to_generation",
    "route_to_guide",
    "route_to_general_chat",
    "route_to_account_or_product_help",
    "ask_clarifying_question",
    "hold_and_wait",
]
SemanticAllowedPatch = Literal[
    "update_answer_slot",
    "append_answer_slots",
    "set_active_object",
    "suspend_current_object",
    "resume_suspended_object",
    "clear_active_object",
    "no_state_change",
]


# open_world_question：来源 source-backed 变式卡（硬约束27）的可作答题，judging
# 走 open-world（无 verified correct_answer，硬约束40），区别于题库 verified 题
# single_question / question_set；它只能驱动 open-world 判分，绝不冒充题库/官方 authority。
QUESTION_ACTIVE_OBJECT_TYPES = {"question_set", "single_question", "open_world_question"}
GUIDE_ACTIVE_OBJECT_TYPES = {"guide_page", "study_plan"}
SESSION_ACTIVE_OBJECT_TYPES = {"open_chat_topic"}
SUPPORTED_ACTIVE_OBJECT_TYPES = (
    QUESTION_ACTIVE_OBJECT_TYPES | GUIDE_ACTIVE_OBJECT_TYPES | SESSION_ACTIVE_OBJECT_TYPES
)
SEMANTIC_RELATIONS = {
    "answer_active_object",
    "revise_answer_on_active_object",
    "ask_about_active_object",
    "continue_same_learning_flow",
    "switch_to_new_object",
    "temporary_detour",
    "out_of_scope_chat",
    "uncertain",
}
SEMANTIC_NEXT_ACTIONS = {
    "route_to_grading",
    "route_to_followup_explainer",
    "route_to_generation",
    "route_to_guide",
    "route_to_general_chat",
    "route_to_account_or_product_help",
    "ask_clarifying_question",
    "hold_and_wait",
}
SEMANTIC_ALLOWED_PATCHES = {
    "update_answer_slot",
    "append_answer_slots",
    "set_active_object",
    "suspend_current_object",
    "resume_suspended_object",
    "clear_active_object",
    "no_state_change",
}
SEMANTIC_ROUTE_BY_NEXT_ACTION = {
    "route_to_grading": "submission",
    "route_to_followup_explainer": "followup",
    "route_to_generation": "practice_generation",
    "route_to_guide": "chat",
    "route_to_general_chat": "chat",
    "route_to_account_or_product_help": "chat",
    "ask_clarifying_question": "chat",
    "hold_and_wait": "chat",
}


@dataclass
class SemanticRoutingResult:
    active_object: dict[str, Any] | None
    suspended_object_stack: list[dict[str, Any]]
    turn_semantic_decision: dict[str, Any]
    question_context: dict[str, Any] | None
    followup_action: dict[str, Any] | None = None


@dataclass
class _SemanticCandidate:
    active_object: dict[str, Any]
    question_context: dict[str, Any]
    turn_semantic_decision: dict[str, Any]
    followup_action: dict[str, Any] | None
    route: str | None
    stack_index: int | None = None


def apply_active_object_transition(
    *,
    previous_active_object: dict[str, Any] | None,
    previous_suspended_object_stack: list[dict[str, Any]] | None,
    turn_semantic_decision: dict[str, Any] | None,
    resolved_active_object: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    active_object = normalize_active_object(previous_active_object)
    suspended_stack = normalize_suspended_object_stack(previous_suspended_object_stack)
    decision = normalize_turn_semantic_decision(
        turn_semantic_decision,
        active_object=active_object,
    )
    next_active_object = normalize_active_object(resolved_active_object) or active_object

    if decision is None:
        return next_active_object, suspended_stack

    allowed_patch = set(decision.get("allowed_patch") or [])
    target_object_ref = decision.get("target_object_ref") or {}

    if "resume_suspended_object" in allowed_patch:
        resumed_active_object, remaining_stack = _resume_from_suspended_stack(
            suspended_stack=suspended_stack,
            target_object_ref=target_object_ref,
        )
        if resumed_active_object is not None:
            next_stack = _push_suspended_object(remaining_stack, active_object)
            if next_active_object is not None and _same_active_object(
                next_active_object,
                resumed_active_object,
            ):
                resumed_active_object = next_active_object
            return resumed_active_object, next_stack

    if "clear_active_object" in allowed_patch:
        return None, suspended_stack

    if next_active_object is not None:
        if active_object is not None and not _same_active_object(active_object, next_active_object):
            suspended_stack = _push_suspended_object(suspended_stack, active_object)
        suspended_stack = _remove_from_suspended_stack(
            suspended_stack,
            build_target_object_ref(next_active_object),
        )
        return next_active_object, suspended_stack

    return active_object, suspended_stack


def normalize_active_object(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    raw_state_snapshot = raw.get("state_snapshot") if isinstance(raw.get("state_snapshot"), dict) else {}
    state_snapshot = normalize_question_followup_context(raw_state_snapshot)
    object_type = str(raw.get("object_type") or "").strip().lower()
    if not object_type and state_snapshot is not None:
        object_type = infer_question_active_object_type(state_snapshot)
    if object_type in QUESTION_ACTIVE_OBJECT_TYPES:
        object_id = _normalize_object_id(raw.get("object_id"), state_snapshot, object_type)
        if not object_id:
            return None

        scope = raw.get("scope") if isinstance(raw.get("scope"), dict) else {}
        if not scope and state_snapshot is not None:
            scope = _build_question_scope(state_snapshot)

        version = _coerce_version(raw.get("version"), default=1)
        return {
            "object_type": object_type,
            "object_id": object_id,
            "scope": dict(scope),
            "state_snapshot": state_snapshot or {},
            "version": version,
            "entered_at": str(raw.get("entered_at") or "").strip(),
            "last_touched_at": str(raw.get("last_touched_at") or "").strip(),
            "source_turn_id": str(raw.get("source_turn_id") or "").strip(),
        }

    if object_type not in GUIDE_ACTIVE_OBJECT_TYPES and object_type not in SESSION_ACTIVE_OBJECT_TYPES:
        return None

    object_id = str(raw.get("object_id") or "").strip()
    if not object_id:
        return None

    scope = raw.get("scope") if isinstance(raw.get("scope"), dict) else {}
    return {
        "object_type": object_type,
        "object_id": object_id,
        "scope": dict(scope),
        "state_snapshot": dict(raw_state_snapshot),
        "version": _coerce_version(raw.get("version"), default=1),
        "entered_at": str(raw.get("entered_at") or "").strip(),
        "last_touched_at": str(raw.get("last_touched_at") or "").strip(),
        "source_turn_id": str(raw.get("source_turn_id") or "").strip(),
    }


def normalize_suspended_object_stack(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        active_object = normalize_active_object(item)
        if active_object is not None:
            normalized.append(active_object)
        if len(normalized) >= 3:
            break
    return normalized


def infer_question_active_object_type(question_context: dict[str, Any] | None) -> QuestionActiveObjectType:
    normalized = normalize_question_followup_context(question_context)
    if normalized is None:
        return "single_question"
    items = normalized.get("items") or []
    return "question_set" if len(items) > 1 else "single_question"


def build_question_active_object(
    question_context: dict[str, Any] | None,
    *,
    prior_active_object: dict[str, Any] | None = None,
    source_turn_id: str = "",
    object_type_override: str | None = None,
) -> dict[str, Any] | None:
    normalized = normalize_question_followup_context(question_context)
    if normalized is None:
        return None

    prior = normalize_active_object(prior_active_object)
    # object_type_override 让出题侧（如 source-backed 变式卡）显式声明 open_world_question
    # tier；否则按 item 数推断 single_question / question_set。只接受受支持的 question
    # tier，非法值回落推断，绝不引入未登记类型。
    override = str(object_type_override or "").strip().lower()
    object_type = (
        override if override in QUESTION_ACTIVE_OBJECT_TYPES
        else infer_question_active_object_type(normalized)
    )
    object_id = _normalize_object_id(None, normalized, object_type)
    if not object_id:
        return None

    version = 1
    entered_at = ""
    if prior and prior.get("object_id") == object_id and prior.get("object_type") == object_type:
        version = int(prior.get("version", 1) or 1) + 1
        entered_at = str(prior.get("entered_at") or "").strip()

    return {
        "object_type": object_type,
        "object_id": object_id,
        "scope": _build_question_scope(normalized),
        "state_snapshot": normalized,
        "version": version,
        "entered_at": entered_at,
        "last_touched_at": "",
        "source_turn_id": str(source_turn_id or "").strip() or str(
            (prior or {}).get("source_turn_id") or ""
        ).strip(),
    }


def question_context_from_active_object(active_object: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = normalize_active_object(active_object)
    if normalized is None:
        return None
    return normalize_question_followup_context(normalized.get("state_snapshot"))


def normalize_turn_semantic_decision(
    raw: dict[str, Any] | None,
    *,
    active_object: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    relation = str(raw.get("relation_to_active_object") or "").strip()
    next_action = str(raw.get("next_action") or "").strip()
    if relation not in SEMANTIC_RELATIONS or next_action not in SEMANTIC_NEXT_ACTIONS:
        return None

    allowed_patch = _normalize_allowed_patch(raw.get("allowed_patch"))
    target_object_ref = _normalize_target_object_ref(raw.get("target_object_ref"))
    if target_object_ref is None and active_object is not None:
        target_object_ref = build_target_object_ref(active_object)
    if target_object_ref is None:
        target_object_ref = {"object_type": "", "object_id": ""}

    return {
        "relation_to_active_object": relation,
        "next_action": next_action,
        "allowed_patch": allowed_patch,
        "confidence": _normalize_confidence(raw.get("confidence"), default=0.0),
        "reason": str(raw.get("reason") or "").strip(),
        "target_object_ref": target_object_ref,
    }


def build_turn_semantic_decision(
    *,
    relation_to_active_object: SemanticRelation,
    next_action: SemanticNextAction,
    allowed_patch: SemanticAllowedPatch | list[SemanticAllowedPatch] | None,
    confidence: float,
    reason: str,
    target_object_ref: dict[str, Any] | None = None,
    active_object: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_target = target_object_ref
    if raw_target is None and active_object is not None:
        raw_target = build_target_object_ref(active_object)
    if raw_target is None:
        raw_target = {"object_type": "", "object_id": ""}
    normalized = normalize_turn_semantic_decision(
        {
            "relation_to_active_object": relation_to_active_object,
            "next_action": next_action,
            "allowed_patch": allowed_patch,
            "confidence": confidence,
            "reason": reason,
            "target_object_ref": raw_target,
        },
        active_object=active_object,
    )
    if normalized is None:
        raise ValueError("invalid semantic decision")
    return normalized


def semantic_route_for_decision(decision: dict[str, Any] | None) -> str | None:
    normalized = normalize_turn_semantic_decision(decision)
    if normalized is None:
        return None
    return SEMANTIC_ROUTE_BY_NEXT_ACTION.get(str(normalized.get("next_action") or ""))


def turn_semantic_decision_route(decision: dict[str, Any] | None) -> str | None:
    route = semantic_route_for_decision(decision)
    if route == "practice_generation":
        return "deep_question"
    if route in {"submission", "followup"}:
        return "deep_question"
    if route == "chat":
        return "chat"
    return None


def is_unresolved_switch_followup(decision: dict[str, Any] | None) -> bool:
    """Canonical predicate: the learner referenced a DIFFERENT / earlier object but the
    runtime could not resolve a concrete structured target, so the decision degraded to
    a followup on the (stale) active object.

    ``switch_to_new_object`` never legitimately co-occurs with
    ``route_to_followup_explainer`` (a real switch resolves a NEW active object and
    routes to generation/grading; a real followup carries ``ask_about_active_object`` /
    ``answer_active_object``). This exact combo is the unambiguous "wanted a different /
    earlier object, fell back to the stale one" signature.

    Context-continuity invariant (see contracts/turn.md §跨能力上下文连续性): such a turn
    depends on prior conversation context that lives in ``conversation_context_text``
    (the canonical shared history, unconditionally injected into the main conversational
    LLM). It MUST be routed to that context-continuous executor (TutorBot) to be answered
    from history — never fail-closed as "I can't locate that question" amnesia. This
    predicate is the SINGLE source of that signature; orchestrator routing and the
    deep_question safety net both read it (no second definition).
    """

    decision = decision if isinstance(decision, dict) else {}
    return (
        str(decision.get("relation_to_active_object") or "").strip() == "switch_to_new_object"
        and str(decision.get("next_action") or "").strip() == "route_to_followup_explainer"
    )


def build_active_object_from_question_context(
    question_context: dict[str, Any] | None,
    *,
    source_turn_id: str = "",
    previous_active_object: dict[str, Any] | None = None,
    object_type_override: str | None = None,
) -> dict[str, Any] | None:
    return build_question_active_object(
        question_context,
        prior_active_object=previous_active_object,
        source_turn_id=source_turn_id,
        object_type_override=object_type_override,
    )


async def resolve_turn_semantic_decision(
    user_message: str,
    active_object: dict[str, Any] | None,
    *,
    history_context: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_active_object = normalize_active_object(active_object)
    accepted_practice_offer = _accepted_recent_practice_offer_action(
        user_message,
        history_context,
    )
    if accepted_practice_offer is not None:
        decision = build_turn_semantic_decision(
            relation_to_active_object=(
                "continue_same_learning_flow"
                if normalized_active_object is not None
                else "switch_to_new_object"
            ),
            next_action="route_to_generation",
            allowed_patch="set_active_object",
            confidence=float(accepted_practice_offer.get("confidence") or 0.0),
            reason=str(accepted_practice_offer.get("reason") or "").strip()
            or "用户接受最近一轮出题巩固邀请。",
            target_object_ref=build_target_object_ref(normalized_active_object)
            or {"object_type": "question_set", "object_id": ""},
            active_object=normalized_active_object,
        )
        return decision, accepted_practice_offer

    question_context = question_context_from_active_object(normalized_active_object)
    if question_context is None:
        if _is_guide_active_object(active_object):
            decision = _decision_from_active_learning_object(
                user_message=user_message,
                active_object=active_object,
            )
            return decision, None
        if _is_open_chat_active_object(active_object):
            decision = _decision_from_active_open_chat_object(
                user_message=user_message,
                active_object=active_object,
            )
            return decision, None
        return None, None

    # Skip the detour when user explicitly submitted their own answer (我选/我改选)
    # WITHOUT an explicit new-question request (换题 etc.).
    # "换题：新题...我选C" → user wants a brand-new question graded, not the active one;
    # keep the detour so we don't bind their answer to the wrong active object.
    # "我选B" / pasted-same-stem + "我选X" → genuine active-question submission;
    # bypass the detour and let the inner LLM routing decide.
    _SUBMISSION_MARKERS = ("我选", "我改选", "我的答案", "我答")
    _NEW_QUESTION_MARKERS = ("换题", "换一题", "换一道", "换道题", "换个题")
    _is_plain_submission = any(m in user_message for m in _SUBMISSION_MARKERS) and not any(
        m in user_message for m in _NEW_QUESTION_MARKERS
    )
    if looks_like_free_text_mcq_grading_request(user_message) and not _is_plain_submission:
        decision = build_turn_semantic_decision(
            relation_to_active_object="temporary_detour",
            next_action="route_to_general_chat",
            allowed_patch="no_state_change",
            confidence=0.74,
            reason="当前输入包含完整新选择题题干和作答，不能绑定到旧 active question。",
            active_object=normalized_active_object,
        )
        return decision, None

    routing = await resolve_question_semantic_routing(
        user_message=user_message,
        metadata={
            "active_object": normalized_active_object,
            "question_followup_context": question_context,
        },
        history_context=history_context,
        interpret_followup_action=lambda message, context: interpret_question_followup_action(
            message,
            context,
            history_context=history_context,
        ),
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )
    return routing.turn_semantic_decision, routing.followup_action


async def resolve_question_semantic_routing(
    *,
    user_message: str,
    metadata: dict[str, Any] | None,
    history_context: str,
    interpret_followup_action: Callable[[str, dict[str, Any] | None], Awaitable[dict[str, Any] | None]],
    resolve_submission_attempt: Callable[[str, dict[str, Any] | None], tuple[dict[str, Any] | None, dict[str, Any] | None]],
    looks_like_question_followup: Callable[[str, dict[str, Any] | None], bool],
    looks_like_practice_generation_request: Callable[[str], bool],
) -> SemanticRoutingResult:
    normalized_metadata = metadata if isinstance(metadata, dict) else {}
    active_object = normalize_active_object(normalized_metadata.get("active_object"))
    suspended_stack = normalize_suspended_object_stack(
        normalized_metadata.get("suspended_object_stack")
    )
    legacy_question_context = normalize_question_followup_context(
        normalized_metadata.get("question_followup_context")
    )
    if active_object is None and legacy_question_context is not None:
        active_object = build_question_active_object(
            legacy_question_context,
            source_turn_id=str(normalized_metadata.get("turn_id") or "").strip(),
        )

    question_context = question_context_from_active_object(active_object) or legacy_question_context
    cached_action = normalized_metadata.get("question_followup_action")
    followup_action = cached_action if isinstance(cached_action, dict) and cached_action else None
    accepted_practice_offer = _accepted_recent_practice_offer_action(
        user_message,
        history_context,
    )
    if accepted_practice_offer is not None:
        practice_decision = build_turn_semantic_decision(
            relation_to_active_object=(
                "continue_same_learning_flow"
                if active_object is not None
                else "switch_to_new_object"
            ),
            next_action="route_to_generation",
            allowed_patch="set_active_object",
            confidence=float(accepted_practice_offer.get("confidence") or 0.0),
            reason=str(accepted_practice_offer.get("reason") or "").strip(),
            target_object_ref=build_target_object_ref(active_object)
            or {"object_type": "question_set", "object_id": ""},
            active_object=active_object,
        )
        return SemanticRoutingResult(
            active_object=active_object,
            suspended_object_stack=suspended_stack,
            turn_semantic_decision=practice_decision,
            question_context=question_context,
            followup_action=accepted_practice_offer,
        )

    if (
        active_object is not None
        and legacy_question_context is None
        and question_context is not None
        and looks_like_free_text_mcq_grading_request(user_message)
    ):
        detour_decision = build_turn_semantic_decision(
            relation_to_active_object="temporary_detour",
            next_action="route_to_general_chat",
            allowed_patch="no_state_change",
            confidence=0.74,
            reason="当前输入包含完整新选择题题干和作答，不能绑定到旧 active question。",
            active_object=active_object,
        )
        return SemanticRoutingResult(
            active_object=active_object,
            suspended_object_stack=suspended_stack,
            turn_semantic_decision=detour_decision,
            question_context=None,
            followup_action=None,
        )

    if (
        question_context is not None
        and looks_like_practice_generation_request(user_message)
        and _has_explicit_practice_generation_intent(user_message)
    ):
        _target_context, submission = resolve_submission_attempt(user_message, question_context)
        if submission is None:
            reset_question_context = (
                reset_question_submission_state(question_context) or question_context
            )
            reset_active_object = active_object
            if active_object is not None:
                reset_active_object = dict(active_object)
                reset_active_object["state_snapshot"] = reset_question_context
            practice_action = {
                "intent": "generate_more_questions",
                "confidence": 0.86,
                "answers": [],
                "reason": "用户明确要求出选择题/练题，应生成新题而不是批改当前 active question。",
            }
            practice_decision = build_turn_semantic_decision(
                relation_to_active_object=(
                    "continue_same_learning_flow"
                    if reset_active_object is not None
                    else "switch_to_new_object"
                ),
                next_action="route_to_generation",
                allowed_patch="set_active_object",
                confidence=0.86,
                reason=practice_action["reason"],
                target_object_ref=build_target_object_ref(reset_active_object)
                or {"object_type": "question_set", "object_id": ""},
                active_object=reset_active_object,
            )
            return SemanticRoutingResult(
                active_object=reset_active_object,
                suspended_object_stack=suspended_stack,
                turn_semantic_decision=practice_decision,
                question_context=reset_question_context,
                followup_action=practice_action,
            )

    llm_action: dict[str, Any] | None = followup_action
    if question_context is not None and looks_like_question_context_exit_request(
        user_message,
        question_context,
    ):
        detour_decision = build_turn_semantic_decision(
            relation_to_active_object="temporary_detour",
            next_action="route_to_general_chat",
            allowed_patch="no_state_change",
            confidence=0.74,
            reason="当前输入是历史总结/内部证据/退出判分请求，不能由 active question 消费。",
            active_object=active_object,
        )
        return SemanticRoutingResult(
            active_object=active_object,
            suspended_object_stack=suspended_stack,
            turn_semantic_decision=detour_decision,
            question_context=question_context,
            followup_action=None,
        )
    # Stage C activation (2026-06-21): the cached followup action is resolved upstream
    # (turn_runtime) BEFORE conversation history is built, so it only ever sees the
    # active question set — it cannot detect that an EXPLANATION turn references a
    # DIFFERENT historical question ("最开始做错的那道"/"刚才第3题"). Here, where the
    # canonical conversation_context_text IS available, drop a cached NON-submission
    # action so the history-aware classifier below re-resolves and can upgrade to
    # ask_other_question (→ switch_to_new_object → context-continuous main LLM).
    # Submission/grading and practice-generation actions keep their deterministic cache.
    #
    # 判分态单一权威收口 Step 4 (2026-06-24, plan §3): 打破 shielded-from-veto。原先所有
    # submission 缓存"永不交 LLM"以保结构化判分权威(硬约束40 真作答必判),但确定性关键词
    # 提交检测器会把"我猜A但你先别判/还没做"误抽成 submission,一旦缓存就终局误判分。改为
    # **只有 HIGH 置信作答**(显式提交、答案是消息主导 payload)的缓存才 shielded;LOW 置信
    # 缓存"提交"允许被 history-aware LLM 复核翻案。confidence 当场由 user_message +
    # question_context 算(单一权威 submission_confidence),不依赖缓存跨层透传。
    _cached_route = followup_action_route(llm_action) if isinstance(llm_action, dict) else None
    _keep_cached_action = _cached_route in {"submission", "practice_generation"}
    if (
        _cached_route == "submission"
        and question_context is not None
        and submission_confidence(user_message, question_context) == "low"
    ):
        _keep_cached_action = False
    if (
        question_context is not None
        and isinstance(llm_action, dict)
        and history_context.strip()
        and not _keep_cached_action
    ):
        llm_action = None
    if question_context is not None and llm_action is None:
        llm_action = await interpret_followup_action(user_message, question_context)

    llm_decision = _decision_from_followup_action(
        action=llm_action,
        active_object=active_object,
        user_message=user_message,
        question_context=question_context,
    )
    # Deterministic reliability for explicit historical back-references (E1, 2026-06-22):
    # "回到我最开始做错的那道题" / "最早那道" / "第一道" must NOT be bound to the current
    # active question just because the LLM relation classifier flakily returned a plain
    # followup (ask_about_active_object). When such an explicit historical back-reference
    # is classified as a followup/ask on the ACTIVE object, upgrade it to the unresolved-
    # switch signature so it routes to the context-continuous main LLM, which recalls the
    # referenced question from shared history (the proven-correct path). The regex only
    # DETECTS the back-reference; it never decides WHICH question (the main LLM does).
    # Grading/submission relations are untouched (a back-referenced answer is different).
    if (
        question_context is not None
        and isinstance(llm_decision, dict)
        and str(llm_decision.get("relation_to_active_object") or "").strip()
        == "ask_about_active_object"
        and _message_is_historical_question_backreference(user_message)
    ):
        llm_decision = build_turn_semantic_decision(
            relation_to_active_object="switch_to_new_object",
            next_action="route_to_followup_explainer",
            allowed_patch="no_state_change",
            confidence=float(llm_decision.get("confidence") or 0.0) or 0.9,
            reason="显式回指更早/其它历史题（确定性检测），落上下文连续主 LLM 从共享历史召回，不绑当前 active 题。",
            active_object=active_object,
        )
    if llm_decision is None and _is_guide_active_object(active_object):
        llm_decision = _decision_from_active_learning_object(
            user_message=user_message,
            active_object=active_object,
        )
    clarify_decision = _decision_from_ambiguity_gate(
        user_message=user_message,
        active_object=active_object,
        suspended_stack=suspended_stack,
        question_context=question_context,
        llm_decision=llm_decision,
        resolve_submission_attempt=resolve_submission_attempt,
    )
    if clarify_decision is not None:
        return SemanticRoutingResult(
            active_object=active_object,
            suspended_object_stack=suspended_stack,
            turn_semantic_decision=clarify_decision,
            question_context=question_context,
            followup_action=llm_action if isinstance(llm_action, dict) else None,
        )
    llm_route = semantic_route_for_decision(llm_decision)
    if (
        llm_route == "practice_generation"
        and question_context is not None
        and not (
            looks_like_practice_generation_request(user_message)
            and _has_explicit_practice_generation_intent(user_message)
        )
    ):
        llm_decision = None
        llm_action = None
        llm_route = None
    if llm_decision is not None and llm_route in {"submission", "followup", "practice_generation"}:
        if suspended_stack and _message_prefers_previous_object(user_message):
            stack_routing = await _resolve_from_suspended_stack(
                user_message=user_message,
                active_object=active_object,
                suspended_stack=suspended_stack,
                history_context=history_context,
                interpret_followup_action=interpret_followup_action,
                resolve_submission_attempt=resolve_submission_attempt,
                looks_like_question_followup=looks_like_question_followup,
                looks_like_practice_generation_request=looks_like_practice_generation_request,
                active_decision=llm_decision,
            )
            if stack_routing is not None:
                return stack_routing
        return SemanticRoutingResult(
            active_object=active_object,
            suspended_object_stack=suspended_stack,
            turn_semantic_decision=llm_decision,
            question_context=question_context,
            followup_action=llm_action if isinstance(llm_action, dict) else None,
        )

    stack_routing = await _resolve_from_suspended_stack(
        user_message=user_message,
        active_object=active_object,
        suspended_stack=suspended_stack,
        history_context=history_context,
        interpret_followup_action=interpret_followup_action,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
        active_decision=llm_decision,
    )
    if stack_routing is not None:
        return stack_routing

    fallback_decision = _decision_from_fallback(
        user_message=user_message,
        active_object=active_object,
        question_context=question_context,
        resolve_submission_attempt=resolve_submission_attempt,
        looks_like_question_followup=looks_like_question_followup,
        looks_like_practice_generation_request=looks_like_practice_generation_request,
    )
    return SemanticRoutingResult(
        active_object=active_object,
        suspended_object_stack=suspended_stack,
        turn_semantic_decision=fallback_decision,
        question_context=question_context,
        followup_action=llm_action if isinstance(llm_action, dict) else None,
    )


def build_target_object_ref(active_object: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = normalize_active_object(active_object)
    if normalized is None:
        return None
    return {
        "object_type": str(normalized.get("object_type") or "").strip(),
        "object_id": str(normalized.get("object_id") or "").strip(),
    }


def _decision_from_followup_action(
    *,
    action: dict[str, Any] | None,
    active_object: dict[str, Any] | None,
    user_message: str,
    question_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    route = followup_action_route(action)
    confidence = _normalize_confidence(action.get("confidence"), default=0.0)
    reason = str(action.get("reason") or "").strip()
    if str(action.get("intent") or "").strip() == "ask_other_question":
        # The learner references a question that is NOT the current active object
        # (by ordinal/position/attribute — "最开始做错的那道"/"第3题"超出当前题组).
        # This is an explanation request about a DIFFERENT object the runtime cannot
        # pin to a structured active object → emit the unresolved-switch signature so
        # the turn routes to the context-continuous main LLM (which has the question in
        # conversation_context_text) instead of binding to / fabricating a followup on
        # the stale active object. NOT a grading/submission route (those stay structured).
        return build_turn_semantic_decision(
            relation_to_active_object="switch_to_new_object",
            next_action="route_to_followup_explainer",
            allowed_patch="no_state_change",
            confidence=confidence or 0.9,
            reason=reason
            or "用户回指对话历史里非当前 active 的另一道题（序数/位置/属性），需落上下文连续主 LLM 从历史定位讲解。",
            active_object=active_object,
        )
    if route == "submission":
        relation: SemanticRelation = (
            "revise_answer_on_active_object"
            if str(action.get("intent") or "").strip() == "revise_answers"
            or _message_looks_like_revision(user_message)
            else "answer_active_object"
        )
        return build_turn_semantic_decision(
            relation_to_active_object=relation,
            next_action="route_to_grading",
            allowed_patch=_submission_allowed_patch(question_context, action),
            confidence=confidence or 0.95,
            reason=reason or "LLM 将当前输入判定为围绕 active question 的答题或改答。",
            active_object=active_object,
        )
    if route == "followup":
        return build_turn_semantic_decision(
            relation_to_active_object="ask_about_active_object",
            next_action="route_to_followup_explainer",
            allowed_patch="no_state_change",
            confidence=confidence or 0.95,
            reason=reason or "LLM 将当前输入判定为围绕 active question 的追问。",
            active_object=active_object,
        )
    if route == "practice_generation":
        return build_turn_semantic_decision(
            relation_to_active_object=(
                "continue_same_learning_flow" if active_object is not None else "switch_to_new_object"
            ),
            next_action="route_to_generation",
            allowed_patch="set_active_object",
            confidence=confidence or 0.95,
            reason=reason or "LLM 将当前输入判定为继续当前练题流。",
            target_object_ref=build_target_object_ref(active_object)
            or {"object_type": "question_set", "object_id": ""},
            active_object=active_object,
        )

    intent = str(action.get("intent") or "").strip()
    if intent == "unrelated":
        return build_turn_semantic_decision(
            relation_to_active_object=(
                "temporary_detour" if active_object is not None else "out_of_scope_chat"
            ),
            next_action="route_to_general_chat",
            allowed_patch="no_state_change",
            confidence=confidence or 0.8,
            reason=reason or "LLM 判定当前输入与 active question 无关。",
            active_object=active_object,
        )
    return None


def _decision_from_active_learning_object(
    *,
    user_message: str,
    active_object: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized_active_object = normalize_active_object(active_object)
    if not _is_guide_active_object(normalized_active_object):
        return None
    if looks_like_practice_generation_request(user_message):
        return build_turn_semantic_decision(
            relation_to_active_object="continue_same_learning_flow",
            next_action="route_to_generation",
            allowed_patch="set_active_object",
            confidence=0.78,
            reason="当前 active guide page 下，用户正在请求转入练题。",
            active_object=normalized_active_object,
        )
    if _looks_like_guide_detour(user_message):
        return build_turn_semantic_decision(
            relation_to_active_object="temporary_detour",
            next_action="route_to_general_chat",
            allowed_patch="no_state_change",
            confidence=0.68,
            reason="当前 active guide page 存在，但输入更像临时产品或账户问答。",
            active_object=normalized_active_object,
        )
    relation: SemanticRelation = (
        "ask_about_active_object"
        if _message_looks_like_learning_question(user_message)
        else "continue_same_learning_flow"
    )
    return build_turn_semantic_decision(
        relation_to_active_object=relation,
        next_action="route_to_guide",
        allowed_patch="no_state_change",
        confidence=0.72 if _message_mentions_guide(user_message) else 0.6,
        reason="当前输入继续围绕 active guide page / study plan 展开。",
        active_object=normalized_active_object,
    )


async def _resolve_from_suspended_stack(
    *,
    user_message: str,
    active_object: dict[str, Any] | None,
    suspended_stack: list[dict[str, Any]],
    history_context: str,
    interpret_followup_action: Callable[[str, dict[str, Any] | None], Awaitable[dict[str, Any] | None]],
    resolve_submission_attempt: Callable[[str, dict[str, Any] | None], tuple[dict[str, Any] | None, dict[str, Any] | None]],
    looks_like_question_followup: Callable[[str, dict[str, Any] | None], bool],
    looks_like_practice_generation_request: Callable[[str], bool],
    active_decision: dict[str, Any] | None,
) -> SemanticRoutingResult | None:
    if looks_like_free_text_mcq_grading_request(user_message):
        return None
    if not suspended_stack:
        return None

    active_route = semantic_route_for_decision(active_decision)
    active_is_strong_match = active_route in {"submission", "followup", "practice_generation"}
    prefers_previous_object = _message_prefers_previous_object(user_message)

    if active_is_strong_match and not prefers_previous_object:
        return None

    best_candidate: tuple[
        dict[str, Any],
        dict[str, Any] | None,
        dict[str, Any] | None,
        dict[str, Any],
    ] | None = None
    for suspended_candidate in suspended_stack:
        candidate_question_context = question_context_from_active_object(suspended_candidate)
        candidate_action: dict[str, Any] | None = None
        if candidate_question_context is not None:
            candidate_action = await interpret_followup_action(user_message, candidate_question_context)
            candidate_decision = _decision_from_followup_action(
                action=candidate_action,
                active_object=suspended_candidate,
                user_message=user_message,
                question_context=candidate_question_context,
            )
            if candidate_decision is None:
                candidate_decision = _decision_from_fallback(
                    user_message=user_message,
                    active_object=suspended_candidate,
                    question_context=candidate_question_context,
                    resolve_submission_attempt=resolve_submission_attempt,
                    looks_like_question_followup=looks_like_question_followup,
                    looks_like_practice_generation_request=looks_like_practice_generation_request,
                )
        else:
            candidate_decision = _decision_from_active_learning_object(
                user_message=user_message,
                active_object=suspended_candidate,
            )

        if candidate_decision is None:
            continue

        candidate_route = semantic_route_for_decision(candidate_decision)
        candidate_next_action = str(candidate_decision.get("next_action") or "").strip()
        if (
            candidate_route not in {"submission", "followup", "practice_generation"}
            and candidate_next_action != "route_to_guide"
        ):
            continue

        best_candidate = (
            suspended_candidate,
            candidate_question_context,
            candidate_action if isinstance(candidate_action, dict) else None,
            candidate_decision,
        )
        if prefers_previous_object:
            break

    if best_candidate is None:
        return None

    suspended_candidate, candidate_question_context, candidate_action, candidate_decision = best_candidate
    candidate_route = semantic_route_for_decision(candidate_decision)
    # Resume a suspended question on a message that does NOT explicitly reference going
    # back only when it is a genuine SUBMISSION to that question (the answer itself
    # disambiguates which question is meant). A mere followup-shaped match — an extension /
    # new-knowledge question that loosely resembles a followup to a suspended question —
    # must NOT resume it: promoting it yields switch_to_new_object + route_to_followup_explainer,
    # which `_is_unresolved_switch_followup` then rejects as an unresolved switch ("can't
    # locate that question, resend it"). Such a question is answered on the current context /
    # open instead. Explicit back-reference (prefers_previous_object) still resumes either way.
    if prefers_previous_object or (not active_is_strong_match and candidate_route == "submission"):
        resumed_decision = _promote_suspended_candidate_decision(
            suspended_candidate=suspended_candidate,
            candidate_decision=candidate_decision,
            active_object=active_object,
        )
        resumed_active_object, resumed_stack = apply_active_object_transition(
            previous_active_object=active_object,
            previous_suspended_object_stack=suspended_stack,
            turn_semantic_decision=resumed_decision,
            resolved_active_object=suspended_candidate,
        )
        return SemanticRoutingResult(
            active_object=resumed_active_object,
            suspended_object_stack=resumed_stack,
            turn_semantic_decision=resumed_decision,
            question_context=candidate_question_context,
            followup_action=candidate_action,
        )
    return None


def _has_explicit_practice_generation_intent(user_message: str | None) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    if _has_question_explainer_intent(text):
        return False
    if any(marker in text for marker in _EXPLICIT_PRACTICE_GENERATION_MARKERS):
        return True
    return any(re.search(pattern, text) for pattern in _EXPLICIT_PRACTICE_GENERATION_PATTERNS)


def has_explicit_practice_generation_intent(user_message: str | None) -> bool:
    return _has_explicit_practice_generation_intent(user_message)


def _has_question_explainer_intent(user_message: str | None) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _QUESTION_EXPLAINER_MARKERS)


def _decision_from_fallback(
    *,
    user_message: str,
    active_object: dict[str, Any] | None,
    question_context: dict[str, Any] | None,
    resolve_submission_attempt: Callable[[str, dict[str, Any] | None], tuple[dict[str, Any] | None, dict[str, Any] | None]],
    looks_like_question_followup: Callable[[str, dict[str, Any] | None], bool],
    looks_like_practice_generation_request: Callable[[str], bool],
) -> dict[str, Any]:
    if question_context is not None:
        _target_context, submission = resolve_submission_attempt(user_message, question_context)
        # 判分态单一权威收口 Step 4.6 (2026-06-24, live 第2轮揪出): 这条确定性降级保底原先
        # 对任何 resolve_submission_attempt 命中即 route_to_grading,对 LOW 置信(试探/推迟/未
        # 明确交卷,如"我猜A但你先别判")仍抽出答案判分,绕过 Step 4(守卫)/4.5(interpret backstop)。
        # 按 commander 设计"keep 但只对 HIGH 生效":只有 HIGH 置信真作答才走确定性判分保底
        # (保硬约束40);LOW fall through 到下方 followup/chat 检测,不凭空判分。
        if submission is not None and submission_confidence(user_message, question_context) != "low":
            relation: SemanticRelation = (
                "revise_answer_on_active_object"
                if _message_looks_like_revision(user_message)
                else "answer_active_object"
            )
            return build_turn_semantic_decision(
                relation_to_active_object=relation,
                next_action="route_to_grading",
                allowed_patch=_submission_allowed_patch(question_context, submission),
                confidence=0.62,
                reason="deterministic fallback 命中答题解析，作为语义降级保底。",
                active_object=active_object,
            )
        practice_request = looks_like_practice_generation_request(user_message)
        followup_request = looks_like_question_followup(user_message, question_context)
        if practice_request and (
            not followup_request or _has_explicit_practice_generation_intent(user_message)
        ):
            return build_turn_semantic_decision(
                relation_to_active_object="continue_same_learning_flow",
                next_action="route_to_generation",
                allowed_patch="set_active_object",
                confidence=0.58,
                reason="deterministic fallback 命中继续练题请求，作为语义降级保底。",
                target_object_ref=build_target_object_ref(active_object)
                or {"object_type": "question_set", "object_id": ""},
                active_object=active_object,
            )
        if followup_request:
            return build_turn_semantic_decision(
                relation_to_active_object="ask_about_active_object",
                next_action="route_to_followup_explainer",
                allowed_patch="no_state_change",
                confidence=0.55,
                reason="deterministic fallback 命中题目追问特征，作为语义降级保底。",
                active_object=active_object,
            )
        return build_turn_semantic_decision(
            relation_to_active_object=(
                "temporary_detour" if active_object is not None else "out_of_scope_chat"
            ),
            next_action="route_to_general_chat",
            allowed_patch="no_state_change",
            confidence=0.52,
            reason="active question 存在，但当前输入未命中题目域 fallback，保守降到通用聊天。",
            active_object=active_object,
        )

    if _is_guide_active_object(active_object):
        decision = _decision_from_active_learning_object(
            user_message=user_message,
            active_object=active_object,
        )
        if decision is not None:
            return decision

    if _is_open_chat_active_object(active_object):
        return _decision_from_active_open_chat_object(
            user_message=user_message,
            active_object=active_object,
        )

    if looks_like_practice_generation_request(user_message):
        return build_turn_semantic_decision(
            relation_to_active_object="switch_to_new_object",
            next_action="route_to_generation",
            allowed_patch="set_active_object",
            confidence=0.66,
            reason="当前无 active object，deterministic fallback 命中新练题请求。",
            target_object_ref={"object_type": "question_set", "object_id": ""},
        )

    return build_turn_semantic_decision(
        relation_to_active_object="out_of_scope_chat",
        next_action="route_to_general_chat",
        allowed_patch="no_state_change",
        confidence=0.5,
        reason="当前无 active object，默认落到通用聊天。",
    )


def _decision_from_ambiguity_gate(
    *,
    user_message: str,
    active_object: dict[str, Any] | None,
    suspended_stack: list[dict[str, Any]],
    question_context: dict[str, Any] | None,
    llm_decision: dict[str, Any] | None,
    resolve_submission_attempt: Callable[[str, dict[str, Any] | None], tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> dict[str, Any] | None:
    if _referenced_slot_overflows(user_message, question_context):
        return build_turn_semantic_decision(
            relation_to_active_object="uncertain",
            next_action="ask_clarifying_question",
            allowed_patch="no_state_change",
            confidence=0.34,
            reason="当前输入引用了超出 active object 槽位范围的编号，必须先澄清再执行。",
            active_object=active_object,
        )

    if (
        not _message_prefers_previous_object(user_message)
        and _has_multiple_parseable_question_candidates(
            user_message=user_message,
            active_object=active_object,
            suspended_stack=suspended_stack,
            resolve_submission_attempt=resolve_submission_attempt,
        )
    ):
        return build_turn_semantic_decision(
            relation_to_active_object="uncertain",
            next_action="ask_clarifying_question",
            allowed_patch="no_state_change",
            confidence=0.31,
            reason="当前输入可同时命中多个题目对象，不能在多候选间硬猜。",
            active_object=active_object,
        )

    if _is_low_signal_continuation(user_message):
        candidate_families = {
            family
            for family in (
                _active_object_family(active_object),
                *(_active_object_family(item) for item in suspended_stack),
            )
            if family
        }
        if len(candidate_families) >= 2:
            return build_turn_semantic_decision(
                relation_to_active_object="uncertain",
                next_action="ask_clarifying_question",
                allowed_patch="no_state_change",
                confidence=0.29,
                reason="低信号继续指令同时可能指向不同对象族，先澄清比误切更安全。",
                active_object=active_object,
            )

    normalized_decision = normalize_turn_semantic_decision(llm_decision, active_object=active_object)
    if normalized_decision is None:
        return None
    if (
        normalized_decision.get("next_action") in {"route_to_grading", "route_to_followup_explainer"}
        and float(normalized_decision.get("confidence") or 0.0) < 0.45
    ):
        return build_turn_semantic_decision(
            relation_to_active_object="uncertain",
            next_action="ask_clarifying_question",
            allowed_patch="no_state_change",
            confidence=0.3,
            reason="当前语义判定置信度过低，继续执行会带来错误副作用，先进入澄清。",
            active_object=active_object,
        )
    return None


def _promote_suspended_candidate_decision(
    *,
    suspended_candidate: dict[str, Any],
    candidate_decision: dict[str, Any],
    active_object: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_candidate_decision = normalize_turn_semantic_decision(
        candidate_decision,
        active_object=suspended_candidate,
    )
    if normalized_candidate_decision is None:
        raise ValueError("candidate decision must be valid")
    allowed_patch = list(normalized_candidate_decision.get("allowed_patch") or [])
    if "resume_suspended_object" not in allowed_patch:
        allowed_patch = ["resume_suspended_object", *allowed_patch]
    return build_turn_semantic_decision(
        relation_to_active_object="switch_to_new_object",
        next_action=str(normalized_candidate_decision["next_action"]),
        allowed_patch=allowed_patch,
        confidence=_normalize_confidence(
            normalized_candidate_decision.get("confidence"),
            default=0.0,
        ),
        reason=(
            str(normalized_candidate_decision.get("reason") or "").strip()
            or "stack 顶部对象比当前 active object 更匹配当前输入。"
        ),
        target_object_ref=build_target_object_ref(suspended_candidate),
        active_object=active_object,
    )


def _normalize_object_id(
    raw_object_id: Any,
    question_context: dict[str, Any] | None,
    object_type: str,
) -> str:
    explicit = str(raw_object_id or "").strip()
    if explicit:
        return explicit
    normalized = normalize_question_followup_context(question_context)
    if normalized is None:
        return ""
    question_id = str(normalized.get("question_id") or "").strip()
    if question_id:
        return question_id
    items = normalized.get("items") or []
    item_ids = [
        str(item.get("question_id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("question_id") or "").strip()
    ]
    if object_type == "question_set" and item_ids:
        return f"question_set:{item_ids[0]}"
    if object_type == "single_question" and item_ids:
        return item_ids[0]
    return object_type


def _build_question_scope(question_context: dict[str, Any]) -> dict[str, Any]:
    items = question_context.get("items") or []
    question_ids = [
        str(item.get("question_id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("question_id") or "").strip()
    ]
    if len(items) > 1:
        return {
            "question_ids": question_ids,
            "question_count": len(items),
        }
    return {
        "question_id": str(question_context.get("question_id") or "").strip(),
    }


def _normalize_target_object_ref(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    object_type = str(raw.get("object_type") or "").strip().lower()
    object_id = str(raw.get("object_id") or "").strip()
    if object_type and object_type not in SUPPORTED_ACTIVE_OBJECT_TYPES:
        return None
    return {"object_type": object_type, "object_id": object_id}


def _normalize_allowed_patch(raw: Any) -> list[str]:
    values = raw if isinstance(raw, list) else [raw]
    normalized = [
        str(value or "").strip()
        for value in values
        if str(value or "").strip() in SEMANTIC_ALLOWED_PATCHES
    ]
    return normalized or ["no_state_change"]


def _normalize_confidence(raw: Any, *, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _active_object_family(active_object: dict[str, Any] | None) -> str:
    normalized = normalize_active_object(active_object)
    if normalized is None:
        return ""
    object_type = str(normalized.get("object_type") or "").strip()
    if object_type in QUESTION_ACTIVE_OBJECT_TYPES:
        return "question"
    if object_type in GUIDE_ACTIVE_OBJECT_TYPES:
        return "guide"
    if object_type in SESSION_ACTIVE_OBJECT_TYPES:
        return "open_chat"
    return ""


def _is_low_signal_continuation(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return text in _LOW_SIGNAL_CONTINUATION_MARKERS


def _has_multiple_parseable_question_candidates(
    *,
    user_message: str,
    active_object: dict[str, Any] | None,
    suspended_stack: list[dict[str, Any]],
    resolve_submission_attempt: Callable[[str, dict[str, Any] | None], tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> bool:
    parseable_count = 0
    for candidate in [active_object, *suspended_stack]:
        question_context = question_context_from_active_object(candidate)
        if question_context is None:
            continue
        _target_context, submission = resolve_submission_attempt(user_message, question_context)
        if submission is None:
            continue
        parseable_count += 1
        if parseable_count >= 2:
            return True
    return False


def _referenced_slot_overflows(
    message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    normalized = normalize_question_followup_context(question_context)
    if normalized is None:
        return False
    referenced_index = _referenced_slot_index(message)
    if referenced_index <= 0:
        return False
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    item_count = len(items) if items else 1
    return referenced_index > item_count


def _referenced_slot_index(message: str) -> int:
    text = str(message or "").strip()
    if not text:
        return 0
    digit_match = re.search(r"第\s*(\d{1,2})\s*(?:题|个|个吧|个答案)?", text)
    if digit_match:
        return int(digit_match.group(1))
    zh_match = re.search(r"第\s*([一二两三四五六七八九十])\s*(?:题|个|个吧|个答案)?", text)
    if zh_match:
        return _ORDINAL_INDEX_MAP.get(zh_match.group(1), 0)
    if text.endswith("个吧") or text.endswith("个") or text.endswith("题吧") or text.endswith("题"):
        leading = text[0]
        return _ORDINAL_INDEX_MAP.get(leading, 0)
    return 0


def _coerce_version(raw: Any, *, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _message_looks_like_revision(message: str) -> bool:
    text = str(message or "").strip().lower()
    return any(marker in text for marker in ("改", "改成", "改为", "更正", "修正", "订正"))


def _message_prefers_previous_object(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(marker in text for marker in _PREVIOUS_OBJECT_MARKERS) or bool(
        _PREVIOUS_OBJECT_REFERENCE_RE.search(text)
    )


# Explicit reference back to an EARLIER / different question by position / ordinal /
# attribute ("回到我最开始做错的那道题" / "最早那道" / "第一道" / "上一道" / "我刚才做错的那道").
# This is a STABLE linguistic back-reference signal — it only DETECTS that the learner
# means a historical (non-active) question; WHICH question is still resolved by the
# context-continuous main LLM from shared history (is_unresolved_switch route). It must
# NOT match a reference to the CURRENT active question ("这道题再讲讲").
_HISTORICAL_QUESTION_BACKREF_RE = re.compile(
    r"(最开始|最早|一开始|开头|最先)(那)?(道|题|一道|一题)"
    r"|第[一1](道|题)"
    r"|上(一|上)?(道|题)"
    r"|(回到|回去|返回).{0,10}(最开始|最早|开头|第[一1]|上一|之前|刚才|前面|做错|答错|错的|那道|那题)"
    r"|(我)?(刚才|之前|先前|最先|一开始)?(做错|答错|选错)(的)?(那)?(道|题|一道|一题)"
)
_ACTIVE_QUESTION_SELF_REF_MARKERS = ("这道", "这题", "这一道", "这一题", "当前这", "本题")


def _message_is_historical_question_backreference(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    if any(marker in text for marker in _ACTIVE_QUESTION_SELF_REF_MARKERS):
        return False
    return bool(_HISTORICAL_QUESTION_BACKREF_RE.search(text))


def _is_guide_active_object(active_object: dict[str, Any] | None) -> bool:
    normalized = normalize_active_object(active_object)
    return bool(normalized) and str(normalized.get("object_type") or "").strip() in GUIDE_ACTIVE_OBJECT_TYPES


def _is_open_chat_active_object(active_object: dict[str, Any] | None) -> bool:
    normalized = normalize_active_object(active_object)
    return bool(normalized) and str(normalized.get("object_type") or "").strip() in SESSION_ACTIVE_OBJECT_TYPES


def _decision_from_active_open_chat_object(
    *,
    user_message: str,
    active_object: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_active_object = normalize_active_object(active_object)
    if looks_like_practice_generation_request(user_message):
        return build_turn_semantic_decision(
            relation_to_active_object="switch_to_new_object",
            next_action="route_to_generation",
            allowed_patch="set_active_object",
            confidence=0.7,
            reason="当前 session 仍在开放对话，但输入明显转入新练题对象。",
            active_object=normalized_active_object,
        )
    return build_turn_semantic_decision(
        relation_to_active_object="continue_same_learning_flow",
        next_action="route_to_general_chat",
        allowed_patch="no_state_change",
        confidence=0.58,
        reason="当前输入继续围绕当前 session 的开放对话对象展开。",
        active_object=normalized_active_object,
    )


def _accepted_recent_practice_offer_action(
    user_message: str,
    history_context: str,
) -> dict[str, Any] | None:
    if not _history_contains_recent_practice_offer(history_context):
        return None

    compact_message = _compact_message(user_message)
    if compact_message in _SHORT_PRACTICE_OFFER_ACCEPTANCES or _REPEATED_PRACTICE_OFFER_RE.search(
        str(user_message or "").strip()
    ):
        return {
            "intent": "generate_more_questions",
            "confidence": 0.84,
            "answers": [],
            "topic": _ACCEPTED_PRACTICE_OFFER_TOPIC,
            "reason": "用户正在接受最近一轮出题/同考点巩固邀请，应继续进入练题生成 authority。",
        }
    return None


def _history_contains_recent_practice_offer(history_context: str) -> bool:
    recent_context = str(history_context or "").strip()[-1600:]
    if not recent_context:
        return False
    return bool(_RECENT_PRACTICE_OFFER_RE.search(recent_context))


def _compact_message(message: str) -> str:
    return re.sub(r"[\s，。！？、,.!?:：；;]+", "", str(message or "").strip().lower())


def _message_mentions_guide(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _GUIDE_CONTINUATION_MARKERS)


def _message_looks_like_learning_question(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return "?" in text or "？" in text or any(
        marker in text for marker in ("为什么", "怎么", "如何", "讲解", "解释", "这页", "这个知识点")
    )


def _looks_like_guide_detour(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _GUIDE_DETOUR_MARKERS)


def _same_active_object(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    normalized_left = normalize_active_object(left)
    normalized_right = normalize_active_object(right)
    if normalized_left is None or normalized_right is None:
        return False
    return (
        normalized_left.get("object_type") == normalized_right.get("object_type")
        and normalized_left.get("object_id") == normalized_right.get("object_id")
    )


def _push_suspended_object(
    suspended_stack: list[dict[str, Any]],
    active_object: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized_active_object = normalize_active_object(active_object)
    if normalized_active_object is None:
        return normalize_suspended_object_stack(suspended_stack)
    next_stack = [normalized_active_object]
    for item in normalize_suspended_object_stack(suspended_stack):
        if _same_active_object(item, normalized_active_object):
            continue
        next_stack.append(item)
        if len(next_stack) >= 3:
            break
    return next_stack


def _remove_from_suspended_stack(
    suspended_stack: list[dict[str, Any]],
    target_object_ref: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(target_object_ref, dict):
        return normalize_suspended_object_stack(suspended_stack)
    object_type = str(target_object_ref.get("object_type") or "").strip().lower()
    object_id = str(target_object_ref.get("object_id") or "").strip()
    if not object_type or not object_id:
        return normalize_suspended_object_stack(suspended_stack)
    filtered: list[dict[str, Any]] = []
    for item in normalize_suspended_object_stack(suspended_stack):
        if (
            str(item.get("object_type") or "").strip().lower() == object_type
            and str(item.get("object_id") or "").strip() == object_id
        ):
            continue
        filtered.append(item)
    return filtered[:3]


def _resume_from_suspended_stack(
    *,
    suspended_stack: list[dict[str, Any]],
    target_object_ref: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    normalized_stack = normalize_suspended_object_stack(suspended_stack)
    if not normalized_stack:
        return None, []
    object_type = str((target_object_ref or {}).get("object_type") or "").strip().lower()
    object_id = str((target_object_ref or {}).get("object_id") or "").strip()
    if not object_type or not object_id:
        return normalized_stack[0], normalized_stack[1:]

    resumed: dict[str, Any] | None = None
    remaining: list[dict[str, Any]] = []
    for item in normalized_stack:
        if resumed is None and (
            str(item.get("object_type") or "").strip().lower() == object_type
            and str(item.get("object_id") or "").strip() == object_id
        ):
            resumed = item
            continue
        remaining.append(item)
    return resumed, remaining[:3]


def _submission_allowed_patch(
    question_context: dict[str, Any] | None,
    action_or_submission: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(action_or_submission, dict):
        return ["update_answer_slot"]
    answers = action_or_submission.get("answers")
    items = (question_context or {}).get("items") or []
    if isinstance(answers, list) and len(answers) > 1:
        return ["append_answer_slots"]
    if len(items) > 1 and str(action_or_submission.get("intent") or "").strip() == "answer_questions":
        return ["append_answer_slots"]
    return ["update_answer_slot"]


__all__ = [
    "SUPPORTED_ACTIVE_OBJECT_TYPES",
    "SEMANTIC_ALLOWED_PATCHES",
    "SEMANTIC_NEXT_ACTIONS",
    "SEMANTIC_RELATIONS",
    "SemanticRoutingResult",
    "build_question_active_object",
    "apply_active_object_transition",
    "build_target_object_ref",
    "build_turn_semantic_decision",
    "build_active_object_from_question_context",
    "infer_question_active_object_type",
    "normalize_active_object",
    "normalize_suspended_object_stack",
    "normalize_turn_semantic_decision",
    "question_context_from_active_object",
    "resolve_question_semantic_routing",
    "resolve_turn_semantic_decision",
    "semantic_route_for_decision",
    "turn_semantic_decision_route",
]
