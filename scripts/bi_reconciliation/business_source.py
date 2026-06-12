"""取数器③：业务库（行为 sqlite + Supabase v_members count，只读）。

行为事件名以 deeptutor.services.observability.product_behavior_catalog 为准
（module_viewed / section_viewed），不发明第二套事件口径。
会员数为 v_members 原始行数；canonical 过滤在 member_console 内部完成、
外部暂不可独立复算（P1 限制，差异由 engine 标 definition_mismatch 后人工复核）。
"""
from __future__ import annotations

import sqlite3
from typing import Any

import httpx

from scripts.bi_reconciliation.types import SOURCE_BUSINESS, SourceReading

_DAY_MS = 86_400_000


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> float:
    row = conn.execute(sql, params).fetchone()
    return float(row[0] if row else 0)


def behavior_readings_from_db(
    conn: sqlite3.Connection, window_days: int, now_ms: int
) -> list[SourceReading]:
    cutoff = now_ms - window_days * _DAY_MS
    module_opens = _count(
        conn,
        "SELECT COUNT(*) FROM product_behavior_events"
        " WHERE event_name = 'module_viewed' AND occurred_at_ms >= ?",
        (cutoff,),
    )
    report_section_views = _count(
        conn,
        "SELECT COUNT(*) FROM product_behavior_events"
        " WHERE event_name = 'section_viewed' AND module = 'learning_report'"
        " AND occurred_at_ms >= ?",
        (cutoff,),
    )
    report_viewers = _count(
        conn,
        "SELECT COUNT(DISTINCT user_id) FROM product_behavior_events"
        " WHERE module = 'learning_report' AND occurred_at_ms >= ?",
        (cutoff,),
    )
    training_starters = _count(
        conn,
        "SELECT COUNT(DISTINCT user_id) FROM product_behavior_events"
        " WHERE event_name = 'learning_action_started' AND occurred_at_ms >= ?",
        (cutoff,),
    )
    components = {
        "report_viewers": report_viewers,
        "training_starters": training_starters,
    }
    return [
        SourceReading(
            "behavior.module.open_count", SOURCE_BUSINESS, module_opens, window_days,
            {"event_name": "module_viewed"},
        ),
        SourceReading(
            "behavior.learning_report.section_view_count", SOURCE_BUSINESS,
            report_section_views, window_days,
            {"event_name": "section_viewed", "module": "learning_report"},
        ),
        SourceReading(
            "behavior.funnel.report_to_training", SOURCE_BUSINESS, None, window_days,
            {"reason": "derived_metric_components_only", "components": components},
        ),
        SourceReading(
            "behavior.member_ops.report_high_no_action", SOURCE_BUSINESS, None, window_days,
            {"reason": "derived_metric_components_only", "components": components},
        ),
        SourceReading(
            "notebook_saves", SOURCE_BUSINESS,
            _count(
                conn,
                "SELECT COUNT(*) FROM product_behavior_events"
                " WHERE event_name = 'note_card_saved' AND occurred_at_ms >= ?",
                (cutoff,),
            ),
            window_days,
            {"event_name": "note_card_saved"},
        ),
    ]


def member_readings_from_supabase(
    rest_url: str, service_key: str, window_days: int
) -> list[SourceReading]:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Prefer": "count=exact",
        "Range": "0-0",
    }
    with httpx.Client(headers=headers, timeout=30) as client:
        resp = client.get(
            f"{rest_url.rstrip('/')}/rest/v1/v_members", params={"select": "id"}
        )
        resp.raise_for_status()
        content_range = resp.headers.get("content-range", "")
        total_text = content_range.split("/")[-1] if "/" in content_range else ""
        total = float(total_text) if total_text.isdigit() else None
    meta: dict[str, Any] = {"definition": "supabase v_members raw count"}
    if total is None:
        meta["reason"] = f"count_unavailable:{content_range or 'no_content_range'}"
    return [SourceReading("registered_members", SOURCE_BUSINESS, total, window_days, meta)]
