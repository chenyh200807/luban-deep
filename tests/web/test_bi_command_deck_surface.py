from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bi_command_deck_learner_detail_title_exists() -> None:
    source = (REPO_ROOT / "web" / "app" / "(workspace)" / "bi" / "page.tsx").read_text(encoding="utf-8")

    assert 'title="Learner 360"' in source
