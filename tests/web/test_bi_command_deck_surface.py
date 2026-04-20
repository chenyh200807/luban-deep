from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_bi_page_source() -> str:
    return (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "page.tsx").read_text(encoding="utf-8")


def test_bi_command_deck_hero_copy_exists() -> None:
    source = _read_bi_page_source()

    assert "DeepTutor BI Deck" in source
    assert "经营、质量、会员、TutorBot 四条主线的一体化指挥舱" in source


def test_bi_command_deck_navigation_chips_exist() -> None:
    source = _read_bi_page_source()

    assert "Overview" in source
    assert "Quality" in source
    assert "Member Ops" in source
    assert "TutorBot" in source


def test_bi_command_deck_removed_jump_links() -> None:
    source = _read_bi_page_source()

    assert "function JumpChip" not in source
    assert 'href="#trend"' not in source
    assert 'href="#knowledge"' not in source


def test_bi_command_deck_learner_detail_title_exists() -> None:
    source = _read_bi_page_source()

    assert 'title="Learner 360"' in source
