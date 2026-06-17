"""BI v2 会员对话工作台：摘要与全文需要结构化 Markdown 渲染。"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DRAWER = (
    REPO_ROOT
    / "web"
    / "app"
    / "(workspace)"
    / "bi"
    / "_v2"
    / "member-ops"
    / "ConversationReviewDrawer.tsx"
)


def test_conversation_summary_and_messages_use_markdown_renderer() -> None:
    source = DRAWER.read_text(encoding="utf-8")

    assert "SimpleMarkdownRenderer" in source
    assert "ConversationMarkdown" in source
    assert "text={session.summary}" in source
    assert "text={message.content}" in source
    assert "摘要：" not in source


def test_conversation_markdown_normalizes_inline_headings_and_rules() -> None:
    source = DRAWER.read_text(encoding="utf-8")

    assert "normalizeConversationMarkdown" in source
    assert ".replace(/\\s+---\\s+/g, '\\n\\n---\\n\\n')" in source
    assert ".replace(/\\s+(#{1,6}\\s+)/g, '\\n\\n$1')" in source
