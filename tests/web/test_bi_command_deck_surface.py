from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_bi_page_source() -> str:
    return (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "page.tsx").read_text(encoding="utf-8")


def test_bi_command_deck_hero_copy_exists() -> None:
    source = _read_bi_page_source()

    assert "DeepTutor BI Deck" in source
    assert "经营、质量、会员、TutorBot 四条主线的一体化指挥舱" in source


def test_bi_command_deck_primary_tabs_contract_exists() -> None:
    source = _read_bi_page_source()

    assert "经营、质量、会员、TutorBot 四条主线的一体化指挥舱" in source
    assert re.search(
        r'(?s)const\s+\w*Tabs?\s*=\s*\[.*?label:\s*"Overview".*?label:\s*"Quality".*?label:\s*"Member Ops".*?label:\s*"TutorBot".*?\]',
        source,
    )


def test_bi_command_deck_removed_jump_links() -> None:
    source = _read_bi_page_source()

    old_section_hrefs = (
        'href="#overview"',
        'href="#trend"',
        'href="#tutorbot"',
        'href="#capability"',
        'href="#knowledge"',
        'href="#member"',
    )

    assert not any(href in source for href in old_section_hrefs)


def test_bi_command_deck_learner_detail_title_exists() -> None:
    source = _read_bi_page_source()

    assert 'title="Learner 360"' in source
