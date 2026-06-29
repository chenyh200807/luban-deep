"""S4 forward-reachability (2026-06-29): once the case active_object survives to the
grading turn (the demote carve-out fix in question_followup), the grading-ctx builder
``_build_v1_case_ctx`` must:

1. Surface the case STEM from the active_object's ``question`` field (it lives there, NOT
   in ``question_stem``) so Tier-3 ``derive_rubric_from_stem`` has a stem. Live ground
   truth on ebb06146d showed ``has_stem=False`` → Tier-3 unreachable → no_reference
   deadlock, even though the stem was present in the active_object.

2. NOT promote the bot-generated (unsigned) ``correct_answer`` to a Tier-2 reference when
   there is no bank/signed authority (``_prefetched_exact_question`` empty). An unsigned
   self-generated answer is not signed truth → grading must stay Tier-3 stem-derived
   diagnostic (``official_score_allowed=False``, rendered with the 诊断 hedge), never an
   official-style Tier-2 score (red line: v1-grading-must-be-open-world-not-lookup).
"""
from __future__ import annotations

from deeptutor.tutorbot.agent.loop import AgentLoop

STEM = (
    "【背景材料】某办公楼项目，合同约定工期300天，合同总价5000万元。施工过程中，"
    "因发包人未能及时提供施工图纸，导致关键工作停工10天。\n\n【问题】\n1. 工期索赔是否成立？说明理由。"
)
ANSWER_BODY = "工期索赔成立，因发包方未及时提供图纸属发包方原因，可顺延工期并索赔窝工损失。"


def _md_with_generated_case_active_object() -> dict:
    """runtime_metadata for the grading turn after a BOT-generated case (no bank authority)."""
    followup = {
        "question_id": "q_1",
        "question": STEM,            # stem lives here for an active_object-derived case
        "question_type": "written",
        "options": None,
        "correct_answer": "工期索赔成立：发包方未及时提供图纸属发包方原因，可顺延工期。",  # unsigned bot ref
    }
    return {
        "question_lifecycle_scene": "case_grading",
        "question_followup_context": followup,
        # NO _prefetched_exact_question → no bank/signed authority
    }


def test_stem_surfaced_from_active_object_question_field() -> None:
    md = _md_with_generated_case_active_object()
    ctx = AgentLoop._build_v1_case_ctx(md, "我的作答：" + ANSWER_BODY)
    assert ctx["question_stem"].strip(), "Tier-3 needs a non-empty stem"
    assert "工期索赔" in ctx["question_stem"], "stem must come from active_object.question"


def test_unsigned_generated_reference_suppressed_forces_tier3() -> None:
    md = _md_with_generated_case_active_object()
    ctx = AgentLoop._build_v1_case_ctx(md, "我的作答：" + ANSWER_BODY)
    # Unsigned bot-generated correct_answer must NOT become the grading reference
    # (otherwise _grade_one_case_v1 takes Tier-2 on_the_fly_reference, non-diagnostic).
    assert not str(ctx["correct_answer"]).strip(), (
        "unsigned generated reference must be suppressed so grading stays Tier-3 diagnostic"
    )


def test_user_answer_flows_into_ctx() -> None:
    md = _md_with_generated_case_active_object()
    ctx = AgentLoop._build_v1_case_ctx(md, "我的作答：" + ANSWER_BODY)
    assert ANSWER_BODY[:8] in str(ctx["user_answer"])


def test_stem_consumed_from_active_object_when_flat_keys_absent() -> None:
    """The ACTUAL live path (S4DIAG-confirmed): the grading turn's runtime_metadata carries
    the canonical ``active_object`` but NOT the flat question_followup_context key. The ctx
    builder must consume the stem/reference from active_object.state_snapshot."""
    stem_ctx = {
        "question_id": "q_1",
        "question": STEM,
        "question_type": "written",
        "correct_answer": "工期索赔成立……（bot 自生成、未签名）",
    }
    md = {
        "question_lifecycle_scene": "case_grading",
        # NO question_followup_context / active_question_context / followup_question_context
        "active_object": {
            "object_type": "single_question",
            "object_id": "q_1",
            "state_snapshot": stem_ctx,
        },
        # NO _prefetched_exact_question (unsigned, generated)
    }
    ctx = AgentLoop._build_v1_case_ctx(md, "我的作答：" + ANSWER_BODY)
    assert "工期索赔" in ctx["question_stem"], "stem must be consumed from active_object"
    assert not str(ctx["correct_answer"]).strip(), "unsigned generated ref still suppressed → Tier-3"


def test_bank_signed_reference_still_flows() -> None:
    """Regression guard: when a bank exact-question IS present (signed authority), its
    reference still flows (the suppression only targets the unsigned no-bank path)."""
    md = {
        "question_lifecycle_scene": "case_grading",
        "_prefetched_exact_question": {
            "question_id": "Q17-1A",
            "stem": STEM,
            "question": STEM,
            "covered_subquestions": [
                {"question": STEM, "authoritative_answer": "官方采分点：工期索赔成立……"}
            ],
            "max_score": 8.0,
        },
    }
    ctx = AgentLoop._build_v1_case_ctx(md, "我的作答：" + ANSWER_BODY)
    assert "官方采分点" in str(ctx["correct_answer"]), "signed bank reference must still flow"
