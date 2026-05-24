from __future__ import annotations

from pathlib import Path


def test_fetch_script_documents_pinned_snapshot_contract() -> None:
    script = Path("scripts/fetch_hermes_upstream.sh").read_text(encoding="utf-8")

    assert "HERMES_EDU_SOURCE" in script
    assert "v0.18.6" in script
    assert "3646be2" in script
    assert "https://github.com/zhongweiv/hermes-edu-skills.git" in script
    assert "rev-parse HEAD" in script
