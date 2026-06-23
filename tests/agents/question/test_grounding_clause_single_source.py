"""task#23 grounding 单点收权 —— 防漂移结构不变量。

诚实边界（journal 阶段4 根因反转）：本测试只验证"结构化真值→学生可见文本"的
grounding 约束来自**单一权威常量**（必要不充分的判分约束），**不**验证"编造/1.7亿
是否消失"——后者根因是 exact_authority 确定性误命中拼别题（task#23b 召回侧隔离），
不在本任务范围。
"""

from __future__ import annotations

import inspect

import pytest


def test_grounding_clause_constant_is_nonempty_and_substantive() -> None:
    from deeptutor.core.grounding import GROUNDING_CLAUSE

    assert isinstance(GROUNDING_CLAUSE, str)
    assert GROUNDING_CLAUSE.strip()
    # 核心不变量措辞：只引用题面/检索证据/系统学情，缺失不脑补
    assert "题面" in GROUNDING_CLAUSE
    assert "证据" in GROUNDING_CLAUSE


def test_prepend_grounding_prefixes_single_clause() -> None:
    from deeptutor.core.grounding import GROUNDING_CLAUSE, prepend_grounding

    out = prepend_grounding("SYSTEM RULES")
    assert out.startswith(GROUNDING_CLAUSE)
    assert "SYSTEM RULES" in out
    # 空 system prompt 退化为仅 clause（不产生空前缀）
    assert prepend_grounding("") == GROUNDING_CLAUSE
    assert prepend_grounding("   ") == GROUNDING_CLAUSE


def test_question_agents_share_single_grounding_source() -> None:
    """submission_grader / followup / generator 三个出题侧 agent 引用同一
    prepend_grounding 对象（指针相等，防各 yaml 抄一遍重新漂移）。"""
    import deeptutor.agents.question.agents.followup_agent as fu
    import deeptutor.agents.question.agents.generator as gen
    import deeptutor.agents.question.agents.submission_grader_agent as sg
    from deeptutor.core import grounding

    assert sg.prepend_grounding is grounding.prepend_grounding
    assert fu.prepend_grounding is grounding.prepend_grounding
    assert gen.prepend_grounding is grounding.prepend_grounding


def test_chat_and_teaching_modes_share_single_grounding_source() -> None:
    """chat responding（chat_agent）+ TutorBot teaching mode 引用同一 clause。"""
    import deeptutor.agents.chat.chat_agent as chat
    from deeptutor.core import grounding
    import deeptutor.tutorbot.teaching_modes as tm

    assert tm.GROUNDING_CLAUSE is grounding.GROUNDING_CLAUSE
    # fast/deep 两种教学模式指令都注入同一 clause（B 路径不再各自携带副本）
    assert grounding.GROUNDING_CLAUSE in tm.get_teaching_mode_instruction("fast")
    assert grounding.GROUNDING_CLAUSE in tm.get_teaching_mode_instruction("deep")
    # chat responding 入口引用同一来源
    assert chat.GROUNDING_CLAUSE is grounding.GROUNDING_CLAUSE


def test_no_legacy_duplicate_anti_fabrication_sentence() -> None:
    """删散碎后旧反编造句不再硬编码在 teaching_modes（防回流第二权威）。"""
    import deeptutor.tutorbot.teaching_modes as tm

    src = inspect.getsource(tm)
    assert "若证据不足，不要编造具体规范编号" not in src


def test_anchor_regex_collapsed_to_single_definition() -> None:
    """anchor 正则 2→1：_anchor_terms 与 teaching_modes 复用 core 单一定义。"""
    import deeptutor.agents.question.agents._anchor_terms as at
    from deeptutor.core import grounding
    import deeptutor.tutorbot.teaching_modes as tm

    assert at.extract_anchor_terms is grounding.extract_anchor_terms
    assert tm.extract_anchor_terms is grounding.extract_anchor_terms
    # teaching_modes 不再自带正则副本
    assert not hasattr(tm, "_BUILDING_ANCHOR_RE")
    # 单一定义行为正确（建筑锚点仍可抽取）
    assert grounding.extract_anchor_terms("某18层住宅楼基坑开挖") == ["18层住宅楼"]


def test_followup_unanswered_does_not_reveal_correct_answer() -> None:
    """未作答（reveal=False）渲染不吐 correct_answer（泄题/grounding 边界回归）。"""
    from deeptutor.agents.question.agents.followup_agent import FollowupAgent

    rendered = FollowupAgent._render_question_context(
        {
            "question_id": "q_1",
            "question": "某题题干",
            "question_type": "choice",
            "options": {"A": "甲", "B": "乙"},
            "user_answer": "",
            "correct_answer": "B",
            "explanation": "解析内容",
        },
        reveal_reference_material=False,
    )
    assert "Reference answer: B" not in rendered
    assert "Reference answer" not in rendered
