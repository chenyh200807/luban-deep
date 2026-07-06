from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from deeptutor.services.path_service import PathService

FREE_TRIAL_RESERVED_STATUS = "free_trial_reserved"
FREE_TRIAL_CONSUMED_STATUS = "metered_not_charged"
FREE_TRIAL_RELEASED_STATUS = "free_trial_released"
FREE_TRIAL_REASON = "free_trial"


@dataclass(frozen=True)
class MemberUsageEvent:
    event_id: int
    wallet_user_id: str
    learning_user_id: str
    source: str
    session_id: str
    turn_id: str
    amount_points: int
    status: str
    metadata: dict[str, Any]
    created_at: float


class MemberUsageMeter:
    """Non-financial learner usage meter for internal beta product reporting."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = PathService.get_instance().get_user_root() / "member_usage_meter.db"
        self._db_path = Path(db_path).expanduser().resolve()

    def record_usage_event(
        self,
        *,
        wallet_user_id: str,
        learning_user_id: str = "",
        source: str,
        session_id: str,
        turn_id: str,
        amount_points: int,
        dedupe_key: str,
        status: str = "metered_not_charged",
        metadata: dict[str, Any] | None = None,
        created_at: float | None = None,
    ) -> bool:
        normalized_wallet_user_id = str(wallet_user_id or "").strip()
        normalized_dedupe_key = str(dedupe_key or "").strip()
        if not normalized_wallet_user_id or not normalized_dedupe_key:
            return False
        self._ensure_schema()
        payload = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        timestamp = float(
            created_at if created_at is not None else datetime.now(timezone.utc).timestamp()
        )
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO member_usage_events (
                        created_at, dedupe_key, source, wallet_user_id, learning_user_id,
                        session_id, turn_id, amount_points, status, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        normalized_dedupe_key,
                        str(source or "").strip(),
                        normalized_wallet_user_id,
                        str(learning_user_id or "").strip(),
                        str(session_id or "").strip(),
                        str(turn_id or "").strip(),
                        max(0, int(amount_points or 0)),
                        str(status or "metered_not_charged").strip()
                        or "metered_not_charged",
                        payload,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def record_usage_event_after_check(
        self,
        *,
        wallet_user_id: str,
        learning_user_id: str = "",
        source: str,
        session_id: str,
        turn_id: str,
        amount_points: int,
        dedupe_key: str,
        status: str = "metered_not_charged",
        metadata: dict[str, Any] | None = None,
        created_at: float | None = None,
        existing_events_limit: int = 100,
        check_existing_events: Callable[[list[MemberUsageEvent]], None] | None = None,
    ) -> bool:
        normalized_wallet_user_id = str(wallet_user_id or "").strip()
        normalized_dedupe_key = str(dedupe_key or "").strip()
        if not normalized_wallet_user_id or not normalized_dedupe_key:
            return False
        self._ensure_schema()
        timestamp = float(
            created_at if created_at is not None else datetime.now(timezone.utc).timestamp()
        )
        bounded_limit = max(1, min(1000, int(existing_events_limit or 100)))
        payload = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT id, created_at, source, wallet_user_id, learning_user_id,
                       session_id, turn_id, amount_points, status, metadata_json
                FROM member_usage_events
                WHERE wallet_user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (normalized_wallet_user_id, bounded_limit),
            ).fetchall()
            if check_existing_events is not None:
                check_existing_events([self._row_to_event(row) for row in rows])
            try:
                conn.execute(
                    """
                    INSERT INTO member_usage_events (
                        created_at, dedupe_key, source, wallet_user_id, learning_user_id,
                        session_id, turn_id, amount_points, status, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        normalized_dedupe_key,
                        str(source or "").strip(),
                        normalized_wallet_user_id,
                        str(learning_user_id or "").strip(),
                        str(session_id or "").strip(),
                        str(turn_id or "").strip(),
                        max(0, int(amount_points or 0)),
                        str(status or "metered_not_charged").strip()
                        or "metered_not_charged",
                        payload,
                    ),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                return False
            conn.commit()
        return True

    def update_usage_event(
        self,
        dedupe_key: str,
        *,
        status: str,
        expected_status: str | None = None,
        expected_metadata: dict[str, Any] | None = None,
        turn_id: str = "",
        metadata_updates: dict[str, Any] | None = None,
    ) -> bool:
        normalized_dedupe_key = str(dedupe_key or "").strip()
        normalized_status = str(status or "").strip()
        if not normalized_dedupe_key or not normalized_status:
            return False
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT status, metadata_json
                FROM member_usage_events
                WHERE dedupe_key = ?
                """,
                (normalized_dedupe_key,),
            ).fetchone()
            if row is None:
                conn.rollback()
                return False
            if expected_status is not None:
                current_status = str(row["status"] or "").strip()
                if current_status != str(expected_status or "").strip():
                    conn.rollback()
                    return False
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            for key, value in (expected_metadata or {}).items():
                if metadata.get(key) != value:
                    conn.rollback()
                    return False
            if metadata_updates:
                metadata.update(metadata_updates)
            payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            cursor = conn.execute(
                """
                UPDATE member_usage_events
                SET status = ?,
                    turn_id = CASE WHEN ? != '' THEN ? ELSE turn_id END,
                    metadata_json = ?
                WHERE dedupe_key = ?
                """,
                (
                    normalized_status,
                    str(turn_id or "").strip(),
                    str(turn_id or "").strip(),
                    payload,
                    normalized_dedupe_key,
                ),
            )
            conn.commit()
        return cursor.rowcount > 0

    def finalize_free_trial_reservation(
        self,
        dedupe_key: str,
        *,
        chargeable: bool,
        turn_id: str = "",
        metadata_updates: dict[str, Any] | None = None,
    ) -> bool:
        status = (
            FREE_TRIAL_CONSUMED_STATUS
            if chargeable
            else FREE_TRIAL_RELEASED_STATUS
        )
        return self.update_usage_event(
            dedupe_key,
            status=status,
            expected_status=FREE_TRIAL_RESERVED_STATUS,
            expected_metadata={"reason": FREE_TRIAL_REASON},
            turn_id=turn_id,
            metadata_updates=metadata_updates,
        )

    def release_free_trial_reservations_before(
        self,
        cutoff_created_at: float,
        *,
        reason: str,
        finalized_by: str = "startup_orphan_recovery",
    ) -> int:
        self._ensure_schema()
        cutoff = float(cutoff_created_at)
        release_reason = str(reason or "").strip() or "orphaned_on_restart"
        released_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT id, metadata_json
                FROM member_usage_events
                WHERE status = ?
                  AND created_at < ?
                """,
                (FREE_TRIAL_RESERVED_STATUS, cutoff),
            ).fetchall()
            released_count = 0
            for row in rows:
                try:
                    metadata = json.loads(str(row["metadata_json"] or "{}"))
                except json.JSONDecodeError:
                    metadata = {}
                if not isinstance(metadata, dict):
                    metadata = {}
                if str(metadata.get("reason") or "").strip().lower() != FREE_TRIAL_REASON:
                    continue
                metadata.update(
                    {
                        "release_reason": release_reason,
                        "finalized_by": str(finalized_by or "").strip()
                        or "startup_orphan_recovery",
                        "released_at": released_at,
                    }
                )
                cursor = conn.execute(
                    """
                    UPDATE member_usage_events
                    SET status = ?,
                        metadata_json = ?
                    WHERE id = ?
                      AND status = ?
                    """,
                    (
                        FREE_TRIAL_RELEASED_STATUS,
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        int(row["id"]),
                        FREE_TRIAL_RESERVED_STATUS,
                    ),
                )
                released_count += int(cursor.rowcount or 0)
            conn.commit()
        return released_count

    def list_usage_events(
        self,
        wallet_user_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemberUsageEvent]:
        normalized_wallet_user_id = str(wallet_user_id or "").strip()
        if not normalized_wallet_user_id:
            return []
        self._ensure_schema()
        bounded_limit = max(1, min(1000, int(limit or 100)))
        bounded_offset = max(0, int(offset or 0))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, source, wallet_user_id, learning_user_id,
                       session_id, turn_id, amount_points, status, metadata_json
                FROM member_usage_events
                WHERE wallet_user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (normalized_wallet_user_id, bounded_limit, bounded_offset),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    source TEXT NOT NULL,
                    wallet_user_id TEXT NOT NULL,
                    learning_user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    amount_points INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_member_usage_dedupe
                ON member_usage_events(dedupe_key)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_member_usage_wallet_created
                ON member_usage_events(wallet_user_id, created_at DESC)
                """
            )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> MemberUsageEvent:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return MemberUsageEvent(
            event_id=int(row["id"]),
            wallet_user_id=str(row["wallet_user_id"] or ""),
            learning_user_id=str(row["learning_user_id"] or ""),
            source=str(row["source"] or ""),
            session_id=str(row["session_id"] or ""),
            turn_id=str(row["turn_id"] or ""),
            amount_points=max(0, int(row["amount_points"] or 0)),
            status=str(row["status"] or ""),
            metadata=metadata,
            created_at=float(row["created_at"] or 0.0),
        )


_member_usage_meter: MemberUsageMeter | None = None


def get_member_usage_meter() -> MemberUsageMeter:
    global _member_usage_meter
    if _member_usage_meter is None:
        _member_usage_meter = MemberUsageMeter()
    return _member_usage_meter


def reset_member_usage_meter() -> None:
    global _member_usage_meter
    _member_usage_meter = None
