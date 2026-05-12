from __future__ import annotations

from deeptutor.services.memory.service import MemoryService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def _make_service(tmp_path):
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    return MemoryService(
        path_service=type(
            "PathServiceStub",
            (),
            {"get_memory_dir": lambda self: tmp_path / "memory"},
        )(),
        store=store,
    )


def test_memory_service_snapshot_is_empty_without_file(tmp_path) -> None:
    service = _make_service(tmp_path)
    snapshot = service.read_snapshot()

    assert snapshot.summary == ""
    assert snapshot.profile == ""
    assert snapshot.summary_updated_at is None
    assert snapshot.profile_updated_at is None


async def _no_change_stream(**_kwargs):
    yield "NO_CHANGE"


async def _rewrite_stream(**_kwargs):
    yield "## Preferences\n- Prefer concise answers.\n\n## Context\n- Working on DeepTutor memory."


def test_memory_service_refresh_turn_writes_rewritten_document(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _rewrite_stream)

    import asyncio

    result = asyncio.run(
        service.refresh_from_turn(
            user_message="Please remember that I like concise answers.",
            assistant_message="Sure, I'll keep answers concise.",
            session_id="s1",
            capability="chat",
            language="en",
        )
    )

    assert result.changed is True
    assert "concise answers" in result.content
    assert service._path("profile").exists() or service._path("summary").exists()


def test_memory_service_refresh_turn_skips_when_model_returns_no_change(
    monkeypatch,
    tmp_path,
) -> None:
    service = _make_service(tmp_path)
    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _no_change_stream)

    import asyncio

    result = asyncio.run(
        service.refresh_from_turn(
            user_message="What is 2+2?",
            assistant_message="4",
            session_id="s1",
            capability="chat",
            language="en",
        )
    )

    assert result.changed is False
    assert result.content == ""
    assert not service._path("profile").exists()
    assert not service._path("summary").exists()


def test_memory_service_write_strips_thinking_tags(tmp_path) -> None:
    service = _make_service(tmp_path)

    snapshot = service.write_file(
        "profile",
        "## Preferences\n- concise\n<thinking>private scratchpad</thinking>",
    )

    assert "thinking" not in snapshot.profile.lower()
    assert "private scratchpad" not in service.read_profile()
    assert "concise" in service.read_profile()


def test_memory_service_read_repairs_existing_thinking_tags(tmp_path) -> None:
    service = _make_service(tmp_path)
    path = service._path("summary")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("## Current Focus\n- waterproofing\n<think>secret", encoding="utf-8")

    assert service.read_summary() == "## Current Focus\n- waterproofing"
    assert path.read_text(encoding="utf-8") == "## Current Focus\n- waterproofing"


async def _invalid_rewrite_stream(**_kwargs):
    yield "<think>draft</think> I can help you with that."


def test_memory_service_rejects_invalid_rewrite_shape(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _invalid_rewrite_stream)

    import asyncio

    result = asyncio.run(
        service.refresh_from_turn(
            user_message="remember my preference",
            assistant_message="ok",
            session_id="s1",
            capability="chat",
            language="en",
        )
    )

    assert result.changed is False
    assert service.read_profile() == ""
    assert service.read_summary() == ""
