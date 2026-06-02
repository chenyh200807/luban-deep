from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from deeptutor.services.observability.product_behavior_catalog import find_forbidden_product_behavior_field


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

    forbidden = find_forbidden_product_behavior_field(raw)
    if forbidden:
        raise ValueError(f"Forbidden product behavior property: {forbidden}")
    return json.dumps(raw, ensure_ascii=False, sort_keys=True)


def _safe_properties(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            raw = json.loads(value or "{}")
        except json.JSONDecodeError:
            raw = {}
    elif isinstance(value, dict):
        raw = value
    else:
        raw = {}
    return raw if isinstance(raw, dict) else {}


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
                  object_type text not null default '',
                  object_id text not null default '',
                  entry_source text not null default '',
                  referrer_module text not null default '',
                  duration_ms integer not null default 0,
                  visible_ms integer not null default 0,
                  result text not null default '',
                  error_code text not null default '',
                  release_id text not null default '',
                  app_version text not null default '',
                  platform text not null default '',
                  device_model text not null default '',
                  network_type text not null default '',
                  properties_json text not null default '{}'
                )
                """
            )
            existing_columns = {
                str(row["name"])
                for row in conn.execute("pragma table_info(product_behavior_events)").fetchall()
            }
            for column_name, column_sql in {
                "object_type": "object_type text not null default ''",
                "object_id": "object_id text not null default ''",
                "entry_source": "entry_source text not null default ''",
                "referrer_module": "referrer_module text not null default ''",
                "duration_ms": "duration_ms integer not null default 0",
                "visible_ms": "visible_ms integer not null default 0",
                "result": "result text not null default ''",
                "error_code": "error_code text not null default ''",
                "release_id": "release_id text not null default ''",
                "app_version": "app_version text not null default ''",
                "platform": "platform text not null default ''",
                "device_model": "device_model text not null default ''",
                "network_type": "network_type text not null default ''",
            }.items():
                if column_name not in existing_columns:
                    conn.execute(f"alter table product_behavior_events add column {column_sql}")
            conn.execute(
                "create index if not exists idx_pbe_user_time on product_behavior_events(user_id, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_module_time on product_behavior_events(module, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_section_time on product_behavior_events(module, section, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_visit_time on product_behavior_events(visit_id, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_surface_time on product_behavior_events(surface, occurred_at_ms)"
            )
            conn.execute(
                "create index if not exists idx_pbe_event_time on product_behavior_events(event_name, occurred_at_ms)"
            )

    def record_event(self, event: dict[str, Any]) -> dict[str, Any]:
        raw_properties = _safe_properties(event.get("properties_json"))
        properties = _safe_properties_json(raw_properties)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    insert into product_behavior_events (
                      event_id, event_name, event_version, occurred_at_ms, received_at_ms,
                      user_id, visit_id, session_id, turn_id, surface, module, section, action,
                      object_type, object_id, entry_source, referrer_module, duration_ms, visible_ms,
                      result, error_code, release_id, app_version, platform, device_model, network_type,
                      properties_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        str(raw_properties.get("object_type") or ""),
                        str(raw_properties.get("object_id") or ""),
                        str(raw_properties.get("entry_source") or ""),
                        str(raw_properties.get("referrer_module") or ""),
                        int(raw_properties.get("duration_ms") or 0),
                        int(raw_properties.get("visible_ms") or 0),
                        str(raw_properties.get("result") or ""),
                        str(raw_properties.get("error_code") or ""),
                        str(raw_properties.get("release_id") or ""),
                        str(raw_properties.get("app_version") or ""),
                        str(raw_properties.get("platform") or ""),
                        str(raw_properties.get("device_model") or ""),
                        str(raw_properties.get("network_type") or ""),
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
            "event_count_7d": 0,
            "last_event_at_ms": 0,
            "cohort": "",
            "cohort_reasons": [],
            "next_action": "观察",
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
                select user_id, module, event_name, action, count(*) as count, max(occurred_at_ms) as last_event_at_ms
                from product_behavior_events
                where user_id in ({placeholders}) and occurred_at_ms >= ?
                group by user_id, module, event_name, action
                """,
                (*unique_user_ids, since),
            ).fetchall()

        counts_by_user: dict[str, dict[tuple[str, str], int]] = {user_id: {} for user_id in unique_user_ids}
        action_counts_by_user: dict[str, dict[tuple[str, str], int]] = {user_id: {} for user_id in unique_user_ids}
        event_counts_by_user: dict[str, int] = {user_id: 0 for user_id in unique_user_ids}
        last_event_by_user: dict[str, int] = {user_id: 0 for user_id in unique_user_ids}
        for row in rows:
            user_id = str(row["user_id"])
            count = int(row["count"])
            event_name = str(row["event_name"])
            action = str(row["action"])
            counts_by_user[user_id][(str(row["module"]), event_name)] = (
                counts_by_user[user_id].get((str(row["module"]), event_name), 0) + count
            )
            action_counts_by_user[user_id][(event_name, action)] = (
                action_counts_by_user[user_id].get((event_name, action), 0) + count
            )
            event_counts_by_user[user_id] += count
            last_event_by_user[user_id] = max(last_event_by_user[user_id], int(row["last_event_at_ms"] or 0))

        summaries: dict[str, dict[str, Any]] = {}
        for user_id, counts in counts_by_user.items():
            action_counts = action_counts_by_user[user_id]
            report_count = counts.get(("learning_report", "module_viewed"), 0)
            history_count = counts.get(("history", "module_viewed"), 0)
            chat_count = counts.get(("chat", "module_viewed"), 0)
            practice_count = counts.get(("practice", "module_viewed"), 0)
            assessment_count = counts.get(("assessment", "module_viewed"), 0)
            action_count = sum(
                count
                for (_module, event_name), count in counts.items()
                if event_name == "learning_action_started"
            )
            review_count = action_counts.get(("learning_action_started", "start_review"), 0)
            training_count = action_counts.get(("learning_action_started", "start_training"), 0)
            retest_count = action_counts.get(("learning_action_started", "start_retest"), 0) + action_counts.get(
                ("learning_action_completed", "start_retest"), 0
            )
            cohort, reasons, next_action = _classify_member_behavior_cohort(
                report_count=report_count,
                history_count=history_count,
                chat_count=chat_count,
                practice_count=practice_count,
                assessment_count=assessment_count,
                action_count=action_count,
                review_count=review_count,
                training_count=training_count,
                retest_count=retest_count,
            )
            summaries[user_id] = {
                "learning_report_open_count_7d": report_count,
                "history_open_count_7d": history_count,
                "action_start_count_7d": action_count,
                "event_count_7d": event_counts_by_user[user_id],
                "last_event_at_ms": last_event_by_user[user_id],
                "cohort": cohort,
                "cohort_reasons": reasons,
                "next_action": next_action,
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

    def get_member_timeline(self, user_id: str, *, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
        since = self._since_ms(days)
        with self._connect() as conn:
            rows = conn.execute(
                """
                select event_id, event_name, occurred_at_ms, surface, module, section, action,
                       visit_id, session_id, turn_id, object_type, object_id, entry_source,
                       referrer_module, duration_ms, visible_ms, result, error_code, release_id,
                       app_version, platform
                from product_behavior_events
                where user_id = ? and occurred_at_ms >= ?
                order by occurred_at_ms desc
                limit ?
                """,
                (user_id, since, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def query_raw_events(self, filters: dict[str, Any] | None = None, *, limit: int = 1000) -> list[dict[str, Any]]:
        filters = filters or {}
        clauses = []
        params: list[Any] = []
        try:
            days = int(filters.get("days") or 7)
        except (TypeError, ValueError):
            days = 7
        clauses.append("occurred_at_ms >= ?")
        params.append(self._since_ms(days))
        for key in ("user_id", "event_name", "surface", "module", "section", "action"):
            value = str(filters.get(key) or "").strip()
            if value:
                clauses.append(f"{key} = ?")
                params.append(value)
        try:
            normalized_limit = int(limit or 1000)
        except (TypeError, ValueError):
            normalized_limit = 1000
        normalized_limit = max(1, min(normalized_limit, 5000))
        where_sql = " and ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select event_id, event_name, event_version, occurred_at_ms, received_at_ms,
                       user_id, visit_id, session_id, turn_id, surface, module, section,
                       action, object_type, object_id, entry_source, referrer_module,
                       duration_ms, visible_ms, result, error_code, release_id, app_version,
                       platform, device_model, network_type, properties_json
                from product_behavior_events
                where {where_sql}
                order by occurred_at_ms desc
                limit ?
                """,
                (*params, normalized_limit),
            ).fetchall()
        return [dict(row) for row in rows]


def _classify_member_behavior_cohort(
    *,
    report_count: int,
    history_count: int,
    chat_count: int,
    practice_count: int,
    assessment_count: int,
    action_count: int,
    review_count: int,
    training_count: int,
    retest_count: int,
) -> tuple[str, list[str], str]:
    if training_count > 0 and retest_count == 0:
        return (
            "training_no_retest",
            [f"已开始训练 {training_count} 次", "7 日内未看到复测动作"],
            "提醒复测",
        )
    if report_count >= 3 and action_count == 0:
        return (
            "report_high_no_action",
            [f"7 日内打开学情 {report_count} 次", "未开始训练/复盘/复测动作"],
            "推送下一步训练",
        )
    if history_count >= 3 and review_count == 0:
        return (
            "history_high_no_review",
            [f"7 日内打开历史 {history_count} 次", "未开始错题复盘"],
            "发送错题复盘",
        )
    if chat_count >= 3 and report_count == 0 and history_count == 0 and practice_count == 0 and assessment_count == 0:
        return (
            "chat_only",
            [f"7 日内对话入口打开 {chat_count} 次", "未进入学情/历史/练习/测评"],
            "引导查看学情",
        )
    return ("", [], "观察")
