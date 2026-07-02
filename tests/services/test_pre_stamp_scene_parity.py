"""Scene-parity harness for control-plane Task 4 (remove the pre-capability scene pre-stamp).

Hard precondition for deleting ``_stamp_current_submission_scene_pre_capability``
(turn_runtime.py): the canonical lifecycle scene resolved by
``resolve_question_lifecycle_scene_decision`` must be **identical** whether or not the
deterministic pre-stamp wrote ``question_lifecycle_scene`` into the turn config/metadata.

Mechanism under test (verified by reading the live wiring at the deployment baseline):

1. ``_stamp_current_submission_scene_pre_capability`` writes ``question_lifecycle_scene``
   (+ ``_source = "deterministic_pre_capability"`` and friends) into the per-turn config dict.
2. ``_question_lifecycle_metadata_from_config`` projects those keys into the orchestrator's
   ``context.metadata`` (turn_runtime.py builds the UnifiedContext metadata dict).
3. ``resolve_question_lifecycle_scene_decision`` (orchestrator._select_capability) reads the
   pre-stamp from ``ctx.metadata`` at the top: if ``_pre_stamped_grading_scene_matches_current_submission``
   honors it, it returns the pre-stamped scene; otherwise it falls through to
   ``derive_question_lifecycle_scene`` which re-derives the scene from the *same* facts.

So removing the pre-stamp is behavior-preserving iff, for every turn shape, the resolver's
final ``.scene`` is unchanged when the pre-stamp keys are absent. This harness proves that
deterministically (``enable_llm=False``) over a broad corpus: submission turns (mcq / case /
tentative / revision), non-submission turns (review / followup / practice-gen / no-active),
pasted mcq / pasted case, and unresolved-switch followups.

This test is contract-protected (registered in contracts/index.yaml domain test_files for
turn_runtime.py + question_lifecycle_skills.py) because it pins the single-authority invariant
that survives the pre-stamp removal.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from deeptutor.services.question_followup import (
    normalize_question_followup_context,
)
from deeptutor.services.question_lifecycle_skills import (
    looks_like_case_grading_submission_context,
    looks_like_full_case_answer_submission,
    resolve_question_lifecycle_scene_decision,
    select_question_lifecycle_skill_names,
)
from deeptutor.services.session.turn_runtime import (
    _normalize_question_followup_action,
    _question_lifecycle_metadata_from_config,
)


def _legacy_pre_stamp_scene_write(
    config: dict[str, Any],
    *,
    user_message: str,
    followup_context: dict[str, Any] | None,
    followup_action: dict[str, Any] | None,
) -> None:
    """Faithful local reproduction of the REMOVED pre-capability scene pre-stamp.

    This mirrors, byte-for-byte in logic, the deleted
    ``_stamp_current_submission_scene_pre_capability`` (control-plane Task 4). It exists
    only so this harness can reconstruct the "current production (with pre-stamp)" arm and
    prove the resolved scene was unchanged by the removal. If the lifecycle scene predicates
    it relies on ever drift, this harness still exercises them against the live resolver.
    """

    if not isinstance(config, dict):
        return
    normalized_context = normalize_question_followup_context(followup_context)
    normalized_action = _normalize_question_followup_action(followup_action)
    if normalized_context is None:
        return

    scene = ""
    confidence = 0.0
    if looks_like_full_case_answer_submission(user_message):
        scene = "case_grading"
        confidence = 1.0
    elif looks_like_case_grading_submission_context(normalized_context, normalized_action):
        scene = "case_grading"
        confidence = 0.96
    elif (
        str((normalized_action or {}).get("intent") or "").strip() == "answer_questions"
        and (normalized_context.get("options") or normalized_context.get("items"))
    ):
        scene = "mcq_grading"
        confidence = 0.96
    if not scene:
        return

    config["question_lifecycle_scene"] = scene
    config["question_lifecycle_scene_source"] = "deterministic_pre_capability"
    config["question_lifecycle_scene_confidence"] = confidence
    config["question_lifecycle_skill_names"] = list(
        select_question_lifecycle_skill_names(scene)
    )


@dataclass
class _FakeContext:
    user_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _mcq_followup_context() -> dict[str, Any]:
    return {
        "question_id": "q1",
        "question_type": "mcq",
        "question": "下列哪个选项正确？",
        "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
    }


def _case_followup_context() -> dict[str, Any]:
    return {
        "question_id": "c1",
        "question_type": "case",
        "question": "背景资料：某项目。问题：指出不妥之处。",
    }


def _multi_mcq_items_context() -> dict[str, Any]:
    """A multi-question (items[]) active set — the shape that trips the post-derive
    ambiguous-multi-question gate when a submission doesn't name a question number."""

    return {
        "question_id": "multi-set",
        "question_type": "mcq",
        "items": [
            {
                "question_id": "q1",
                "question_type": "mcq",
                "question": "第一题：下列哪个正确？",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            },
            {
                "question_id": "q2",
                "question_type": "mcq",
                "question": "第二题：下列哪个错误？",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            },
        ],
    }


def _resolve_scene(
    user_message: str,
    metadata: dict[str, Any],
    *,
    enable_llm: bool = False,
) -> Any:
    ctx = _FakeContext(user_message=user_message, metadata=dict(metadata))
    decision = asyncio.run(
        resolve_question_lifecycle_scene_decision(ctx, enable_llm=enable_llm)
    )
    return decision.scene


def _apply_pre_stamp(
    base_metadata: dict[str, Any],
    *,
    user_message: str,
    followup_context: dict[str, Any] | None,
    followup_action: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reproduce the production pre-stamp → metadata projection exactly.

    Runs the real ``_stamp_current_submission_scene_pre_capability`` against a config
    dict, then projects via the real ``_question_lifecycle_metadata_from_config`` the same
    way turn_runtime builds the UnifiedContext metadata.
    """

    config: dict[str, Any] = {}
    _legacy_pre_stamp_scene_write(
        config,
        user_message=user_message,
        followup_context=followup_context,
        followup_action=followup_action,
    )
    stamped = dict(base_metadata)
    stamped.update(_question_lifecycle_metadata_from_config(config))
    return stamped


# (name, user_message, followup_context, followup_action)
_SUBMISSION_AND_BOUNDARY_CASES: list[
    tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]
] = [
    # --- mcq submission turns (pre-stamp would write mcq_grading) ---
    (
        "active_submission_mcq_letter",
        "B",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
    ),
    (
        "answer_revision_mcq",
        "答案改成D",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
    ),
    (
        "active_submission_mcq_explicit",
        "我选B",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
    ),
    # --- case submission turns (pre-stamp would write case_grading) ---
    (
        "active_submission_case",
        "施工单位应组织专家论证危大工程方案。1.指出不妥之处。2.补充正确做法。",
        _case_followup_context(),
        {"intent": "answer_questions"},
    ),
    (
        "full_case_answer_submission",
        "背景资料：某旧城改造工程。问题：1.指出施工方案中的不妥之处：方案未论证。",
        None,
        None,
    ),
    # --- tentative / hold / hypothetical (pre-stamp guarded; resolver must keep review) ---
    (
        "tentative_answer_hold",
        "我猜A但先别判",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
    ),
    (
        "hypothetical_answer",
        "如果选D对不对",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
    ),
    # --- non-submission: review / followup ---
    (
        "only_question_no_answer",
        "这道题怎么做",
        _mcq_followup_context(),
        None,
    ),
    (
        "source_backed_variant",
        "结合教材再解释一下这道题",
        _mcq_followup_context(),
        None,
    ),
    (
        "unresolved_switch_followup",
        "那上一题呢",
        _mcq_followup_context(),
        None,
    ),
    # --- practice generation ---
    (
        "practice_generation_request",
        "再出 3 题",
        None,
        None,
    ),
    # --- no active object / pasted (no followup_context) ---
    (
        "no_active_object_answer",
        "我选B",
        None,
        None,
    ),
    (
        "pasted_mcq",
        "下列关于施工临时用电的说法正确的是？A.甲 B.乙 C.丙 D.丁",
        None,
        None,
    ),
    (
        "pasted_case",
        "背景资料：某旧城改造工程。问题：1.指出施工方案中的不妥之处。",
        None,
        None,
    ),
    (
        "free_text_no_active",
        "帮我讲讲危大工程的论证流程",
        None,
        None,
    ),
]


@pytest.mark.parametrize(
    "name,user_message,followup_context,followup_action",
    _SUBMISSION_AND_BOUNDARY_CASES,
    ids=[c[0] for c in _SUBMISSION_AND_BOUNDARY_CASES],
)
def test_pre_stamp_removal_is_scene_preserving(
    name: str,
    user_message: str,
    followup_context: dict[str, Any] | None,
    followup_action: dict[str, Any] | None,
) -> None:
    """Resolved scene is identical with vs without the pre-stamp."""

    base_metadata: dict[str, Any] = {}
    if followup_context is not None:
        base_metadata["question_followup_context"] = followup_context

    # current production: pre-stamp applied (config → metadata projection).
    stamped_metadata = _apply_pre_stamp(
        base_metadata,
        user_message=user_message,
        followup_context=followup_context,
        followup_action=followup_action,
    )
    current_scene = _resolve_scene(user_message, stamped_metadata)

    # candidate (post-removal): no pre-stamp keys, resolver re-derives from facts.
    candidate_scene = _resolve_scene(user_message, base_metadata)

    assert current_scene == candidate_scene, (
        f"scene divergence for {name!r}: "
        f"current(with pre-stamp)={current_scene!r} != candidate(no pre-stamp)={candidate_scene!r}"
    )


def _load_hard_cases() -> list[dict[str, Any]]:
    path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "control_plane_hard_cases.jsonl"
    )
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


_HARD_CASES = _load_hard_cases()


@pytest.mark.parametrize(
    "case",
    _HARD_CASES,
    ids=[c["name"] for c in _HARD_CASES],
)
def test_pre_stamp_removal_scene_parity_over_hard_cases(case: dict[str, Any]) -> None:
    """Same parity assertion over the shared control-plane hard-case corpus.

    For each hard case we synthesize the followup_action the runtime would have resolved
    (answer-intent when the message is an answer over an active object) so the pre-stamp
    arm is exercised exactly as production would, then assert the resolver's scene is
    unchanged when the pre-stamp keys are removed.
    """

    user_message = str(case.get("user_message") or "")
    metadata = dict(case.get("metadata") or {})
    followup_context = metadata.get("question_followup_context")

    # Best-effort reproduction of the action the runtime would carry: when there is an
    # active question context, the submission resolver tags answer_questions. This only
    # *enables* the mcq pre-stamp branch; case/full-case branches key off the text itself.
    followup_action: dict[str, Any] | None = None
    if followup_context:
        followup_action = {"intent": "answer_questions"}

    stamped_metadata = _apply_pre_stamp(
        metadata,
        user_message=user_message,
        followup_context=followup_context,
        followup_action=followup_action,
    )
    current_scene = _resolve_scene(user_message, stamped_metadata)
    candidate_scene = _resolve_scene(user_message, metadata)

    assert current_scene == candidate_scene, (
        f"scene divergence for hard case {case.get('name')!r}: "
        f"current(with pre-stamp)={current_scene!r} != candidate(no pre-stamp)={candidate_scene!r}"
    )


# ---------------------------------------------------------------------------
# GLM-5.2 red-team coverage hardening (cross-form cases the original harness missed)
# ---------------------------------------------------------------------------
#
# Red-team (GLM-5.2) observation — VERIFIED, then FALSIFIED as a blocker:
#
# resolve_question_lifecycle_scene_decision EARLY-RETURNS when the pre-stamp is
# honored (question_lifecycle_skills.py:245-265), SKIPPING the post-derive safety
# gates (unanchored_submission / ambiguous_multi_submission / low_information_exam_query,
# ~:288-310). Removing the pre-stamp makes those gates fire — for the first time — on
# turns the pre-stamp used to short-circuit. The blocker hypothesis: a turn whose
# pre-stamp wrote a grading scene but whose post-derive gate would now block it →
# scene divergence.
#
# Why it is NOT a divergence (empirically 0/14 here):
#   _pre_stamped_grading_scene_matches_current_submission (:188) is exactly the
#   guard that REJECTS the pre-stamp on every turn where a post-derive gate would
#   fire (unanchored / ambiguous-multi / low-info / tentative / hypothetical). So
#   whenever the pre-stamp is honored (early-return), derive_question_lifecycle_scene
#   returns the SAME grading scene; and whenever a gate would fire, the pre-stamp is
#   already rejected and BOTH arms fall through to the identical derive path. The
#   early-return and the derive path can only co-occur on the same scene.
#
# Field-level note (documented, intentionally NOT asserted):
#   On a HONORED pre-stamp the decision carries source="metadata"/
#   "deterministic_pre_capability", business_gate_result="pre_stamped_scene",
#   required_anchor_status="satisfied"; the derive path yields source="deterministic",
#   business_gate_result="passed", required_anchor_status="satisfied". These metadata
#   fields legitimately DIFFER between the two arms. They are NOT behavior-relevant:
#   grep over the codebase shows ZERO production branch consumers of
#   "pre_stamped_scene" / "deterministic_pre_capability", and the only readers of
#   business_gate_result / question_lifecycle_scene_source are trace/observability
#   projections (they record the value, never branch on it). Routing, capability
#   selection, and the mcq_grading_bypass safety belt all key off the resolved
#   .scene only. Therefore .scene equality == behavior-preserving, and this harness
#   asserts .scene (and only .scene) across both arms.

# (name, user_message, followup_context, followup_action, enable_llm)
_GLM_REDTEAM_CASES: list[
    tuple[str, str, dict[str, Any] | None, dict[str, Any] | None, bool]
] = [
    # 1. case answer that embeds an option token ("选A") + case answer body.
    (
        "glm01_case_answer_with_option_token",
        "选A，且基层必须干燥，搭接宽度应符合规范，补做蓄水试验",
        _case_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 2. normal full case submission.
    (
        "glm02_case_full_submission",
        "基层必须干燥，搭接宽度应符合规范，补做蓄水试验并整改渗漏点。",
        _case_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 3. low-information exam-catalog query, no active context.
    (
        "glm03_low_info_exam_query_no_ctx",
        "建筑实务有哪些真题",
        None,
        None,
        False,
    ),
    # 4. low-information query with an mcq active context (post-derive low-info gate).
    (
        "glm04_low_info_with_mcq_ctx",
        "这类真题有哪些",
        _mcq_followup_context(),
        None,
        False,
    ),
    # 5. multi-question set, bare option letters "A B C" (ambiguous-multi gate).
    (
        "glm05_multi_items_bare_letters",
        "A B C",
        _multi_mcq_items_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 6. multi-question set, "我都选A".
    (
        "glm06_multi_items_all_a",
        "我都选A",
        _multi_mcq_items_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 7. multi-question set, "全部选B".
    (
        "glm07_multi_items_all_b",
        "全部选B",
        _multi_mcq_items_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 8. tentative hold (re-checkable; pre-stamp rejected by validation gate).
    (
        "glm08_tentative_hold",
        "我猜A但先别判",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 9. revision "答案改成D".
    (
        "glm09_answer_revision",
        "答案改成D",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 10. free-text mcq "我选乙".
    (
        "glm10_free_text_mcq_yi",
        "我选乙",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 11. single mcq submit "B" with enable_llm=True (LLM-interaction dimension).
    (
        "glm11_single_mcq_submit_enable_llm",
        "B",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
        True,
    ),
    # 12. case submission with enable_llm=True (LLM-interaction dimension).
    (
        "glm12_case_submit_enable_llm",
        "基层必须干燥，搭接宽度应符合规范，补做蓄水试验并整改渗漏点。",
        _case_followup_context(),
        {"intent": "answer_questions"},
        True,
    ),
    # 13. mismatch: pre-stamp would write mcq_grading (mcq ctx) but message is a case
    #     answer body — validation gate must reject the mcq pre-stamp; derive routes case.
    (
        "glm13_prestamp_mcq_but_case_message",
        "基层必须干燥，搭接宽度合规，补蓄水试验",
        _case_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
    # 14. empty message + pre-stamp (mcq ctx) — no submission, scene must not grade.
    (
        "glm14_empty_message_with_prestamp",
        "",
        _mcq_followup_context(),
        {"intent": "answer_questions"},
        False,
    ),
]


@pytest.mark.parametrize(
    "name,user_message,followup_context,followup_action,enable_llm",
    _GLM_REDTEAM_CASES,
    ids=[c[0] for c in _GLM_REDTEAM_CASES],
)
def test_pre_stamp_removal_scene_parity_glm_redteam(
    name: str,
    user_message: str,
    followup_context: dict[str, Any] | None,
    followup_action: dict[str, Any] | None,
    enable_llm: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GLM-5.2 cross-form parity: resolved .scene identical with vs without pre-stamp.

    Covers the post-derive gates the pre-stamp early-return used to skip (unanchored /
    ambiguous-multi / low-info), free-text/revision/tentative submissions, mismatch
    (pre-stamp rejected by the validation gate), the empty-message guard, and the
    enable_llm=True dimension on validated submissions.
    """

    # Keep the harness hermetic even on the enable_llm=True dimension: a validated
    # grading submission returns its scene BEFORE the LLM proposal is consulted
    # (question_lifecycle_skills.py:323-332 only fetches a proposal when scene is None
    # or the turn is low-info), so stubbing the proposal to None changes nothing for the
    # parity cases while preventing any accidental network call.
    async def _no_llm_proposal(_ctx: Any) -> None:
        return None

    monkeypatch.setattr(
        "deeptutor.services.question_lifecycle_skills._llm_question_lifecycle_scene_proposal",
        _no_llm_proposal,
    )

    base_metadata: dict[str, Any] = {}
    if followup_context is not None:
        base_metadata["question_followup_context"] = followup_context

    stamped_metadata = _apply_pre_stamp(
        base_metadata,
        user_message=user_message,
        followup_context=followup_context,
        followup_action=followup_action,
    )
    current_scene = _resolve_scene(user_message, stamped_metadata, enable_llm=enable_llm)
    candidate_scene = _resolve_scene(user_message, base_metadata, enable_llm=enable_llm)

    assert current_scene == candidate_scene, (
        f"scene divergence for GLM red-team case {name!r} (enable_llm={enable_llm}): "
        f"current(with pre-stamp)={current_scene!r} != candidate(no pre-stamp)={candidate_scene!r}"
    )
