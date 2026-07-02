"""S4 forward-reachability (2026-06-29): a free-text answer to a stored single
written/case question must be recognized as a real submission by the SINGLE
submission authority ``resolve_submission_attempt``.

Root cause (live + deterministic confirmed): a bot-generated case is written to
the active_object with the stem in ``question`` and a reference in
``correct_answer``. On the free-text answer turn, scene fires ``case_grading`` (via
``_looks_like_free_text_case_grading``) but ``resolve_submission_attempt`` returned
``None`` because the explicit answer marker ("我的作答如下：") sat MID-message (after a
"针对刚才的案例题，" preamble) so the anchored ``_LEADING_SUBMISSION_PREFIX`` missed it
and the trailing grading-request "？" vetoed it. The turn-start demote carve-out
(``_message_is_submission_for_stored_set`` → ``resolve_submission_attempt`` bool) was
therefore False → the case active_object was demoted before the grading dispatch
could read its stem → Tier-3 ``no_reference`` deadlock (live 3/3).

The fix recognizes a mid-message explicit answer-submission marker; it must NOT
turn questions / 试探 / explanation requests into submissions (SEV: 凭空判分/倒诬).
"""
from __future__ import annotations

from deeptutor.services.question_followup import resolve_submission_attempt


def _stored_case_context() -> dict:
    stem = (
        "【背景材料】某办公楼项目，合同约定工期300天，合同总价5000万元。施工过程中，"
        "因发包人未能及时提供施工图纸，导致关键工作停工10天。\n\n【问题】\n1. 工期索赔是否成立？说明理由。"
    )
    return {
        "question_id": "q_1",
        "question": stem,
        "question_type": "written",
        "options": None,
        "correct_answer": "工期索赔成立：发包人未及时提供图纸属发包方原因，可顺延工期。",
        "items": [
            {"question_id": "q_1", "question": stem, "question_type": "written",
             "correct_answer": "工期索赔成立..."}
        ],
    }


SUBJECTIVE_ANSWER = (
    "本工程因建设单位未按时提供图纸导致停工，属发包方原因造成的工期延误，施工方不承担责任，"
    "可申请工期顺延，顺延天数按实际停工天数计算；同时窝工、机械闲置等损失可一并提出费用索赔。"
)


def test_free_text_case_answer_with_midmessage_marker_is_submission() -> None:
    """The exact live-failing phrasing: preamble + mid-message '我的作答如下：' + answer +
    trailing grading request with '？'. Must resolve to a single submission."""
    msg = (
        "针对你刚出的这道案例题，我的作答如下：" + SUBJECTIVE_ANSWER
        + " 帮我按采分点判一下我能得几分？"
    )
    _target, submission = resolve_submission_attempt(msg, _stored_case_context())
    assert submission is not None, "free-text case answer must be a recognized submission"
    assert submission.get("kind") == "single"
    assert SUBJECTIVE_ANSWER[:8] in str(submission.get("answer") or "")


def test_bare_colon_case_answer_is_submission() -> None:
    msg = "我的作答：工期索赔成立，因发包方未及时提供图纸属发包方原因，可顺延工期并索赔窝工损失。"
    _target, submission = resolve_submission_attempt(msg, _stored_case_context())
    assert submission is not None
    assert submission.get("kind") == "single"


# ---- SEV negatives: questions / 试探 / explanation requests must NOT become submissions ----

def test_asking_for_answer_is_not_submission() -> None:
    _t, sub = resolve_submission_attempt("这道题我的答案是什么？", _stored_case_context())
    assert sub is None


def test_explanation_request_is_not_submission() -> None:
    _t, sub = resolve_submission_attempt("这道案例题怎么分析？给我讲讲思路", _stored_case_context())
    assert sub is None


def test_bare_question_is_not_submission() -> None:
    _t, sub = resolve_submission_attempt("工期索赔的法律依据是什么？", _stored_case_context())
    assert sub is None


def test_probe_without_answer_marker_is_not_forced_submission() -> None:
    """A 试探 with no explicit answer-submission framing stays non-submission."""
    _t, sub = resolve_submission_attempt("我觉得应该能索赔吧，你看对不对？", _stored_case_context())
    assert sub is None
