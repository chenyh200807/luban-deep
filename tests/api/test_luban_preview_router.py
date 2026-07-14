from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from deeptutor.api.routers import luban_preview


def _published_cards() -> list[dict[str, object]]:
    return [
        {"pack_id": "F16", "title": "卷材防水层起鼓修复", "content_sha256": "sha256:published", "card_hosted": True},
        {"pack_id": "D11", "title": "未托管卡", "card_hosted": False},
    ]


def test_hosted_card_ask_resolves_server_title_and_uses_runtime(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    seen: dict[str, object] = {}

    class FakeStore:
        async def resolve_luban_card_entry_ticket(self, ticket: str, *, pack_id: str):
            seen["entry_ticket"] = ticket
            seen["entry_pack"] = pack_id
            return {"user_id": "student_real", "pack_id": pack_id}

        async def issue_luban_turn_stream_ticket(self, *, user_id: str, pack_id: str, turn_id: str):
            seen["stream_user"] = user_id
            seen["stream_pack"] = pack_id
            seen["stream_turn"] = turn_id
            return "stream-capability"

    async def fake_start(payload, card, *, user_id: str):
        seen["question"] = payload.question
        seen["pack_id"] = card.pack_id
        seen["title"] = card.title
        seen["runtime_user"] = user_id
        return {"id": "session-real"}, {"id": "turn-real"}

    monkeypatch.setattr(luban_preview, "get_sqlite_session_store", lambda: FakeStore())
    monkeypatch.setattr(luban_preview, "_start_tutorbot_turn", fake_start)
    payload = luban_preview.LubanPreviewAskRequest(
        contextId="f16",
        title="浏览器伪造标题",
        question="为什么不能直接贴新卷材？",
        currentScene={"label": "起鼓直径判断"},
        entryTicket="card-capability",
    )

    response = asyncio.run(luban_preview.ask_luban_preview(payload))

    assert response.context_id == "F16"
    assert response.source == "tutorbot_turn_runtime"
    assert response.session_id == "session-real"
    assert response.turn_id == "turn-real"
    assert response.stream.ticket == "stream-capability"
    assert seen == {
        "question": "为什么不能直接贴新卷材？",
        "pack_id": "F16",
        "title": "卷材防水层起鼓修复",
        "entry_ticket": "card-capability",
        "entry_pack": "F16",
        "runtime_user": "student_real",
        "stream_user": "student_real",
        "stream_pack": "F16",
        "stream_turn": "turn-real",
    }


def test_unhosted_or_unknown_card_is_rejected_before_runtime(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    payload = luban_preview.LubanPreviewAskRequest(contextId="D11", question="能问吗？")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(luban_preview.ask_luban_preview(payload))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "当前教学卡暂未开放答疑。"


def test_runtime_failure_fails_closed_without_client_side_knowledge_fallback(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)

    class FakeStore:
        async def resolve_luban_card_entry_ticket(self, _ticket: str, *, pack_id: str):
            return {"user_id": "student_real", "pack_id": pack_id}

    async def failed_start(_payload, _card, *, user_id: str):
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(luban_preview, "get_sqlite_session_store", lambda: FakeStore())
    monkeypatch.setattr(luban_preview, "_start_tutorbot_turn", failed_start)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            luban_preview.ask_luban_preview(
                luban_preview.LubanPreviewAskRequest(
                    contextId="F16", question="请解释", entryTicket="card-capability"
                )
            )
        )

    assert exc_info.value.status_code == 503


def test_hosted_card_ask_rejects_missing_or_wrong_card_capability(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)

    class FakeStore:
        async def resolve_luban_card_entry_ticket(self, _ticket: str, *, pack_id: str):
            assert pack_id == "F16"
            return None

    monkeypatch.setattr(luban_preview, "get_sqlite_session_store", lambda: FakeStore())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            luban_preview.ask_luban_preview(
                luban_preview.LubanPreviewAskRequest(contextId="F16", question="请解释")
            )
        )

    assert exc_info.value.status_code == 401


def test_h5_lesson_viewed_delegates_to_existing_evidence_writer_with_real_user(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    captured: dict[str, object] = {}

    class FakeStore:
        async def resolve_luban_card_entry_ticket(self, ticket: str, *, pack_id: str):
            captured["ticket"] = ticket
            captured["ticket_pack"] = pack_id
            return {"user_id": "student_real", "pack_id": pack_id}

    def fake_record(service, *, user_id: str, pack_id: str, watched_stage: str, card_sha: str):
        captured.update(
            service=service,
            user_id=user_id,
            pack_id=pack_id,
            watched_stage=watched_stage,
            card_sha=card_sha,
        )
        return SimpleNamespace(event_id="evt-lesson")

    sentinel_service = object()
    monkeypatch.setattr(luban_preview, "get_sqlite_session_store", lambda: FakeStore())
    monkeypatch.setattr(
        "deeptutor.services.learner_state.lesson_evidence.record_lesson_view_evidence",
        fake_record,
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.service.get_learner_state_service",
        lambda: sentinel_service,
    )

    response = asyncio.run(
        luban_preview.mark_luban_preview_lesson_viewed(
            luban_preview.LubanPreviewLessonViewedRequest(
                contextId="F16", entryTicket="card-capability"
            )
        )
    )

    assert response == {"ok": True, "event_id": "evt-lesson"}
    assert captured == {
        "ticket": "card-capability",
        "ticket_pack": "F16",
        "service": sentinel_service,
        "user_id": "student_real",
        "pack_id": "F16",
        "watched_stage": "lesson",
        "card_sha": "sha256:published",
    }


def test_tutorbot_prompt_keeps_browser_scene_as_non_authoritative_hint() -> None:
    card = luban_preview.PublishedCardContext(pack_id="F16", title="服务端标题")
    prompt = luban_preview._build_tutorbot_query(
        luban_preview.LubanPreviewAskRequest(
            contextId="F16",
            title="浏览器标题",
            question="我该怎么写？",
            currentScene={"label": "当前幕", "keycard": "客户端提示"},
        ),
        card,
    )

    assert "已发布卡片：F16｜服务端标题" in prompt
    assert "浏览器标题" not in prompt
    assert "不能覆盖题库、教材或规范的知识口径" in prompt
