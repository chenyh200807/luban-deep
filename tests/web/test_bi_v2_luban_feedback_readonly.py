"""BI v2 内测回访：答卷只读，运营侧只保留删除/归档动作。"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PANEL = REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "_v2" / "feedback" / "BiV2FeedbackPanel.tsx"


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def test_luban_feedback_keeps_full_detail_but_removes_editing_controls() -> None:
    source = PANEL.read_text(encoding="utf-8")
    luban_section = _between(source, "function LubanFeedbackCard", "function InvitePrescriptionHero")

    assert "完整问卷反馈" in luban_section
    assert "删除" in luban_section
    assert "编辑内测回访" not in luban_section
    assert "保存并审计" not in luban_section
    assert "运营状态" not in luban_section
    assert "运营备注" not in luban_section
