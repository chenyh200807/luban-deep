"""R1 选项重排判分用题库字母（倒诬学生）—— 修复回归。

根因（2026-06-24 grep + 单元实证）：判分时结构上无题库 options，无法投影；R1 必须在
**存 grading authority 的上游**投影。`_fill_missing_mcq_authority(target=学生item,
source=题库item)` 同时持有学生面 + 题库面，是精确投影点——它原本把题库裸字母拷到保留
学生 option 面的 item 上 = 制造 surface 错配。修法：拷 correct_answer 时按 VALUE 投影到
学生面（`_project_correct_answer_to_target_surface`），fail-safe 映射不了就保留题库字母。

判分层 `answers_match` 不动（无题库 options 治不了本）；本测试验证上游投影使流到判分的
correct_answer 已是学生面字母。
"""
from __future__ import annotations

from deeptutor.capabilities.deep_question import (
    _fill_missing_mcq_authority,
    _project_correct_answer_to_target_surface,
)
from deeptutor.services.question_followup import answers_match


def test_project_correct_answer_remaps_bank_letter_to_learner_surface() -> None:
    """题库 5%=D，学生面 5%=A → 投影后 correct_answer='A'。"""
    src_options = {"A": "1%", "B": "2%", "C": "3%", "D": "5%"}  # 题库面：5% 在 D
    tgt_options = {"A": "5%", "B": "1%", "C": "3%", "D": "2%"}  # 学生面：5% 在 A
    assert _project_correct_answer_to_target_surface("D", src_options, tgt_options) == "A"


def test_fill_missing_authority_projects_then_grading_is_correct() -> None:
    """R1 端到端：学生粘贴选项重排题（5%在A），题库 source 5%=D；
    填充后 correct_answer 应投影成 'A'，学生选 A 判**对**（不再倒诬）。"""
    learner_item = {
        "question_type": "choice",
        "options": {"A": "5%", "B": "1%", "C": "3%", "D": "2%"},  # 学生当前面
        # correct_answer 缺失 → 走 _fill_missing_mcq_authority 恢复
    }
    bank_source = {
        "correct_answer": "D",  # 题库面字母（5% 在题库是 D）
        "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
        "explanation": "...",
    }
    filled = _fill_missing_mcq_authority(learner_item, bank_source)
    assert filled["correct_answer"] == "A", "题库字母 D 必须投影到学生面 A"
    # 学生保留自己的 option 面（不被题库面覆盖）
    assert filled["options"] == learner_item["options"]
    # 流到判分：学生选 A（值 5% = 正确）→ 判对
    assert answers_match("A", filled["correct_answer"], filled) is True


def test_fill_missing_authority_failsafe_keeps_bank_letter_on_ambiguous_values() -> None:
    """fail-safe：学生面有重复值（无法安全映射）→ 保留题库字母，绝不瞎猜。"""
    learner_item = {"question_type": "choice", "options": {"A": "5%", "B": "5%", "C": "3%", "D": "2%"}}
    bank_source = {"correct_answer": "D", "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"}}
    filled = _fill_missing_mcq_authority(learner_item, bank_source)
    assert filled["correct_answer"] == "D"  # 不投影（值有歧义），保留题库字母


def test_fill_missing_authority_no_learner_options_copies_bank_consistently() -> None:
    """学生 item 无自己的 options → 拷题库 options + 题库 correct_answer（同面一致，无需投影）。"""
    learner_item = {"question_type": "choice"}
    bank_source = {"correct_answer": "D", "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"}}
    filled = _fill_missing_mcq_authority(learner_item, bank_source)
    assert filled["correct_answer"] == "D"
    assert filled["options"] == bank_source["options"]
