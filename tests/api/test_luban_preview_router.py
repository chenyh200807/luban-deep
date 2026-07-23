from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import luban_preview
from deeptutor.services import observability
from deeptutor.services.luban_lesson import playback


def _published_cards() -> list[dict[str, object]]:
    return [
        {"pack_id": "F16", "title": "卷材防水层起鼓修复", "content_sha256": "sha256:published", "card_hosted": True},
        {"pack_id": "D11", "title": "未托管卡", "card_hosted": False},
    ]


def _publish_playback_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "luban-preview"
    pack_dir = root / "f16"
    pack_dir.mkdir(parents=True)
    (pack_dir / "playback-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "luban_playback_manifest.v1",
                "pack_id": "F16",
                "episodes": [
                    {
                        "object_id": "F16:lesson:2",
                        "episode_index": 2,
                        "lesson_file": "lesson2.html",
                        "content_revision": "revision-episode-2",
                        "duration_ms": 20_000,
                        "sections": [
                            {
                                "id": "section-1",
                                "index": 1,
                                "label": "第一节",
                                "group": "讲解",
                                "start_ms": 0,
                                "end_ms": 10_000,
                            },
                            {
                                "id": "section-2",
                                "index": 2,
                                "label": "第二节",
                                "group": "练习",
                                "start_ms": 10_000,
                                "end_ms": 20_000,
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(playback, "_PUBLIC_PREVIEW_ROOT", root)


def _playback_request(**overrides: object):
    payload: dict[str, object] = {
        "contextId": "F16",
        "entryTicket": "episode-ticket",
        "eventId": "client-event-0001",
        "action": "checkpoint",
        "objectId": "F16:lesson:2",
        "section": "section-1",
        "occurredAt": 1,
        "playbackSessionId": "playback-session-0001",
        "sequence": 1,
        "contentRevision": "revision-episode-2",
        "positionMs": 9_000,
        "fromPositionMs": 8_000,
        "toPositionMs": 9_000,
        "watchedDeltaMs": 1_000,
        "reason": "auto",
    }
    payload.update(overrides)
    return luban_preview.LubanPreviewPlaybackEventRequest(**payload)


class _EpisodeTicketStore:
    def __init__(self, resource_id: str | None = "F16:lesson:2") -> None:
        self.resource_id = resource_id

    async def resolve_luban_card_entry_ticket(
        self, ticket: str, *, pack_id: str
    ):
        assert ticket == "episode-ticket"
        assert pack_id == "F16"
        return {
            "user_id": "student-real",
            "pack_id": pack_id,
            "resource_id": self.resource_id,
        }


def test_playback_event_uses_exact_episode_ticket_and_semantic_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish_playback_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    monkeypatch.setattr(
        luban_preview,
        "get_sqlite_session_store",
        lambda: _EpisodeTicketStore(),
    )
    observability.reset_surface_event_store()
    behavior_store = observability.reset_product_behavior_store(
        tmp_path / "behavior.db"
    )

    first = asyncio.run(
        luban_preview.record_luban_preview_playback_event(
            _playback_request(eventId="client-event-0001")
        )
    )
    retry = asyncio.run(
        luban_preview.record_luban_preview_playback_event(
            _playback_request(eventId="client-event-0002")
        )
    )

    assert first["status"] == "accepted"
    assert retry["status"] == "duplicate"
    assert first["event_id"] == retry["event_id"]
    assert first["event_id"].startswith("luban_playback_")
    rows = behavior_store.query_raw_events(
        {"event_name": "microlesson_playback"}, limit=10
    )
    assert len(rows) == 1
    assert rows[0]["user_id"] == "student-real"
    assert rows[0]["object_id"] == "F16:lesson:2"
    assert rows[0]["section"] == "section-1"
    assert rows[0]["duration_ms"] == 1_000
    assert rows[0]["occurred_at_ms"] != 1
    properties = json.loads(rows[0]["properties_json"])
    assert properties["app_version"] == ""
    assert properties["content_revision"] == "revision-episode-2"


@pytest.mark.parametrize(
    ("ticket_resource", "payload_overrides", "detail"),
    [
        (
            "F16:lesson:2",
            {"objectId": "F16:lesson:1"},
            "object_id does not match entry capability",
        ),
        (
            "F16:lesson:2",
            {"contentRevision": "stale-revision"},
            "content revision mismatch",
        ),
        (
            "F16:lesson:2",
            {"positionMs": 21_001},
            "playback position out of range",
        ),
    ],
)
def test_playback_event_rejects_untrusted_episode_revision_and_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ticket_resource: str,
    payload_overrides: dict[str, object],
    detail: str,
) -> None:
    _publish_playback_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    monkeypatch.setattr(
        luban_preview,
        "get_sqlite_session_store",
        lambda: _EpisodeTicketStore(ticket_resource),
    )
    observability.reset_surface_event_store()
    behavior_store = observability.reset_product_behavior_store(
        tmp_path / "behavior.db"
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            luban_preview.record_luban_preview_playback_event(
                _playback_request(**payload_overrides)
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == detail
    assert (
        behavior_store.query_raw_events(
            {"event_name": "microlesson_playback"}, limit=10
        )
        == []
    )


def test_playback_event_rejects_legacy_pack_only_ticket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish_playback_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    monkeypatch.setattr(
        luban_preview,
        "get_sqlite_session_store",
        lambda: _EpisodeTicketStore(resource_id=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            luban_preview.record_luban_preview_playback_event(
                _playback_request()
            )
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "播放身份版本过旧，请返回小程序重新打开这一集。"


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

    async def fake_start(payload, card, *, user_id: str, session_id: str):
        seen["question"] = payload.question
        seen["pack_id"] = card.pack_id
        seen["title"] = card.title
        seen["runtime_user"] = user_id
        seen["runtime_session"] = session_id
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
        "runtime_session": luban_preview._conversation_session_id(
            ticket="card-capability", pack_id="F16"
        ),
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

    async def failed_start(_payload, _card, *, user_id: str, session_id: str):
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


def test_card_capability_is_the_single_conversation_session_authority() -> None:
    first = luban_preview._conversation_session_id(
        ticket="same-card-capability", pack_id="F16"
    )
    followup = luban_preview._conversation_session_id(
        ticket="same-card-capability", pack_id="f16"
    )
    different_entry = luban_preview._conversation_session_id(
        ticket="new-card-capability", pack_id="F16"
    )

    assert first == followup
    assert first.startswith("luban-preview:F16:")
    assert first != different_entry
    assert "same-card-capability" not in first


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


def test_luban_card_context_keeps_browser_scene_as_non_authoritative_anchor() -> None:
    card = luban_preview.PublishedCardContext(
        pack_id="F16", title="服务端标题", content_sha256="sha256:published"
    )
    context = luban_preview._build_luban_turn_context_metadata(
        luban_preview.LubanPreviewAskRequest(
            contextId="F16",
            title="浏览器标题",
            question="我该怎么写？",
            currentScene={"label": "当前幕", "keycard": "客户端提示"},
            currentCaption={"speaker": "鲁班", "text": "当前旁白"},
        ),
        card,
    )

    assert context == {
        "source": "luban_teaching_card",
        "card": {
            "pack_id": "F16",
            "title": "服务端标题",
            "content_sha256": "sha256:published",
            "current_scene": {"label": "当前幕", "keycard": "客户端提示"},
            "current_caption": {"speaker": "鲁班", "text": "当前旁白"},
            "time": None,
        },
    }


def test_luban_card_reuses_mobile_turn_bootstrap_and_preserves_plain_question(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeRuntime:
        async def start_turn(self, payload: dict[str, object]):
            captured.update(payload)
            return {"id": "session-real"}, {"id": "turn-real"}

    monkeypatch.setattr(luban_preview, "get_turn_runtime_manager", lambda: FakeRuntime())
    card = luban_preview.PublishedCardContext(pack_id="F16", title="服务端标题")
    payload = luban_preview.LubanPreviewAskRequest(
        contextId="F16",
        question="为什么这一步不能省？",
        currentScene={"id": "b3", "label": "割补前半", "keycard": "先放气"},
        currentCaption={"speaker": "鲁班", "text": "先放气再擦干"},
        time=75.3,
    )

    asyncio.run(
        luban_preview._start_tutorbot_turn(
            payload,
            card,
            user_id="student-real",
            session_id="luban-preview:F16:stable",
        )
    )

    assert captured["content"] == "为什么这一步不能省？"
    assert captured["capability"] is None
    assert captured["session_id"] == "luban-preview:F16:stable"
    config = captured["config"]
    assert isinstance(config, dict)
    assert config["general_knowledge_context"] is True
    assert config["chat_mode"] == "smart"
    assert "followup_question_context" not in config
    assert config["billing_context"] == {
        "source": "wx_miniprogram",
        "user_id": "student-real",
        "wallet_user_id": "student-real",
        "learning_user_id": "student-real",
    }
    assert config["interaction_hints"]["product_surface"] == "luban_teaching_card"
    assert config["luban_teaching_card_context"] == {
        "source": "luban_teaching_card",
        "card": {
            "pack_id": "F16",
            "title": "服务端标题",
            "content_sha256": "",
            "current_scene": {"id": "b3", "label": "割补前半", "keycard": "先放气"},
            "current_caption": {"speaker": "鲁班", "text": "先放气再擦干"},
            "time": 75.3,
        },
    }
