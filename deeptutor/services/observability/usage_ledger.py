"""Persistent internal ledger for all observed LLM usage events."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from deeptutor.services.path_service import PathService


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _as_str(value: Any) -> str:
    return str(value or "").strip()


@dataclass(slots=True)
class UsageLedgerTotals:
    measured_input_tokens: int = 0
    measured_output_tokens: int = 0
    measured_total_tokens: int = 0
    measured_total_cost: float = 0.0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_tokens: int = 0
    estimated_total_cost: float = 0.0
    events: int = 0
    coverage_start_ts: float | None = None
    coverage_end_ts: float | None = None

    @property
    def input_tokens(self) -> int:
        return self.measured_input_tokens + self.estimated_input_tokens

    @property
    def output_tokens(self) -> int:
        return self.measured_output_tokens + self.estimated_output_tokens

    @property
    def total_tokens(self) -> int:
        return self.measured_total_tokens + self.estimated_total_tokens

    @property
    def total_cost(self) -> float:
        return self.measured_total_cost + self.estimated_total_cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "total_tokens": int(self.total_tokens),
            "total_cost_usd": round(float(self.total_cost or 0.0), 8),
            "measured_input_tokens": int(self.measured_input_tokens),
            "measured_output_tokens": int(self.measured_output_tokens),
            "measured_total_tokens": int(self.measured_total_tokens),
            "measured_total_cost_usd": round(float(self.measured_total_cost or 0.0), 8),
            "estimated_input_tokens": int(self.estimated_input_tokens),
            "estimated_output_tokens": int(self.estimated_output_tokens),
            "estimated_total_tokens": int(self.estimated_total_tokens),
            "estimated_total_cost_usd": round(float(self.estimated_total_cost or 0.0), 8),
            "events": int(self.events),
            "coverage_start_ts": self.coverage_start_ts,
            "coverage_end_ts": self.coverage_end_ts,
        }


class UsageLedger:
    def __init__(self, db_path: Path | None = None) -> None:
        path_service = PathService.get_instance()
        self._db_path = (db_path or (path_service.get_user_root() / "llm_usage.db")).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS llm_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    dedupe_key TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    turn_id TEXT NOT NULL DEFAULT '',
                    capability TEXT NOT NULL DEFAULT '',
                    scope_id TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    provider_name TEXT NOT NULL DEFAULT '',
                    usage_source TEXT NOT NULL DEFAULT '',
                    measured_input_tokens INTEGER NOT NULL DEFAULT 0,
                    measured_output_tokens INTEGER NOT NULL DEFAULT 0,
                    measured_total_tokens INTEGER NOT NULL DEFAULT 0,
                    measured_total_cost REAL NOT NULL DEFAULT 0.0,
                    estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_total_cost REAL NOT NULL DEFAULT 0.0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_llm_usage_events_created_at
                    ON llm_usage_events(created_at);

                CREATE INDEX IF NOT EXISTS idx_llm_usage_events_provider_model_created_at
                    ON llm_usage_events(provider_name, model, created_at);

                CREATE TABLE IF NOT EXISTS llm_usage_dedupe_keys (
                    dedupe_key TEXT PRIMARY KEY,
                    created_at REAL NOT NULL
                );
                """
            )
            columns = {
                str(row["name"]): row
                for row in conn.execute("PRAGMA table_info(llm_usage_events)").fetchall()
            }
            if "dedupe_key" not in columns:
                conn.execute(
                    "ALTER TABLE llm_usage_events ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''"
                )
            conn.execute("DROP INDEX IF EXISTS idx_llm_usage_events_dedupe_key")
            conn.commit()

    def record_usage_event(
        self,
        *,
        usage_source: str,
        usage_details: dict[str, float] | None,
        cost_details: dict[str, float] | None,
        model: str | None,
        metadata: dict[str, Any] | None,
        session_id: str = "",
        turn_id: str = "",
        capability: str = "",
        scope_id: str = "",
        dedupe_key: str = "",
        created_at: float | None = None,
    ) -> bool:
        if not usage_details and not cost_details:
            return False

        source = _as_str(usage_source).lower() or "estimated"
        measured = source in {"provider", "measured", "actual"}
        payload = dict(metadata or {})
        provider_name = _as_str(payload.get("provider_name"))

        input_tokens = _safe_int((usage_details or {}).get("input"))
        output_tokens = _safe_int((usage_details or {}).get("output"))
        total_tokens = _safe_int((usage_details or {}).get("total"))
        total_cost = round(_safe_float((cost_details or {}).get("total")), 8)

        if total_tokens <= 0 and total_cost <= 0:
            return False

        row = {
            "created_at": float(created_at if created_at is not None else time.time()),
            "dedupe_key": _as_str(dedupe_key),
            "session_id": _as_str(session_id),
            "turn_id": _as_str(turn_id),
            "capability": _as_str(capability),
            "scope_id": _as_str(scope_id),
            "model": _as_str(model),
            "provider_name": provider_name,
            "usage_source": source,
            "measured_input_tokens": input_tokens if measured else 0,
            "measured_output_tokens": output_tokens if measured else 0,
            "measured_total_tokens": total_tokens if measured else 0,
            "measured_total_cost": total_cost if measured else 0.0,
            "estimated_input_tokens": 0 if measured else input_tokens,
            "estimated_output_tokens": 0 if measured else output_tokens,
            "estimated_total_tokens": 0 if measured else total_tokens,
            "estimated_total_cost": 0.0 if measured else total_cost,
            "metadata_json": json.dumps(payload, ensure_ascii=False, default=str),
        }

        with self._lock:
            with self._connect() as conn:
                dedupe_value = row["dedupe_key"]
                if dedupe_value:
                    before_changes = conn.total_changes
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO llm_usage_dedupe_keys (dedupe_key, created_at)
                        VALUES (?, ?)
                        """,
                        (dedupe_value, row["created_at"]),
                    )
                    if conn.total_changes == before_changes:
                        conn.rollback()
                        return False
                conn.execute(
                    """
                    INSERT OR IGNORE INTO llm_usage_events (
                        created_at, dedupe_key, session_id, turn_id, capability, scope_id, model,
                        provider_name, usage_source,
                        measured_input_tokens, measured_output_tokens, measured_total_tokens, measured_total_cost,
                        estimated_input_tokens, estimated_output_tokens, estimated_total_tokens, estimated_total_cost,
                        metadata_json
                    ) VALUES (
                        :created_at, :dedupe_key, :session_id, :turn_id, :capability, :scope_id, :model,
                        :provider_name, :usage_source,
                        :measured_input_tokens, :measured_output_tokens, :measured_total_tokens, :measured_total_cost,
                        :estimated_input_tokens, :estimated_output_tokens, :estimated_total_tokens, :estimated_total_cost,
                        :metadata_json
                    )
                    """,
                    row,
                )
                inserted = conn.total_changes > 0
                conn.commit()
        return inserted

    def get_totals(
        self,
        *,
        start_ts: float,
        end_ts: float,
        provider_name: str | None = None,
        model: str | None = None,
    ) -> UsageLedgerTotals:
        clauses = ["created_at >= ?", "created_at <= ?"]
        params: list[Any] = [float(start_ts), float(end_ts)]
        if _as_str(provider_name):
            clauses.append("provider_name = ?")
            params.append(_as_str(provider_name))
        if _as_str(model):
            clauses.append("model = ?")
            params.append(_as_str(model))

        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            aggregate = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(measured_input_tokens), 0) AS measured_input_tokens,
                    COALESCE(SUM(measured_output_tokens), 0) AS measured_output_tokens,
                    COALESCE(SUM(measured_total_tokens), 0) AS measured_total_tokens,
                    COALESCE(SUM(measured_total_cost), 0.0) AS measured_total_cost,
                    COALESCE(SUM(estimated_input_tokens), 0) AS estimated_input_tokens,
                    COALESCE(SUM(estimated_output_tokens), 0) AS estimated_output_tokens,
                    COALESCE(SUM(estimated_total_tokens), 0) AS estimated_total_tokens,
                    COALESCE(SUM(estimated_total_cost), 0.0) AS estimated_total_cost,
                    COUNT(*) AS events,
                    MIN(created_at) AS coverage_start_ts,
                    MAX(created_at) AS coverage_end_ts
                FROM llm_usage_events
                WHERE {where_sql}
                """,
                params,
            ).fetchone()

        if aggregate is None:
            return UsageLedgerTotals()
        return UsageLedgerTotals(
            measured_input_tokens=_safe_int(aggregate["measured_input_tokens"]),
            measured_output_tokens=_safe_int(aggregate["measured_output_tokens"]),
            measured_total_tokens=_safe_int(aggregate["measured_total_tokens"]),
            measured_total_cost=_safe_float(aggregate["measured_total_cost"]),
            estimated_input_tokens=_safe_int(aggregate["estimated_input_tokens"]),
            estimated_output_tokens=_safe_int(aggregate["estimated_output_tokens"]),
            estimated_total_tokens=_safe_int(aggregate["estimated_total_tokens"]),
            estimated_total_cost=_safe_float(aggregate["estimated_total_cost"]),
            events=_safe_int(aggregate["events"]),
            coverage_start_ts=_safe_float(aggregate["coverage_start_ts"]) or None,
            coverage_end_ts=_safe_float(aggregate["coverage_end_ts"]) or None,
        )

    def has_usage_for_turn(self, turn_id: str) -> bool:
        resolved_turn_id = _as_str(turn_id)
        if not resolved_turn_id:
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM llm_usage_events
                WHERE turn_id = ?
                LIMIT 1
                """,
                (resolved_turn_id,),
            ).fetchone()
        return row is not None


_ledger: UsageLedger | None = None


def get_usage_ledger() -> UsageLedger:
    global _ledger
    if _ledger is None:
        _ledger = UsageLedger()
    return _ledger


__all__ = ["UsageLedger", "UsageLedgerTotals", "get_usage_ledger"]
