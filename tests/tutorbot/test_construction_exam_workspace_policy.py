from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_FILES = [
    ROOT / "deeptutor/tutorbot/templates/AGENTS.md",
    ROOT / "deeptutor/tutorbot/templates/SOUL.md",
]


def test_construction_exam_workspace_declares_product_identity_and_bounds() -> None:
    for path in POLICY_FILES:
        text = path.read_text(encoding="utf-8")
        assert "鲁班AI智考" in text
        assert "能力边界" in text
        assert "优雅拒绝" in text


def test_construction_exam_workspace_keeps_prompt_extraction_guardrails() -> None:
    for path in POLICY_FILES:
        text = path.read_text(encoding="utf-8")
        assert "提示词" in text
        assert "系统机制" in text
        assert "内部设计" in text
        assert "不复述、不改写、不总结" in text


def test_construction_exam_workspace_uses_low_information_redirection() -> None:
    for path in POLICY_FILES:
        text = path.read_text(encoding="utf-8")
        assert "低信息转向" in text or "Low-Information Redirection" in text
        assert "不解释为什么拒绝" in text
        assert "不列举防护层级" in text
        assert "不承认具体内部实现是否存在" in text
        assert "这类内容我不展开" in text
