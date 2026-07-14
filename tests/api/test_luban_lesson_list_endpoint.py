from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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


def test_card_entry_is_bound_to_authenticated_user_and_hosted_pack(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeStore:
        async def issue_luban_card_entry_ticket(self, *, user_id: str, pack_id: str) -> str:
            captured.update(user_id=user_id, pack_id=pack_id)
            return "card-capability"

    monkeypatch.setattr(
        luban_lesson,
        "build_lesson_viewmodel",
        lambda pack_id: {"pack_id": str(pack_id).upper(), "card_url": "https://cards.example/f16/lesson.html"},
    )
    monkeypatch.setattr(luban_lesson, "get_sqlite_session_store", lambda: FakeStore())

    response = asyncio.run(
        luban_lesson.issue_card_entry("f16", current_user=SimpleNamespace(user_id="student_real"))
    )

    assert response.entry_ticket == "card-capability"
    assert response.expires_in_seconds == 45 * 60
    assert captured == {"user_id": "student_real", "pack_id": "F16"}


def test_card_entry_fails_closed_when_no_hosted_card(monkeypatch) -> None:
    monkeypatch.setattr(luban_lesson, "build_lesson_viewmodel", lambda _pack_id: {"pack_id": "F16", "card_url": ""})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(luban_lesson.issue_card_entry("f16", current_user=SimpleNamespace(user_id="student_real")))

    assert exc_info.value.status_code == 404
