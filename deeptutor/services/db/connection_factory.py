"""Raw-Postgres connection factory — the ONE approved place to open a raw psycopg
connection, parameterized by FACT (not by a raw env string at the call site).

Why this exists (RESOURCE_GOVERNANCE_FIX_PLAN Layer 1 · P0):
    17+ call sites today each connect to a raw url read straight from an env var.
    The target database is selected by an env STRING with no machine check, and
    the connection runs as a DB role that bypasses RLS. That is the structural
    root of cross-db / cross-project silent writes (the Supabase double-project
    incident). This factory collapses the "which env → which database" decision
    into ONE place that derives it from contracts/db_registry.yaml, so the target
    database is machine-confirmed against the single canonical registry.

Discipline (thin wrapper / less is more):
    - This is a THIN wrapper over ``psycopg.connect`` / ``psycopg2.connect``. It
      adds NO pooling, NO ORM, NO query layer, NO retry policy — just fact→url
      resolution + the same connect call the call sites already make. Modeled on
      the llm-client-factory precedent (deeptutor/services/llm/factory.py).
    - It does NOT grant write authority and is NOT a credential store. RLS / role
      grants remain the database's job; the registry's ``rls_required`` and
      ``writable_by`` are policy metadata the CI guard reads, not runtime checks.
    - It reads the SAME registry the check_db_registry.py guard reads, so the
      runtime resolution and the CI gate share one source of truth.

Usage (migration target shape)::

    from deeptutor.services.db.connection_factory import connect_for_fact

    with connect_for_fact("kb_v5_chunk_retrieval", readonly=True, timeout_s=20) as conn:
        ...

The ``db_url`` override (for tests / explicit callers) is preserved so existing
injection points keep working unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "contracts" / "db_registry.yaml"


class DbResolutionError(RuntimeError):
    """Raised when a fact cannot be resolved to a configured database url."""


def _load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    databases = payload.get("databases")
    if not isinstance(databases, list) or not databases:
        raise DbResolutionError("contracts/db_registry.yaml has no databases list")
    return payload


def resolve_url_for_fact(
    fact: str,
    *,
    db_url: str | None = None,
    environ: dict[str, str] | None = None,
    registry: dict[str, Any] | None = None,
) -> str:
    """Resolve a business ``fact`` to a Postgres url via the canonical registry.

    Resolution order (behavior-preserving — same env precedence the call sites use):
      1. an explicit ``db_url`` override (tests / explicit callers) wins;
      2. otherwise, find the database whose ``canonical_for_facts`` contains the
         fact, then read its ``url_envs`` (then ``fallback_url_envs``) in order and
         return the first env that is set.

    Raises ``DbResolutionError`` if the fact is not registered or no env is set —
    fail-closed, never silently connect to an unintended database.
    """
    if db_url:
        return db_url
    env = environ if environ is not None else os.environ
    payload = registry or _load_registry()

    target_db: dict[str, Any] | None = None
    for db in payload["databases"]:
        if fact in (db.get("canonical_for_facts") or []):
            target_db = db
            break
    if target_db is None:
        raise DbResolutionError(
            f"fact '{fact}' is not registered as canonical_for_facts on any database "
            f"in contracts/db_registry.yaml — register it before connecting."
        )

    candidate_envs = list(target_db.get("url_envs") or []) + list(
        target_db.get("fallback_url_envs") or []
    )
    for env_name in candidate_envs:
        value = str(env.get(env_name, "") or "").strip()
        if value:
            return value

    raise DbResolutionError(
        f"fact '{fact}' resolves to database '{target_db.get('name')}' but none of its "
        f"url envs are set: {', '.join(candidate_envs) or '(none declared)'}."
    )


def connect_for_fact(
    fact: str,
    *,
    db_url: str | None = None,
    readonly: bool = False,
    timeout_s: float = 20.0,
    **connect_kwargs: Any,
):
    """Open a raw Postgres connection for ``fact`` (psycopg, psycopg2 fallback).

    Thin wrapper: resolves the url from the registry, then makes the SAME
    ``connect(url, connect_timeout=...)`` call the existing sites make. When
    ``readonly`` is set it applies the existing hard read-only guard
    (``set_session(readonly=True, autocommit=True)``), exactly as the kb_v5 /
    governed-extractor read paths already do.
    """
    url = resolve_url_for_fact(fact, db_url=db_url)
    timeout = max(1, int(timeout_s))

    try:
        import psycopg  # type: ignore

        conn = psycopg.connect(url, connect_timeout=timeout, **connect_kwargs)
    except ImportError:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(url, connect_timeout=timeout, **connect_kwargs)

    if readonly:
        # hard read-only guard, identical to the existing read-path sites.
        conn.set_session(readonly=True, autocommit=True)
    return conn
