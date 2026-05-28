"""Tests for the closed-book quality eval pipeline (offline, injected completer).

No network / no LLM: a fake completer drives the scoring + aggregation so the
verified-transmit pipeline is provably correct before any keyed run.
"""

from __future__ import annotations

import asyncio

from deeptutor.services.benchmark.exam_quality_bank import ExamQuestion
from deeptutor.services.benchmark.exam_quality_eval import (
    build_closed_book_prompt,
    run_closed_book_eval,
)

_Q_SINGLE = ExamQuestion(
    question_id="2025-sc-01",
    year=2025,
    type="single_choice",
    exact_question={
        "answer_kind": "mcq",
        "correct_answer": "B",
        "stem": "下列建筑物中，属于工业建筑的是（ ）。",
        "options": {"A": "电影院", "B": "仓储建筑", "C": "住宅", "D": "饲料加工站"},
    },
)
_Q_MULTI = ExamQuestion(
    question_id="2023-mc-01",
    year=2023,
    type="multiple_choice",
    exact_question={
        "answer_kind": "mcq",
        "correct_answer": "ABD",
        "stem": "下列焊接方法中属于熔焊的有（ ）。",
        "options": {"A": "塞焊", "B": "槽焊", "C": "电渣焊", "D": "气电立焊", "E": "坡口焊"},
    },
)


def test_prompt_discloses_type_not_answer_count() -> None:
    p_single = build_closed_book_prompt(_Q_SINGLE.exact_question, is_multiple=False)
    p_multi = build_closed_book_prompt(_Q_MULTI.exact_question, is_multiple=True)
    assert "单选题" in p_single and "多选题" not in p_single
    assert "多选题" in p_multi
    # must not leak the authoritative answer / its letter count
    assert "答案：B" not in p_single
    assert "答案：ABD" not in p_multi
    # options are presented; the answer format is instructed
    assert "仓储建筑" in p_single
    assert "答案：" in p_single and "字母" in p_single


def test_perfect_model_scores_full_accuracy() -> None:
    async def perfect(*, prompt, system_prompt, model, **kwargs):
        # An oracle model that always answers the correct letters.
        which = "ABD" if "多选题" in prompt else "B"
        return f"答案：{which}"

    result = asyncio.run(
        run_closed_book_eval([_Q_SINGLE, _Q_MULTI], completer=perfect)
    )
    assert result.accuracy == 1.0
    assert result.errors == 0
    assert result.by_year[2025] == {"total": 1, "correct": 1}


def test_wrong_and_erroring_model() -> None:
    async def flaky(*, prompt, system_prompt, model, **kwargs):
        if "多选题" in prompt:
            raise RuntimeError("provider timeout")
        return "答案：C"  # wrong on the single

    result = asyncio.run(
        run_closed_book_eval([_Q_SINGLE, _Q_MULTI], completer=flaky)
    )
    assert result.accuracy == 0.0
    assert result.errors == 1
    assert all(s.correct is False for s in result.scores)
