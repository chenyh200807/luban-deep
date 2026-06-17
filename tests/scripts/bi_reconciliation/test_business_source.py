from __future__ import annotations

import sqlite3

import httpx

from scripts.bi_reconciliation.business_source import (
    behavior_readings_from_db,
    member_readings_from_supabase,
)

NOW_MS = 1_780_000_000_000  # 锚定测试时钟（ms）
DAY_MS = 86_400_000


def _mk_db() -> sqlite3.Connection:
    """表结构与生产 /root/deeptutor/data/user/product_behavior.db 实拍 DDL 同形（列子集）。"""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE product_behavior_events ("
        " event_id text primary key, event_name text not null,"
        " occurred_at_ms integer not null, user_id text not null,"
        " visit_id text not null, module text not null, section text not null default '')"
    )
    rows = [
        ("e1", "module_viewed", NOW_MS - 1 * DAY_MS, "u1", "v1", "learning", ""),
        ("e2", "module_viewed", NOW_MS - 2 * DAY_MS, "u1", "v1", "history", ""),
        ("e3", "section_viewed", NOW_MS - 1 * DAY_MS, "u2", "v2", "learning_report", "current_state"),
        ("e4", "section_viewed", NOW_MS - 1 * DAY_MS, "u2", "v2", "notebook", "x"),  # 非学情 section
        ("e5", "module_viewed", NOW_MS - 30 * DAY_MS, "u3", "v3", "learning", ""),  # 窗口外
    ]
    conn.executemany("INSERT INTO product_behavior_events VALUES (?,?,?,?,?,?,?)", rows)
    return conn


def test_behavior_counts_respect_window_and_module_filter():
    readings = {r.metric_id: r for r in behavior_readings_from_db(_mk_db(), window_days=7, now_ms=NOW_MS)}
    assert readings["behavior.module.open_count"].value == 2.0
    assert readings["behavior.learning_report.section_view_count"].value == 1.0


def test_derived_behavior_metrics_record_components_not_values():
    readings = {r.metric_id: r for r in behavior_readings_from_db(_mk_db(), window_days=7, now_ms=NOW_MS)}
    funnel = readings["behavior.funnel.report_to_training"]
    assert funnel.value is None
    assert funnel.meta["reason"] == "derived_metric_components_only"
    assert "report_viewers" in funnel.meta["components"]


def test_member_count_from_supabase(monkeypatch):
    def fake_get(self, url, params=None, **kwargs):
        assert "/rest/v1/v_members" in url
        return httpx.Response(
            200, headers={"content-range": "0-0/93"}, json=[{"id": "x"}],
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    readings = member_readings_from_supabase("https://fake.supabase.co", "key", window_days=7)
    by_id = {r.metric_id: r for r in readings}
    assert by_id["registered_members"].value == 93.0
    assert by_id["registered_members"].meta["definition"] == "supabase v_members raw count"
