"""Forward-reachability family collapse (Phase 2, 2026-06-29).

One coherent principle across the forward family: the deterministic single
authority (resolve_submission_attempt / derive_question_lifecycle_scene /
looks_like_practice_generation_request) routes genuine submissions to grading
and generation intents to generation — and never fails closed by mislabelling.

Holes collapsed here (deterministic layer):
- B1: a practice-generation request that LANDS in a case context must route to
  practice_generation, NOT case_grading (negated "判分" substring + "案例分析题"
  must not trip free-text case grading when there is no answer payload).
- A1: a multi-题号 answer batch carrying parenthetical option text must resolve
  as a COMPLETE batch (all items), not degrade to a single (grade q1, drop rest).

SEV guardrails proven here (must NOT regress fail-open / 凭空判分):
- An answer-led turn that also asks for new questions still grades (submission wins).
- A genuinely ambiguous single bare answer on a multi-set stays ambiguous (by-design).
- Existing clean batch / numbered formats still parse (no regression).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from deeptutor.services.question_followup import (
    resolve_submission_attempt,
    submission_confidence,
)
from deeptutor.services.question_lifecycle_skills import (
    derive_question_lifecycle_scene,
)


@dataclass
class _Ctx:
    user_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _case_ctx() -> dict[str, Any]:
    return {
        "question_id": "c1",
        "question": "某工程因建设单位未按时提供图纸停工30天，问能否工期顺延及理由。",
        "question_type": "case",
        "options": None,
        "correct_answer": "",
    }


def _case_meta() -> dict[str, Any]:
    c = _case_ctx()
    return {"question_followup_context": c, "active_object": {"state_snapshot": c}}


def _three_item_ctx() -> dict[str, Any]:
    items = [
        {
            "question_id": "q_1",
            "question": "三级安全教育包括企业、项目和哪一项？",
            "question_type": "choice",
            "options": {"A": "班组", "B": "科室", "C": "部门", "D": "车间"},
            "correct_answer": "A",
        },
        {
            "question_id": "q_2",
            "question": "施工现场安全教育时间不少于（）学时？",
            "question_type": "choice",
            "options": {"A": "24", "B": "32", "C": "40", "D": "48"},
            "correct_answer": "A",
        },
        {
            "question_id": "q_3",
            "question": "“四口”防护指哪四口？",
            "question_type": "choice",
            "options": {
                "A": "楼梯口、电梯口、通道口、预留洞口",
                "B": "门口、窗口、洞口、通道口",
                "C": "楼梯口、电梯口、门口、窗口",
                "D": "通道口、预留洞口、门口、窗口",
            },
            "correct_answer": "A",
        },
    ]
    primary = dict(items[0])
    primary["question_id"] = "question_set"
    primary["question"] = "（题组）"
    primary["options"] = None
    primary["correct_answer"] = ""
    primary["items"] = items
    return primary


# ---------------- B1: 出题-after-case 优先级 ----------------


@pytest.mark.parametrize(
    "message",
    [
        "我没让你判分啊，我是让你出一道新的案例分析题给我做，你直接出题就行",
        "请你现在出题。题目：一道二级建造师建筑实务的案例分析题，不要判分",
        "再来一道难点的案例分析题，多几个采分点的那种，带背景材料，先别判分",
    ],
)
def test_b1_generation_request_in_case_context_routes_to_practice_generation(message: str):
    # Forward hole: a generation request that lands in a case context must NOT be
    # mislabelled case_grading (which deadlocks "出新题" into the no-authority demand).
    ctx = _Ctx(user_message=message, metadata=_case_meta())
    assert derive_question_lifecycle_scene(ctx) == "practice_generation"


def test_b1_real_case_answer_still_routes_to_case_grading():
    # SEV/guard: a genuine case answer submission must STILL grade (don't break grading).
    ctx = _Ctx(
        user_message=(
            "针对刚才的案例题，我的作答如下：本工程因建设单位未按时提供图纸停工，属发包方原因，"
            "施工方可申请工期顺延，顺延天数按实际停工天数计算。请按采分点判一下。"
        ),
        metadata=_case_meta(),
    )
    assert derive_question_lifecycle_scene(ctx) == "case_grading"


# ---------------- A1: 题号 batch 带括号选项文字 ----------------


def test_a1_parenthetical_numbered_batch_resolves_complete_batch():
    # Forward hole: "第N题选X（选项文字）" for all 3 must resolve as a complete batch,
    # not degrade to a single (grade q1, silently drop q2/q3).
    msg = (
        "第1题选A（班组），第2题选A（24学时），"
        "第3题选A（楼梯口、电梯口、通道口、预留洞口）。三道一起判，告诉我各自对错"
    )
    _ctx, submission = resolve_submission_attempt(msg, _three_item_ctx())
    assert submission is not None
    assert submission.get("kind") == "batch"
    assert len(submission.get("answers") or []) == 3
    assert [a.get("user_answer") for a in submission["answers"]] == ["A", "A", "A"]


def test_a1_clean_q_batch_still_parses_regression():
    # Regression: the already-working compact q-batch must keep working.
    _ctx, submission = resolve_submission_attempt("q1 A q2 B q3 C", _three_item_ctx())
    assert submission is not None
    assert submission.get("kind") == "batch"
    assert len(submission.get("answers") or []) == 3


def test_a1_bare_single_answer_on_multiset_stays_ambiguous():
    # by-design guard (phantom — do NOT change): one bare answer on a 3-set is genuinely
    # ambiguous (which question?), must stay ambiguous (request the question number),
    # never silently graded.
    _ctx, submission = resolve_submission_attempt("我选A", _three_item_ctx())
    assert submission is not None
    assert submission.get("kind") == "ambiguous"


# ---------------- A2: 跳步 — committed answer embedded in reasoning ----------------


def _single_mcq_ctx() -> dict[str, Any]:
    return {
        "question_id": "q1",
        "question": "屋面防水基本要求",
        "question_type": "choice",
        "options": {"A": "以排为主", "B": "坡度不小于2%", "C": "最薄15mm", "D": "年限不低于20年"},
        "correct_answer": "D",
    }


@pytest.mark.parametrize(
    "message",
    [
        "我觉得这题选D吧，因为防水设计年限确实是20年，我记得挺牢的，对吧",
        "我认为这题选D",
        "应该选D吧",
    ],
)
def test_a2_committed_answer_in_reasoning_reaches_high_confidence(message: str):
    # Forward hole: a genuine answer committed in softened/reasoning phrasing
    # ("我觉得这题选D，因为…对吧") must reach HIGH confidence → grading scene, not be
    # blocked into question_review (跳步: bot teaches instead of judging, needs re-prompt).
    assert submission_confidence(message, _single_mcq_ctx()) == "high"
    ctx = _Ctx(user_message=message, metadata={"question_followup_context": _single_mcq_ctx()})
    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


@pytest.mark.parametrize(
    "message",
    [
        "我猜是A吧，但你先别判，我还没想好",  # 试探 + deferral
        "我选D，但先别判",  # committed BUT defers — respect the defer (SEV: don't grade when told to wait)
        "D选项说年限20年这个说法本身对吗",  # asking ABOUT an option, not answering
    ],
)
def test_a2_tentative_or_deferred_or_question_stays_low_not_graded(message: str):
    # SEV guardrail ①: a non-committed / deferring / option-question turn must NOT reach
    # HIGH (would 凭空判分 a non-answer or grade against an explicit "先别判"). Stays LOW →
    # question_review (LLM holds the final is-this-an-answer call), never a hard grade.
    assert submission_confidence(message, _single_mcq_ctx()) != "high"
    ctx = _Ctx(user_message=message, metadata={"question_followup_context": _single_mcq_ctx()})
    assert derive_question_lifecycle_scene(ctx) != "mcq_grading"


def test_a2_non_answer_chatter_is_not_a_submission():
    # SEV: pure non-answer ("还没想好") is not a submission at all → no grade.
    assert submission_confidence("还没想好怎么答呢", _single_mcq_ctx()) is None
