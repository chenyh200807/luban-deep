"""Member 360 must not pass a DOM click event as the selected member."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEMBER_360_DRAWER = (
    REPO_ROOT
    / "web"
    / "app"
    / "(workspace)"
    / "bi"
    / "_v2"
    / "member-ops"
    / "Member360Drawer.tsx"
)


def test_conversation_buttons_do_not_leak_click_event_into_member_handoff() -> None:
    source = MEMBER_360_DRAWER.read_text(encoding="utf-8")

    assert source.count("onClick={() => onOpenConversation()}") == 2
    assert "onClick={onOpenConversation}" not in source
