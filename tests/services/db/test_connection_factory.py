"""TDD for the raw-Postgres connection factory — fact→database url resolution.

These tests pin the behavior-preserving resolution rules (explicit override wins,
then registry url_envs in order, fail-closed on unknown fact / unset env). They do
NOT open a real connection — only ``resolve_url_for_fact`` (pure) is exercised, so
they are deterministic and touch no database.
"""

from __future__ import annotations

import pytest

from deeptutor.services.db.connection_factory import (
    DbResolutionError,
    resolve_url_for_fact,
)


def test_explicit_db_url_override_wins() -> None:
    # an explicit db_url (tests / explicit callers) short-circuits env resolution.
    url = resolve_url_for_fact("kb_v5_chunk_retrieval", db_url="postgres://override")
    assert url == "postgres://override"


def test_resolve_kb_v5_fact_to_kbv5_db_url() -> None:
    url = resolve_url_for_fact(
        "kb_v5_chunk_retrieval", environ={"KBV5_DB_URL": "postgres://kbv5"}
    )
    assert url == "postgres://kbv5"


def test_resolve_app_primary_fact_prefers_primary_env_then_fallback() -> None:
    # url_envs (DATABASE_URL/DB_URL) come before fallback envs.
    primary = resolve_url_for_fact(
        "luban_feedback",
        environ={"DATABASE_URL": "postgres://primary", "FEEDBACK_DATABASE_URL": "postgres://fb"},
    )
    assert primary == "postgres://primary"
    # when no primary env is set, a declared fallback env is used.
    fallback = resolve_url_for_fact(
        "luban_feedback", environ={"FEEDBACK_DATABASE_URL": "postgres://fb"}
    )
    assert fallback == "postgres://fb"


def test_unregistered_fact_fails_closed() -> None:
    with pytest.raises(DbResolutionError) as exc:
        resolve_url_for_fact("totally_made_up_fact", environ={})
    assert "not registered" in str(exc.value)


def test_registered_fact_but_no_env_fails_closed() -> None:
    # fact resolves to a database, but none of its url envs are set → never
    # silently connect to an unintended database.
    with pytest.raises(DbResolutionError) as exc:
        resolve_url_for_fact("kb_v5_chunk_retrieval", environ={})
    assert "url envs are set" in str(exc.value)
