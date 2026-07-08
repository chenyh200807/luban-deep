"""S4(b): turn-START demote ↔ canonical resume 是相位互补 pipeline，非双权威冲突。

控制面物理重构 QTPK S4 的 investigation 已证：active_object / suspended_object_stack
的转换跨三个**相位**，各自单一权威，互不重判同一输入：

  1. turn-START 相位（``deeptutor/services/session/turn_runtime.py`` 的 demote 块）：
     在 scene gate 之前，把 stored active question object **降级（压栈）**到
     suspended_object_stack；但带 task#14 (2026-06-22) 的 ordinal guard——当本轮用
     "第N题" 引用 stored 套题的某个 item 时**不压栈**，让套题保持 active，scene
     low-information gate 才锚得住 "第N题"。turn-START 只压栈，从不出栈。
  2. routing 相位（``deeptutor/services/semantic_router.py::apply_active_object_transition``）：
     orchestrator 经 ``metadata.suspended_object_stack`` 读到 turn-START 压栈的对象，
     在 ``resume_suspended_object`` 决策下**恢复（出栈）**。canonical 只出栈，从不在
     turn-START 那个输入上重做压栈决策。
  3. turn-END 相位（E8 grading merge，已 QTPK 化 ``apply_grading_result_patch``）：
     只 merge-back 评分状态，不当第二个 set-destroying writer。

本测试证现状（相位互补），不改现状：
  - pipeline：turn-START demote 的输出（被压栈的对象）经 ``apply_active_object_transition``
    能被 routing 相位读到并 resume —— 是 pipeline 非冲突。
  - task#14：套题被 "第N题" ordinal 引用时 turn-START **不 demote**，是 routing 相位
    没有的 turn-START 相位独有 SEV-1 回指保护。
  - 相位边界：turn-START 只压栈、canonical 才出栈，两者不在同一输入上做矛盾决策。

owner 决策 (b)：文档化相位互补，不强行收敛（强收敛冒回指 SEV-1 + 给 canonical 加
复杂度违 "架构简单"）。相位权威划分见 ``contracts/turn.md`` §"QTPK 物理抽出 S4(b)"。
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.active_object_builder import (
    build_active_object_from_question_context,
    extract_question_context_from_active_object,
)
from deeptutor.services.question_turn_policy import (
    _message_is_submission_for_stored_set,
    _message_references_stored_question_set_item,
    _message_requests_active_mcq_represent,
)
from deeptutor.services.semantic_router import apply_active_object_transition
from deeptutor.services.session.turn_runtime import _prepend_suspended_object


def _question_set_context() -> dict[str, Any]:
    """A batch question_set (2 items) — the exact shape a stored active 套题 carries."""

    return {
        "question_id": "set-1",
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
                "question": "第二题：下列哪个正确？",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            },
        ],
    }


def test_unanswered_implicit_help_is_demote_carveout_explicit_passes() -> None:
    """安全 SEV（2026-06-30，Langfuse 取证定位）：turn-START demote 第 4 个 carve-out。

    与 task#14(ordinal)/#287(re-present)/S1(submission) 同形——"本轮引用活跃对象 → 不
    demote"。未作答活跃题 + **隐式求助**（"给点提示/还是不会"，should_block=True）必须
    命中 carve-out（不压栈，活跃题保留，下游 anti-peek 短路才可达，否则落自由 LLM 泄底）。
    **显式要答案**（"公布答案"，should_block=False）不命中 → 照常 demote，reveal 路径放行。

    turn_runtime demote 块的 carve-out 谓词 = should_block_unanswered_reference_reveal
    （reveal/anti-peek 单一权威，此处只读不重判）。
    """
    from deeptutor.services.question_followup import (
        should_block_unanswered_reference_reveal,
        should_keep_unanswered_question_active_for_followup,
    )

    unanswered_ctx = _question_set_context()  # 无 user_answer / is_correct = 未作答

    # 隐式求助 → carve-out 命中（should_block=True → demote 条件被否定 → 不压栈）。
    for message in ("给点提示", "还是不会", "这题怎么想", "再多说点"):
        assert should_block_unanswered_reference_reveal(message, unanswered_ctx) is True, message

    # 显式要答案 → 不命中 carve-out（should_block=False → 照常 demote → reveal 放行）。
    for message in ("公布答案", "直接告诉我答案", "把答案给我"):
        assert should_block_unanswered_reference_reveal(message, unanswered_ctx) is False, message
        assert should_keep_unanswered_question_active_for_followup(message, unanswered_ctx) is False, message

    # 具体未答题显式 reveal 仍要保活，让下游 anti-peek 短路可达，不能因 preference=True 被 demote。
    for message in ("第2题答案是什么", "直接说第2题哪个对"):
        assert should_block_unanswered_reference_reveal(message, unanswered_ctx) is True, message
        assert should_keep_unanswered_question_active_for_followup(message, unanswered_ctx) is True, message

    # 安全学习辅助不走 anti-peek 短路，但仍保留活动题连续性，避免下一轮作答绑不到题。
    message = "给我整理一建建筑实务记忆口诀"
    assert should_block_unanswered_reference_reveal(message, unanswered_ctx) is False
    assert should_keep_unanswered_question_active_for_followup(message, unanswered_ctx) is True

    # 指向当前题的口诀仍属于当前未答题求助，不开放到自由 LLM。
    message = "给我整理这道题的记忆口诀"
    assert should_block_unanswered_reference_reveal(message, unanswered_ctx) is True
    assert should_keep_unanswered_question_active_for_followup(message, unanswered_ctx) is True

    # 已作答题不命中（attempt 存在 → should_block=False，不属本 carve-out）。
    answered_ctx = _question_set_context()
    answered_ctx["items"][0]["user_answer"] = "A"
    answered_ctx["items"][0]["is_correct"] = False
    answered_ctx["items"][1]["user_answer"] = "B"
    answered_ctx["items"][1]["is_correct"] = True
    assert should_block_unanswered_reference_reveal("给点提示", answered_ctx) is False
    assert should_keep_unanswered_question_active_for_followup("给我整理记忆口诀", answered_ctx) is False


def _resume_decision(active_object: dict[str, Any]) -> dict[str, Any]:
    """A canonical routing-phase decision that asks to resume the suspended object."""

    return {
        "relation_to_active_object": "temporary_detour",
        "next_action": "route_to_followup_explainer",
        "allowed_patch": ["resume_suspended_object"],
        "confidence": 0.9,
        "reason": "回到刚才那道套题",
        "target_object_ref": {
            "object_type": str(active_object.get("object_type") or ""),
            "object_id": str(active_object.get("object_id") or ""),
        },
    }


def test_turn_start_demote_output_feeds_canonical_resume_as_pipeline() -> None:
    """turn-START 压栈的对象，经 metadata.suspended_object_stack 喂给 canonical 能被 resume。

    这证明两个相位是 pipeline（上游产出 → 下游消费），不是在同一输入上的两套冲突权威。
    """

    stored_active = build_active_object_from_question_context(_question_set_context())
    assert stored_active is not None
    assert stored_active["object_type"] == "question_set"

    # --- turn-START 相位：demote 块用 _prepend_suspended_object 把 stored set 压栈 ---
    # （turn_runtime.py demote 块在无 ordinal 引用时执行的就是这一步，输出写进
    #  stored_suspended_object_stack，并最终落进 metadata.suspended_object_stack。）
    demoted_stack = _prepend_suspended_object([], stored_active)
    assert [item["object_id"] for item in demoted_stack] == ["set-1"]

    # --- routing 相位：canonical 从 metadata.suspended_object_stack 读到该栈并 resume ---
    resumed_active, remaining_stack = apply_active_object_transition(
        previous_active_object=None,
        previous_suspended_object_stack=demoted_stack,  # 上游 turn-START 压栈输出
        turn_semantic_decision=_resume_decision(stored_active),
    )

    # canonical resume 拿回的正是 turn-START 压栈的同一个对象（pipeline 闭环）。
    assert resumed_active is not None
    assert resumed_active["object_id"] == "set-1"
    assert remaining_stack == []


def test_task14_ordinal_reference_blocks_turn_start_demote() -> None:
    """task#14：套题被 "第N题" 引用时 turn-START 不 demote —— 相位独有 SEV-1 保护。

    这是 routing 相位 (apply_active_object_transition) 没有的 turn-START 相位独占保护：
    保留套题 active，scene low-information gate 才锚得住 "第N题"，否则 fail-closed。
    """

    stored_active = build_active_object_from_question_context(_question_set_context())
    assert stored_active is not None
    stored_ctx = extract_question_context_from_active_object(stored_active)
    assert stored_ctx is not None

    # "第2题" 经单一 ordinal→item 权威 (requested_question_item_index) 命中 stored set 的 item，
    # 触发 stored_set_ordinal_referenced=True → demote 块的 guard 跳过压栈。
    assert (
        _message_references_stored_question_set_item("第2题的答案和考点讲讲", stored_ctx)
        is True
    )

    # 无 ordinal 引用（话题切换）时 guard 不触发 → demote 块照常压栈。
    assert (
        _message_references_stored_question_set_item("换个话题，讲讲地基处理", stored_ctx)
        is False
    )


def test_s1_submission_blocks_turn_start_demote() -> None:
    """S1 (2026-06-29)：本轮是对活跃题组的真实作答时 turn-START 不 demote。

    与 task#14 (ordinal) / #287 (re-present) 同形（"本轮引用了活跃对象 → 不要 demote"）。
    没有这条 carve-out 时，作答轮（batch "q1 B q2 C q3 A" / 裸答 "我选B"）不被识别为
    "引用活跃对象"，活跃 question_set 在 scene/grading dispatch 之前就被压栈 → 判分能力读不到
    题组 → 重显题面而非判分（live S1 0/6，turn-start 埋点实证 WILL_DEMOTE=True on 作答轮）。
    单一 submission 意图权威 = question_followup.resolve_submission_attempt。

    可证伪：删掉 carve-out（demote 条件不含 ``not stored_set_submission_referenced``）则
    作答轮被压栈，本测试断言的"作答→不 demote"行为消失。
    """

    # 3-item set so the batch "q1 q2 q3" maps to real items (the live S1 shape).
    three_item_set = {
        "question_id": "set-1",
        "items": [
            {
                "question_id": f"q{i}",
                "question_type": "choice",
                "question": f"第{i}题：下列哪个正确？",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            }
            for i in (1, 2, 3)
        ],
    }
    stored_active = build_active_object_from_question_context(three_item_set)
    assert stored_active is not None
    stored_ctx = extract_question_context_from_active_object(stored_active)
    assert stored_ctx is not None

    # batch 作答（带尾随讲解请求）→ 命中 submission carve-out → demote 守卫跳过压栈。
    assert (
        _message_is_submission_for_stored_set("q1 B q2 C q3 A，帮我对答案逐题讲解", stored_ctx)
        is True
    )
    # 裸答 → 命中 submission carve-out（保活，由下游 submission_confidence 决定判/澄清）。
    assert _message_is_submission_for_stored_set("我选B", stored_ctx) is True
    # 非作答（话题切换 / 纯追问）→ 不命中 → demote 块照常压栈（不误保活）。
    assert _message_is_submission_for_stored_set("换个话题，讲讲地基处理", stored_ctx) is False
    assert _message_is_submission_for_stored_set("这道题为什么选B", stored_ctx) is False


def _single_mcq_context() -> dict[str, Any]:
    """A single-question choice MCQ — the shape a stored active MCQ carries (#287)."""

    return {
        "question_id": "q_1",
        "question": "一级建造师注册证书的有效期是几年？",
        "question_type": "choice",
        "options": {"A": "1年", "B": "3年", "C": "4年", "D": "5年"},
        "user_answer": "",
        "is_correct": None,
        "multi_select": False,
        "items": [],
    }


def test_287_represent_reference_blocks_turn_start_demote() -> None:
    """#287: 学生 terse 引用活跃 MCQ 要求重排 / 重新展示时 turn-START 不 demote。

    与 task#14 ordinal carve-out 同形（"本轮引用了活跃对象 → 不要 demote"），让活跃 MCQ
    保持 active，tutorbot/deep_question 的确定性 re-present 短路才能 fire（不再幻觉换题）。
    单一 re-present 意图权威 = question_followup.message_has_represent_request_intent。
    """

    stored_active = build_active_object_from_question_context(_single_mcq_context())
    assert stored_active is not None
    assert stored_active["object_type"] == "single_question"
    stored_ctx = extract_question_context_from_active_object(stored_active)
    assert stored_ctx is not None

    # issue #287 复现用的 terse 措辞 → 命中 re-present 引用 → demote 守卫跳过压栈。
    assert _message_requests_active_mcq_represent("选项重新排列一下", stored_ctx) is True
    assert (
        _message_requests_active_mcq_represent("把abcd换个顺序重新给我看", stored_ctx) is True
    )

    # 换新题 / 作答 / 闲聊不算 re-present 引用 → demote 守卫照常压栈（不误伤）。
    assert _message_requests_active_mcq_represent("换一道题", stored_ctx) is False
    assert _message_requests_active_mcq_represent("我选B", stored_ctx) is False
    assert _message_requests_active_mcq_represent("这道题好难", stored_ctx) is False

    # 无 stored question context 时绝不触发（fail-safe）。
    assert _message_requests_active_mcq_represent("选项重新排列一下", None) is False


def test_287_represent_carveout_only_for_single_choice_mcq() -> None:
    """异源核(GLM)硬化：carve-out 只对单选 choice MCQ 生效。

    套题 batch / 非 choice / 即便带残留 question context 的对象，都不在本 carve-out 范围
    → 照常 demote（不误保活、不状态泄漏）。名实相符：是 active_MCQ_represent，不是 any-object。
    """

    # 套题 batch（items>1）即使命中 re-present 措辞也不触发 carve-out → 照常 demote。
    batch_ctx = _question_set_context()
    assert _message_requests_active_mcq_represent("选项重新排列一下", batch_ctx) is False

    # 非 choice（如 case 简答题）不触发。
    case_ctx = {
        "question_id": "c1",
        "question": "论述危大工程论证流程",
        "question_type": "case",
        "items": [],
    }
    assert _message_requests_active_mcq_represent("选项重新排列一下", case_ctx) is False

    # 单选 choice MCQ 才触发（对照组）。
    assert (
        _message_requests_active_mcq_represent("选项重新排列一下", _single_mcq_context())
        is True
    )


def test_turn_start_only_pushes_canonical_only_pops_phase_boundary() -> None:
    """相位边界：turn-START 只压栈、canonical 才出栈，两者不在同一输入上矛盾。

    - turn-START helper (_prepend_suspended_object) 把对象推入栈，永不出栈。
    - routing helper (apply_active_object_transition + resume_suspended_object) 才出栈。
    两者作用在 pipeline 的两端，不构成对同一决策的双重写。
    """

    set_a = build_active_object_from_question_context(_question_set_context())
    assert set_a is not None

    # turn-START 相位只压栈：传入对象一定进入栈，且不会触发 resume / 出栈。
    pushed = _prepend_suspended_object([], set_a)
    assert pushed[0]["object_id"] == "set-1"

    # 二次压栈仍只增不减（去重后 head 还是 set-1），证明 turn-START 不做出栈语义。
    pushed_again = _prepend_suspended_object(pushed, set_a)
    assert [item["object_id"] for item in pushed_again] == ["set-1"]

    # routing 相位才出栈：resume 决策把对象从栈中移出，栈变空。
    resumed_active, remaining_stack = apply_active_object_transition(
        previous_active_object=None,
        previous_suspended_object_stack=pushed,
        turn_semantic_decision=_resume_decision(set_a),
    )
    assert resumed_active is not None
    assert resumed_active["object_id"] == "set-1"
    assert remaining_stack == []  # canonical 完成出栈，turn-START 从不会做这一步
