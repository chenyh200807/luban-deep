"""R1 选项重排判分用题库字母（倒诬学生）—— 复现 + 修复回归。

根因（2026-06-24 grep 实证）：投影权威 `_project_to_query_option_surface` 只被
RAG 检索侧（historical_questions.py / supabase.py）+ LLM grounding 文本
（loop.py:2512 project_grounding_text_to_query_surface）消费；**判分侧确定性
`answers_match` 路径零投影调用** = dormant authority / unconsumed island。

当学生粘贴的题与题库同题但选项顺序不同（值 5% 在题库是 D、学生当前题面是 A），
判分拿题库面字母 "D" 在学生当前面 options 上比，把答对判错。

修复方向：判分前把 `correct_answer` 投影到学生当前题面（消费已存在的投影权威），
或让判分按 VALUE 比对而非字母。修复落点在**上游 grading-context 构建**（题库
options 仍在处），不在 answers_match（那里只有当前面无题库面，无法投影）。

本测试当前 **FAIL = R1 复现**；修复后转 GREEN。
"""
from __future__ import annotations

import pytest

from deeptutor.services.question_followup import answers_match


def test_answers_match_projected_surface_is_correct() -> None:
    """对照：correct_answer 已投影到当前面（A）时判分正确——证明投影后 answers_match 工作。"""
    ctx = {
        "question_type": "choice",
        "options": {"A": "5%", "B": "1%", "C": "3%", "D": "2%"},
        "correct_answer": "A",  # 已投影到当前面
    }
    assert answers_match("A", "A", ctx) is True


@pytest.mark.xfail(
    reason="R1 未修：判分侧不消费投影权威，用题库面字母比当前面 → 倒诬学生。"
    "修复后去掉 xfail。",
    strict=True,
)
def test_answers_match_reordered_options_does_not_misgrade() -> None:
    """R1 复现：题库 correct_answer='D'（值5%在题库是D），学生当前题面 5% 在 A，
    学生选 A（值5%=正确）→ 应判**对**。当前用题库字母比 → 判错（倒诬学生）。"""
    ctx_current_surface = {
        "question_type": "choice",
        "options": {"A": "5%", "B": "1%", "C": "3%", "D": "2%"},  # 当前面：5% 在 A
        "correct_answer": "D",  # 题库面裸字母（未投影）
    }
    # 学生选 A（值 5% = 正确答案的值）→ 必须判对
    assert answers_match("A", "D", ctx_current_surface) is True
