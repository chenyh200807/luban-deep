import pytest

from deeptutor.services.notebook_card.store import (
    InMemoryNotebookCardStore,
    OptimisticConcurrencyError,
)


def _row(note_id="note_1", version=1):
    return {"user_id": "u1", "note_id": note_id, "title": "t", "version": version}


def test_upsert_then_get_roundtrip():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row())
    got = store.get_card("u1", "note_1")
    assert got["title"] == "t" and got["version"] == 1


def test_update_with_stale_version_raises():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row(version=1))
    with pytest.raises(OptimisticConcurrencyError):
        store.update_card("u1", "note_1", {"title": "new"}, expected_version=99)


def test_update_bumps_version():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row(version=1))
    updated = store.update_card("u1", "note_1", {"title": "new"}, expected_version=1)
    assert updated["title"] == "new" and updated["version"] == 2


def test_list_excludes_archived_and_scopes_by_user():
    store = InMemoryNotebookCardStore()
    store.upsert_card(_row(note_id="a"))
    store.upsert_card({"user_id": "u2", "note_id": "b", "version": 1})
    store.update_card("u1", "a", {"archived_at": "2026-05-26T00:00:00+08:00"}, expected_version=1)
    assert store.list_cards("u1") == []
    assert len(store.list_cards("u2")) == 1
