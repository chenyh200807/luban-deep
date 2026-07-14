from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.api.routers import luban_lesson


def test_lessons_exposes_manifest_pack_universe(monkeypatch) -> None:
    monkeypatch.setattr(luban_lesson, "list_all_pack_ids", lambda: ["A01", "B02", "C02"])
    green_lessons = [
            {
                "pack_id": "A01",
                "retest_available": False,
                "card_hosted": True,
                "teaching_episode_count": 2,
            }
        ]
    teaching_points = [
            {
                "teaching_point_id": "A01:lesson:1",
                "pack_id": "A01",
                "episode_index": 1,
                "episode_total": 2,
            },
            {
                "teaching_point_id": "A01:lesson:2",
                "pack_id": "A01",
                "episode_index": 2,
                "episode_total": 2,
            },
        ]
    monkeypatch.setattr(
        luban_lesson,
        "list_lesson_catalog",
        lambda: (green_lessons, teaching_points),
    )
    monkeypatch.setattr(luban_lesson, "_review_module_enabled", lambda: False)
    monkeypatch.setattr(luban_lesson, "_light_practice_enabled", lambda: False)

    payload = asyncio.run(luban_lesson.lessons(None))

    assert payload["pack_universe"] == 3
    assert payload["teaching_point_universe"] == 2
    assert payload["teaching_topic_universe"] == 1
    assert payload["teaching_points"] == [
        {
            "teaching_point_id": "A01:lesson:1",
            "pack_id": "A01",
            "episode_index": 1,
            "episode_total": 2,
        },
        {
            "teaching_point_id": "A01:lesson:2",
            "pack_id": "A01",
            "episode_index": 2,
            "episode_total": 2,
        },
    ]
    assert payload["lessons"] == [{
        "pack_id": "A01",
        "retest_available": False,
        "card_hosted": True,
        "teaching_episode_count": 2,
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


def test_lesson_detail_forwards_episode_to_the_single_read_model(monkeypatch) -> None:
    captured = {}

    def _build(pack_id, *, episode_index):
        captured.update(pack_id=pack_id, episode_index=episode_index)
        return {"pack_id": pack_id, "teaching_episode": {"index": episode_index}}

    monkeypatch.setattr(luban_lesson, "build_lesson_viewmodel", _build)

    payload = asyncio.run(luban_lesson.lesson_detail("D14", episode=2, _=None))

    assert captured == {"pack_id": "D14", "episode_index": 2}
    assert payload["teaching_episode"] == {"index": 2}
