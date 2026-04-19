from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Awaitable, Callable, Literal

from deeptutor.services.question_followup import (
    followup_action_route,
    interpret_question_followup_action,
    looks_like_question_followup,
    normalize_question_followup_context,
    resolve_submission_attempt,
)
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


QuestionActiveObjectType = Literal["question_set", "single_question"]
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


QUESTION_ACTIVE_OBJECT_TYPES = {"question_set", "single_question"}
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
class QuestionObjectTransition:
    active_object: dict[str, Any] | None
    suspended_object_stack: list[dict[str, Any]]
    question_context: dict[str, Any] | None


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
) -> dict[str, Any] | None:
    normalized = normalize_question_followup_context(question_context)
    if normalized is None:
        return None

    prior = normalize_active_object(prior_active_object)
    object_type = infer_question_active_object_type(normalized)
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


def build_active_object_from_question_context(
    question_context: dict[str, Any] | None,
    *,
    source_turn_id: str = "",
    previous_active_object: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    return build_question_active_object(
        question_context,
        prior_active_object=previous_active_object,
        source_turn_id=source_turn_id,
    )


def apply_question_object_transition(
    *,
    active_object: dict[str, Any] | None,
    suspended_object_stack: list[dict[str, Any]] | None,
    turn_semantic_decision: dict[str, Any] | None,
    candidate_question_context: dict[str, Any] | None = None,
    candidate_active_object: dict[str, Any] | None = None,
    source_turn_id: str = "",
) -> QuestionObjectTransition:
    current_active = normalize_active_object(active_object)
    current_stack = normalize_suspended_object_stack(suspended_object_stack)
    decision = normalize_turn_semantic_decision(turn_semantic_decision, active_object=current_active)
    normalized_candidate_context = normalize_question_followup_context(candidate_question_context)
    target_candidate = normalize_active_object(candidate_active_object)
    if target_candidate is None and normalized_candidate_context is not None:
        previous_object = _resolve_transition_target(
            active_object=current_active,
            suspended_object_stack=current_stack,
            target_object_ref=(decision or {}).get("target_object_ref"),
        )
        target_candidate = build_active_object_from_question_context(
            normalized_candidate_context,
            source_turn_id=source_turn_id,
            previous_active_object=previous_object or current_active,
        )

    next_active = current_active
    next_stack = list(current_stack)
    next_question_context = (
        normalized_candidate_context
        or question_context_from_active_object(current_active)
    )

    target_object = _resolve_transition_target(
        active_object=current_active,
        suspended_object_stack=current_stack,
        target_object_ref=(decision or {}).get("target_object_ref"),
    )
    allowed_patch = list((decision or {}).get("allowed_patch") or [])

    if "resume_suspended_object" in allowed_patch and target_object is not None:
        resumed_active = target_candidate if target_candidate is not None else target_object
        next_stack = _remove_object_from_stack(current_stack, target_object)
        if current_active is not None and not _same_active_object(current_active, resumed_active):
            next_stack = _prepend_stack_object(next_stack, current_active)
        next_active = resumed_active
        next_question_context = (
            normalized_candidate_context
            or question_context_from_active_object(resumed_active)
        )
        return QuestionObjectTransition(
            active_object=next_active,
            suspended_object_stack=next_stack,
            question_context=next_question_context,
        )

    if target_candidate is not None:
        next_active = target_candidate
        next_question_context = (
            normalized_candidate_context
            or question_context_from_active_object(target_candidate)
        )
        if current_active is not None and not _same_active_object(current_active, target_candidate):
            if any(
                patch in allowed_patch
                for patch in ("set_active_object", "suspend_current_object")
            ):
                next_stack = _prepend_stack_object(current_stack, current_active)
        return QuestionObjectTransition(
            active_object=next_active,
            suspended_object_stack=next_stack,
            question_context=next_question_context,
        )

    if target_object is not None:
        next_active = target_object
        next_question_context = question_context_from_active_object(target_object)

    return QuestionObjectTransition(
        active_object=next_active,
        suspended_object_stack=next_stack,
        question_context=next_question_context,
    )


async def resolve_turn_semantic_decision(
    user_message: str,
    active_object: dict[str, Any] | None,
    *,
    history_context: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_active_object = normalize_active_object(active_object)
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

    llm_action: dict[str, Any] | None = followup_action
    if question_context is not None and llm_action is None:
        llm_action = await interpret_followup_action(user_message, question_context)

    llm_decision = _decision_from_followup_action(
        action=llm_action,
        active_object=active_object,
        user_message=user_message,
        question_context=question_context,
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
    if llm_decision is not None and llm_route in {"submission", "followup", "practice_generation"}:
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
    if prefers_previous_object or not active_is_strong_match:
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
        if submission is not None:
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
        if looks_like_question_followup(user_message, question_context):
            return build_turn_semantic_decision(
                relation_to_active_object="ask_about_active_object",
                next_action="route_to_followup_explainer",
                allowed_patch="no_state_change",
                confidence=0.55,
                reason="deterministic fallback 命中题目追问特征，作为语义降级保底。",
                active_object=active_object,
            )
        if looks_like_practice_generation_request(user_message):
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
    return any(marker in text for marker in _PREVIOUS_OBJECT_MARKERS)


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
