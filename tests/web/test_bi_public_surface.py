from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_bi_page_source() -> str:
    return (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "page.tsx").read_text(encoding="utf-8")


def test_bi_page_is_not_guarded_by_generic_web_auth() -> None:
    source = _read_bi_page_source()

    assert "if (!requiresWebAuth())" not in source
    assert 'title="BI workspace unavailable"' not in source


def test_sidebar_keeps_bi_visible_without_web_auth() -> None:
    source = (REPO_ROOT / "web" / "components" / "sidebar" / "SidebarShell.tsx").read_text(encoding="utf-8")

    assert 'if (item.href === "/" || item.href === "/bi") return true;' in source
