from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from deeptutor.services.observability.product_behavior_catalog import (
    find_forbidden_product_behavior_field,
)


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
        # WAL:让读不被写阻塞。默认 journal_mode=delete 下读写互斥,本库有并发读写
        # (埋点写 + BI 读),互斥会把并发压成串行。journal_mode 持久化在 db 文件里,
        # 每次连接设置是幂等自愈;有其他连接持锁时设置失败并保持原样。
        #
        # **顺序不能颠倒**:实测 sqlite 3.51 —— synchronous 停在默认值时,
        # `journal_mode=WAL` 会把它从 FULL(2) 隐式降级到 NORMAL(1);显式设过 FULL
        # 的连接切 WAL 不降。故必须先钉 FULL 再切 WAL。
        #
        # 前置已确认:生产 data 是 ext4 本地块设备(WAL 依赖 -shm 共享内存映射)。
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
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
            # 同一播放器 session 的 sequence 是语义幂等键。仍写唯一
            # product_behavior_events authority，不新建 video analytics 表。
            conn.execute(
                """
                create unique index if not exists idx_pbe_playback_sequence
                on product_behavior_events(
                  user_id,
                  json_extract(properties_json, '$.playback_session_id'),
                  cast(json_extract(properties_json, '$.sequence') as integer)
                )
                where event_name = 'microlesson_playback'
                """
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

    def get_data_quality_snapshot(
        self,
        *,
        days: int = 7,
        identity_groups: dict[str, list[str]] | None = None,
        exclude_user_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Return the canonical readiness evidence for product-behavior BI readers.

        ``identity_groups`` collapses aliases belonging to one business member.  When
        supplied, only unambiguous identities in those groups are in scope.  Exact
        exclusions are applied before both event and member counts so eval/internal
        identities cannot make the quality signal look healthy.
        """
        window_days = max(1, int(days or 1))
        excluded = {
            str(user_id or "").strip()
            for user_id in (exclude_user_ids or [])
            if str(user_id or "").strip()
        }
        identity_to_groups: dict[str, set[str]] = {}
        if identity_groups is not None:
            for group_key, identities in identity_groups.items():
                normalized_group = str(group_key or "").strip()
                if not normalized_group:
                    continue
                for identity in identities:
                    normalized_identity = str(identity or "").strip()
                    if normalized_identity and normalized_identity not in excluded:
                        identity_to_groups.setdefault(normalized_identity, set()).add(normalized_group)
            identity_to_group = {
                identity: next(iter(group_keys))
                for identity, group_keys in identity_to_groups.items()
                if len(group_keys) == 1
            }
            scoped_user_ids = sorted(identity_to_group)
            identity_collision_count = sum(1 for groups in identity_to_groups.values() if len(groups) > 1)
        else:
            identity_to_group = {}
            scoped_user_ids = []
            identity_collision_count = 0

        where = ["occurred_at_ms >= ?"]
        params: list[Any] = [self._since_ms(window_days)]
        if identity_groups is not None:
            if not scoped_user_ids:
                return self._empty_data_quality_snapshot(
                    days=window_days,
                    identity_collision_count=identity_collision_count,
                )
            where.append(f"user_id in ({','.join('?' for _ in scoped_user_ids)})")
            params.extend(scoped_user_ids)
        elif excluded:
            sorted_excluded = sorted(excluded)
            where.append(f"user_id not in ({','.join('?' for _ in sorted_excluded)})")
            params.extend(sorted_excluded)

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    select user_id, count(*) as event_count,
                           max(occurred_at_ms) as last_event_at_ms,
                           sum(case when release_id != '' then 1 else 0 end) as release_id_count,
                           sum(case when app_version != '' then 1 else 0 end) as app_version_count,
                           sum(case when release_id != '' or app_version != '' then 1 else 0 end) as version_count,
                           sum(case when platform != '' then 1 else 0 end) as platform_count
                    from product_behavior_events
                    where {' and '.join(where)}
                    group by user_id
                    """,
                    tuple(params),
                ).fetchall()
        except sqlite3.Error:
            snapshot = self._empty_data_quality_snapshot(
                days=window_days,
                identity_collision_count=identity_collision_count,
            )
            snapshot.update({"available": False, "status": "unavailable"})
            return snapshot

        event_count = sum(int(row["event_count"] or 0) for row in rows)
        if not event_count:
            return self._empty_data_quality_snapshot(
                days=window_days,
                identity_collision_count=identity_collision_count,
            )

        release_id_count = sum(int(row["release_id_count"] or 0) for row in rows)
        app_version_count = sum(int(row["app_version_count"] or 0) for row in rows)
        version_count = sum(int(row["version_count"] or 0) for row in rows)
        platform_count = sum(int(row["platform_count"] or 0) for row in rows)
        member_keys = {
            identity_to_group.get(str(row["user_id"]), str(row["user_id"]))
            for row in rows
        }

        def coverage(populated_count: int) -> dict[str, Any]:
            return {
                "populated_event_count": populated_count,
                "coverage_rate": round(populated_count / event_count, 4),
            }

        release_coverage = coverage(release_id_count)
        app_coverage = coverage(app_version_count)
        version_coverage = coverage(version_count)
        platform_coverage = coverage(platform_count)
        status = (
            "ready"
            if version_coverage["coverage_rate"] == 1.0
            and platform_coverage["coverage_rate"] == 1.0
            and identity_collision_count == 0
            else "degraded"
        )
        return {
            "available": True,
            "status": status,
            "window_days": window_days,
            "event_count": event_count,
            "user_count": len(member_keys),
            "last_event_at_ms": max(int(row["last_event_at_ms"] or 0) for row in rows),
            "identity_collision_count": identity_collision_count,
            "coverage": {
                "release_id": release_coverage,
                "app_version": app_coverage,
                "version": version_coverage,
                "platform": platform_coverage,
            },
        }

    def _empty_data_quality_snapshot(
        self,
        *,
        days: int,
        identity_collision_count: int = 0,
    ) -> dict[str, Any]:
        empty_coverage = {"populated_event_count": 0, "coverage_rate": 0.0}
        return {
            "available": True,
            "status": "empty",
            "window_days": days,
            "event_count": 0,
            "user_count": 0,
            "last_event_at_ms": 0,
            "identity_collision_count": identity_collision_count,
            "coverage": {
                "release_id": dict(empty_coverage),
                "app_version": dict(empty_coverage),
                "version": dict(empty_coverage),
                "platform": dict(empty_coverage),
            },
        }

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
        user_ids: Sequence[str] | None = None,
        exclude_user_ids: Sequence[str] | None = None,
        exclude_user_id_prefixes: Sequence[str] | None = None,
        order_by: str = "member_count",
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
        user_ids（2026-07-21 新增，单会员行为明细 §7）：inclusive 白名单，收窄到指定用户——
        与全局视图共享同一个聚合函数(同一事实的不同过滤维度)，不新建"单用户行为"的第二套聚合。
        """
        allowed_dims = {"object_id", "object_type", "action", "module"}
        dim = group_dim if group_dim in allowed_dims else "object_id"
        since = self._since_ms(days)

        where = ["occurred_at_ms >= ?"]
        params: list[Any] = [since]
        if module:
            where.append("module = ?")
            params.append(str(module))
        included = sorted({str(u).strip() for u in (user_ids or []) if str(u).strip()})
        if included:
            where.append(f"user_id in ({','.join('?' for _ in included)})")
            params.extend(included)
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
            select {dim} as k, object_type, user_id, visit_id, event_name, action, result, error_code,
                   visible_ms, duration_ms, count(*) as event_count,
                   max(occurred_at_ms) as last_event_at_ms
            from product_behavior_events
            where {' and '.join(where)}
            group by {dim}, object_type, user_id, visit_id, event_name, action, result, error_code,
                     visible_ms, duration_ms
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
                    "_meaningful_visits_by_user": {},
                    "event_count": 0,
                    "view_count": 0,
                    "start_count": 0,
                    "selection_count": 0,
                    "content_open_count": 0,
                    "completion_count": 0,
                    "exit_count": 0,
                    "error_count": 0,
                    "answered_count": 0,
                    "correct_count": 0,
                    "_dwell_sum": 0,
                    "_dwell_n": 0,
                    "_last_event_at_ms": 0,
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
            event_name = str(row["event_name"] or "")
            if event_name == "module_viewed":
                bucket["view_count"] += event_count
            elif event_name == "learning_action_started":
                bucket["start_count"] += event_count
                action = str(row["action"] or "")
                if action == "open_detail":
                    bucket["selection_count"] += event_count
                elif action == "start_training":
                    bucket["content_open_count"] += event_count
            meaningful = (
                (dim == "module" and event_name == "module_viewed")
                or (dim != "module" and event_name == "module_viewed" and object_type == "station")
                or (
                    dim != "module"
                    and event_name == "learning_action_started"
                    and (object_type != "microlesson" or str(row["action"] or "") == "start_training")
                )
            )
            if meaningful and user_id and visit_id:
                bucket["_meaningful_visits_by_user"].setdefault(user_id, set()).add(visit_id)
            elif event_name == "learning_action_completed":
                bucket["completion_count"] += event_count
            elif event_name == "module_exited":
                bucket["exit_count"] += event_count
            if (
                event_name == "event_error"
                or str(row["result"] or "") in {"error", "fail", "failed"}
                or bool(str(row["error_code"] or "").strip())
            ):
                bucket["error_count"] += event_count
            bucket["_last_event_at_ms"] = max(
                bucket["_last_event_at_ms"], int(row["last_event_at_ms"] or 0)
            )
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
            meaningful_visits = bucket["_meaningful_visits_by_user"]
            engaged_member_count = len(meaningful_visits)
            meaningful_visit_count = sum(len(visits) for visits in meaningful_visits.values())
            repeat_user_count = sum(1 for visits in meaningful_visits.values() if len(visits) >= 2)
            answered = bucket["answered_count"]
            dominant_type = ""
            if bucket["object_types"]:
                dominant_type = max(bucket["object_types"].items(), key=lambda kv: kv[1])[0]
            engagement_count = (
                bucket["content_open_count"]
                if dominant_type == "microlesson"
                else bucket["start_count"] or bucket["view_count"]
            )
            breakdown.append(
                {
                    "key": bucket["key"],
                    "object_type": dominant_type,
                    "member_count": member_count,
                    "visit_count": len(bucket["visits"]),
                    "engaged_member_count": engaged_member_count,
                    "meaningful_visit_count": meaningful_visit_count,
                    "repeat_user_count": repeat_user_count,
                    "repeat_user_rate": (
                        round(repeat_user_count / engaged_member_count, 4)
                        if engaged_member_count
                        else None
                    ),
                    "event_count": bucket["event_count"],
                    "view_count": bucket["view_count"],
                    "start_count": bucket["start_count"],
                    "selection_count": bucket["selection_count"],
                    "content_open_count": bucket["content_open_count"],
                    "completion_count": bucket["completion_count"],
                    "exit_count": bucket["exit_count"],
                    "error_count": bucket["error_count"],
                    "engagement_count": engagement_count,
                    "answered_count": answered,
                    "correct_count": bucket["correct_count"],
                    "accuracy": round(bucket["correct_count"] / answered, 4) if answered else None,
                    # 旧客户端兼容字段；它只是原始事件密度，不得再解释为复看率。
                    "repeat_rate": round(bucket["event_count"] / member_count, 4) if member_count else 0.0,
                    "raw_event_density": round(bucket["event_count"] / member_count, 4) if member_count else 0.0,
                    "total_dwell_ms": bucket["_dwell_sum"],
                    "avg_dwell_ms": int(bucket["_dwell_sum"] / bucket["_dwell_n"]) if bucket["_dwell_n"] else 0,
                    "dwell_event_count": bucket["_dwell_n"],
                    "last_event_at_ms": bucket["_last_event_at_ms"],
                }
            )
        allowed_order = {
            "member_count",
            "event_count",
            "engagement_count",
            "view_count",
            "start_count",
            "content_open_count",
        }
        order_key = order_by if order_by in allowed_order else "member_count"
        breakdown.sort(
            key=lambda item: (item[order_key], item["member_count"], item["event_count"]),
            reverse=True,
        )
        return breakdown[: max(1, int(limit))] if limit else breakdown

    def get_microlesson_playback_breakdown(
        self,
        *,
        days: int = 7,
        exclude_user_ids: Sequence[str] | None = None,
        exclude_user_id_prefixes: Sequence[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Project player/section facts from the canonical behavior ledger.

        ``section_enter`` means reached, never watched. A section counts as
        watched only when the same playback session has active playback time
        and a server-validated section progress of at least 90%. Contiguous
        progress stops at the first not-watched section, so jumping to section
        7 cannot fabricate completion of sections 1-6.
        """
        where = [
            "occurred_at_ms >= ?",
            "event_name = 'microlesson_playback'",
            "object_type = 'microlesson'",
            "object_id != ''",
        ]
        params: list[Any] = [self._since_ms(days)]
        excluded = sorted(
            {
                str(user_id).strip()
                for user_id in (exclude_user_ids or [])
                if str(user_id).strip()
            }
        )
        if excluded:
            where.append(
                f"user_id not in ({','.join('?' for _ in excluded)})"
            )
            params.extend(excluded)
        for prefix in sorted(
            {
                str(value).strip()
                for value in (exclude_user_id_prefixes or [])
                if str(value).strip()
            }
        ):
            where.append(r"user_id not like ? escape '\'")
            params.append(
                prefix.replace("\\", r"\\")
                .replace("%", r"\%")
                .replace("_", r"\_")
                + "%"
            )
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select user_id, visit_id, object_id, section, action,
                       duration_ms, occurred_at_ms, properties_json
                from product_behavior_events
                where {' and '.join(where)}
                order by occurred_at_ms asc, event_id asc
                """,
                tuple(params),
            ).fetchall()

        sessions: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            try:
                properties = json.loads(str(row["properties_json"] or "{}"))
            except json.JSONDecodeError:
                properties = {}
            if not isinstance(properties, dict):
                properties = {}
            user_id = str(row["user_id"] or "")
            session_id = str(
                properties.get("playback_session_id")
                or row["visit_id"]
                or ""
            )
            object_id = str(row["object_id"] or "")
            if not user_id or not session_id or not object_id:
                continue
            session = sessions.setdefault(
                (user_id, session_id, object_id),
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "object_id": object_id,
                    "play_count": 0,
                    "completed": False,
                    "total_active_ms": 0,
                    "max_progress_pct": 0,
                    "sections": {},
                    "last_event_at_ms": 0,
                },
            )
            action = str(row["action"] or "")
            if action in {"play", "replay"}:
                session["play_count"] += 1
            if action == "complete":
                session["completed"] = True
            active_ms = max(0, int(row["duration_ms"] or 0))
            session["total_active_ms"] += active_ms
            session["max_progress_pct"] = max(
                session["max_progress_pct"],
                int(properties.get("progress_pct") or 0),
            )
            session["last_event_at_ms"] = max(
                session["last_event_at_ms"],
                int(row["occurred_at_ms"] or 0),
            )
            section_id = str(row["section"] or "")
            if not section_id:
                continue
            section = session["sections"].setdefault(
                section_id,
                {
                    "section_id": section_id,
                    "section_index": int(
                        properties.get("section_index") or 0
                    ),
                    "section_label": str(
                        properties.get("section_label") or ""
                    ),
                    "section_group": str(
                        properties.get("section_group") or ""
                    ),
                    "entered": False,
                    "active_ms": 0,
                    "max_progress_pct": 0,
                    "entry_trigger": "",
                    "section_start_ms": int(
                        properties.get("section_start_ms") or 0
                    ),
                    "section_end_ms": int(
                        properties.get("section_end_ms") or 0
                    ),
                    "watched_intervals": [],
                },
            )
            if action == "section_enter":
                section["entered"] = True
                section["entry_trigger"] = str(
                    properties.get("reason") or ""
                )
            else:
                # Any validated playback transition proves the player reached
                # this section even if a legacy client missed section_enter.
                section["entered"] = True
                if action == "seek":
                    # The real runtime emits one canonical seek transition for
                    # both scrub and section-chip jumps. Do not require a
                    # synthetic second section_enter event to recover source.
                    section["entry_trigger"] = str(
                        properties.get("reason") or ""
                    )
            section["active_ms"] += active_ms
            section["max_progress_pct"] = max(
                section["max_progress_pct"],
                int(properties.get("section_progress_pct") or 0),
            )
            if action == "checkpoint" and active_ms > 0:
                section_start = int(section["section_start_ms"])
                section_end = int(section["section_end_ms"])
                interval_start = max(
                    section_start,
                    int(properties.get("from_position_ms") or 0),
                )
                interval_end = min(
                    section_end,
                    int(properties.get("to_position_ms") or 0),
                )
                if interval_end > interval_start:
                    section["watched_intervals"].append(
                        (interval_start, interval_end)
                    )

        content_buckets: dict[str, dict[str, Any]] = {}
        section_buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for session in sessions.values():
            for section in session["sections"].values():
                intervals = sorted(section["watched_intervals"])
                covered_ms = 0
                covered_end = 0
                for interval_start, interval_end in intervals:
                    if covered_ms == 0:
                        covered_end = interval_end
                        covered_ms = interval_end - interval_start
                    elif interval_start <= covered_end:
                        if interval_end > covered_end:
                            covered_ms += interval_end - covered_end
                            covered_end = interval_end
                    else:
                        covered_end = interval_end
                        covered_ms += interval_end - interval_start
                section["unique_covered_ms"] = covered_ms
                section_duration = max(
                    0,
                    int(section["section_end_ms"])
                    - int(section["section_start_ms"]),
                )
                section["watched"] = (
                    section_duration > 0
                    and covered_ms * 10 >= section_duration * 9
                    and int(section["max_progress_pct"]) >= 90
                )
            watched_indexes = {
                int(section["section_index"])
                for section in session["sections"].values()
                if int(section["section_index"]) > 0
                and section["watched"]
            }
            contiguous_index = 0
            while contiguous_index + 1 in watched_indexes:
                contiguous_index += 1
            reached_index = max(
                (
                    int(section["section_index"])
                    for section in session["sections"].values()
                ),
                default=0,
            )
            content = content_buckets.setdefault(
                session["object_id"],
                {
                    "object_id": session["object_id"],
                    "members": set(),
                    "sessions": 0,
                    "play_count": 0,
                    "completed_sessions": 0,
                    "total_active_ms": 0,
                    "progress_25_sessions": 0,
                    "progress_50_sessions": 0,
                    "progress_75_sessions": 0,
                    "progress_90_sessions": 0,
                    "max_reached_section_index": 0,
                    "max_contiguous_watched_section_index": 0,
                    "last_event_at_ms": 0,
                },
            )
            content["members"].add(session["user_id"])
            content["sessions"] += 1
            content["play_count"] += session["play_count"]
            content["completed_sessions"] += int(session["completed"])
            content["total_active_ms"] += session["total_active_ms"]
            for checkpoint in (25, 50, 75, 90):
                if session["max_progress_pct"] >= checkpoint:
                    content[f"progress_{checkpoint}_sessions"] += 1
            content["max_reached_section_index"] = max(
                content["max_reached_section_index"], reached_index
            )
            content["max_contiguous_watched_section_index"] = max(
                content["max_contiguous_watched_section_index"],
                contiguous_index,
            )
            content["last_event_at_ms"] = max(
                content["last_event_at_ms"], session["last_event_at_ms"]
            )

            for section in session["sections"].values():
                key = (session["object_id"], section["section_id"])
                bucket = section_buckets.setdefault(
                    key,
                    {
                        "object_id": session["object_id"],
                        "section_id": section["section_id"],
                        "section_index": section["section_index"],
                        "section_label": section["section_label"],
                        "section_group": section["section_group"],
                        "members": set(),
                        "sessions": 0,
                        "watched_sessions": 0,
                        "total_active_ms": 0,
                        "auto_entries": 0,
                        "seek_entries": 0,
                        "chip_entries": 0,
                    },
                )
                bucket["members"].add(session["user_id"])
                bucket["sessions"] += 1
                watched = bool(section["watched"])
                bucket["watched_sessions"] += int(watched)
                bucket["total_active_ms"] += int(section["active_ms"])
                trigger = str(section["entry_trigger"] or "")
                if trigger == "auto":
                    bucket["auto_entries"] += 1
                elif trigger == "chip":
                    bucket["chip_entries"] += 1
                elif trigger in {"scrub", "seek"}:
                    bucket["seek_entries"] += 1

        content_rows = []
        for bucket in content_buckets.values():
            session_count = int(bucket.pop("sessions"))
            members = bucket.pop("members")
            completed = int(bucket["completed_sessions"])
            content_rows.append(
                {
                    **bucket,
                    "member_count": len(members),
                    "playback_session_count": session_count,
                    "completion_rate": (
                        round(completed / session_count, 4)
                        if session_count
                        else None
                    ),
                    "avg_active_ms": (
                        int(bucket["total_active_ms"] / session_count)
                        if session_count
                        else 0
                    ),
                }
            )
        content_rows.sort(
            key=lambda row: (
                row["playback_session_count"],
                row["total_active_ms"],
            ),
            reverse=True,
        )
        section_rows = []
        for bucket in section_buckets.values():
            session_count = int(bucket.pop("sessions"))
            members = bucket.pop("members")
            watched = int(bucket["watched_sessions"])
            section_rows.append(
                {
                    **bucket,
                    "member_count": len(members),
                    "reached_session_count": session_count,
                    "watched_rate": (
                        round(watched / session_count, 4)
                        if session_count
                        else None
                    ),
                }
            )
        section_rows.sort(
            key=lambda row: (
                row["object_id"],
                int(row["section_index"]),
                row["section_id"],
            )
        )
        safe_limit = max(1, int(limit or 50))
        return {
            "available": bool(rows),
            "time_source": "player_active_time",
            "trust_level": "C",
            "evidence_class": "server_validated_client_playback_claim",
            "mastery_eligible": False,
            "use_boundary": "product_interest_only",
            "event_count": len(rows),
            "playback_session_count": len(sessions),
            "content": content_rows[:safe_limit],
            "sections": section_rows[: safe_limit * 20],
        }

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
