"""R4 自承无答案仍编采分点+硬配分 —— 案例判分 open_skill authority guard 防漂移。

g4 T7:bot 自承"检索没命中标准答案"后仍编完整采分点 + 硬给 5.5/6。
根因:这违反了**已存在**的案例判分规则(open_skill 不硬估标准分 + 不得自拼 rubric)。
属"规则在但 live 未强制"类(同 R5),真正残留是运行时强制(最可能 TutorBot 自由文本绕过
case_kernel,违 capability.md §硬约束 33)。本测试钉住这条 authority guard 不被悄悄删除
(防漂移),live 强制验证另需跑 g4 序列(规则已在,不需新规则)。
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_DIR = _REPO_ROOT / "deeptutor/tutorbot/skills/construction-case-grading"


def _read(rel: str) -> str:
    return (_SKILL_DIR / rel).read_text(encoding="utf-8")


def test_open_skill_must_not_hard_estimate_standard_score() -> None:
    """open_skill 档必须明确'不硬估标准分'——防这条规则被漂移删除。"""
    protocol = _read("references/grading-protocol.md")
    skill = _read("SKILL.md")
    assert "不硬估标准分" in protocol or "不硬估标准分" in skill
    assert "open_skill" in skill


def test_open_skill_authority_guard_forbids_self_assembled_rubric() -> None:
    """authority guard:不得仅凭模型常识/相似题/题面暗示自拼 projected_rubric。"""
    skill = _read("SKILL.md")
    assert "Authority guard" in skill
    assert "不得仅凭模型常识" in skill
    assert "projected_rubric" in skill
