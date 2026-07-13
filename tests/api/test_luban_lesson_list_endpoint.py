from __future__ import annotations

import asyncio

from deeptutor.api.routers import luban_lesson


def test_lessons_exposes_manifest_pack_universe(monkeypatch) -> None:
    monkeypatch.setattr(luban_lesson, "list_all_pack_ids", lambda: ["A01", "B02", "C02"])
    monkeypatch.setattr(
        luban_lesson,
        "list_green_lessons",
        lambda: [{"pack_id": "A01", "retest_available": False, "card_hosted": True}],
    )
    monkeypatch.setattr(luban_lesson, "_review_module_enabled", lambda: False)
    monkeypatch.setattr(luban_lesson, "_light_practice_enabled", lambda: False)

    payload = asyncio.run(luban_lesson.lessons(None))

    assert payload["pack_universe"] == 3
    assert payload["lessons"] == [{
        "pack_id": "A01",
        "retest_available": False,
        "card_hosted": True,
        "light_practice_available": False,
    }]
