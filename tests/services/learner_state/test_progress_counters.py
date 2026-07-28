from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from deeptutor.services.learner_state.progress_counters import (
    build_progress_counters,
    build_progress_counters_patch,
    write_progress_counters,
)

_TZ = timezone(timedelta(hours=8))


def _now_iso(*, days_ago: int = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


@dataclass
class _Event:
    event_id: str
    dedupe_key: str
    payload_json: dict[str, Any]
    memory_kind: str = "learning_evidence"
    source_feature: str = "first_run_diagnostic"
    source_id: str = ""
    created_at: str = field(default_factory=_now_iso)


def _evidence(
    index: int,
    *,
    days_ago: int = 0,
    payload: dict[str, Any] | None = None,
    source_feature: str = "first_run_diagnostic",
) -> _Event:
    body = {"event_type": "learning_evidence", "question_id": f"q{index}"}
    body.update(payload or {})
    return _Event(
        event_id=f"evt_{index}",
        dedupe_key=f"dedupe_{index}",
        payload_json=body,
        source_feature=source_feature,
        created_at=_now_iso(days_ago=days_ago),
    )


def test_counters_derive_totals_today_and_last_practiced_at() -> None:
    events = [_evidence(1, days_ago=3), _evidence(2), _evidence(3)]

    counters = build_progress_counters(events)

    assert counters["total_attempts"] == 3
    assert counters["today_done"] == 2
    assert counters["last_practiced_at"] == max(event.created_at for event in events)


def test_counters_are_derived_not_accumulated_so_replay_is_stable() -> None:
    events = [_evidence(1), _evidence(2)]

    assert build_progress_counters(events) == build_progress_counters(events)


def test_replicated_rows_count_once_but_sibling_items_stay_distinct() -> None:
    """本地/远端同一条证据算一次；同一次完成的不同题目各算一次。

    反向红线：不能用 completion_id 去重——first_run 一次完成的 N 道题共享它。
    """
    one = _evidence(1, payload={"completion_id": "c-1"})
    same_row_replica = deepcopy(one)
    same_row_replica.event_id = "evt_remote_1"
    sibling = _evidence(2, payload={"completion_id": "c-1"})

    counters = build_progress_counters([one, same_row_replica, sibling])

    assert counters["total_attempts"] == 2


def test_non_countable_rows_are_excluded() -> None:
    events = [
        _evidence(1),
        _evidence(2, payload={"evidence_source": "conversation_synthesis"}),
        _evidence(3, payload={"quality": {"progress_countable": False}}),
        _evidence(4, payload={"completion_terminal": True, "retest_completion_id": "r-1"}),
        _Event(
            event_id="evt_5",
            dedupe_key="dedupe_5",
            payload_json={"event_type": "chat_summary"},
            memory_kind="summary",
        ),
    ]

    assert build_progress_counters(events)["total_attempts"] == 1


def test_missing_or_future_timestamps_do_not_inflate_counts() -> None:
    broken = _evidence(1)
    broken.created_at = ""
    future = _evidence(2)
    future.created_at = (datetime.now(_TZ) + timedelta(days=1)).isoformat()

    counters = build_progress_counters([broken, future, _evidence(3)])

    assert counters["total_attempts"] == 1
    assert counters["today_done"] == 1


def test_patch_is_monotonic_and_deep_merge_shaped() -> None:
    events = [_evidence(1), _evidence(2)]

    patch = build_progress_counters_patch(
        events,
        existing_progress={
            "total_attempts": 9,
            "last_practiced_at": "2099-01-01T00:00:00+08:00",
            "today": {"today_done": 7, "daily_target": 30},
        },
    )

    assert patch["total_attempts"] == 9
    assert patch["last_practiced_at"] == "2099-01-01T00:00:00+08:00"
    assert patch["today"] == {"today_done": 7}
    assert set(patch) <= {"total_attempts", "last_practiced_at", "today"}


def test_empty_ledger_writes_nothing() -> None:
    assert build_progress_counters_patch([], existing_progress={}) == {}


class _FakeService:
    def __init__(self, events: list[_Event], progress: dict[str, Any] | None = None) -> None:
        self.events = events
        self.progress: dict[str, Any] = dict(progress or {})
        self.merge_calls = 0

    def list_memory_events(self, user_id: str, limit: int | None = 20) -> list[_Event]:
        assert user_id == "user-1"
        events = list(self.events)
        if limit is None or limit < 0:
            return events
        return events[-limit:]

    def read_progress(self, user_id: str) -> dict[str, Any]:
        return deepcopy(self.progress)

    def merge_progress(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.merge_calls += 1
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(self.progress.get(key), dict):
                self.progress[key] = {**self.progress[key], **value}
            else:
                self.progress[key] = value
        return deepcopy(self.progress)


def test_write_projects_counters_into_progress_without_touching_other_keys() -> None:
    service = _FakeService(
        [_evidence(1), _evidence(2)],
        progress={"today": {"today_done": 0, "daily_target": 30}, "chapters": [{"done": 0}]},
    )

    patch = write_progress_counters(service, user_id="user-1")

    assert patch["total_attempts"] == 2
    assert service.progress["today"] == {"today_done": 2, "daily_target": 30}
    assert service.progress["chapters"] == [{"done": 0}]


def test_write_is_idempotent_across_repeated_calls() -> None:
    service = _FakeService([_evidence(1), _evidence(2)])

    write_progress_counters(service, user_id="user-1")
    write_progress_counters(service, user_id="user-1")

    assert service.merge_calls == 2
    assert service.progress["total_attempts"] == 2
    assert service.progress["today"] == {"today_done": 2}


def test_write_degrades_quietly_when_service_cannot_serve_it() -> None:
    class _Bare:
        pass

    assert write_progress_counters(_Bare(), user_id="user-1") == {}
    assert write_progress_counters(_FakeService([]), user_id="") == {}
