"""Persistent internal ledger for all observed LLM usage events."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    provider_calls: int = 0
    unattributed_provider_calls: int = 0
    billable_turns: int = 0
    metadata_breakdown: dict[str, int] = field(default_factory=dict)
    currency_amounts: dict[str, float] = field(default_factory=dict)
    provider_amounts: dict[str, float] = field(default_factory=dict)
    cost_center_amounts: dict[str, dict[str, float]] = field(default_factory=dict)
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

    @property
    def calls_per_billable_turn(self) -> float:
        if self.billable_turns <= 0:
            return 0.0
        return round(float(self.provider_calls) / float(self.billable_turns), 4)

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
            "provider_calls": int(self.provider_calls),
            "unattributed_provider_calls": int(self.unattributed_provider_calls),
            "billable_turns": int(self.billable_turns),
            "calls_per_billable_turn": self.calls_per_billable_turn,
            "metadata_breakdown": dict(self.metadata_breakdown),
            "currency_amounts": {
                key: round(float(value or 0.0), 8)
                for key, value in self.currency_amounts.items()
            },
            "provider_amounts": {
                key: round(float(value or 0.0), 8)
                for key, value in self.provider_amounts.items()
            },
            "cost_center_amounts": {
                center: {
                    currency: round(float(amount or 0.0), 8)
                    for currency, amount in amounts.items()
                }
                for center, amounts in self.cost_center_amounts.items()
            },
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
        if usage_details:
            payload.setdefault("usage_details", dict(usage_details))
        if cost_details:
            payload.setdefault("cost_details", dict(cost_details))
        if "billing_currency" not in payload:
            currency = _as_str(payload.get("pricing_currency") or (cost_details or {}).get("currency"))
            if currency:
                payload["billing_currency"] = currency

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
        billable_only: bool = False,
        environment: str | None = None,
        cost_center: str | None = None,
        api_key_fingerprint: str | None = None,
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
            rows = conn.execute(
                f"""
                SELECT
                    created_at, turn_id, scope_id, provider_name, usage_source,
                    measured_input_tokens, measured_output_tokens, measured_total_tokens,
                    measured_total_cost, estimated_input_tokens, estimated_output_tokens,
                    estimated_total_tokens, estimated_total_cost, metadata_json
                FROM llm_usage_events
                WHERE {where_sql}
                """,
                params,
            ).fetchall()

        totals = UsageLedgerTotals()
        billable_turn_ids: set[str] = set()
        requested_environment = _as_str(environment)
        requested_cost_center = _as_str(cost_center)
        requested_api_key = _as_str(api_key_fingerprint)

        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}

            row_environment = _as_str(metadata.get("runtime_environment"))
            row_cost_center = _as_str(metadata.get("cost_center"))
            row_api_key = _as_str(metadata.get("api_key_fingerprint"))
            if requested_environment and row_environment != requested_environment:
                continue
            if requested_cost_center and row_cost_center != requested_cost_center:
                continue
            if requested_api_key and row_api_key != requested_api_key:
                continue

            billable_turn_id = _as_str(
                metadata.get("billable_turn_id") or row["turn_id"] or row["scope_id"]
            )
            is_billable = (
                _as_str(metadata.get("billable_unit")) == "conversation_turn"
                and _as_str(metadata.get("billing_capture_status")) == "captured"
                and bool(billable_turn_id)
            )
            if billable_only and not is_billable:
                continue

            totals.measured_input_tokens += _safe_int(row["measured_input_tokens"])
            totals.measured_output_tokens += _safe_int(row["measured_output_tokens"])
            totals.measured_total_tokens += _safe_int(row["measured_total_tokens"])
            totals.measured_total_cost += _safe_float(row["measured_total_cost"])
            totals.estimated_input_tokens += _safe_int(row["estimated_input_tokens"])
            totals.estimated_output_tokens += _safe_int(row["estimated_output_tokens"])
            totals.estimated_total_tokens += _safe_int(row["estimated_total_tokens"])
            totals.estimated_total_cost += _safe_float(row["estimated_total_cost"])
            totals.events += 1
            totals.provider_calls += 1
            if is_billable:
                billable_turn_ids.add(billable_turn_id)
            if not row_environment or not row_cost_center or not row_api_key:
                totals.unattributed_provider_calls += 1

            created_at = _safe_float(row["created_at"])
            if created_at:
                totals.coverage_start_ts = (
                    created_at
                    if totals.coverage_start_ts is None
                    else min(totals.coverage_start_ts, created_at)
                )
                totals.coverage_end_ts = (
                    created_at
                    if totals.coverage_end_ts is None
                    else max(totals.coverage_end_ts, created_at)
                )

            usage_payload = metadata.get("usage_details")
            if not isinstance(usage_payload, dict):
                usage_payload = {}
            official_usage_fields = metadata.get("official_usage_fields")
            if not isinstance(official_usage_fields, dict):
                official_usage_fields = {}
            cache_hit_tokens = _safe_int(
                usage_payload.get("input_cache_hit")
                or official_usage_fields.get("prompt_cache_hit_tokens")
            )
            cache_miss_tokens = _safe_int(
                usage_payload.get("input_cache_miss")
                or official_usage_fields.get("prompt_cache_miss_tokens")
            )
            if cache_hit_tokens:
                totals.metadata_breakdown["input_cache_hit_tokens"] = (
                    totals.metadata_breakdown.get("input_cache_hit_tokens", 0)
                    + cache_hit_tokens
                )
            if cache_miss_tokens:
                totals.metadata_breakdown["input_cache_miss_tokens"] = (
                    totals.metadata_breakdown.get("input_cache_miss_tokens", 0)
                    + cache_miss_tokens
                )

            cost_payload = metadata.get("cost_details")
            if not isinstance(cost_payload, dict):
                cost_payload = {}
            amount = _safe_float(
                cost_payload.get("total")
                or (_safe_float(row["measured_total_cost"]) + _safe_float(row["estimated_total_cost"]))
            )
            currency = _as_str(
                metadata.get("billing_currency")
                or metadata.get("pricing_currency")
                or cost_payload.get("currency")
            ).upper()
            if currency and amount:
                totals.currency_amounts[currency] = (
                    totals.currency_amounts.get(currency, 0.0) + amount
                )
                provider = _as_str(row["provider_name"]) or "unknown"
                totals.provider_amounts[provider] = (
                    totals.provider_amounts.get(provider, 0.0) + amount
                )
                if row_cost_center:
                    center_amounts = totals.cost_center_amounts.setdefault(row_cost_center, {})
                    center_amounts[currency] = center_amounts.get(currency, 0.0) + amount

        totals.billable_turns = len(billable_turn_ids)
        return totals

    def get_window_summary(self, *, start_ts: float, end_ts: float) -> dict[str, Any]:
        """窗口聚合：totals（measured/estimated 分列）+ by_model + by_usage_source。

        BI 成本读数的唯一权威入口（P2 收权，2026-06-12）。
        """
        totals = self.get_totals(start_ts=start_ts, end_ts=end_ts)

        group_sql = """
            SELECT
                {column} AS group_key,
                COUNT(*) AS events,
                SUM(measured_total_tokens + estimated_total_tokens) AS total_tokens,
                SUM(measured_total_cost) AS measured_cost,
                SUM(estimated_total_cost) AS estimated_cost
            FROM llm_usage_events
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY {column}
            ORDER BY SUM(measured_total_cost + estimated_total_cost) DESC, COUNT(*) DESC
        """
        with self._connect() as conn:
            model_rows = conn.execute(
                group_sql.format(column="model"), (float(start_ts), float(end_ts))
            ).fetchall()
            source_rows = conn.execute(
                group_sql.format(column="usage_source"), (float(start_ts), float(end_ts))
            ).fetchall()
            day_rows = conn.execute(
                group_sql.format(column="date(created_at, 'unixepoch', 'localtime')"),
                (float(start_ts), float(end_ts)),
            ).fetchall()

        def _group_payload(row: Any, key_name: str) -> dict[str, Any]:
            measured = _safe_float(row["measured_cost"])
            estimated = _safe_float(row["estimated_cost"])
            return {
                key_name: _as_str(row["group_key"]) or "unknown",
                "events": _safe_int(row["events"]),
                "total_tokens": _safe_int(row["total_tokens"]),
                "measured_total_cost_usd": round(measured, 8),
                "estimated_total_cost_usd": round(estimated, 8),
                "total_cost_usd": round(measured + estimated, 8),
            }

        by_day = sorted(
            (_group_payload(row, "date") for row in day_rows), key=lambda item: item["date"]
        )
        return {
            "totals": totals.to_dict(),
            "by_model": [_group_payload(row, "model") for row in model_rows],
            "by_usage_source": [_group_payload(row, "usage_source") for row in source_rows],
            "by_day": by_day,
        }

    def mark_turn_billable(self, *, turn_id: str, billing_capture: dict[str, Any]) -> int:
        resolved_turn_id = _as_str(turn_id)
        if not resolved_turn_id:
            return 0
        if _as_str((billing_capture or {}).get("status")) != "captured":
            return 0

        updated = 0
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, metadata_json
                    FROM llm_usage_events
                    WHERE turn_id = ? OR scope_id = ?
                    """,
                    (resolved_turn_id, resolved_turn_id),
                ).fetchall()
                for row in rows:
                    try:
                        metadata = json.loads(row["metadata_json"] or "{}")
                    except json.JSONDecodeError:
                        metadata = {}
                    metadata.update(
                        {
                            "billable_unit": "conversation_turn",
                            "billable_turn_id": resolved_turn_id,
                            "billing_capture_status": "captured",
                            "billing_capture_idempotency_key": _as_str(
                                billing_capture.get("idempotency_key")
                            ),
                            "billing_reference_id": resolved_turn_id,
                            "billing_amount_points": _safe_int(
                                billing_capture.get("amount_points")
                            ),
                            "billing_amount_source": _as_str(
                                billing_capture.get("billing_amount_source")
                            ),
                        }
                    )
                    conn.execute(
                        "UPDATE llm_usage_events SET metadata_json = ? WHERE id = ?",
                        (json.dumps(metadata, ensure_ascii=False, default=str), row["id"]),
                    )
                    updated += 1
                conn.commit()
        return updated

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
