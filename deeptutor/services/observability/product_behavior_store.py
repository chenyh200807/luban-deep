from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Sequence
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
                  practice_mode text not null default '',
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
                "practice_mode": "practice_mode text not null default ''",
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
            # 学习模块偏好计划 §6-P1：object 级 Top-N(内容偏好/练习正确率)全局聚合走此索引，
            # 否则 get_engagement_breakdown 的 BI-wide 查询全表扫。
            conn.execute(
                "create index if not exists idx_pbe_object on product_behavior_events(object_type, object_id, occurred_at_ms)"
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
                      practice_mode, properties_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        str(raw_properties.get("practice_mode") or ""),
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
            "first_run_evidence_status": "not_started",
            "first_run_question_count": 0,
            "first_run_completion_count": 0,
            "first_run_legacy_completion_count": 0,
            "top_module_7d": "",
            "module_usage_7d": [],
            "cohort": "",
            "cohort_reasons": [],
            "next_action": "观察",
            "trust_level": "B",
        }

    def get_member_behavior_summaries_for_identity_groups(
        self,
        identity_groups: dict[str, list[str]],
        *,
        days: int = 7,
    ) -> dict[str, dict[str, Any]]:
        normalized_groups: dict[str, list[str]] = {}
        identity_to_group_keys: dict[str, set[str]] = {}
        for group_key, identities in (identity_groups or {}).items():
            key = str(group_key or "").strip()
            if not key:
                continue
            normalized = sorted({str(identity or "").strip() for identity in identities if str(identity or "").strip()})
            normalized_groups[key] = normalized
            for identity in normalized:
                identity_to_group_keys.setdefault(identity, set()).add(key)
        ambiguous_identity_groups = {
            identity: group_keys
            for identity, group_keys in identity_to_group_keys.items()
            if len(group_keys) > 1
        }
        identity_to_group_keys = {
            identity: group_keys
            for identity, group_keys in identity_to_group_keys.items()
            if len(group_keys) == 1
        }

        if not normalized_groups:
            return {}

        unique_user_ids = sorted(identity_to_group_keys)
        if not unique_user_ids:
            return {key: self._empty_summary() for key in normalized_groups}

        since = self._since_ms(days)
        placeholders = ",".join("?" for _ in unique_user_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select user_id, module, event_name, event_version, action, object_type, result,
                       count(*) as count, max(occurred_at_ms) as last_event_at_ms
                from product_behavior_events
                where user_id in ({placeholders}) and occurred_at_ms >= ?
                group by user_id, module, event_name, event_version, action, object_type, result
                """,
                (*unique_user_ids, since),
            ).fetchall()
            first_run_rows = conn.execute(
                f"""
                select user_id, event_name, event_version, object_type, result, count(*) as count
                from product_behavior_events
                where user_id in ({placeholders}) and module = 'first_run'
                group by user_id, event_name, event_version, object_type, result
                """,
                unique_user_ids,
            ).fetchall()

        counts_by_user: dict[str, dict[tuple[str, str], int]] = {key: {} for key in normalized_groups}
        action_counts_by_user: dict[str, dict[tuple[str, str], int]] = {key: {} for key in normalized_groups}
        event_counts_by_user: dict[str, int] = {key: 0 for key in normalized_groups}
        last_event_by_user: dict[str, int] = {key: 0 for key in normalized_groups}
        first_run_by_user: dict[str, dict[str, int]] = {
            key: {"started": 0, "questions": 0, "completed": 0, "legacy": 0}
            for key in normalized_groups
        }
        for row in rows:
            user_id = str(row["user_id"])
            count = int(row["count"])
            event_name = str(row["event_name"])
            action = str(row["action"])
            for group_key in identity_to_group_keys.get(user_id, set()):
                counts_by_user[group_key][(str(row["module"]), event_name)] = (
                    counts_by_user[group_key].get((str(row["module"]), event_name), 0) + count
                )
                action_counts_by_user[group_key][(event_name, action)] = (
                    action_counts_by_user[group_key].get((event_name, action), 0) + count
                )
                event_counts_by_user[group_key] += count
                last_event_by_user[group_key] = max(
                    last_event_by_user[group_key],
                    int(row["last_event_at_ms"] or 0),
                )
        for row in first_run_rows:
            count = int(row["count"])
            for group_key in identity_to_group_keys.get(str(row["user_id"]), set()):
                if str(row["event_name"]) == "first_run_started":
                    first_run_by_user[group_key]["started"] += count
                elif str(row["event_name"]) == "first_run_question_completed":
                    first_run_by_user[group_key]["questions"] += count
                elif str(row["event_name"]) == "learning_action_completed" and str(row["object_type"]) == "script":
                    if str(row["result"]) == "synced" and int(row["event_version"] or 1) >= 2:
                        first_run_by_user[group_key]["completed"] += count
                    elif str(row["result"]) in {"go_report", "remind"}:
                        first_run_by_user[group_key]["legacy"] += count

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
            module_usage = []
            for module in sorted({module for module, _event_name in counts} - {"login", "first_run"}):
                view_count = counts.get((module, "module_viewed"), 0)
                action_count_for_module = counts.get((module, "learning_action_started"), 0)
                completion_count = counts.get((module, "learning_action_completed"), 0)
                event_count = sum(count for (event_module, _event_name), count in counts.items() if event_module == module)
                module_usage.append(
                    {
                        "module": module,
                        "view_count": view_count,
                        "action_count": action_count_for_module,
                        "completion_count": completion_count,
                        "event_count": event_count,
                    }
                )
            module_usage.sort(
                key=lambda item: (
                    item["action_count"] + item["completion_count"],
                    item["view_count"],
                    item["event_count"],
                    item["module"],
                ),
                reverse=True,
            )
            first_run = first_run_by_user[user_id]
            first_run_status = (
                "completed"
                if first_run["completed"]
                else "legacy_completion_signal"
                if first_run["legacy"]
                else "in_progress"
                if first_run["started"] or first_run["questions"]
                else "not_started"
            )
            summaries[user_id] = {
                "learning_report_open_count_7d": report_count,
                "history_open_count_7d": history_count,
                "action_start_count_7d": action_count,
                "event_count_7d": event_counts_by_user[user_id],
                "last_event_at_ms": last_event_by_user[user_id],
                "first_run_evidence_status": first_run_status,
                "first_run_question_count": first_run["questions"],
                "first_run_completion_count": first_run["completed"],
                "first_run_legacy_completion_count": first_run["legacy"],
                "top_module_7d": module_usage[0]["module"] if module_usage else "",
                "module_usage_7d": module_usage,
                "cohort": cohort,
                "cohort_reasons": reasons,
                "next_action": next_action,
                "identity_collision_count": sum(
                    1 for group_keys in ambiguous_identity_groups.values() if user_id in group_keys
                ),
                "trust_level": (
                    "C" if any(user_id in group_keys for group_keys in ambiguous_identity_groups.values()) else "B"
                ),
            }
        return summaries

    def get_product_usage_overview_for_identity_groups(
        self,
        identity_groups: dict[str, list[str]],
        *,
        days: int = 7,
    ) -> dict[str, Any]:
        identity_to_groups: dict[str, set[str]] = {}
        for group_key, identities in (identity_groups or {}).items():
            normalized_group = str(group_key or "").strip()
            if not normalized_group:
                continue
            for identity in identities:
                normalized_identity = str(identity or "").strip()
                if normalized_identity:
                    identity_to_groups.setdefault(normalized_identity, set()).add(normalized_group)
        ambiguous_identity_groups = {
            identity: group_keys
            for identity, group_keys in identity_to_groups.items()
            if len(group_keys) > 1
        }
        identity_to_groups = {
            identity: group_keys
            for identity, group_keys in identity_to_groups.items()
            if len(group_keys) == 1
        }

        rows: list[sqlite3.Row] = []
        identities = sorted(identity_to_groups)
        since = self._since_ms(days)
        with self._connect() as conn:
            for start in range(0, len(identities), 500):
                batch = identities[start : start + 500]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                rows.extend(
                    conn.execute(
                        f"""
                        select user_id, visit_id, module, event_name, event_version, object_type,
                               result, duration_ms, visible_ms, count(*) as event_count
                        from product_behavior_events
                        where user_id in ({placeholders}) and occurred_at_ms >= ?
                        group by user_id, visit_id, module, event_name, event_version,
                                 object_type, result, duration_ms, visible_ms
                        """,
                        (*batch, since),
                    ).fetchall()
                )

        tracked_members: set[str] = set()
        first_run_members = {"started": set(), "questions": set(), "completed": set(), "legacy": set()}
        modules: dict[str, dict[str, Any]] = {}
        for row in rows:
            event_count = int(row["event_count"] or 0)
            group_keys = identity_to_groups.get(str(row["user_id"]), set())
            for group_key in group_keys:
                tracked_members.add(group_key)
                module = str(row["module"])
                event_name = str(row["event_name"])
                if module == "first_run":
                    if event_name == "first_run_started":
                        first_run_members["started"].add(group_key)
                    elif event_name == "first_run_question_completed":
                        first_run_members["questions"].add(group_key)
                    elif event_name == "learning_action_completed" and str(row["object_type"]) == "script":
                        if str(row["result"]) == "synced" and int(row["event_version"] or 1) >= 2:
                            first_run_members["completed"].add(group_key)
                        elif str(row["result"]) in {"go_report", "remind"}:
                            first_run_members["legacy"].add(group_key)
                if module in {"", "login", "first_run"}:
                    continue
                usage = modules.setdefault(
                    module,
                    {
                        "module": module,
                        "members": set(),
                        "visits": set(),
                        "view_count": 0,
                        "action_count": 0,
                        "completion_count": 0,
                        "exit_count": 0,
                        "quick_exit_count": 0,
                    },
                )
                usage["members"].add(group_key)
                visit_id = str(row["visit_id"] or "")
                if visit_id:
                    usage["visits"].add((group_key, visit_id))
                if event_name == "module_viewed":
                    usage["view_count"] += event_count
                elif event_name == "learning_action_started":
                    usage["action_count"] += event_count
                elif event_name == "learning_action_completed":
                    usage["completion_count"] += event_count
                elif event_name == "module_exited":
                    usage["exit_count"] += event_count
                    dwell_ms = int(row["visible_ms"] or row["duration_ms"] or 0)
                    if 0 < dwell_ms < 5_000:
                        usage["quick_exit_count"] += event_count

        module_usage = [
            {
                "module": usage["module"],
                "member_count": len(usage["members"]),
                "visit_count": len(usage["visits"]),
                "view_count": usage["view_count"],
                "action_count": usage["action_count"],
                "completion_count": usage["completion_count"],
                "exit_count": usage["exit_count"],
                "quick_exit_count": usage["quick_exit_count"],
            }
            for usage in modules.values()
        ]
        module_usage.sort(key=lambda item: (item["member_count"], item["visit_count"], item["view_count"]), reverse=True)
        started_count = len(first_run_members["started"])
        eligible_count = len({str(key).strip() for key in identity_groups if str(key).strip()})
        completed_count = len(first_run_members["completed"])
        started_completion_count = len(first_run_members["completed"] & first_run_members["started"])
        return {
            "tracked_member_count": len(tracked_members),
            "identity_collision_count": len(ambiguous_identity_groups),
            "identity_collision_member_count": len(
                {group_key for group_keys in ambiguous_identity_groups.values() for group_key in group_keys}
            ),
            "first_run": {
                "started_member_count": started_count,
                "eligible_member_count": eligible_count,
                "not_started_member_count": max(
                    0,
                    eligible_count
                    - len(
                        first_run_members["started"]
                        | first_run_members["questions"]
                        | first_run_members["completed"]
                    ),
                ),
                "question_member_count": len(first_run_members["questions"]),
                "completed_member_count": completed_count,
                "legacy_completion_member_count": len(first_run_members["legacy"] - first_run_members["completed"]),
                "completion_rate": round(started_completion_count / started_count, 4) if started_count else 0.0,
                "completion_rate_of_eligible": round(completed_count / eligible_count, 4) if eligible_count else 0.0,
            },
            "module_usage": module_usage,
        }

    def get_member_behavior_summaries(self, user_ids: list[str], *, days: int = 7) -> dict[str, dict[str, Any]]:
        unique_user_ids = sorted({str(user_id) for user_id in user_ids if str(user_id)})
        return self.get_member_behavior_summaries_for_identity_groups(
            {user_id: [user_id] for user_id in unique_user_ids},
            days=days,
        )

    def get_member_behavior_summary(self, user_id: str, *, days: int = 7) -> dict[str, Any]:
        return self.get_member_behavior_summaries([user_id], days=days).get(user_id, self._empty_summary())

    def get_learning_report_section_breakdown_for_identity_group(
        self,
        user_ids: list[str],
        *,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        unique_user_ids = sorted({str(user_id) for user_id in user_ids if str(user_id)})
        if not unique_user_ids:
            return []
        since = self._since_ms(days)
        placeholders = ",".join("?" for _ in unique_user_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select section, count(*) as view_count
                from product_behavior_events
                where user_id in ({placeholders})
                  and occurred_at_ms >= ?
                  and module = 'learning_report'
                  and event_name = 'section_viewed'
                  and section != ''
                group by section
                order by view_count desc, section asc
                """,
                (*unique_user_ids, since),
            ).fetchall()
        return [{"section": str(row["section"]), "view_count": int(row["view_count"])} for row in rows]

    def get_learning_report_section_breakdown(self, user_id: str, *, days: int = 7) -> list[dict[str, Any]]:
        return self.get_learning_report_section_breakdown_for_identity_group([user_id], days=days)

    def get_engagement_breakdown(
        self,
        *,
        group_dim: str = "object_id",
        days: int = 7,
        module: str | None = None,
        event_names: Sequence[str] | None = None,
        object_types: Sequence[str] | None = None,
        exclude_user_ids: Sequence[str] | None = None,
        exclude_user_id_prefixes: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """学习模块偏好计划 §6-P1 的单一参数化 object 级聚合（泛化自 section breakdown）。

        一次 group-by 同时支撑三个偏好切面（同事实的不同 group_dim，非三套 authority）：
        - 内容偏好（"哪几个微课/考点讲解被反复看"）：group_dim=object_id,
          object_types=LEARNING_CONTENT_OBJECT_TYPES, module=learning。
        - 功能偏好（"哪些功能被点得多"）：group_dim=object_id|action, module=learning。
        - 练习正确率（"练习做了多少+对不对"）：event_names=[retest_item_answered],
          answered/correct 来自 result 字段。
        单一数据权威；bi.py 薄 handler 调它，不进 member_console/service.py（避 learner_state 受保护域）。
        exclude_user_ids 供 demo/eval cohort 隔离（默认排除，防合成数据污染真值）。
        """
        allowed_dims = {"object_id", "object_type", "action", "module"}
        dim = group_dim if group_dim in allowed_dims else "object_id"
        since = self._since_ms(days)

        where = ["occurred_at_ms >= ?"]
        params: list[Any] = [since]
        if module:
            where.append("module = ?")
            params.append(str(module))
        events = [str(e).strip() for e in (event_names or []) if str(e).strip()]
        if events:
            where.append(f"event_name in ({','.join('?' for _ in events)})")
            params.extend(events)
        otypes = [str(o).strip() for o in (object_types or []) if str(o).strip()]
        if otypes:
            where.append(f"object_type in ({','.join('?' for _ in otypes)})")
            params.extend(otypes)
        excluded = sorted({str(u).strip() for u in (exclude_user_ids or []) if str(u).strip()})
        if excluded:
            where.append(f"user_id not in ({','.join('?' for _ in excluded)})")
            params.extend(excluded)
        # demo/eval cohort 隔离（D 红线）：按账号前缀排除合成数据，防污染真值。
        # SQLite LIKE 的 _ / % 是通配符，需转义 + 声明 escape，否则 'eval_' 会误匹配 'evalX'。
        excluded_prefixes = sorted({str(p).strip() for p in (exclude_user_id_prefixes or []) if str(p).strip()})
        for prefix in excluded_prefixes:
            where.append(r"user_id not like ? escape '\'")
            params.append(prefix.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_") + "%")
        # 分组维度为空的事件不计入（如 object_id 维度下未带 object 的埋点）。
        where.append(f"{dim} != ''")

        sql = f"""
            select {dim} as k, object_type, user_id, visit_id, result,
                   visible_ms, duration_ms, count(*) as event_count
            from product_behavior_events
            where {' and '.join(where)}
            group by {dim}, object_type, user_id, visit_id, result, visible_ms, duration_ms
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row["k"])
            event_count = int(row["event_count"] or 0)
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "object_types": {},
                    "members": set(),
                    "visits": set(),
                    "event_count": 0,
                    "answered_count": 0,
                    "correct_count": 0,
                    "_dwell_sum": 0,
                    "_dwell_n": 0,
                },
            )
            object_type = str(row["object_type"] or "")
            if object_type:
                bucket["object_types"][object_type] = bucket["object_types"].get(object_type, 0) + event_count
            user_id = str(row["user_id"] or "")
            visit_id = str(row["visit_id"] or "")
            if user_id:
                bucket["members"].add(user_id)
                if visit_id:
                    bucket["visits"].add((user_id, visit_id))
            bucket["event_count"] += event_count
            result = str(row["result"] or "")
            if result in {"correct", "incorrect"}:
                bucket["answered_count"] += event_count
                if result == "correct":
                    bucket["correct_count"] += event_count
            dwell_ms = int(row["visible_ms"] or row["duration_ms"] or 0)
            if dwell_ms > 0:
                bucket["_dwell_sum"] += dwell_ms * event_count
                bucket["_dwell_n"] += event_count

        breakdown: list[dict[str, Any]] = []
        for bucket in buckets.values():
            member_count = len(bucket["members"])
            answered = bucket["answered_count"]
            dominant_type = ""
            if bucket["object_types"]:
                dominant_type = max(bucket["object_types"].items(), key=lambda kv: kv[1])[0]
            breakdown.append(
                {
                    "key": bucket["key"],
                    "object_type": dominant_type,
                    "member_count": member_count,
                    "visit_count": len(bucket["visits"]),
                    "event_count": bucket["event_count"],
                    "answered_count": answered,
                    "correct_count": bucket["correct_count"],
                    "accuracy": round(bucket["correct_count"] / answered, 4) if answered else None,
                    "repeat_rate": round(bucket["event_count"] / member_count, 4) if member_count else 0.0,
                    "avg_dwell_ms": int(bucket["_dwell_sum"] / bucket["_dwell_n"]) if bucket["_dwell_n"] else 0,
                }
            )
        breakdown.sort(key=lambda item: (item["member_count"], item["event_count"]), reverse=True)
        return breakdown[: max(1, int(limit))] if limit else breakdown

    def get_member_timeline_for_identity_group(
        self,
        user_ids: list[str],
        *,
        days: int = 7,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        unique_user_ids = sorted({str(user_id) for user_id in user_ids if str(user_id)})
        if not unique_user_ids:
            return []
        since = self._since_ms(days)
        placeholders = ",".join("?" for _ in unique_user_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select event_id, event_name, occurred_at_ms, surface, module, section, action,
                       visit_id, session_id, turn_id, object_type, object_id, entry_source,
                       referrer_module, duration_ms, visible_ms, result, error_code, release_id,
                       app_version, platform
                from product_behavior_events
                where user_id in ({placeholders}) and occurred_at_ms >= ?
                order by occurred_at_ms desc
                limit ?
                """,
                (*unique_user_ids, since, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_member_timeline(self, user_id: str, *, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
        return self.get_member_timeline_for_identity_group([user_id], days=days, limit=limit)

    def query_raw_events(self, filters: dict[str, Any] | None = None, *, limit: int = 1000) -> list[dict[str, Any]]:
        filters = filters or {}
        clauses = []
        params: list[Any] = []
        start_ts_ms = filters.get("start_ts_ms")
        end_ts_ms = filters.get("end_ts_ms")
        if start_ts_ms is not None:
            clauses.append("occurred_at_ms >= ?")
            params.append(int(start_ts_ms))
        else:
            try:
                days = int(filters.get("days") or 7)
            except (TypeError, ValueError):
                days = 7
            clauses.append("occurred_at_ms >= ?")
            params.append(self._since_ms(days))
        if end_ts_ms is not None:
            clauses.append("occurred_at_ms <= ?")
            params.append(int(end_ts_ms))
        for key in ("user_id", "event_name", "surface", "module", "section", "action", "practice_mode"):
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
                       platform, device_model, network_type, practice_mode, properties_json
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
