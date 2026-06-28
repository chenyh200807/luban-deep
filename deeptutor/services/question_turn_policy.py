"""Question-Turn Policy Kernel (QTPK) — physical home of question-turn policy.

This module is the single physical place that will own the five question-turn
facts of the unified ``/api/v1/ws`` path:

  1. ``question_lifecycle_scene`` — the lifecycle scene of the turn.
  2. ``turn_semantic_decision`` — relation + next_action (suspend/resume/demote).
  3. submission **intent + evidence** — what the learner submitted, with span.
  4. **current object identity** — which active object the turn is about.
  5. **active-object patch** — the suspend/resume/demote transition applied.

QTPK does NOT reimplement any of those facts. It is a *read-only forwarder* over
the already-canonical resolvers, collapsing the policy that is currently parsed
three times (``turn_runtime.start_turn`` mode-selection, ``turn_runtime._run_turn``
authoritative restore, and ``orchestrator._resolve_semantic_routing``) into one
resolution. The canonical resolvers it forwards to (and never re-derives):

  * ``deeptutor.services.semantic_router.resolve_question_semantic_routing``
    — relation/submission semantic decision.
  * ``deeptutor.services.semantic_router.apply_active_object_transition``
    — the suspend/resume/demote canonical (active-object patch).
  * ``deeptutor.services.question_lifecycle_skills.resolve_question_lifecycle_scene_decision``
    — lifecycle scene canonical.
  * ``deeptutor.services.active_object_builder`` — active object construction.
  * ``deeptutor.services.question_followup`` — followup context/action normalize.

GOD-OBJECT RED LINE (enforced by ``scripts/check_qtpk_import_allowlist.py``):
QTPK MUST NOT import or own a sixth class of fact. It is forbidden to import any
LLM client, grading kernel, RAG / retrieval, learner-state, reveal/answer-reveal,
terminal-result/visible-output, stream/transport, orchestrator, or turn_runtime
module. QTPK owns ONLY the five facts above; reveal/response_mode/practice
strategy/terminal/score are NOT QTPK facts.

S1 status: this module now **physically owns** the submission-intent resolver
``_resolve_question_followup_context_and_action`` (and its private helper cluster)
plus the active-object identity helpers, moved verbatim (zero behavior change)
from ``turn_runtime``. ``turn_runtime`` imports them back so every existing
callsite is unchanged; the differential parity net in
``tests/services/test_qtpk_differential.py`` asserts the QTPK path produces the
same submission intent + evidence as the pre-move ``turn_runtime`` path.
``resolve_turn_policy`` is an S1 **partial** forwarder: it forwards the one
resolver S1 physically moved (submission intent + evidence) into the envelope.
The full five-fact assembly (scene + semantic decision + active-object patch
wired together) is built in S2+; the other envelope fields stay at their empty
defaults until then.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from deeptutor.services.active_object_builder import (
    build_active_object_from_question_context,
    extract_question_context_from_active_object,
    normalize_active_object,
)
from deeptutor.services.question_followup import (
    batch_answer_action_for_numbered_single,
    followup_action_route,
    interpret_question_followup_action,
    looks_like_practice_generation_request,
    looks_like_question_followup,
    normalize_question_followup_context,
    reset_question_submission_state,
    resolve_submission_attempt,
    submission_confidence,
)
from deeptutor.services.question_lifecycle_skills import (
    case_grading_context_from_full_submission,
    looks_like_free_text_mcq_grading_request,
    looks_like_free_text_mcq_question_surface,
    looks_like_full_case_answer_submission,
    mcq_grading_context_from_full_submission,
    split_full_case_answer_submission,
)
from deeptutor.services.semantic_router import (
    has_explicit_practice_generation_intent,
)


@dataclass(frozen=True)
class TurnPolicyDecision:
    """Immutable envelope of the five question-turn facts QTPK owns.

    Every field mirrors an already-canonical control-plane fact; QTPK only
    forwards the canonical resolvers' output into this envelope. It introduces
    no sixth fact (no reveal / response_mode / practice strategy / terminal /
    score). All fields default to an empty value so the S0 skeleton can build an
    empty envelope without implying any decision.
    """

    # Current object identity (which active object this turn is about).
    active_object: dict[str, Any] | None = None
    # Active-object patch result: the suspended-object stack after transition.
    suspended_object_stack: list[dict[str, Any]] = field(default_factory=list)
    # Relation + next_action (suspend/resume/demote) canonical decision.
    turn_semantic_decision: dict[str, Any] | None = None
    # Submission intent + evidence: the normalized followup context.
    question_followup_context: dict[str, Any] | None = None
    # Submission next action derived alongside the followup context.
    question_followup_action: dict[str, Any] | None = None
    # Lifecycle scene of the turn (string scene name).
    lifecycle_scene: str | None = None
    # Full lifecycle scene decision envelope (scene + supporting fields).
    scene_decision: dict[str, Any] | None = None

    @property
    def lifecycle_state(self) -> dict[str, Any] | None:
        """READ-ONLY explicit question lifecycle state, purely derived from the
        envelope's already-canonical facts (active_object + suspended stack). NOT a
        sixth fact — holds no new truth. ``None`` for non-question objects. See
        ``derive_question_lifecycle_state``."""

        return derive_question_lifecycle_state(
            active_object=self.active_object,
            suspended_object_stack=self.suspended_object_stack,
        )


# --------------------------------------------------------------------------- #
# M1: explicit question lifecycle_state — READ-ONLY derivation (no sixth fact). #
# --------------------------------------------------------------------------- #
#
# The question-turn lifecycle FSM already exists IMPLICITLY: the per-item state of
# a question instance is fully determined by the already-canonical facts QTPK owns
# (object_type + state_snapshot.items[].{user_answer, is_correct,
# construction_grading_result} + scene + suspended_object_stack). This block names
# it EXPLICITLY as a pure derivation — it holds NO new truth (god-object red line:
# per-item progress is READ from items[].grading fields, never stored), so it is
# not a sixth QTPK fact. It exists for diagnostic value (shadow parity vs the
# implicit object_type+scene classification) and as the assertable anchor M2/M3
# collapse against. Zero behavior: assertions are observe-only (never fail-close).

LIFECYCLE_PRESENTED = "presented"  # 未答 (I3: 答案不泄)
LIFECYCLE_ATTEMPTED = "attempted"  # 已答待判 (I1: 作答锚==学生所见呈现面)
LIFECYCLE_GRADED = "graded"  # 已判 (score 进 turn receipt 非 session truth)
LIFECYCLE_SUSPENDED = "suspended"  # 挂起 (I2: 回指锚唯一身份, task#14)

# Only these object_types are question instances with a lifecycle. Non-question
# objects (open_chat_topic / guide_page / study_plan / clarification) have NO
# question lifecycle → derivation returns None (M2 will route them family-first).
_QUESTION_LIFECYCLE_OBJECT_TYPES = frozenset(
    {"single_question", "question_set", "open_world_question"}
)


def _item_is_graded(item: dict[str, Any]) -> bool:
    if item.get("is_correct") is not None:
        return True
    grading_result = item.get("construction_grading_result")
    return isinstance(grading_result, dict) and bool(grading_result)


def _item_is_attempted(item: dict[str, Any]) -> bool:
    return bool(str(item.get("user_answer") or "").strip())


def _derive_item_lifecycle_state(
    item: dict[str, Any],
    *,
    object_type: str,
) -> tuple[str, bool]:
    """Return (state, graded_pending) for ONE question item, READ-only.

    graded_pending = open_world question that has a learner attempt but no verdict
    yet (is_correct is None and no construction_grading_result) — the ATTEMPTED↔
    GRADED substate where a RAG/open-world judgment is still pending. It is a flag
    ON the ATTEMPTED state, not a fifth flat state.
    """

    if not isinstance(item, dict):
        return LIFECYCLE_PRESENTED, False
    if _item_is_graded(item):
        return LIFECYCLE_GRADED, False
    if _item_is_attempted(item):
        graded_pending = object_type == "open_world_question"
        return LIFECYCLE_ATTEMPTED, graded_pending
    return LIFECYCLE_PRESENTED, False


def _summarize_item_states(item_states: list[str]) -> str:
    """Summary state of a set from its per-item states (per-item array is the
    load-bearing dimension; this summary is convenience only)."""

    if not item_states:
        return LIFECYCLE_PRESENTED
    if all(state == LIFECYCLE_GRADED for state in item_states):
        return LIFECYCLE_GRADED
    if any(state in (LIFECYCLE_ATTEMPTED, LIFECYCLE_GRADED) for state in item_states):
        return LIFECYCLE_ATTEMPTED
    return LIFECYCLE_PRESENTED


def derive_question_lifecycle_state(
    *,
    active_object: dict[str, Any] | None,
    suspended_object_stack: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """READ-ONLY derivation of the active question object's lifecycle state.

    Returns ``None`` for non-question objects (open_chat_topic / guide_page /
    study_plan / clarification) and when there is no active question — those have
    no question lifecycle. For a question object returns a pure-derived envelope::

        {
          "object_type": "question_set",
          "state": "attempted",          # summary of the active object
          "graded_pending": False,        # open_world awaiting verdict
          "items": [{"question_id", "state", "graded_pending"}, ...],  # per-item
          "suspended": [{"object_type", "object_id"}, ...],  # SUSPENDED objects (I2)
        }

    NO new truth is held: per-item state is READ from
    items[].{user_answer, is_correct, construction_grading_result}; SUSPENDED is
    READ from the suspended_object_stack. This is the single derivation authority;
    ``TurnPolicyDecision.lifecycle_state`` forwards it.
    """

    normalized = normalize_active_object(active_object)
    if not isinstance(normalized, dict):
        return None
    object_type = str(normalized.get("object_type") or "").strip()
    if object_type not in _QUESTION_LIFECYCLE_OBJECT_TYPES:
        return None
    context = extract_question_context_from_active_object(normalized) or {}
    raw_items = context.get("items")
    items = [it for it in raw_items if isinstance(it, dict)] if isinstance(raw_items, list) else []

    per_item: list[dict[str, Any]] = []
    if items:
        for item in items:
            state, graded_pending = _derive_item_lifecycle_state(item, object_type=object_type)
            per_item.append(
                {
                    "question_id": str(item.get("question_id") or "").strip(),
                    "state": state,
                    "graded_pending": graded_pending,
                }
            )
        summary_state = _summarize_item_states([entry["state"] for entry in per_item])
        graded_pending = any(entry["graded_pending"] for entry in per_item)
    else:
        # single_question / open_world_question: the state_snapshot itself is the item.
        summary_state, graded_pending = _derive_item_lifecycle_state(
            context, object_type=object_type
        )
        per_item = [
            {
                "question_id": str(context.get("question_id") or "").strip(),
                "state": summary_state,
                "graded_pending": graded_pending,
            }
        ]

    suspended: list[dict[str, Any]] = []
    for entry in suspended_object_stack or []:
        ref = _active_object_ref(entry)
        if ref.get("object_type") or ref.get("object_id"):
            suspended.append(ref)

    return {
        "object_type": object_type,
        "state": summary_state,
        "graded_pending": graded_pending,
        "items": per_item,
        "suspended": suspended,
    }


def _normalize_question_followup_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    intent = str(raw.get("intent") or "").strip()
    if not intent:
        return None
    return {
        "intent": intent,
        "confidence": raw.get("confidence"),
        "preserve_other_answers": bool(raw.get("preserve_other_answers", False)),
        "answers": raw.get("answers") if isinstance(raw.get("answers"), list) else [],
        "reason": str(raw.get("reason") or "").strip(),
    }


def _active_object_ref(active_object: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(active_object, dict):
        return {}
    return {
        "object_type": str(active_object.get("object_type") or "").strip(),
        "object_id": str(active_object.get("object_id") or "").strip(),
    }


def _same_active_object_identity(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> bool:
    normalized_left = normalize_active_object(left)
    normalized_right = normalize_active_object(right)
    if not isinstance(normalized_left, dict) or not isinstance(normalized_right, dict):
        return False
    return (
        str(normalized_left.get("object_type") or "").strip()
        == str(normalized_right.get("object_type") or "").strip()
        and str(normalized_left.get("object_id") or "").strip()
        == str(normalized_right.get("object_id") or "").strip()
    )


def _message_references_stored_question_set_item(
    message: str,
    stored_question_context: dict[str, Any] | None,
) -> bool:
    """True if ``message`` references an item of the stored batch question_set by ordinal
    ("第N题"), via the single ordinal→item authority
    (``question_followup.requested_question_item_index``, same one the submission path uses).

    Used by the turn-start suspend guard to NOT demote an active batch set into the
    suspended stack when the user is actually referring to one of its items (task#14):
    keeping the set in active_object lets the scene low-information gate anchor "第N题".
    """

    if not stored_question_context:
        return False
    try:
        from deeptutor.services.question_followup import (  # noqa: WPS433
            requested_question_item_index,
        )
    except Exception:
        return False
    return requested_question_item_index(message, stored_question_context) is not None


def _message_requests_active_mcq_represent(
    message: str,
    stored_question_context: dict[str, Any] | None,
) -> bool:
    """True if ``message`` explicitly asks to re-present / reshuffle the stored active
    MCQ ("选项重新排列一下" / "把abcd换个顺序重新给我看"), via the single re-present
    intent authority (``question_followup.message_has_represent_request_intent`` — the
    same markers ``build_canonical_represent_response`` consumes).

    Used by the turn-start suspend guard to NOT demote the active MCQ into the suspended
    stack when the learner is referencing it for a re-present (#287). Without this, the
    demote guard treats the re-present turn as "moved on", pushes the MCQ to the suspended
    stack and surfaces an open_chat_topic as active_object → the deterministic re-present
    short-circuit fail-safes (no active choice MCQ in context) and the free LLM hallucinates
    a different question. Mirror of the task#14 ordinal carve-out
    (``_message_references_stored_question_set_item``): same shape ("this turn references the
    active object → keep it active"), reusing an existing single authority, not a new gate.
    """

    if not stored_question_context:
        return False
    try:
        from deeptutor.services.question_followup import (  # noqa: WPS433
            _validate_single_mcq_snapshot,
            message_has_represent_request_intent,
        )
    except Exception:
        return False
    # Only a single-choice MCQ can be deterministically re-presented from
    # state_snapshot (build_canonical_represent_response 的同一 shape 权威
    # _validate_single_mcq_snapshot)。套题 batch / 非 choice / 学习计划等对象即便带
    # 残留 question context 也不在本 carve-out 范围 → 照常 demote（不误保活、不状态泄漏）。
    if _validate_single_mcq_snapshot(stored_question_context) is None:
        return False
    return message_has_represent_request_intent(message)


def _message_is_submission_for_stored_set(
    message: str,
    stored_question_context: dict[str, Any] | None,
) -> bool:
    """True if ``message`` is a real answer submission against the stored active
    question set (batch ``"q1 B q2 C q3 A"`` or bare ``"我选B"``), via the SINGLE
    submission-intent authority ``question_followup.resolve_submission_attempt`` —
    the same resolver the scene/grading path uses (not a new detector).

    Forward-reachability carve-out (S1, 2026-06-29): the turn-start suspend guard
    only carved out ordinal-reference (task#14) and re-present (#287) turns. A turn
    that ANSWERS the stored set was not recognized as "referencing the active
    object", so its active question_set was demoted into the suspended stack before
    the scene/grading dispatch could read it → the grading capability lost the set
    and re-presented the question instead of grading (live S1 0/6, confirmed via
    turn-start instrumentation: WILL_DEMOTE=True on every batch/bare answer turn).
    Same shape as the two existing carve-outs ("this turn references the active
    object → keep it active"): a real submission ⇒ do NOT demote, so the set flows
    into the grading dispatch. SEV-safe: keeping the set active does not grade
    anything by itself — what actually grades is still gated downstream by
    ``submission_confidence`` (LOW / 试探 / 推迟 / 回指 → ask_followup), so the
    凭空判分 / 倒诬 protections are untouched.
    """

    if not stored_question_context:
        return False
    try:
        from deeptutor.services.question_followup import (  # noqa: WPS433
            resolve_submission_attempt,
        )
    except Exception:
        return False
    _target, submission = resolve_submission_attempt(message, stored_question_context)
    return bool(submission)


def _context_has_reference_answer(context: dict[str, Any] | None) -> bool:
    def _item_has_reference_answer(item: dict[str, Any] | None) -> bool:
        if not isinstance(item, dict):
            return False
        if str(item.get("correct_answer") or "").strip():
            return True
        grading_key = item.get("grading_key")
        return isinstance(grading_key, dict) and bool(
            str(grading_key.get("correct_answer") or "").strip()
        )

    normalized = normalize_question_followup_context(context)
    if normalized is None:
        return False
    if _item_has_reference_answer(normalized):
        return True
    return any(_item_has_reference_answer(item) for item in normalized.get("items") or [])


def _merge_public_submission_with_authoritative_context(
    explicit_context: dict[str, Any] | None,
    candidate_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    explicit = normalize_question_followup_context(explicit_context)
    candidate = normalize_question_followup_context(candidate_context)
    if explicit is None or candidate is None:
        return None
    if _context_has_reference_answer(explicit) or not _context_has_reference_answer(candidate):
        return None

    explicit_items = explicit.get("items") or []
    candidate_items = candidate.get("items") or []
    if explicit_items and candidate_items:
        merged_items = [dict(item) for item in candidate_items]
        candidate_by_id = {
            str(item.get("question_id") or "").strip(): index
            for index, item in enumerate(candidate_items)
            if str(item.get("question_id") or "").strip()
        }
        for index, item in enumerate(explicit_items):
            target_index = candidate_by_id.get(str(item.get("question_id") or "").strip(), index)
            if target_index < 0 or target_index >= len(merged_items):
                continue
            user_answer = str(item.get("user_answer") or "").strip()
            if user_answer:
                merged_items[target_index]["user_answer"] = user_answer
        merged = dict(candidate)
        merged["items"] = merged_items
        merged_user_answer = str(explicit.get("user_answer") or "").strip()
        if merged_user_answer:
            merged["user_answer"] = merged_user_answer
        return normalize_question_followup_context(merged)

    if candidate_items:
        explicit_question_id = str(explicit.get("question_id") or "").strip()
        target_index: int | None = None
        if explicit_question_id:
            for index, item in enumerate(candidate_items):
                if str(item.get("question_id") or "").strip() == explicit_question_id:
                    target_index = index
                    break
        elif len(candidate_items) == 1:
            target_index = 0
        if target_index is not None and 0 <= target_index < len(candidate_items):
            merged = dict(candidate_items[target_index])
            user_answer = str(explicit.get("user_answer") or "").strip()
            if user_answer:
                merged["user_answer"] = user_answer
            return normalize_question_followup_context(merged)

    explicit_question_id = str(explicit.get("question_id") or "").strip()
    candidate_question_id = str(candidate.get("question_id") or "").strip()
    if explicit_question_id and candidate_question_id and explicit_question_id != candidate_question_id:
        return None
    merged = dict(candidate)
    user_answer = str(explicit.get("user_answer") or "").strip()
    if user_answer:
        merged["user_answer"] = user_answer
    return normalize_question_followup_context(merged)


def _practice_generation_action_for_explicit_request(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not looks_like_practice_generation_request(user_message):
        return None
    if not has_explicit_practice_generation_intent(user_message):
        return None
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return None
    _target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    if submission is not None:
        return None
    return {
        "intent": "generate_more_questions",
        "confidence": 0.86,
        "answers": [],
        "reason": "用户明确要求出题/选择题，应生成新题而不是批改当前题目。",
    }


def _looks_like_batch_correction_reference(user_message: str) -> bool:
    return bool(
        re.search(r"第\s*[0-9一二两三四五六七八九十]+\s*[题问]?", user_message)
        and ("不动" in user_message or "不变" in user_message or "不改" in user_message)
    )


def _normalize_question_identity_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s　，,。.!！?？；;：:、/／+\-—_（）()【】\[\]<>《》\"'“”‘’]+", "", text)


def _identity_ngrams(text: str, *, size: int = 2) -> set[str]:
    normalized = _normalize_question_identity_text(text)
    if len(normalized) < size:
        return set()
    return {normalized[index : index + size] for index in range(0, len(normalized) - size + 1)}


def _question_context_matches_free_text_surface(
    user_message: str,
    question_context: dict[str, Any],
) -> bool:
    message_identity = _normalize_question_identity_text(user_message)
    if not message_identity:
        return False

    question_identity = _normalize_question_identity_text(question_context.get("question"))
    if question_identity:
        if len(question_identity) >= 10 and question_identity in message_identity:
            return True
        question_grams = _identity_ngrams(question_identity)
        if question_grams:
            message_grams = _identity_ngrams(message_identity)
            overlap_ratio = len(question_grams & message_grams) / max(len(question_grams), 1)
            if overlap_ratio >= 0.55:
                return True
        return False

    options = question_context.get("options") if isinstance(question_context, dict) else None
    if not isinstance(options, dict) or not options:
        return False
    option_hits = 0
    for value in options.values():
        option_identity = _normalize_question_identity_text(value)
        if len(option_identity) >= 2 and option_identity in message_identity:
            option_hits += 1
    return option_hits >= min(2, len(options))


def _question_context_matches_current_surface(
    user_message: str,
    current_surface_context: dict[str, Any],
    question_context: dict[str, Any],
) -> bool:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return False
    current_type = str(current_surface_context.get("question_type") or "").strip().lower()
    if current_type == "case":
        return _case_context_matches_full_case_surface(user_message, normalized_context)
    return _question_context_matches_free_text_surface(user_message, normalized_context)


def _case_context_matches_full_case_surface(
    user_message: str,
    question_context: dict[str, Any],
) -> bool:
    message_identity = _normalize_question_identity_text(user_message)
    if not message_identity:
        return False

    def _has_current_question_anchor(value: Any) -> bool:
        text = str(value or "")
        return bool(
            "【问题" in text
            or "问题】" in text
            or re.search(r"问题\s*[：:]", text)
            or "？" in text
            or "?" in text
        )

    def _question_identity_values(context: dict[str, Any]):
        for key in ("question", "question_stem", "stem"):
            yield context.get(key)
        for item in context.get("items") or []:
            if not isinstance(item, dict):
                continue
            for key in ("question", "question_stem", "stem"):
                yield item.get(key)

    for value in _question_identity_values(question_context):
        if not _has_current_question_anchor(value):
            continue
        question_identity = _normalize_question_identity_text(value)
        if len(question_identity) >= 8 and (
            question_identity in message_identity or message_identity in question_identity
        ):
            return True
    return False


def _annotate_full_case_submission_context(
    user_message: str,
    question_context: dict[str, Any],
) -> dict[str, Any]:
    _stem, learner_answer = split_full_case_answer_submission(user_message)
    if not learner_answer.strip():
        return question_context
    updated = dict(question_context)
    updated["user_answer"] = learner_answer.strip()
    return updated


def _full_case_submission_action() -> dict[str, Any]:
    return {
        "intent": "answer_questions",
        "confidence": 0.92,
        "answers": [],
        "reason": "用户消息包含当前完整案例题题面和作答，优先进入案例批改。",
    }


def _current_surface_submission_context_and_action(
    user_message: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    mcq_context = mcq_grading_context_from_full_submission(user_message)
    if mcq_context is not None:
        submission_context, submission_action = _submission_action_for_user_message(
            user_message,
            mcq_context,
        )
        if submission_action is None and str(mcq_context.get("user_answer") or "").strip():
            submission_action = {
                "intent": "answer_questions",
                "confidence": 0.92,
                "answers": [
                    {
                        "question_id": str(mcq_context.get("question_id") or "").strip(),
                        "answer": str(mcq_context.get("user_answer") or "").strip(),
                    }
                ],
                "reason": "用户消息包含当前完整选择题题面和作答，优先进入批改。",
            }
        return submission_context or mcq_context, submission_action

    case_context = case_grading_context_from_full_submission(user_message)
    if case_context is not None:
        return case_context, _full_case_submission_action()

    return None, None


def _should_ignore_explicit_context_for_free_text_mcq(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return False
    if not (
        looks_like_free_text_mcq_grading_request(user_message)
        and looks_like_free_text_mcq_question_surface(user_message)
    ):
        return False
    return not _question_context_matches_free_text_surface(user_message, normalized_context)


def _submission_action_for_user_message(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return None, None
    items = normalized_context.get("items") or []
    if not items and _looks_like_batch_correction_reference(user_message):
        return normalized_context, None
    target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    if (
        items
        and _looks_like_batch_correction_reference(user_message)
        and isinstance(submission, dict)
        and submission.get("kind") != "batch"
    ):
        return normalized_context, None
    if not target_context or not submission:
        return normalized_context, None
    if submission.get("kind") == "ambiguous":
        return target_context, None
    if submission.get("kind") == "batch":
        return target_context, {
            "intent": "answer_questions",
            "confidence": 0.92,
            "answers": submission.get("answers") or [],
            "reason": "用户消息包含当前题组的可解析答案，优先进入批改。",
        }
    # object-continuity (E8 SEV-1): a numbered single answer to ONE item of a multi-item
    # set must be graded WITHIN the full set so the other items survive — returning the
    # narrowed single context here collapses the set at turn-start (before any capability
    # runs), so a later "第1题" binds to the 1-item set and grades the wrong question.
    # This is the single chokepoint above both tutorbot and deep_question grading paths.
    batch_action = batch_answer_action_for_numbered_single(submission, normalized_context)
    if batch_action is not None:
        return normalized_context, batch_action
    # 判分态单一权威收口 Step 5 (2026-06-24, 单一 chokepoint): 这是 submission action 的最上游
    # 构造点(decider map 自承"single chokepoint above both grading paths")。只有 HIGH 置信的
    # 裸单题作答才在此构造 answer_questions 提交动作;LOW 置信(试探/推迟,如"我猜A但你先别判",
    # submission_confidence 首子句非干净答案)不构造 → 下游不缓存 submission、不进判分。把 Step
    # 4.5/4.6 的逐路径 gate 收敛到单一最早点(未来新增下游消费路径自动继承,止 whack-a-mole);
    # per-path gate 保留作 defense-in-depth。保硬约束40:HIGH 裸作答仍构造提交动作必判。
    # batch / numbered-single 是显式结构化提交(=HIGH),走上面分支,不经此 gate。
    if submission_confidence(user_message, normalized_context) == "low":
        return normalized_context, None
    return target_context, {
        "intent": "answer_questions",
        "confidence": 0.92,
        "answers": [
            {
                "question_id": submission.get("question_id", ""),
                "answer": str(submission.get("answer") or "").strip(),
            }
        ],
        "reason": "用户消息包含当前题目的可解析答案，优先进入批改。",
    }


def _deterministic_followup_action_for_user_message(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return None
    _target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    if isinstance(submission, dict) and submission.get("kind") != "ambiguous":
        return None
    if not looks_like_question_followup(user_message, normalized_context):
        return None
    return {
        "intent": "ask_followup",
        "confidence": 0.88,
        "answers": [],
        "reason": "用户消息是围绕当前题目的稳定格式追问，不应被解释成改答或提交答案。",
    }


def _demote_submission_hint_when_deterministic_followup(
    user_message: str,
    question_context: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep an upstream action hint from overruling the submission authority."""

    if followup_action_route(action) != "submission":
        return action
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return action
    if submission_confidence(user_message, normalized_context) is not None:
        return action
    deterministic_followup_action = _deterministic_followup_action_for_user_message(
        user_message,
        normalized_context,
    )
    return deterministic_followup_action or action


def _has_ambiguous_submission_attempt(
    user_message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    normalized_context = normalize_question_followup_context(question_context)
    if normalized_context is None:
        return False
    _target_context, submission = resolve_submission_attempt(user_message, normalized_context)
    return isinstance(submission, dict) and submission.get("kind") == "ambiguous"


async def _resolve_question_followup_context_and_action(
    *,
    user_message: str,
    explicit_context: dict[str, Any] | None,
    explicit_action: dict[str, Any] | None,
    candidate_contexts: list[dict[str, Any] | None] | tuple[dict[str, Any] | None, ...] = (),
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_explicit = normalize_question_followup_context(explicit_context)
    normalized_action = _normalize_question_followup_action(explicit_action)
    free_text_mcq_grading_request = (
        looks_like_free_text_mcq_grading_request(user_message)
        and looks_like_free_text_mcq_question_surface(user_message)
    )
    full_case_answer_submission = looks_like_full_case_answer_submission(user_message)
    current_surface_context, current_surface_action = _current_surface_submission_context_and_action(
        user_message
    )
    if (
        current_surface_context is not None
        and normalized_explicit is not None
        and not _question_context_matches_current_surface(
            user_message,
            current_surface_context,
            normalized_explicit,
        )
    ):
        normalized_explicit = None
        normalized_action = None

    if _should_ignore_explicit_context_for_free_text_mcq(user_message, normalized_explicit):
        normalized_explicit = None
        normalized_action = None
    if (
        full_case_answer_submission
        and normalized_explicit is not None
        and not _case_context_matches_full_case_surface(user_message, normalized_explicit)
    ):
        normalized_explicit = None
        normalized_action = None
    if (
        normalized_explicit is not None
        and not (normalized_explicit.get("items") or [])
        and _looks_like_batch_correction_reference(user_message)
    ):
        normalized_explicit = None
        normalized_action = None

    if normalized_explicit is not None:
        for candidate in candidate_contexts:
            if (
                current_surface_context is not None
                and not _question_context_matches_current_surface(
                    user_message,
                    current_surface_context,
                    candidate or {},
                )
            ):
                continue
            merged = _merge_public_submission_with_authoritative_context(
                normalized_explicit,
                candidate,
            )
            if merged is not None:
                normalized_explicit = merged
                break
        if full_case_answer_submission:
            normalized_explicit = _annotate_full_case_submission_context(
                user_message,
                normalized_explicit,
            )
            return normalized_explicit, _full_case_submission_action()
        submission_context, submission_action = _submission_action_for_user_message(
            user_message,
            normalized_explicit,
        )
        if submission_action is not None:
            return submission_context or normalized_explicit, submission_action
        if _has_ambiguous_submission_attempt(user_message, normalized_explicit):
            return normalized_explicit, None
        if (
            followup_action_route(normalized_action) == "practice_generation"
            and not looks_like_practice_generation_request(user_message)
        ):
            normalized_action = None
        if normalized_action is None:
            practice_action = _practice_generation_action_for_explicit_request(
                user_message,
                normalized_explicit,
            )
            if practice_action is not None:
                normalized_explicit = (
                    reset_question_submission_state(normalized_explicit)
                    or normalized_explicit
                )
                normalized_action = practice_action
            else:
                deterministic_followup_action = _deterministic_followup_action_for_user_message(
                    user_message,
                    normalized_explicit,
                )
                if deterministic_followup_action is not None:
                    return normalized_explicit, deterministic_followup_action
                normalized_action = await interpret_question_followup_action(
                    user_message,
                    normalized_explicit,
                )
                if (
                    followup_action_route(normalized_action) == "practice_generation"
                    and not looks_like_practice_generation_request(user_message)
                ):
                    normalized_action = None
        deterministic_followup = looks_like_question_followup(user_message, normalized_explicit)
        if (
            deterministic_followup
            and followup_action_route(normalized_action) == "practice_generation"
            and not looks_like_practice_generation_request(user_message)
        ):
            normalized_action = None
        normalized_action = _demote_submission_hint_when_deterministic_followup(
            user_message,
            normalized_explicit,
            normalized_action,
        )
        return normalized_explicit, normalized_action

    for candidate in candidate_contexts:
        normalized_candidate = normalize_question_followup_context(candidate)
        if normalized_candidate is None:
            continue
        if (
            current_surface_context is not None
            and not _question_context_matches_current_surface(
                user_message,
                current_surface_context,
                normalized_candidate,
            )
        ):
            continue
        if (
            full_case_answer_submission
            and not _case_context_matches_full_case_surface(user_message, normalized_candidate)
        ):
            continue
        if full_case_answer_submission:
            normalized_candidate = _annotate_full_case_submission_context(
                user_message,
                normalized_candidate,
            )
            return normalized_candidate, _full_case_submission_action()
        if (
            free_text_mcq_grading_request
            and not _question_context_matches_free_text_surface(user_message, normalized_candidate)
        ):
            continue
        if (
            not (normalized_candidate.get("items") or [])
            and _looks_like_batch_correction_reference(user_message)
        ):
            continue
        submission_context, submission_action = _submission_action_for_user_message(
            user_message,
            normalized_candidate,
        )
        if submission_action is not None:
            return submission_context or normalized_candidate, submission_action
        if _has_ambiguous_submission_attempt(user_message, normalized_candidate):
            return normalized_candidate, None
        practice_action = _practice_generation_action_for_explicit_request(
            user_message,
            normalized_candidate,
        )
        if practice_action is not None:
            return (
                reset_question_submission_state(normalized_candidate) or normalized_candidate,
                practice_action,
            )
        deterministic_followup_action = _deterministic_followup_action_for_user_message(
            user_message,
            normalized_candidate,
        )
        if deterministic_followup_action is not None:
            return normalized_candidate, deterministic_followup_action
        deterministic_followup = looks_like_question_followup(user_message, normalized_candidate)
        candidate_action = await interpret_question_followup_action(
            user_message,
            normalized_candidate,
        )
        candidate_route = followup_action_route(candidate_action)
        if candidate_route == "submission":
            return normalized_candidate, candidate_action
        if candidate_route == "practice_generation" and looks_like_practice_generation_request(
            user_message
        ):
            return normalized_candidate, candidate_action
        if candidate_route == "followup" and deterministic_followup:
            return normalized_candidate, candidate_action
        if deterministic_followup:
            return normalized_candidate, None

    if current_surface_context is not None:
        return current_surface_context, current_surface_action

    return None, None


def grading_merge_needs_prior(result_active_object: dict[str, Any]) -> bool:
    """Decide whether the grading-merge patch needs to read the prior active_object.

    Byte-identical pre-check for the §6 SEV-1 套题防塌 merge: this replicates,
    verbatim, the three early-return conditions at the **top** of the pre-move
    ``turn_runtime._merge_grading_result_into_active_set`` that ran *before* the
    store read of the prior active_object. Those early-returns short-circuit the
    method without ever touching the store:

      1. ``normalize_active_object(result_active_object) is None`` → early return;
      2. ``extract_question_context_from_active_object(result_ao) is None`` → early return;
      3. ``len(result_ctx.get("items") or []) > 1`` → early return.

    Only when none of the three fire does the original method fall through to the
    ``store.get_active_object`` read. So this returns ``True`` (the prior must be
    read) iff:

        result_ao is not None AND result_ctx is not None AND len(result_items) <= 1

    and ``False`` otherwise (no store read needed — caller short-circuits exactly
    as the original early-return path did).

    PURE: no I/O. Lets the transport keep the store read **conditional** (the
    early-return path does not read the store), preserving byte-identical behavior
    — ``_safe_store_call`` can re-raise non-persistence errors, so an unconditional
    read on the early-return path would not be byte-identical.
    """
    result_ao = normalize_active_object(result_active_object)
    if result_ao is None:
        return False
    result_ctx = extract_question_context_from_active_object(result_ao)
    if result_ctx is None:
        return False
    result_items = result_ctx.get("items") or []
    if len(result_items) > 1:
        return False
    return True


def apply_grading_result_patch(
    *,
    prior_active_object: dict[str, Any] | None,
    result_active_object: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Active-object patch fact: keep a batch question_set alive across a single-item grading turn.

    §6 SEV-1 套题防塌安全带 (E8/E1 object-continuity). A grading turn judges ONE
    item; the capability emits a single-question active_object. If the prior
    canonical active_object is a multi-item set and this result is a single
    question that BELONGS to that set, merge the judged item back into the set (by
    question_id) and keep the SET as active_object — do not let turn-END collapse
    the set to the lone judged item. A genuine switch (the result question is not
    part of the prior set, e.g. a freshly generated question) passes through
    unchanged so real transitions still work.

    Single-authority: the only active_object identity writer is turn-START; this
    keeps turn-END from acting as a second, set-destroying writer.

    PURE (S2): the prior active_object is **passed in** by the caller (turn_runtime
    reads it from the store; that I/O stays in transport). This function performs
    no I/O — it only forwards the canonical ``active_object_builder`` resolvers and
    applies the merge decision branch logic verbatim (byte-identical to the
    pre-move ``turn_runtime._merge_grading_result_into_active_set``).
    """
    result_ao = normalize_active_object(result_active_object)
    if result_ao is None:
        return result_active_object
    result_ctx = extract_question_context_from_active_object(result_ao)
    if result_ctx is None:
        return result_active_object
    result_items = result_ctx.get("items") or []
    # Only single-item results can collapse a set; a result that is itself a set
    # is either a fresh generated set (switch) or already whole — leave it.
    if len(result_items) > 1:
        return result_active_object
    result_single = result_items[0] if result_items else result_ctx
    result_qid = str(result_single.get("question_id") or "").strip()

    prior_ao = prior_active_object
    normalized_prior_ao = normalize_active_object(prior_ao)
    prior_ctx = extract_question_context_from_active_object(prior_ao)
    prior_items = list((prior_ctx or {}).get("items") or [])
    decision = metadata.get("turn_semantic_decision")
    next_action = str((decision or {}).get("next_action") or "").strip() if isinstance(decision, dict) else ""
    result_mode = str(
        metadata.get("mode") or metadata.get("selected_mode") or ""
    ).strip().lower()
    is_grading_result = next_action == "route_to_grading" or result_mode == "grading"
    if len(prior_items) <= 1:
        if is_grading_result and prior_ctx is not None:
            prior_object_id = str((normalized_prior_ao or {}).get("object_id") or "").strip()
            result_object_id = str(result_ao.get("object_id") or "").strip()
            if prior_object_id and result_object_id and prior_object_id != result_object_id:
                return prior_ao if isinstance(prior_ao, dict) else result_active_object
        # Prior was not a batch set → nothing to preserve, behave as before.
        return result_active_object

    prior_qids = [str(it.get("question_id") or "").strip() for it in prior_items]

    if result_qid and result_qid in prior_qids:
        # Grading-of-set-item: merge the judged version back into the set.
        merged_items = [
            dict(result_single) if qid == result_qid else it
            for it, qid in zip(prior_items, prior_qids)
        ]
    elif next_action == "route_to_grading":
        # Grading turn but the result id does not line up with the set (id not
        # preserved through grading). Never collapse on a grading turn: keep the
        # prior set intact (the judging is already surfaced in the response).
        merged_items = prior_items
    else:
        # Genuine switch (new object not in the prior set) → let it replace.
        return result_active_object

    merged_ctx = dict(prior_ctx)
    merged_ctx["items"] = merged_items
    merged_ao = build_active_object_from_question_context(
        merged_ctx,
        previous_active_object=prior_ao,
        source_turn_id=str(metadata.get("turn_id") or "").strip() or None,
    )
    return merged_ao or result_active_object


async def resolve_turn_policy(
    *,
    user_message: str,
    explicit_context: dict[str, Any] | None,
    explicit_action: dict[str, Any] | None,
    candidate_contexts: list[dict[str, Any] | None] | tuple[dict[str, Any] | None, ...] = (),
    grading_prior_active_object: dict[str, Any] | None = None,
    grading_result_active_object: dict[str, Any] | None = None,
    grading_metadata: dict[str, Any] | None = None,
) -> TurnPolicyDecision:
    """Resolve the question-turn policy for a single turn (QTPK entry point).

    Owns the five question-turn facts (scene / relation+next_action / submission
    intent+evidence / current object identity / active-object patch) by
    forwarding — never reimplementing — the canonical resolvers documented in the
    module docstring.

    S1+S2: **partial** forwarder. Forwarded so far:
      * submission **intent + evidence** (S1, ``_resolve_question_followup_context_and_action``);
      * **active-object patch** (S2, ``apply_grading_result_patch`` — the E8 §6
        SEV-1 套题防塌 merge) **when** the grading inputs are supplied. The prior
        active_object is passed in (turn_runtime reads it from the store; that
        I/O stays in transport). S2 only *wires* this fact into the envelope; the
        production callsite (turn_runtime._merge_grading_result_into_active_set)
        still calls ``apply_grading_result_patch`` directly — the envelope path is
        consumed by production only in S5.

    The remaining facts (scene / semantic decision / current object identity)
    stay at their empty envelope defaults until later steps wire the rest of the
    canonical resolvers in. This zero-behavior forwarder is what the differential
    parity nets assert is identical to the pre-move ``turn_runtime`` resolution.
    """

    (
        question_followup_context,
        question_followup_action,
    ) = await _resolve_question_followup_context_and_action(
        user_message=user_message,
        explicit_context=explicit_context,
        explicit_action=explicit_action,
        candidate_contexts=candidate_contexts,
    )
    active_object: dict[str, Any] | None = None
    if grading_result_active_object is not None:
        active_object = apply_grading_result_patch(
            prior_active_object=grading_prior_active_object,
            result_active_object=grading_result_active_object,
            metadata=grading_metadata or {},
        )
    return TurnPolicyDecision(
        active_object=active_object,
        question_followup_context=question_followup_context,
        question_followup_action=question_followup_action,
    )
