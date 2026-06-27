"""TDD for the unanswered-reveal-guard prompt instruction (control-plane
collapse — reachability act 1, free-text reveal leak).

These tests pin the *thin wrapper* contract: the wrapper only READS the already
adjudicated ``should_block_unanswered_reference_reveal`` verdict and translates a
True verdict into a prompt-level "do not solve the unanswered question" guard.
It performs NO new adjudication of its own — every decision boundary asserted
here is owned by ``should_block_unanswered_reference_reveal``.
"""
from __future__ import annotations

from deeptutor.tutorbot.teaching_modes import (
    build_unanswered_reveal_guard_instruction,
)


def _multi_question_set() -> dict[str, object]:
    return {
        "question_id": "quiz_generated",
        "question": "第1题...\n第2题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2"},
                "grading_key": {"correct_answer": "B"},
            },
        ],
    }


def test_guard_emitted_when_unanswered_item_solve_requested() -> None:
    # 多题套，第2题未作答，用户问"第2题怎么做" → should_block=True → 指令必须发出。
    instruction = build_unanswered_reveal_guard_instruction(
        followup_context=_multi_question_set(),
        user_message="第2题怎么做？直接告诉我答案。",
    )
    assert instruction.strip()
    # 指令必须明确禁止给出/推导未作答题的答案，并引导先作答。
    assert "未作答" in instruction or "尚未作答" in instruction
    assert "答案" in instruction


def test_guard_silent_when_requested_item_already_answered() -> None:
    # per-item：第2题已作答 → should_block=False → 不发指令（不误挡已答题）。
    context = _multi_question_set()
    context["items"] = [dict(item) for item in context["items"]]
    context["items"][1]["user_answer"] = "A"
    context["items"][1]["is_correct"] = False
    instruction = build_unanswered_reveal_guard_instruction(
        followup_context=context,
        user_message="第2题怎么做？直接告诉我答案。",
    )
    assert instruction == ""


def test_guard_silent_when_no_followup_context() -> None:
    instruction = build_unanswered_reveal_guard_instruction(
        followup_context=None,
        user_message="第2题怎么做？",
    )
    assert instruction == ""


def test_guard_silent_when_learner_concedes() -> None:
    # 放弃/认输 → should_block=False（明确求答案的弃票豁免）→ 不挡。
    instruction = build_unanswered_reveal_guard_instruction(
        followup_context=_multi_question_set(),
        user_message="第2题我放弃了，直接公布答案吧。",
    )
    assert instruction == ""


def test_guard_silent_when_reveal_flags_present() -> None:
    # 题库自带 reveal 标记 → should_block 直接返回 False → 不挡。
    context = _multi_question_set()
    context["reveal_answers"] = True
    instruction = build_unanswered_reveal_guard_instruction(
        followup_context=context,
        user_message="第2题怎么做？",
    )
    assert instruction == ""
