"""Tests for tutorbot turn-outcome replay (walking skeleton, offline)."""

from __future__ import annotations

import json

import pytest

from deeptutor.services.benchmark.tutorbot_turn_replay import (
    OutcomeMismatch,
    TurnOutcome,
    diff_outcomes,
    load_tutorbot_outcomes,
    outcome_summary,
)
from deeptutor.services.observability.turn_event_log import (
    TurnEventLog,
    reset_turn_event_log,
)


def _event(
    turn_id="t1",
    capability="tutorbot",
    status="completed",
    error_type="",
    retrieval_hit=None,
    latency_ms=120.0,
    token_total=900,
) -> dict:
    return {
        "type": "turn_observation",
        "timestamp": 1.0,
        "session_id": "s1",
        "turn_id": turn_id,
        "trace_id": "tr1",
        "capability": capability,
        "status": status,
        "error_type": error_type,
        "retrieval_hit": retrieval_hit,
        "latency_ms": latency_ms,
        "token_total": token_total,
        "route": "",
        "surface": "",
        "user_id": "",
        "release": {},
        "metadata": {},
    }


@pytest.fixture
def isolated_log(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    reset_turn_event_log(events_dir=events_dir)
    log = TurnEventLog(events_dir=events_dir)
    yield log
    reset_turn_event_log()  # restore default for other tests


def test_load_filters_to_tutorbot_capability(isolated_log) -> None:
    isolated_log.append(_event(turn_id="t1", capability="tutorbot"))
    isolated_log.append(_event(turn_id="t2", capability="chat"))
    isolated_log.append(_event(turn_id="t3", capability="tutorbot", status="cancelled"))
    outcomes = load_tutorbot_outcomes(log=isolated_log)
    assert {o.turn_id for o in outcomes} == {"t1", "t3"}
    s = outcome_summary(outcomes)
    assert s["total"] == 2 and s["by_status"] == {"completed": 1, "cancelled": 1}


def test_diff_outcomes_strict_correctness_fields() -> None:
    base = TurnOutcome.from_event(_event(turn_id="t1", status="completed"))
    cand_status_drift = TurnOutcome.from_event(_event(turn_id="t1", status="cancelled"))
    diffs = diff_outcomes(base, cand_status_drift)
    assert any(d.field == "status" for d in diffs)


def test_diff_outcomes_latency_within_tolerance_is_no_diff() -> None:
    base = TurnOutcome.from_event(_event(latency_ms=1000.0))
    cand = TurnOutcome.from_event(_event(latency_ms=2400.0))  # 1400ms < 1500 tol
    assert diff_outcomes(base, cand) == []


def test_diff_outcomes_latency_beyond_tolerance_flagged() -> None:
    base = TurnOutcome.from_event(_event(latency_ms=1000.0))
    cand = TurnOutcome.from_event(_event(latency_ms=3000.0))  # 2000ms drift > 1500
    diffs = diff_outcomes(base, cand)
    assert any(d.field == "latency_ms" for d in diffs)


def test_diff_outcomes_token_ratio_drift_flagged() -> None:
    base = TurnOutcome.from_event(_event(token_total=1000))
    cand = TurnOutcome.from_event(_event(token_total=1500))  # 50% drift > 30%
    diffs = diff_outcomes(base, cand)
    assert any(d.field == "token_total" for d in diffs)
