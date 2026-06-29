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
    _LIVE_EMIT_SOURCE_FILES,
    _WATCHED_WRITER_ROLES,
    _watch_target_liveness_error,
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


_COMPAT_HIT = {
    "fact": "turn_semantic_decision",
    "writer_role": "compat_projection",
    "writer_symbol": "run",
    "path": "deep_question",
    "canonical_present": False,
}
# Live-shadow blind-spot fixes: the canonical-missing guard now carries a scene
# and site; the S5/S6 bare-build sites are unconditional_fabricate hits whose
# canonical_present may be True (they fabricate even with canonical present).
_GUARD_SCENED_HIT = {
    "fact": "turn_semantic_decision",
    "writer_role": "compat_projection",
    "writer_symbol": "run",
    "path": "deep_question",
    "site": "canonical_missing_guard",
    "scene": "practice_generation",
    "canonical_present": False,
}
_S5_FABRICATE_HIT = {
    "fact": "turn_semantic_decision",
    "writer_role": "unconditional_fabricate",
    "writer_symbol": "run",
    "path": "deep_question",
    "site": "S5_review_render",
    "scene": "question_review",
    # canonical_present True — the blind spot: S5 fabricates even when canonical present.
    "canonical_present": True,
}
_S6_FABRICATE_HIT = {
    "fact": "turn_semantic_decision",
    "writer_role": "unconditional_fabricate",
    "writer_symbol": "run",
    "path": "deep_question",
    "site": "S6_refused",
    "scene": "practice_generation",
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
    assert report["compat_projection_production_reads"] == 0


def test_counter_clean_window_is_green(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="clean-1")
    _write_event(event_log, session_id="clean-2", shadow_hits=[])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 0
    assert report["total_canonical_turns"] == 2
    assert report["instrumented_turns"] == 2
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
    _write_predate_event(event_log, session_id="predate-hit-1", shadow_hits=[_COMPAT_HIT])
    _write_event(event_log, session_id="instrumented-clean-1")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    assert report["compat_projection_production_reads"] == 1


def test_counter_compat_projection_read_is_red(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="compat-1", shadow_hits=[_COMPAT_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    assert report["compat_projection_production_reads"] == 1


def test_counter_excludes_test_only_events(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(
        event_log,
        session_id="synthetic-1",
        shadow_hits=[_COMPAT_HIT],
        test_only=True,
    )
    _write_event(event_log, session_id="clean-1")
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    # the test_only compat hit must be excluded → window is clean
    assert report["exit_code"] == 0
    assert report["compat_projection_production_reads"] == 0
    assert report["total_canonical_turns"] == 1
    assert report["excluded_test_only_event_count"] == 1


def test_counter_aggregates_per_writer(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="a", shadow_hits=[_COMPAT_HIT, _S5_FABRICATE_HIT])
    _write_event(event_log, session_id="b", shadow_hits=[_COMPAT_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    # two compat-projection canonical-gap reads + one unconditional_fabricate read
    assert report["compat_projection_production_reads"] == 3
    # per_writer aggregates raw hits by writer_symbol (all three are "run")
    assert report["per_writer"]["run"]["count"] == 3
    assert report["counting_method"]


def test_run_cli_exit_code_matches_report(tmp_path, capsys) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="compat-1", shadow_hits=[_COMPAT_HIT])
    exit_code = run_cli(["--days", "7"], event_log=event_log)
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "compat_projection_production_reads" in out


# ---------------------------------------------------------------------------
# Blind-spot fixes: per-scene / per-site breakdown + unconditional_fabricate
# counted toward compat_projection_production_reads (it is an operative second
# authority regardless of canonical_present).
# ---------------------------------------------------------------------------
def test_counter_breaks_down_per_scene(tmp_path) -> None:
    """The window aggregates hits per scene so generation (practice_generation)
    fabrication can be proven distinct from review (question_review)."""
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="gen-1", shadow_hits=[_GUARD_SCENED_HIT, _S6_FABRICATE_HIT])
    _write_event(event_log, session_id="rev-1", shadow_hits=[_S5_FABRICATE_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["per_scene"]["practice_generation"] == 2
    assert report["per_scene"]["question_review"] == 1


def test_counter_breaks_down_per_site(tmp_path) -> None:
    """The window aggregates hits per site so the canonical-missing guard, the
    S5 review-render fabricate, and the S6 refused fabricate are separable."""
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(
        event_log,
        session_id="multi-1",
        shadow_hits=[_GUARD_SCENED_HIT, _S5_FABRICATE_HIT, _S6_FABRICATE_HIT],
    )
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["per_site"]["canonical_missing_guard"] == 1
    assert report["per_site"]["S5_review_render"] == 1
    assert report["per_site"]["S6_refused"] == 1


def test_unconditional_fabricate_counts_as_production_read_even_canonical_present(
    tmp_path,
) -> None:
    """S5 fabricates even when canonical_present is True. unconditional_fabricate
    is an operative second authority, so it MUST count toward
    compat_projection_production_reads regardless of canonical_present."""
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="s5-present", shadow_hits=[_S5_FABRICATE_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    # canonical_present is True here, yet it still counts (operative second authority).
    assert report["compat_projection_production_reads"] == 1


def test_unconditional_fabricate_canonical_absent_also_counts(tmp_path) -> None:
    event_log = TurnEventLog(events_dir=tmp_path)
    _write_event(event_log, session_id="s6-absent", shadow_hits=[_S6_FABRICATE_HIT])
    report = report_control_plane_shadow_hits(event_log=event_log, days=7)
    assert report["exit_code"] == 1
    assert report["compat_projection_production_reads"] == 1


# ---------------------------------------------------------------------------
# Per-watch-target liveness self-check (P0-a anti green-by-omission). Coverage is
# proven globally, but EXISTENCE must be proven per watch-target: every counted
# writer_role MUST have a live `"writer_role": "<role>"` emit site in production
# code. A watch-target with no live emit is a ghost — its counter is pinned at 0
# not because production is clean but because nothing can fire it (the exact
# failure mode of the removed _select_legacy_capability / production_decider
# watch-targets). A ghost target is exit 2, never silent green.
# ---------------------------------------------------------------------------
def test_watched_roles_are_only_the_live_emitting_set() -> None:
    """The counted watch-targets are exactly the roles with a live emit site;
    the removed legacy decider and the never-emitted production_decider are NOT
    watched (watching them would borrow global coverage = the green-by-omission
    bug)."""
    assert _WATCHED_WRITER_ROLES == frozenset(
        {"compat_projection", "unconditional_fabricate"}
    )


def test_watch_targets_all_live_on_real_sources() -> None:
    """Positive control: against the real production emit sources, every counted
    role has a live emit, so the self-check passes (returns None)."""
    assert _watch_target_liveness_error() is None


def test_watch_target_ghost_fails_closed(tmp_path) -> None:
    """CORE counter-example (the discriminating difference vs the old false-green).

    Rename a live ``writer_role`` emit literal in a copy of the production source
    (simulating someone deleting/renaming the live emit). The self-check then
    turns the metric RED (exit 2) — whereas the old legacy-symbol watch-target,
    which had NO live emit at all, sat at 0 and reported exit 0 forever."""
    real_src = _LIVE_EMIT_SOURCE_FILES[0].read_text(encoding="utf-8")
    assert '"writer_role": "unconditional_fabricate"' in real_src
    mutated = real_src.replace(
        '"writer_role": "unconditional_fabricate"',
        '"writer_role": "unconditional_fabricate_RENAMED"',
    )
    ghost_src = tmp_path / "deep_question_mutated.py"
    ghost_src.write_text(mutated, encoding="utf-8")

    event_log = TurnEventLog(events_dir=tmp_path)
    # A perfectly clean, instrumented window — under the OLD design this is green.
    _write_event(event_log, session_id="clean-1")
    report = report_control_plane_shadow_hits(
        event_log=event_log, days=7, live_emit_source_files=[ghost_src]
    )
    assert report["exit_code"] == 2
    assert "unconditional_fabricate" in report["error"]
    assert "has no live emit site" in report["error"]
    assert "ghost" in report["error"]
