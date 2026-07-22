from __future__ import annotations

from pathlib import Path
import sqlite3
import time

import pytest

from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore


def test_store_dedupes_events_and_builds_member_summary(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    event = {
        "event_id": "evt-1",
        "event_name": "module_viewed",
        "event_version": 1,
        "occurred_at_ms": now_ms,
        "received_at_ms": now_ms + 100,
        "user_id": "u1",
        "visit_id": "visit-1",
        "session_id": "",
        "turn_id": "",
        "surface": "web",
        "module": "learning_report",
        "section": "",
        "action": "view",
        "properties_json": {"module": "learning_report"},
    }

    assert store.record_event(event)["status"] == "accepted"
    assert store.record_event(event)["status"] == "duplicate"

    summary = store.get_member_behavior_summary("u1", days=7)
    assert summary["learning_report_open_count_7d"] == 1
    assert summary["history_open_count_7d"] == 0
    assert summary["trust_level"] == "B"


def _record(store: SQLiteProductBehaviorStore, **overrides) -> None:
    """record_event 从 properties_json 读维度字段（与 surface_events ingest 同路径），
    故 object_type/object_id/result 等必须放进 properties_json，不能只放顶层。"""
    now_ms = int(time.time() * 1000)
    dims = {
        key: overrides.pop(key)
        for key in ("object_type", "object_id", "result", "practice_mode", "visible_ms", "duration_ms")
        if key in overrides
    }
    properties = {"object_type": "microlesson", "object_id": "F16:tp1:1", **dims}
    base = {
        "event_id": overrides.pop("event_id"),
        "event_name": "learning_action_started",
        "event_version": 1,
        "occurred_at_ms": now_ms,
        "received_at_ms": now_ms + 10,
        "user_id": "u1",
        "visit_id": "visit-1",
        "session_id": "",
        "turn_id": "",
        "surface": "wechat_yousenwebview",
        "module": "learning",
        "section": "",
        "action": "open_detail",
        "properties_json": properties,
    }
    base.update(overrides)
    store.record_event(base)


def test_data_quality_snapshot_collapses_identity_groups_and_excludes_internal_ids(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(
        store,
        event_id="legacy",
        user_id="legacy-u1",
        app_version="ignored-top-level",
        properties_json={"app_version": "1.2.3", "platform": "ios"},
    )
    _record(
        store,
        event_id="canonical",
        user_id="canonical-u1",
        properties_json={"app_version": "1.2.3", "platform": "ios"},
    )
    _record(
        store,
        event_id="internal",
        user_id="machine-uuid",
        properties_json={"app_version": "1.2.3", "platform": "devtools"},
    )

    snapshot = store.get_data_quality_snapshot(
        days=7,
        identity_groups={
            "member-1": ["legacy-u1", "canonical-u1"],
            "internal": ["machine-uuid"],
        },
        exclude_user_ids=["machine-uuid"],
    )

    assert snapshot["available"] is True
    assert snapshot["status"] == "ready"
    assert snapshot["event_count"] == 2
    assert snapshot["user_count"] == 1
    assert snapshot["last_event_at_ms"] > 0
    assert snapshot["coverage"]["release_id"]["coverage_rate"] == 0.0
    assert snapshot["coverage"]["app_version"]["coverage_rate"] == 1.0
    assert snapshot["coverage"]["platform"]["coverage_rate"] == 1.0


def test_data_quality_snapshot_is_empty_or_degraded_without_version_evidence(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    assert store.get_data_quality_snapshot(days=7)["status"] == "empty"

    _record(store, event_id="missing-metadata", user_id="u1")
    snapshot = store.get_data_quality_snapshot(days=7)

    assert snapshot["status"] == "degraded"
    assert snapshot["event_count"] == 1
    assert snapshot["user_count"] == 1
    assert snapshot["coverage"]["app_version"]["populated_event_count"] == 0


def test_data_quality_snapshot_reports_store_unavailability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")

    def fail_connect():
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(store, "_connect", fail_connect)
    snapshot = store.get_data_quality_snapshot(days=7)

    assert snapshot["available"] is False
    assert snapshot["status"] == "unavailable"
    assert snapshot["event_count"] == 0


def test_engagement_breakdown_ranks_content_and_computes_repeat_rate(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    # 微课 A：u1 看 2 次(不同 visit) + u2 看 1 次 → members=2, events=3, repeat=1.5
    _record(store, event_id="a1", user_id="u1", visit_id="v1", object_id="F16:tp1:1")
    _record(store, event_id="a2", user_id="u1", visit_id="v2", object_id="F16:tp1:1")
    _record(store, event_id="a3", user_id="u2", visit_id="v3", object_id="F16:tp1:1")
    # 微课 B：u1 看 1 次 → members=1, events=1
    _record(store, event_id="b1", user_id="u1", visit_id="v1", object_id="F16:tp2:1")
    # 考点卡（另一 object_type，也是学习内容）
    _record(store, event_id="c1", user_id="u2", visit_id="v3", object_type="concept_card", object_id="card-9")

    content = store.get_engagement_breakdown(
        group_dim="object_id",
        object_types=["microlesson", "concept_card"],
        days=7,
    )
    top = content[0]
    assert top["key"] == "F16:tp1:1"
    assert top["object_type"] == "microlesson"
    assert top["member_count"] == 2
    assert top["visit_count"] == 3
    assert top["event_count"] == 3
    assert top["repeat_rate"] == 1.5
    assert top["total_dwell_ms"] == 0
    assert top["dwell_event_count"] == 0
    assert top["last_event_at_ms"] > 0
    # 按 member_count 降序：微课 A(2) 在考点卡(1)/微课 B(1) 之前
    assert content[0]["member_count"] >= content[1]["member_count"]


def test_engagement_breakdown_returns_complete_video_dwell_evidence(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(store, event_id="view", object_id="F16:tp:1")
    _record(store, event_id="exit-1", event_name="module_exited", object_id="F16:tp:1", visible_ms=30_000)
    _record(store, event_id="exit-2", event_name="module_exited", object_id="F16:tp:1", duration_ms=90_000)

    row = store.get_engagement_breakdown(group_dim="object_id", days=7)[0]

    assert row["total_dwell_ms"] == 120_000
    assert row["avg_dwell_ms"] == 60_000
    assert row["dwell_event_count"] == 2
    assert row["start_count"] == 1
    assert row["selection_count"] == 1
    assert row["content_open_count"] == 0
    assert row["exit_count"] == 2
    assert row["view_count"] == 0
    assert row["last_event_at_ms"] > 0


def test_engagement_breakdown_separates_episode_selection_from_content_open(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(store, event_id="selected", object_id="F16:tp:1", action="open_detail")
    _record(store, event_id="opened", object_id="F16:tp:1", action="start_training")

    row = store.get_engagement_breakdown(group_dim="object_id", days=7)[0]

    assert row["event_count"] == 2
    assert row["start_count"] == 2
    assert row["selection_count"] == 1
    assert row["content_open_count"] == 1
    assert row["engaged_member_count"] == 1
    assert row["meaningful_visit_count"] == 1
    assert row["repeat_user_count"] == 0
    assert row["repeat_user_rate"] == 0.0


def test_engagement_breakdown_repeat_rate_uses_distinct_meaningful_visits(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(store, event_id="select-1", object_id="F16:tp:1", action="open_detail", visit_id="list-1")
    _record(store, event_id="open-1", object_id="F16:tp:1", action="start_training", visit_id="station-1")
    _record(store, event_id="exit-1", event_name="module_exited", object_id="F16:tp:1", visit_id="station-1")
    _record(store, event_id="select-2", object_id="F16:tp:1", action="open_detail", visit_id="list-2")
    _record(store, event_id="open-2", object_id="F16:tp:1", action="start_training", visit_id="station-2")

    row = store.get_engagement_breakdown(group_dim="object_id", days=7)[0]

    assert row["event_count"] == 5
    assert row["engaged_member_count"] == 1
    assert row["meaningful_visit_count"] == 2
    assert row["repeat_user_count"] == 1
    assert row["repeat_user_rate"] == 1.0


def test_engagement_breakdown_orders_content_by_effective_open_not_raw_density(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    for index in range(4):
        _record(
            store,
            event_id=f"noisy-{index}",
            event_name="module_exited",
            object_id="noisy:tp:1",
            user_id=f"u-{index}",
        )
    _record(
        store,
        event_id="opened",
        object_id="opened:tp:1",
        action="start_training",
    )

    rows = store.get_engagement_breakdown(
        group_dim="object_id", order_by="engagement_count", days=7
    )

    assert rows[0]["key"] == "opened:tp:1"
    assert rows[0]["engagement_count"] == 1
    assert rows[1]["event_count"] == 4
    assert rows[1]["engagement_count"] == 0


def test_engagement_breakdown_treats_station_view_as_meaningful_visit(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(
        store,
        event_id="station-view",
        event_name="module_viewed",
        object_type="station",
        object_id="A01",
        action="view",
    )

    row = store.get_engagement_breakdown(group_dim="object_type", days=7)[0]

    assert row["key"] == "station"
    assert row["engaged_member_count"] == 1
    assert row["meaningful_visit_count"] == 1


def test_engagement_breakdown_counts_event_error_failures(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(
        store,
        event_id="assessment-error",
        event_name="event_error",
        object_type="quiz",
        object_id="quiz-1",
        module="assessment",
        action="submit",
        result="fail",
    )

    row = store.get_engagement_breakdown(group_dim="module", days=7)[0]

    assert row["error_count"] == 1


def test_engagement_breakdown_computes_practice_accuracy(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    for idx, result in enumerate(["correct", "correct", "incorrect"]):
        _record(
            store,
            event_id=f"p{idx}",
            event_name="retest_item_answered",
            module="practice",
            action="complete",
            object_type="variant",
            object_id=f"var-{idx}",
            result=result,
            practice_mode="review",
        )
    rows = store.get_engagement_breakdown(
        group_dim="object_type", event_names=["retest_item_answered"], days=7
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["key"] == "variant"
    assert row["answered_count"] == 3
    assert row["correct_count"] == 2
    assert row["accuracy"] == round(2 / 3, 4)


def test_engagement_breakdown_user_ids_filter_scopes_to_one_member(tmp_path: Path) -> None:
    """单会员行为明细 §7：user_ids 是 inclusive 白名单，收窄到指定用户，
    与全局视图共享同一个聚合函数(不新建"单用户行为"的第二套聚合)。"""
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(store, event_id="a1", user_id="u-a", object_id="F16:tp1:1", module="learning")
    _record(store, event_id="a2", user_id="u-a", object_id="F16:tp2:1", module="learning")
    _record(store, event_id="b1", user_id="u-b", object_id="F16:tp1:1", module="learning")

    # 全局视图(无过滤): F16:tp1:1 触达2人(u-a+u-b), F16:tp2:1 触达1人
    all_rows = store.get_engagement_breakdown(group_dim="object_id", days=7)
    assert {r["key"]: r["member_count"] for r in all_rows} == {"F16:tp1:1": 2, "F16:tp2:1": 1}

    # 单会员视图: 只看 u-a，两个内容各1次，u-b 的事件不计入
    u_a_rows = store.get_engagement_breakdown(group_dim="object_id", days=7, user_ids=["u-a"])
    assert {r["key"]: r["event_count"] for r in u_a_rows} == {"F16:tp1:1": 1, "F16:tp2:1": 1}
    assert all(r["member_count"] == 1 for r in u_a_rows)

    # 按 module 维度收窄到单会员("每个模块点了多少次")
    module_rows = store.get_engagement_breakdown(group_dim="module", days=7, user_ids=["u-a"])
    assert {r["key"]: r["event_count"] for r in module_rows} == {"learning": 2}


def test_engagement_breakdown_supports_module_dim(tmp_path: Path) -> None:
    """全模块偏好("产品功能偏好")：group_dim=module 按模块聚合所有被监测模块。"""
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(store, event_id="l1", user_id="u1", module="learning")
    _record(store, event_id="l2", user_id="u2", module="learning")
    _record(store, event_id="c1", user_id="u1", module="chat")
    _record(store, event_id="f1", user_id="u1", module="first_run", event_name="first_run_started")
    rows = store.get_engagement_breakdown(group_dim="module", days=7)
    keys = {r["key"]: r["member_count"] for r in rows}
    assert keys["learning"] == 2  # 两个独立用户
    assert keys["chat"] == 1
    assert keys["first_run"] == 1
    # 按触达降序：learning(2) 在最前
    assert rows[0]["key"] == "learning"


def test_engagement_breakdown_excludes_demo_cohort_by_prefix(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    _record(store, event_id="real1", user_id="u-real", object_id="F16:tp1:1")
    _record(store, event_id="demo1", user_id="eval_demo_1", object_id="F16:tp1:1")
    _record(store, event_id="demo2", user_id="qa_eval_seed", object_id="F16:tp1:1")

    with_demo = store.get_engagement_breakdown(group_dim="object_id", days=7)
    assert with_demo[0]["member_count"] == 3

    without_demo = store.get_engagement_breakdown(
        group_dim="object_id", days=7, exclude_user_id_prefixes=("qa_eval_", "eval_", "qa_")
    )
    assert without_demo[0]["member_count"] == 1


def test_store_builds_learning_report_section_breakdown(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for index, section in enumerate(["next_action", "next_action", "evidence"]):
        store.record_event(
            {
                "event_id": f"evt-section-{index}",
                "event_name": "section_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + 100 + index,
                "user_id": "u1",
                "visit_id": "visit-1",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "learning_report",
                "section": section,
                "action": "view",
                "properties_json": {"section": section},
            }
        )

    breakdown = store.get_learning_report_section_breakdown("u1", days=7)
    assert breakdown[0] == {"section": "next_action", "view_count": 2}
    assert breakdown[1] == {"section": "evidence", "view_count": 1}


def test_store_detects_report_high_no_action_cohort(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for index in range(3):
        store.record_event(
            {
                "event_id": f"evt-report-{index}",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + 100 + index,
                "user_id": "u1",
                "visit_id": f"visit-{index}",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "learning_report",
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    assert store.get_member_behavior_summary("u1", days=7)["cohort"] == "report_high_no_action"


def test_store_detects_p0_member_behavior_cohorts_with_reasons(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)

    scenarios = [
        ("history_user", "history", "module_viewed", "view", 3, "history_high_no_review"),
        ("chat_user", "chat", "module_viewed", "view", 3, "chat_only"),
        ("training_user", "practice", "learning_action_started", "start_training", 1, "training_no_retest"),
    ]
    for user_id, module, event_name, action, count, _expected in scenarios:
        for index in range(count):
            store.record_event(
                {
                    "event_id": f"evt-{user_id}-{index}",
                    "event_name": event_name,
                    "event_version": 1,
                    "occurred_at_ms": now_ms + index,
                    "received_at_ms": now_ms + 100 + index,
                    "user_id": user_id,
                    "visit_id": f"visit-{user_id}-{index}",
                    "session_id": "",
                    "turn_id": "",
                    "surface": "web",
                    "module": module,
                    "section": "",
                    "action": action,
                    "properties_json": {},
                }
            )

    summaries = store.get_member_behavior_summaries([item[0] for item in scenarios], days=7)

    for user_id, _module, _event_name, _action, _count, expected in scenarios:
        assert summaries[user_id]["cohort"] == expected
        assert summaries[user_id]["next_action"]
        assert summaries[user_id]["cohort_reasons"]


def test_store_uses_occurred_at_for_offline_replay_window(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for event_id, occurred_at_ms in [
        ("evt-replay-3d", now_ms - 3 * 86400 * 1000),
        ("evt-replay-10d", now_ms - 10 * 86400 * 1000),
    ]:
        store.record_event(
            {
                "event_id": event_id,
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": occurred_at_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "visit-replay",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "history",
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    summary = store.get_member_behavior_summary("u1", days=7)
    assert summary["history_open_count_7d"] == 1


def test_member_timeline_respects_days_window(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for event_id, occurred_at_ms in [
        ("evt-recent", now_ms - 2 * 86400 * 1000),
        ("evt-old", now_ms - 10 * 86400 * 1000),
    ]:
        store.record_event(
            {
                "event_id": event_id,
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": occurred_at_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "visit-window",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "history",
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    timeline = store.get_member_timeline("u1", days=7)

    assert [event["event_id"] for event in timeline] == ["evt-recent"]


def test_store_rejects_forbidden_properties_for_direct_callers(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)

    with pytest.raises(ValueError, match="Forbidden product behavior property"):
        store.record_event(
            {
                "event_id": "evt-forbidden-direct",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "visit-1",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "history",
                "section": "",
                "action": "view",
                "properties_json": {"full_answer_text": "do not store"},
            }
        )


def test_store_rejects_nested_forbidden_properties_for_direct_callers(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)

    with pytest.raises(ValueError, match="Forbidden product behavior property"):
        store.record_event(
            {
                "event_id": "evt-forbidden-nested-direct",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "visit-1",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "history",
                "section": "",
                "action": "view",
                "properties_json": {"extra": {"complete_subjective_answer": "do not store"}},
            }
        )


def test_store_builds_batch_member_summaries_with_one_query_shape(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for user_id, module in [("u1", "history"), ("u2", "learning_report")]:
        store.record_event(
            {
                "event_id": f"evt-{user_id}",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": user_id,
                "visit_id": f"visit-{user_id}",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": module,
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    summaries = store.get_member_behavior_summaries(["u1", "u2"], days=7)
    assert summaries["u1"]["history_open_count_7d"] == 1
    assert summaries["u2"]["learning_report_open_count_7d"] == 1


def test_store_builds_member_summaries_across_identity_group(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for index, user_id in enumerate(["legacy_u1", "canonical_u1", "canonical_u1"]):
        store.record_event(
            {
                "event_id": f"evt-identity-{index}",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + index,
                "user_id": user_id,
                "visit_id": f"visit-identity-{index}",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "learning_report",
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    summaries = store.get_member_behavior_summaries_for_identity_groups(
        {"member_u1": ["legacy_u1", "canonical_u1"]},
        days=7,
    )

    assert summaries["member_u1"]["learning_report_open_count_7d"] == 3
    assert summaries["member_u1"]["cohort"] == "report_high_no_action"


def test_store_reads_sections_and_timeline_across_identity_group(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for index, (user_id, section) in enumerate(
        [("legacy_u1", "next_action"), ("canonical_u1", "next_action"), ("canonical_u1", "evidence")]
    ):
        store.record_event(
            {
                "event_id": f"evt-group-section-{index}",
                "event_name": "section_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + index,
                "user_id": user_id,
                "visit_id": f"visit-group-section-{index}",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "learning_report",
                "section": section,
                "action": "view",
                "properties_json": {},
            }
        )

    identities = ["legacy_u1", "canonical_u1"]

    sections = store.get_learning_report_section_breakdown_for_identity_group(identities, days=7)
    timeline = store.get_member_timeline_for_identity_group(identities, days=7, limit=10)

    assert sections[0] == {"section": "next_action", "view_count": 2}
    assert sections[1] == {"section": "evidence", "view_count": 1}
    assert [event["event_id"] for event in timeline] == [
        "evt-group-section-2",
        "evt-group-section-1",
        "evt-group-section-0",
    ]


def test_store_persists_and_filters_by_practice_mode(tmp_path: Path) -> None:
    """spike 命门:forward(学习轮当天轻练)/review(复习轮次日复测)必须能从埋点分出——
    否则 D1 留存(GO 门=人次日回来做换皮复测)读不出。practice_mode 落 column 且
    query_raw_events 可按之过滤。"""
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for evt_id, mode in [("evt-fwd", "forward"), ("evt-rev", "review")]:
        assert store.record_event(
            {
                "event_id": evt_id,
                "event_name": "learning_action_completed",
                "event_version": 1,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "v1",
                "session_id": "",
                "turn_id": "",
                "surface": "wechat_yousenwebview",
                "module": "practice",
                "section": "",
                "action": "complete",
                "properties_json": {
                    "object_type": "retest",
                    "object_id": "S05",
                    "result": "3/5",
                    "practice_mode": mode,
                },
            }
        )["status"] == "accepted"

    review_only = store.query_raw_events(
        {"event_name": "learning_action_completed", "practice_mode": "review"}
    )
    assert [e["event_id"] for e in review_only] == ["evt-rev"]
    assert review_only[0]["practice_mode"] == "review"  # column 回读,不靠 JSON 解析
    forward_only = store.query_raw_events({"practice_mode": "forward"})
    assert [e["event_id"] for e in forward_only] == ["evt-fwd"]


def test_default_product_behavior_store_uses_independent_sibling_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from deeptutor.services import observability
    from deeptutor.services.session import sqlite_store

    session_db = tmp_path / "chat_history.db"
    monkeypatch.setattr(
        sqlite_store,
        "get_sqlite_session_store",
        lambda: SimpleNamespace(db_path=session_db),
    )

    store = observability.reset_product_behavior_store()

    assert Path(store.db_path) == tmp_path / "product_behavior.db"
    assert Path(store.db_path) != session_db


def test_store_exposes_first_run_terminal_truth_and_member_module_usage(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)

    events = [
        ("start", "first_run_started", "first_run", "view", "act_war", "", "", 1),
        ("question", "first_run_question_completed", "first_run", "complete", "", "question", "correct", 1),
        ("legacy", "learning_action_completed", "first_run", "complete", "", "script", "go_report", 1),
        ("terminal", "learning_action_completed", "first_run", "complete", "", "script", "synced", 2),
        ("history", "module_viewed", "history", "view", "", "", "", 1),
        ("report", "module_viewed", "learning_report", "view", "", "", "", 1),
        ("training", "learning_action_started", "learning_report", "start_training", "next_action", "", "", 1),
    ]
    for index, (suffix, event_name, module, action, section, object_type, result, version) in enumerate(events):
        store.record_event(
            {
                "event_id": f"evt-{suffix}",
                "event_name": event_name,
                "event_version": version,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + index,
                "user_id": "canonical-u1" if index % 2 else "legacy-u1",
                "visit_id": "visit-u1",
                "session_id": "",
                "turn_id": "",
                "surface": "wechat_yousenwebview",
                "module": module,
                "section": section,
                "action": action,
                "properties_json": {
                    "object_type": object_type,
                    "result": result,
                },
            }
        )

    summary = store.get_member_behavior_summaries_for_identity_groups(
        {"member-u1": ["legacy-u1", "canonical-u1"]},
        days=7,
    )["member-u1"]

    assert summary["first_run_evidence_status"] == "completed"
    assert summary["first_run_question_count"] == 1
    assert summary["first_run_legacy_completion_count"] == 1
    assert summary["top_module_7d"] == "learning_report"
    assert summary["module_usage_7d"][0] == {
        "module": "learning_report",
        "view_count": 1,
        "action_count": 1,
        "completion_count": 0,
        "event_count": 2,
    }


def test_store_builds_real_member_product_usage_overview_without_raw_ledger_leak(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)

    def record(
        event_id: str,
        user_id: str,
        event_name: str,
        module: str,
        action: str,
        *,
        visit_id: str,
        section: str = "",
        object_type: str = "",
        result: str = "",
        event_version: int = 1,
        duration_ms: int = 0,
    ) -> None:
        store.record_event(
            {
                "event_id": event_id,
                "event_name": event_name,
                "event_version": event_version,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": user_id,
                "visit_id": visit_id,
                "session_id": "",
                "turn_id": "",
                "surface": "wechat_yousenwebview",
                "module": module,
                "section": section,
                "action": action,
                "properties_json": {
                    "object_type": object_type,
                    "result": result,
                    "duration_ms": duration_ms,
                },
            }
        )

    record("start-1", "legacy-u1", "first_run_started", "first_run", "view", visit_id="visit-1", section="act_war")
    record("question-1", "canonical-u1", "first_run_question_completed", "first_run", "complete", visit_id="visit-1")
    record(
        "complete-1",
        "canonical-u1",
        "learning_action_completed",
        "first_run",
        "complete",
        visit_id="visit-1",
        object_type="script",
        result="synced",
        event_version=2,
    )
    record("history-view-1", "canonical-u1", "module_viewed", "history", "view", visit_id="visit-1")
    record("history-exit-1", "canonical-u1", "module_exited", "history", "return", visit_id="visit-1", duration_ms=4_000)
    record("history-view-2", "canonical-u2", "module_viewed", "history", "view", visit_id="visit-2")
    record("chat-view", "internal-qa", "module_viewed", "chat", "view", visit_id="qa-visit")

    overview = store.get_product_usage_overview_for_identity_groups(
        {
            "member-u1": ["legacy-u1", "canonical-u1"],
            "member-u2": ["canonical-u2"],
        },
        days=7,
    )

    assert overview["tracked_member_count"] == 2
    assert overview["first_run"] == {
        "started_member_count": 1,
        "eligible_member_count": 2,
        "not_started_member_count": 1,
        "question_member_count": 1,
        "completed_member_count": 1,
        "legacy_completion_member_count": 0,
        "completion_rate": 1.0,
        "completion_rate_of_eligible": 0.5,
    }
    assert overview["module_usage"][0] == {
        "module": "history",
        "member_count": 2,
        "visit_count": 2,
        "view_count": 2,
        "action_count": 0,
        "completion_count": 0,
        "exit_count": 1,
        "quick_exit_count": 1,
    }
    assert all(row["module"] != "chat" for row in overview["module_usage"])


def test_identity_collision_is_excluded_instead_of_double_attributed(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    store.record_event(
        {
            "event_id": "shared-identity-view",
            "event_name": "module_viewed",
            "event_version": 1,
            "occurred_at_ms": now_ms,
            "received_at_ms": now_ms,
            "user_id": "shared-alias",
            "visit_id": "visit-shared",
            "session_id": "",
            "turn_id": "",
            "surface": "wechat_yousenwebview",
            "module": "history",
            "section": "home",
            "action": "view",
            "properties_json": {},
        }
    )
    identity_groups = {
        "member-a": ["member-a", "shared-alias"],
        "member-b": ["member-b", "shared-alias"],
    }

    summaries = store.get_member_behavior_summaries_for_identity_groups(identity_groups, days=7)
    overview = store.get_product_usage_overview_for_identity_groups(identity_groups, days=7)

    assert summaries["member-a"]["event_count_7d"] == 0
    assert summaries["member-b"]["event_count_7d"] == 0
    assert overview["tracked_member_count"] == 0
    assert overview["module_usage"] == []
    assert overview["identity_collision_count"] == 1
    assert overview["identity_collision_member_count"] == 2
    assert summaries["member-a"]["identity_collision_count"] == 1
    assert summaries["member-a"]["trust_level"] == "C"
