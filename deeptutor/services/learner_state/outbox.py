from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from deeptutor.services.path_service import PathService, get_path_service

_DEFAULT_RELATIVE_DB_PATH = Path("data") / "runtime" / "outbox.db"


@dataclass(frozen=True)
class LearnerStateOutboxItem:
    id: str
    user_id: str
    event_type: str
    payload_json: dict[str, Any]
    dedupe_key: str
    status: str
    retry_count: int
    created_at: str
    last_error: str | None


class LearnerStateOutbox:
    """Durable local SQLite outbox for learner-state writeback events."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        path_service: PathService | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        self._db_path = self._resolve_db_path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def enqueue(
        self,
        *,
        user_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        dedupe_key: str,
        id: str | None = None,
        created_at: str | None = None,
    ) -> LearnerStateOutboxItem:
        normalized_user_id = _normalize_text(user_id, "user_id")
        normalized_event_type = _normalize_text(event_type, "event_type")
        normalized_dedupe_key = _normalize_text(dedupe_key, "dedupe_key")
        created_at_value = str(created_at or _iso_now())
        item_id = str(id or _generate_id())
        payload_text = _dump_json(payload_json)

        with self._connect() as conn:
            conn.execute(
                """
                insert into learner_state_outbox (
                    id, user_id, event_type, payload_json, dedupe_key,
                    status, retry_count, created_at, last_error
                )
                values (?, ?, ?, ?, ?, 'pending', 0, ?, null)
                on conflict(dedupe_key) do nothing
                """,
                (
                    item_id,
                    normalized_user_id,
                    normalized_event_type,
                    payload_text,
                    normalized_dedupe_key,
                    created_at_value,
                ),
            )
            row = conn.execute(
                """
                select id, user_id, event_type, payload_json, dedupe_key,
                       status, retry_count, created_at, last_error
                from learner_state_outbox
                where dedupe_key = ?
                """,
                (normalized_dedupe_key,),
            ).fetchone()
        return self._row_to_item(row)

    def claim_pending(self, limit: int = 20) -> list[LearnerStateOutboxItem]:
        if limit <= 0:
            return []

        with self._connect() as conn:
            conn.execute("begin immediate")
            rows = conn.execute(
                """
                select id
                from learner_state_outbox
                where status = 'pending'
                order by created_at asc, id asc
                limit ?
                """,
                (int(limit),),
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            if not ids:
                conn.commit()
                return []
            conn.executemany(
                """
                update learner_state_outbox
                set status = 'processing'
                where id = ?
                """,
                [(item_id,) for item_id in ids],
            )
            claimed_rows = conn.execute(
                f"""
                select id, user_id, event_type, payload_json, dedupe_key,
                       status, retry_count, created_at, last_error
                from learner_state_outbox
                where id in ({",".join("?" for _ in ids)})
                order by created_at asc, id asc
                """,
                ids,
            ).fetchall()
            conn.commit()
        return [self._row_to_item(row) for row in claimed_rows]

    def list_pending(
        self,
        user_id: str | None = None,
        limit: int | None = 20,
    ) -> list[LearnerStateOutboxItem]:
        query = """
            select id, user_id, event_type, payload_json, dedupe_key,
                   status, retry_count, created_at, last_error
            from learner_state_outbox
            where status = 'pending'
        """
        params: list[Any] = []
        if user_id:
            query += " and user_id = ?"
            params.append(str(user_id).strip())
        query += " order by created_at asc, id asc"
        if limit is not None and limit >= 0:
            query += " limit ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_item(row) for row in rows]

    def mark_sent(self, id: str) -> LearnerStateOutboxItem | None:
        normalized_id = _normalize_text(id, "id")
        with self._connect() as conn:
            conn.execute(
                """
                update learner_state_outbox
                set status = 'sent',
                    last_error = null
                where id = ?
                """,
                (normalized_id,),
            )
            row = conn.execute(
                """
                select id, user_id, event_type, payload_json, dedupe_key,
                       status, retry_count, created_at, last_error
                from learner_state_outbox
                where id = ?
                """,
                (normalized_id,),
            ).fetchone()
        return self._row_to_item(row) if row else None

    def mark_failed(self, id: str, *, last_error: str | None = None) -> LearnerStateOutboxItem | None:
        normalized_id = _normalize_text(id, "id")
        normalized_error = str(last_error or "").strip() or None
        with self._connect() as conn:
            conn.execute(
                """
                update learner_state_outbox
                set status = 'pending',
                    retry_count = retry_count + 1,
                    last_error = ?
                where id = ?
                """,
                (normalized_error, normalized_id),
            )
            row = conn.execute(
                """
                select id, user_id, event_type, payload_json, dedupe_key,
                       status, retry_count, created_at, last_error
                from learner_state_outbox
                where id = ?
                """,
                (normalized_id,),
            ).fetchone()
        return self._row_to_item(row) if row else None

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists learner_state_outbox (
                    id text primary key,
                    user_id text not null,
                    event_type text not null,
                    payload_json text not null,
                    dedupe_key text not null,
                    status text not null default 'pending',
                    retry_count integer not null default 0,
                    created_at text not null,
                    last_error text
                )
                """
            )
            conn.execute(
                """
                create unique index if not exists idx_learner_state_outbox_dedupe
                on learner_state_outbox(dedupe_key)
                """
            )
            conn.execute(
                """
                create index if not exists idx_learner_state_outbox_status_created
                on learner_state_outbox(status, created_at)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma journal_mode=wal")
        conn.execute("pragma foreign_keys=on")
        return conn

    def _resolve_db_path(self, db_path: str | Path | None) -> Path:
        if db_path is not None:
            return Path(db_path)
        getter = getattr(self._path_service, "get_learner_state_outbox_db", None)
        if callable(getter):
            return Path(getter())
        return (self._path_service.project_root / _DEFAULT_RELATIVE_DB_PATH).resolve()

    @staticmethod
    def _row_to_item(row: sqlite3.Row | None) -> LearnerStateOutboxItem:
        if row is None:
            raise ValueError("outbox item does not exist")
        payload_raw = str(row["payload_json"] or "{}")
        try:
            payload_json = dict(json.loads(payload_raw)) if payload_raw else {}
        except Exception:
            payload_json = {}
        return LearnerStateOutboxItem(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            event_type=str(row["event_type"]),
            payload_json=payload_json,
            dedupe_key=str(row["dedupe_key"]),
            status=str(row["status"]),
            retry_count=int(row["retry_count"] or 0),
            created_at=str(row["created_at"]),
            last_error=(str(row["last_error"]) if row["last_error"] is not None else None),
        )


def _normalize_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _dump_json(payload_json: dict[str, Any]) -> str:
    return json.dumps(payload_json or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_id() -> str:
    # Local durable outbox IDs only need to be unique within the SQLite store.
    return uuid.uuid4().hex


__all__ = ["LearnerStateOutbox", "LearnerStateOutboxItem"]
