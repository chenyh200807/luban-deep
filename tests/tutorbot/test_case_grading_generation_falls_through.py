"""S4 forward-reachability: a practice-generation request must never be captured /
clobbered by the case-grading no-authority template.

Root cause (deadlock, live-confirmed on deployed main 033ffbc85, 3/3): when the bot
generated a case itself, the no-authority case fallback
(`_case_grading_no_authority_score_fallback` -> `build_case_grading_diagnostic_only_response`)
emitted "把标准答案/采分点发来" — which (a) demands ground truth the student can never
produce for a bot-authored case and (b) clobbers a freshly generated "再出一道新题" with the
same template, deadlocking generation.

Fix = fall-through, not fail-closed-to-template: a generation turn produces a QUESTION,
never a grade, so it is exempt from the no-authority case-score demote. This locks that
exemption AND the boundary (a real grading turn is NOT exempt — SEV protection intact).

Hermetic: pure static helpers, no LLM / network.
"""
from __future__ import annotations

from deeptutor.tutorbot.agent.loop import AgentLoop
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request

# The unsatisfiable demand that the no-authority template renders.
_DEMAND_GROUND_TRUTH = "把题卡、题号、标准答案或采分点一起发来"

# A freshly generated case the LLM produced for "再出一道新题" — contains case-score-ish
# text ("满分10分") that the old demote regex false-positives on.
_GENERATED_CASE = (
    "### 第 1 题\n某工程因发包人未按时提供图纸导致停工5天，承包人提出工期与费用索赔。"
    "请回答承包人的索赔是否成立并说明理由。（本题满分10分）"
)
_GENERATION_REQUEST = "再出一道新的案例分析题给我做，带背景材料，先别判分"
_GRADING_REQUEST = (
    "针对你刚出的这道案例题，我的作答如下：本工程因建设单位未按时提供图纸导致停工，"
    "属于发包方原因，可申请工期顺延并一并索赔窝工损失。帮我按采分点判一下我能得几分？"
)


def _fallback(final_content, scene, user_message):
    md = {"question_lifecycle_scene": scene} if scene is not None else {}
    return AgentLoop._case_grading_no_authority_score_fallback(
        final_content, runtime_metadata=md, user_message=user_message
    )


# ---- boundary: the predicate that drives the exemption -----------------------------------
def test_generation_request_classified_grading_request_not():
    # T3 (generation) is exempt; T2 (grading the bot's own case) is NOT — it must still
    # route through grading, never silently fall through.
    assert looks_like_practice_generation_request(_GENERATION_REQUEST) is True
    assert looks_like_practice_generation_request(_GRADING_REQUEST) is False


# ---- Guard: generation request is never clobbered by the no-authority template ----------
def test_generation_request_falls_through_case_grading_scene():
    # scene pinned case_grading + no authority + a generated question -> return "" so the
    # generated content survives (caller does `... or final_content`). NOT the demand template.
    out = _fallback(_GENERATED_CASE, "case_grading", _GENERATION_REQUEST)
    assert out == ""


def test_generation_request_falls_through_unclassified_scene():
    # scene "" + generated case text that trips the no-authority case-score regex -> still
    # exempt (it's a generated question, not an ungrounded grade).
    out = _fallback(_GENERATED_CASE, "", _GENERATION_REQUEST)
    assert out == ""


# ---- boundary: a real grading turn is STILL demoted (SEV / fail-open protection intact) --
def test_grading_request_still_demotes_in_case_scene():
    out = _fallback("", "case_grading", _GRADING_REQUEST)
    assert _DEMAND_GROUND_TRUTH in out
    assert "本次不硬估标准分" in out


def test_unauthorized_case_score_still_demoted_when_not_generation():
    # The P1-A safety net: unclassified turn asserting an official case score without
    # authority, and NOT a generation request -> still demoted to diagnostic-only.
    ungrounded = "你的作答得8分，命中4个采分点，扣2分。"
    out = _fallback(ungrounded, "", ungrounded)
    # 新契约（P0 2026-07-29）：诊断正文保留，硬分口径经追加免责声明降级——
    # 模板只保留"不硬估官方分"的出生使命，收回整篇替换权。
    assert out.startswith(ungrounded)
    assert "评分口径说明" in out and "不构成官方阅卷得分" in out


# ---- defensive invariant unchanged ------------------------------------------------------
def test_v1_graded_still_short_circuits():
    md = {"question_lifecycle_scene": "case_grading", "_v1_case_graded": True}
    out = AgentLoop._case_grading_no_authority_score_fallback(
        "已判分", runtime_metadata=md, user_message=_GRADING_REQUEST
    )
    assert out == ""


# ---- PR3-6a(2026-08-10 三族根因 §3):同族裁决补到 tutorbot 侧 ---------------------------
# 本文件钉的 84d1efc58 家族裁决(fall-through, not fail-closed-to-template)在 PR3 被
# 补到 tutorbot lifecycle 侧:澄清模板短路退役,blocked 轮 fall-through 主 LLM;
# 数据面否决(exact 权威锁)原样保留。此钉登记 loop.py 的 protected-file domain 覆盖。
def test_lifecycle_blocked_turn_data_face_veto_survives_falls_through_family():
    # 撤话语面不撤数据面:blocked 轮 exact 权威候选必须被否决(主 LLM 无权威运行),
    # 与本文件"真判分轮仍 demote"同构——防御保数据权,不保话语终局权。
    exact_question = {
        "question_id": "q-2025-3",
        "question": "2025年真题第3题题干",
        "correct_answer": "B",
        "match_type": "exact",
        "answer_kind": "mcq",
    }
    assert (
        AgentLoop._prefetched_exact_authority_candidate(
            {
                "_prefetched_exact_question": dict(exact_question),
                "exact_question_blocked_reason": "low_information_exam_query",
            },
            current_message="2025年真题第3题答案",
        )
        is None
    )
