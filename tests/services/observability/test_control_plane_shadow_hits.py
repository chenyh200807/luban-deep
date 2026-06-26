"""Deterministic tests for the control-plane shadow-hit observe-only metric.

This metric is OBSERVE-ONLY infra (mirrors Task 1): it does NOT change any
control flow / return value / cap_name / fabricated decision. It reuses the
single terminal turn-observation event (TurnEventLog.append at the one live
turn_runtime callsite) by piggy-backing a structured list on
``metadata["control_plane_shadow_hits"]`` so the report script can count how
often a compat/projection/legacy writer became the operative source in
production.

Two parts under test:
1. emitter — ``_build_terminal_turn_observation_event`` must passthrough the
   ``control_plane_shadow_hits`` key from ``trace_metadata`` into
   ``event["metadata"]`` (whitelist passthrough). RED before the whitelist line.
2. counter — ``scripts/report_control_plane_shadow_hits`` aggregates hits over a
   window, excludes synthetic/test_only events, derives the two gate numbers,
   and exits 0 (clean) / 1 (any hit) / 2 (fail-closed: no data).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability.turn_event_log import (  # noqa: E402
    TurnEventLog,
    build_turn_observation_event,
)
from deeptutor.services.session.turn_runtime import (  # noqa: E402
    _build_terminal_turn_observation_event,
)
from deeptutor.services.observability.turn_event_log import (  # noqa: E402
    INSTRUMENTATION_MARKER_KEY as _INSTRUMENTATION_MARKER_KEY,
    SHADOW_INSTRUMENTATION_VERSION as _INSTRUMENTATION_VERSION,
)
from scripts.report_control_plane_shadow_hits import (  # noqa: E402
    report_control_plane_shadow_hits,
    run_cli,
)


# ---------------------------------------------------------------------------
# Emitter passthrough (RED before the turn_runtime whitelist line is added)
# ---------------------------------------------------------------------------
def test_terminal_event_passes_through_control_plane_shadow_hits() -> None:
    hits = [
        {
            "fact": "legacy_capability_selection",
            "writer_role": "legacy_decider",
            "writer_symbol": "_select_legacy_capability",
            "path": "disabled",
            "canonical_present": False,
        }
    ]
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="deep_question",
        duration_ms=12.0,
        trace_metadata={
            "context_route": "question_followup",
            "control_plane_shadow_hits": hits,
        },
        usage_summary={"total_tokens": 1},
    )
    assert event["metadata"]["control_plane_shadow_hits"] == hits


def test_terminal_event_omits_shadow_hits_when_absent() -> None:
    event = _build_terminal_turn_observation_event(
        session_id="session-1",
        turn_id="turn-1",
        status="completed",
        capability_name="chat",
        duration_ms=12.0,
        trace_metadata={"context_route": "chat"},
        usage_summary={"total_tokens": 1},
    )
    # A clean turn carries NO shadow hits, but MUST carry the unconditional
    # instrumentation marker so the counter can prove coverage (distinguish
    # "verified clean" from "never measured").
    assert "control_plane_shadow_hits" not in event["metadata"]
    assert event["metadata"][_INSTRUMENTATION_MARKER_KEY] == _INSTRUMENTATION_VERSION


def test_canonical_builder_always_stamps_instrumentation_marker() -> None:
    # The marker is stamped unconditionally by the canonical builder for EVERY
    # turn, with or without competing-writer hits.
    event = build_turn_observation_event(
        session_id="s",
        turn_id="t",
        status="completed",
        capability="chat",
    )
    assert event["metadata"][_INSTRUMENTATION_MARKER_KEY] == _INSTRUMENTATION_VERSION


# ---------------------------------------------------------------------------
# Counter helpers
# ---------------------------------------------------------------------------
def _write_event(
    event_log: TurnEventLog,
    *,
    session_id: str,
    shadow_hits: list[dict] | None = None,
    test_only: bool | None = None,
    surface: str = "authenticated_ws",
) -> None:
    """Write a turn via the canonical builder (carries the instrumentation marker)."""
    metadata: dict = {"source": "turn_runtime_terminal"}
    if shadow_hits is not None:
        metadata["control_plane_shadow_hits"] = shadow_hits
    event = build_turn_observation_event(
        session_id=session_id,
        turn_id=f"turn-{session_id}",
        status="completed",
        capability="deep_question",
        surface=surface,
        metadata=metadata,
        test_only=test_only,
        timestamp=time.time(),
    )
    # Coverage invariant: every turn through the canonical builder must carry the
    # instrumentation marker, regardless of whether a competing writer fired.
    assert event["metadata"][_INSTRUMENTATION_MARKER_KEY] == _INSTRUMENTATION_VERSION
    assert event_log.append(event) is True


def _write_predate_event(
    event_log: TurnEventLog,
    *,
    session_id: str,
    shadow_hits: list[dict] | None = None,
) -> None:
    """Write a turn that PREDATES instrumentation: a raw event with NO marker.

    This is the byte-shape of every historical turn logged before this metric
    existed. A clean instrumented turn and a predate turn are otherwise
    indistinguishable (neither carries control_plane_shadow_hits), which is
    exactly the green-by-omission the coverage guard must catch.
    """
    metadata: dict = {"source": "turn_runtime_terminal"}
    if shadow_hits is not None:
        metadata["control_plane_shadow_hits"] = shadow_hits
    raw_event = {
        "type": "turn_observation",
        "timestamp": time.time(),
        "session_id": session_id,
        "turn_id": f"turn-{session_id}",
        "status": "completed",
        "capability": "deep_question",
        "surface": "authenticated_ws",
        "metadata": metadata,
    }
    assert _INSTRUMENTATION_MARKER_KEY not in raw_event["metadata"]
    assert event_log.append(raw_event) is True


_LEGACY_HIT = {
    "fact": "legacy_capability_selection",
    "writer_role": "legacy_decider",
    "writer_symbol": "_select_legacy_capability",
    "path": "disabled",
    "canonical_present": False,
}
_COMPAT_HIT = {
    "fact": "turn_semantic_decision",
    "writer_role": "compat_projection",
    "writer_symbol": "run",
    "path": "deep_question",
    "canonical_present": False,
}


# ---------------------------------------------------------------------------
# Counter behaviour
# ---------------------------------------------------------------------------
def test_counter_empty_window_fails_closed(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 2
    assert report["total_canonical_turns"] == 0
    assert report["legacy_production_decision_hits"] == 0
    assert report["compat_projection_production_reads"] == 0


def test_counter_clean_window_is_green(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="clean-1")
    _write_event(event_log, session_id="clean-2", shadow_hits=[])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 0
    assert report["total_canonical_turns"] == 2
    assert report["instrumented_turns"] == 2
    assert report["legacy_production_decision_hits"] == 0
    assert report["compat_projection_production_reads"] == 0


def test_counter_predate_window_fails_closed_no_coverage(tmp_path) -> None:
    """CRITICAL green-by-omission guard: a window of pre-instrumentation turns
    (no marker) must NOT report green. There are canonical turns, but zero are
    instrumented, so the metric cannot prove anything is clean → exit 2."""
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_predate_event(event_log, session_id="predate-1")
    _write_predate_event(event_log, session_id="predate-2")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 2
    assert report["total_canonical_turns"] == 2
    assert report["instrumented_turns"] == 0
    assert report["legacy_production_decision_hits"] == 0
    assert report["compat_projection_production_reads"] == 0


def test_counter_mixed_predate_and_instrumented_counts_only_instrumented(tmp_path) -> None:
    """When some turns predate instrumentation and some are instrumented-clean,
    coverage is proven (instrumented_turns > 0) so the window can report green;
    instrumented_turns reflects only the marked turns."""
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_predate_event(event_log, session_id="predate-1")
    _write_event(event_log, session_id="instrumented-clean-1")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 0
    assert report["total_canonical_turns"] == 2
    assert report["instrumented_turns"] == 1


def test_counter_predate_hit_still_red(tmp_path) -> None:
    """Defense in depth: even a hit recorded on a (hypothetical) predate-shaped
    event is still a red signal — a recorded competing-writer fire is never
    suppressed by missing the marker."""
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_predate_event(event_log, session_id="predate-hit-1", shadow_hits=[_LEGACY_HIT])
    _write_event(event_log, session_id="instrumented-clean-1")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    assert report["legacy_production_decision_hits"] == 1


def test_counter_legacy_production_hit_is_red(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="legacy-1", shadow_hits=[_LEGACY_HIT])
    _write_event(event_log, session_id="clean-1")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    assert report["legacy_production_decision_hits"] == 1
    # legacy hit is also a canonical_present==False read by a non-canonical writer
    assert report["compat_projection_production_reads"] >= 0
    assert report["total_canonical_turns"] == 2
    assert report["per_writer"]["_select_legacy_capability"]["count"] == 1


def test_counter_compat_projection_read_is_red(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="compat-1", shadow_hits=[_COMPAT_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    assert report["legacy_production_decision_hits"] == 0
    assert report["compat_projection_production_reads"] == 1


def test_counter_excludes_test_only_events(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(
        event_log,
        session_id="synthetic-1",
        shadow_hits=[_LEGACY_HIT],
        test_only=True,
    )
    _write_event(event_log, session_id="clean-1")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    # the test_only legacy hit must be excluded → window is clean
    assert report["exit_code"] == 0
    assert report["legacy_production_decision_hits"] == 0
    assert report["total_canonical_turns"] == 1
    assert report["excluded_test_only_event_count"] == 1


def test_counter_aggregates_per_writer(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="a", shadow_hits=[_LEGACY_HIT, _COMPAT_HIT])
    _write_event(event_log, session_id="b", shadow_hits=[_LEGACY_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["legacy_production_decision_hits"] == 2
    # legacy_decider role is NOT a compat_projection role; only the single compat
    # hit counts toward compat_projection_production_reads.
    assert report["compat_projection_production_reads"] == 1
    assert report["per_writer"]["_select_legacy_capability"]["count"] == 2
    assert report["per_writer"]["run"]["count"] == 1
    assert report["counting_method"]


def test_run_cli_exit_code_matches_report(tmp_path, capsys) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="legacy-1", shadow_hits=[_LEGACY_HIT])
    exit_code = run_cli(["--days", "7"], event_log=event_log)
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "legacy_production_decision_hits" in out
