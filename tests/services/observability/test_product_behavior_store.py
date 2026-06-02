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
