from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from deeptutor.services.observability.product_behavior_catalog import FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS


def _safe_properties_json(value: Any) -> str:
    if isinstance(value, str):
        try:
            raw = json.loads(value or "{}")
        except json.JSONDecodeError:
            raw = {}
    elif isinstance(value, dict):
        raw = value
    else:
        raw = {}

    forbidden = sorted(set(raw) & FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS)
    if forbidden:
        raise ValueError(f"Forbidden product behavior property: {forbidden[0]}")
    return json.dumps(raw, ensure_ascii=False, sort_keys=True)


class SQLiteProductBehaviorStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists product_behavior_events (
                  event_id text primary key,
                  event_name text not null,
                  event_version integer not null,
                  occurred_at_ms integer not null,
                  received_at_ms integer not null,
                  user_id text not null,
                  visit_id text not null,
                  session_id text not null default '',
                  turn_id text not null default '',
                  surface text not null,
                  module text not null,
                  section text not null default '',
                  action text not null,
                  properties_json text not null default '{}'
                )
                """
            )
            conn.execute(
                "create index if not exists idx_pbe_user_time on product_behavior_events(user_id, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_module_time on product_behavior_events(module, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_section_time on product_behavior_events(module, section, occurred_at_ms)"
            )

    def record_event(self, event: dict[str, Any]) -> dict[str, Any]:
        properties = _safe_properties_json(event.get("properties_json"))
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    insert into product_behavior_events (
                      event_id, event_name, event_version, occurred_at_ms, received_at_ms,
                      user_id, visit_id, session_id, turn_id, surface, module, section, action, properties_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(event["event_id"]),
                        str(event["event_name"]),
                        int(event.get("event_version") or 1),
                        int(event.get("occurred_at_ms") or 0),
                        int(event.get("received_at_ms") or int(time.time() * 1000)),
                        str(event["user_id"]),
                        str(event.get("visit_id") or ""),
                        str(event.get("session_id") or ""),
                        str(event.get("turn_id") or ""),
                        str(event["surface"]),
                        str(event["module"]),
                        str(event.get("section") or ""),
                        str(event["action"]),
                        properties,
                    ),
                )
            return {"accepted": True, "status": "accepted", "event_id": str(event["event_id"])}
        except sqlite3.IntegrityError:
            return {"accepted": False, "status": "duplicate", "event_id": str(event["event_id"])}

    def _since_ms(self, days: int) -> int:
        return int((time.time() - max(1, days) * 86400) * 1000)

    def _empty_summary(self) -> dict[str, Any]:
        return {
            "learning_report_open_count_7d": 0,
            "history_open_count_7d": 0,
            "action_start_count_7d": 0,
            "cohort": "",
            "trust_level": "B",
        }

    def get_member_behavior_summaries(self, user_ids: list[str], *, days: int = 7) -> dict[str, dict[str, Any]]:
        unique_user_ids = sorted({str(user_id) for user_id in user_ids if str(user_id)})
        if not unique_user_ids:
            return {}

        since = self._since_ms(days)
        placeholders = ",".join("?" for _ in unique_user_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select user_id, module, event_name, count(*) as count
                from product_behavior_events
                where user_id in ({placeholders}) and occurred_at_ms >= ?
                group by user_id, module, event_name
                """,
                (*unique_user_ids, since),
            ).fetchall()

        counts_by_user: dict[str, dict[tuple[str, str], int]] = {user_id: {} for user_id in unique_user_ids}
        for row in rows:
            counts_by_user[str(row["user_id"])][(str(row["module"]), str(row["event_name"]))] = int(row["count"])

        summaries: dict[str, dict[str, Any]] = {}
        for user_id, counts in counts_by_user.items():
            report_count = counts.get(("learning_report", "module_viewed"), 0)
            history_count = counts.get(("history", "module_viewed"), 0)
            action_count = sum(
                count
                for (_module, event_name), count in counts.items()
                if event_name == "learning_action_started"
            )
            cohort = "report_high_no_action" if report_count >= 3 and action_count == 0 else ""
            summaries[user_id] = {
                "learning_report_open_count_7d": report_count,
                "history_open_count_7d": history_count,
                "action_start_count_7d": action_count,
                "cohort": cohort,
                "trust_level": "B",
            }
        return summaries

    def get_member_behavior_summary(self, user_id: str, *, days: int = 7) -> dict[str, Any]:
        return self.get_member_behavior_summaries([user_id], days=days).get(user_id, self._empty_summary())

    def get_learning_report_section_breakdown(self, user_id: str, *, days: int = 7) -> list[dict[str, Any]]:
        since = self._since_ms(days)
        with self._connect() as conn:
            rows = conn.execute(
                """
                select section, count(*) as view_count
                from product_behavior_events
                where user_id = ?
                  and occurred_at_ms >= ?
                  and module = 'learning_report'
                  and event_name = 'section_viewed'
                  and section != ''
                group by section
                order by view_count desc, section asc
                """,
                (user_id, since),
            ).fetchall()
        return [{"section": str(row["section"]), "view_count": int(row["view_count"])} for row in rows]

    def get_member_timeline(self, user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select event_id, event_name, occurred_at_ms, surface, module, section, action
                from product_behavior_events
                where user_id = ?
                order by occurred_at_ms desc
                limit ?
                """,
                (user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]
