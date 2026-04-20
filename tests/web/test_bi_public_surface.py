from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sidebar_keeps_bi_visible_without_web_auth() -> None:
    source = (REPO_ROOT / "web" / "components" / "sidebar" / "SidebarShell.tsx").read_text(encoding="utf-8")

    assert 'if (item.href === "/" || item.href === "/bi") return true;' in source
