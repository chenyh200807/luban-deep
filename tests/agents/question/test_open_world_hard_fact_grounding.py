"""闸-4 — open-world 判分 directive 的硬事实纪律(防"4000万"类运行时现编).

根因(2026-06-24 端到端 eval + 三厂异源 + 教材仲裁):bot 在缺参考答案的 open-world 判分里
用"专业推理"臆造具体阈值(如"二级资质合同额4000万")当规范依据。单一权威 GROUNDING_CLAUSE
已禁止编造具体数值/规范编号,但 submission_grader 的 open-world directive 那句"或专业推理"
局部抵触(authority drift)——给 LLM 重新开了用专业推理生成硬事实依据的逃生口。

本测试钉死:open-world directive 不得把"专业推理"授权为硬事实**依据**的来源;专业推理只用于
判断逻辑(哪个答案对),具体数值/规范编号/条文/阈值的依据必须回归 grounding 证据。
不验证"是否拒判"——open-world 仍必须判(硬约束40),只约束依据来源。
"""
from __future__ import annotations

from deeptutor.agents.question.agents.submission_grader_agent import (
    SubmissionGraderAgent,
)


def _render_missing_authority() -> str:
    # 无 construction_grading_result + 无 correct_answer => missing_answer_authority
    return SubmissionGraderAgent._render_question_context(
        {
            "question_id": "q_zizhi",
            "question_type": "choice",
            "question": "某工业厂房建筑高度120m，合同额3800万，（）资质的施工总承包企业可承接。",
            "options": {"A": "特级", "B": "一级", "C": "二级", "D": "三级"},
            "user_answer": "C",
            "correct_answer": "",  # 无参考答案 → open-world
        }
    )


def test_open_world_directive_present_and_does_not_refuse() -> None:
    """open-world 仍必须判分(不拒判),directive 在位。"""
    rendered = _render_missing_authority()
    assert "Open-world adjudication directive" in rendered
    assert "禁止以缺少标准答案为由拒绝判分" in rendered


def test_professional_reasoning_not_authorized_for_hard_fact_basis() -> None:
    """专业推理不得被授权为硬事实**依据**来源——旧 drift 措辞'…证据或专业推理'(把专业推理
    并列为判定依据来源)必须消失。"""
    rendered = _render_missing_authority()
    # 旧逃生口:把"专业推理"并列成判定依据的来源
    assert "检索证据或专业推理" not in rendered
    assert "证据与专业推理独立裁决" not in rendered


def test_hard_fact_basis_must_trace_to_grounding_not_fabricated() -> None:
    """directive 必须显式把硬事实(具体数值/规范编号/阈值)的依据收回 grounding 证据,
    并禁止用专业推理臆造具体值。"""
    rendered = _render_missing_authority()
    # 必须出现硬事实纪律:专业推理限于判断逻辑,具体数值/规范编号依据须来自证据,无证据不臆造
    assert "判断逻辑" in rendered
    assert "臆造" in rendered
    # 必须点名硬事实类别(数值/规范编号/阈值之一)受证据约束
    assert any(k in rendered for k in ("具体数值", "规范编号", "阈值", "条文号"))
