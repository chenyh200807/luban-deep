import pytest

from deeptutor.services.notebook_card.store import (
    InMemoryNotebookCardStore,
    OptimisticConcurrencyError,
    PostgresNotebookCardStore,
    SupabaseNotebookCardStore,
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


def test_postgres_store_uses_notebook_card_database_url_first(monkeypatch):
    monkeypatch.setenv("NOTEBOOK_CARD_DATABASE_URL", "postgresql://note-db")
    monkeypatch.setenv("DB_URL", "postgresql://app-db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback-db")

    store = PostgresNotebookCardStore()

    assert store._database_url == "postgresql://note-db"


def test_postgres_store_falls_back_to_app_db_url(monkeypatch):
    monkeypatch.delenv("NOTEBOOK_CARD_DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_URL", "postgresql://app-db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback-db")

    store = PostgresNotebookCardStore()

    assert store._database_url == "postgresql://app-db"


def test_supabase_store_uses_main_supabase_url_not_kb_v5(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://legacy.example.supabase.co")
    monkeypatch.setenv("SUPABASE_URL_V5", "https://v5.example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-service-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY_V5", "v5-service-key")

    store = SupabaseNotebookCardStore()

    assert store._base_url == "https://legacy.example.supabase.co"
    assert store._service_key == "legacy-service-key"


def test_supabase_store_keeps_legacy_service_role_fallback(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://legacy.example.supabase.co")
    monkeypatch.delenv("SUPABASE_URL_V5", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-service-key")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY_V5", raising=False)

    store = SupabaseNotebookCardStore()

    assert store._base_url == "https://legacy.example.supabase.co"
    assert store._service_key == "legacy-service-key"
