from __future__ import annotations

import time
from pathlib import Path

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
