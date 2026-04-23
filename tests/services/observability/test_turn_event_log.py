from __future__ import annotations

from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import build_turn_observation_event


def test_turn_event_log_appends_and_loads_events(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    event = build_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        trace_id="trace-1",
        status="completed",
        capability="chat",
        latency_ms=1234.0,
        surface="web",
        user_id="user-1",
    )

    event_log.append(event)

    loaded = event_log.load_events()
    assert len(loaded) == 1
    assert loaded[0]["type"] == "turn_observation"
    assert loaded[0]["turn_id"] == "turn-1"
    assert loaded[0]["status"] == "completed"
    assert event_log.stats()["today_events"] == 1
    assert event_log.stats()["last_write_error"] == ""
    assert event_log.stats()["append_success_total"] == 1
    assert event_log.stats()["append_failure_total"] == 0


def test_turn_event_log_append_failure_is_visible(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)

    assert event_log.append({"bad": object()}) is False

    stats = event_log.stats()
    assert stats["today_events"] == 0
    assert "TypeError" in stats["last_write_error"]
    assert stats["append_success_total"] == 0
    assert stats["append_failure_total"] == 1


def test_turn_observation_event_keeps_release_spine() -> None:
    event = build_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        release={"release_id": "rel-1", "git_sha": "abc"},
    )

    assert event["release"]["release_id"] == "rel-1"
    assert event["release"]["git_sha"] == "abc"
