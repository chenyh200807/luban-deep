#!/usr/bin/env python3
"""Observe-only report: control-plane shadow-hit counter (live-shadow metric).

OBSERVE-ONLY. This script never changes any control flow / return value /
cap_name / fabricated decision. It only *reads* the single canonical terminal
turn-observation event log (``TurnEventLog``) and counts how often a
compat/projection/fabricate writer became the operative source of a
control-plane fact in production.

The hits are piggy-backed (no second observation authority, no new event type,
no new append site) on the one terminal ``turn_observation`` event under
``metadata["control_plane_shadow_hits"]``: a list of structured entries shaped::

    {
      "fact": "<control-plane fact name>",
      "writer_role": "compat_projection" | "unconditional_fabricate" | ...,
      "writer_symbol": "<emitting symbol>",
      "path": "<code path tag>",
      "canonical_present": <bool>,
    }

One gate number is derived from the window:

- ``compat_projection_production_reads`` — hits whose ``writer_role`` is the
  non-canonical compat writer (``compat_projection``) AND whose
  ``canonical_present`` is ``False`` (it filled a canonical gap), OR whose
  ``writer_role`` is an ``unconditional_fabricate`` site (an operative second
  authority regardless of ``canonical_present`` — it fabricates even when the
  canonical decision is present).

Per-watch-target liveness (anti green-by-omission). Coverage is proven globally
by the instrumentation marker, but EXISTENCE must be proven per watch-target:
every counted ``writer_role`` MUST have a live ``"writer_role": "<role>"`` emit
site in production code. A watch-target with no live emit is a *ghost* — its
counter is pinned at 0 not because production is clean but because nothing can
ever fire it. That is exactly how a removed legacy decider
(``_select_legacy_capability``) and a never-emitted ``production_decider`` watch
sat at 0 forever while the coverage marker vouched the window "measured". A
startup AST self-check (``_watch_target_liveness_error``) scans the production
emit sources and fails closed (exit 2) the moment a counted role has no live
emit — the metric refuses to claim green for a target it can no longer observe.

Semantics: each counted hit = one time a compat/fabricate writer became the
operative source in a real (non-synthetic, non-test_only) production turn.

Exit codes:
  0  the gate number is 0 over the window (gate green)
  1  the gate number > 0 (a compat/fabricate writer was operative in production)
  2  fail-closed: a counted watch-target ``writer_role`` has NO live emit site
     (the metric is a ghost — see the liveness self-check above); OR the event
     log is unreadable; OR the window has zero turns carrying the
     instrumentation marker (no measured coverage). A window of
     pre-instrumentation turns is NOT clean — it is not-measured, so green
     cannot be claimed.

Coverage marker: every turn through the canonical builder is stamped
``metadata["control_plane_shadow_instrumentation_version"]`` unconditionally so
a clean instrumented turn is distinguishable from a turn that simply predates
this metric (otherwise both lack ``control_plane_shadow_hits`` and look
identical — the green-by-omission failure mode this guard closes).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability.turn_event_log import (  # noqa: E402
    INSTRUMENTATION_MARKER_KEY,
    SHADOW_INSTRUMENTATION_VERSION,
    TurnEventLog,
    event_is_test_only,
    get_turn_event_log,
)

# Non-canonical writer roles whose operative use is a control-plane shadow hit
# ONLY when the canonical decision was absent (a compat writer filled the gap
# because nothing canonical was present). NOTE: ``production_decider`` is NOT
# watched here — it has no live emit site, so watching it would borrow the
# global coverage marker for a target nothing can ever fire (the same
# green-by-omission as the removed ``_select_legacy_capability`` watch). Only
# roles with a live emit may be counted (enforced by ``_watch_target_liveness_error``).
_NON_CANONICAL_WRITER_ROLES: frozenset[str] = frozenset({"compat_projection"})
# Writer roles that are an operative SECOND authority regardless of whether the
# canonical decision was present — a bare unconditional ``build_turn_semantic_decision``
# site fabricates even when canonical is present, so canonical_present is NOT a gate.
_UNCONDITIONAL_FABRICATE_WRITER_ROLES: frozenset[str] = frozenset(
    {"unconditional_fabricate"}
)
# The full set of ``writer_role`` literals this metric still counts. Per-target
# liveness is enforced against this set: each MUST have a live emit site.
_WATCHED_WRITER_ROLES: frozenset[str] = (
    _NON_CANONICAL_WRITER_ROLES | _UNCONDITIONAL_FABRICATE_WRITER_ROLES
)
# Production source files that emit ``control_plane_shadow_hits`` (the only place
# a counted ``writer_role`` literal is constructed). The liveness self-check scans
# these for live emit sites. Keep in sync if a new emit site is added elsewhere.
_LIVE_EMIT_SOURCE_FILES: tuple[Path, ...] = (
    PROJECT_ROOT / "deeptutor" / "capabilities" / "deep_question.py",
)

_COUNTING_METHOD = (
    "live window measurement over the single canonical terminal turn_observation "
    "event log; synthetic/test_only events excluded; ONLY turns carrying the "
    f"instrumentation marker ({INSTRUMENTATION_MARKER_KEY}=={SHADOW_INSTRUMENTATION_VERSION}) "
    "are counted as measured — a turn WITHOUT the marker predates instrumentation "
    "and is NOT-MEASURED (not 'clean'); each hit = one time a compat/fabricate "
    "writer became the operative control-plane source in a real, instrumented "
    "production turn. exit 2 (fail-closed) when zero instrumented turns are in the "
    "window (no coverage means green cannot be claimed) OR when a counted "
    "watch-target role has no live emit site (the metric would test a ghost)."
)


def _scan_live_writer_roles(source_files: Iterable[Path]) -> frozenset[str]:
    """AST-scan production source for ``{"writer_role": "<role>"}`` dict literals.

    Returns the set of ``writer_role`` string-literal values that actually appear
    as a live emit in the given sources. Pure / read-only: parses syntax only, it
    never imports or executes the source, so missing runtime deps are irrelevant.
    Unreadable / unparseable sources contribute nothing (the liveness check then
    fail-closes because the watched role is absent).
    """
    roles: set[str] = set()
    for path in source_files:
        try:
            source = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "writer_role"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    roles.add(value.value)
    return frozenset(roles)


def _watch_target_liveness_error(
    source_files: Iterable[Path] | None = None,
) -> str | None:
    """Per-watch-target existence proof (anti green-by-omission).

    Every counted ``writer_role`` (``_WATCHED_WRITER_ROLES``) MUST have a live
    emit site in the production sources. A watched role with no live emit is a
    ghost: its counter can only ever read 0, so green for it is meaningless.
    Returns a human-readable error string when any watched role is a ghost
    (caller maps to exit 2), or ``None`` when every watched role is live.
    """
    files = _LIVE_EMIT_SOURCE_FILES if source_files is None else tuple(source_files)
    live_roles = _scan_live_writer_roles(files)
    ghosts = sorted(role for role in _WATCHED_WRITER_ROLES if role not in live_roles)
    if not ghosts:
        return None
    return "; ".join(
        f"watch-target role={role} has no live emit site — metric is testing a "
        f"ghost, cannot claim green"
        for role in ghosts
    )


def _is_instrumented(event: dict[str, Any]) -> bool:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get(INSTRUMENTATION_MARKER_KEY) or "").strip() == (
        SHADOW_INSTRUMENTATION_VERSION
    )


def _iter_shadow_hits(event: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return []
    hits = metadata.get("control_plane_shadow_hits")
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, dict)]


def _is_compat_projection_read(hit: dict[str, Any]) -> bool:
    role = str(hit.get("writer_role") or "").strip()
    # Unconditional bare-build fabricate: operative second authority irrespective
    # of canonical_present (it fabricates even when canonical is present).
    if role in _UNCONDITIONAL_FABRICATE_WRITER_ROLES:
        return True
    # Compat/projection writers count only when they filled a canonical gap.
    return role in _NON_CANONICAL_WRITER_ROLES and hit.get("canonical_present") is False


def _load_window_events(
    event_log: TurnEventLog,
    *,
    days: int | None,
    start_ts: float | None,
    end_ts: float | None,
) -> list[dict[str, Any]]:
    if start_ts is not None and end_ts is not None:
        return event_log.load_events_window(start_ts=start_ts, end_ts=end_ts)
    return event_log.load_events_range(days=max(int(days or 7), 1))


def _ghost_target_report(
    *,
    error: str,
    days: int | None,
    start_ts: float | None,
    end_ts: float | None,
) -> dict[str, Any]:
    """Fail-closed report dict for a ghost watch-target (exit 2)."""
    return {
        "exit_code": 2,
        "error": error,
        "total_canonical_turns": 0,
        "instrumented_turns": 0,
        "excluded_test_only_event_count": 0,
        "compat_projection_production_reads": 0,
        "per_writer": {},
        "per_fact": {},
        "per_path": {},
        "per_scene": {},
        "per_site": {},
        "coverage": f"fail-closed: {error}",
        "window": {"days": days, "start_ts": start_ts, "end_ts": end_ts},
        "counting_method": _COUNTING_METHOD,
    }


def report_control_plane_shadow_hits(
    *,
    event_log: TurnEventLog | None = None,
    days: int | None = 7,
    start_ts: float | None = None,
    end_ts: float | None = None,
    live_emit_source_files: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Aggregate control-plane shadow hits over a window (observe-only)."""
    # Per-watch-target liveness FIRST (independent of the window): if a counted
    # writer_role has no live emit site, the metric is a ghost and cannot claim
    # green for any window. Fail closed before reading any events.
    ghost_error = _watch_target_liveness_error(live_emit_source_files)
    if ghost_error is not None:
        return _ghost_target_report(
            error=ghost_error, days=days, start_ts=start_ts, end_ts=end_ts
        )

    log = event_log if event_log is not None else get_turn_event_log()
    try:
        raw_events = _load_window_events(
            log, days=days, start_ts=start_ts, end_ts=end_ts
        )
    except Exception as exc:  # fail-closed: unreadable log cannot report green
        return {
            "exit_code": 2,
            "error": f"{type(exc).__name__}: {exc}",
            "total_canonical_turns": 0,
            "instrumented_turns": 0,
            "excluded_test_only_event_count": 0,
            "compat_projection_production_reads": 0,
            "per_writer": {},
            "per_fact": {},
            "per_path": {},
            "per_scene": {},
            "per_site": {},
            "coverage": "fail-closed: event log unreadable; no coverage measurable",
            "window": {"days": days, "start_ts": start_ts, "end_ts": end_ts},
            "counting_method": _COUNTING_METHOD,
        }

    canonical_events = [e for e in raw_events if not event_is_test_only(e)]
    excluded_test_only = max(len(raw_events) - len(canonical_events), 0)
    instrumented_turns = sum(1 for e in canonical_events if _is_instrumented(e))

    compat_reads = 0
    per_writer: dict[str, dict[str, int]] = {}
    per_fact: dict[str, int] = {}
    per_path: dict[str, int] = {}
    per_scene: dict[str, int] = {}
    per_site: dict[str, int] = {}

    # Count hits across all canonical events (defense in depth: a recorded
    # competing-writer fire is a red signal regardless of marker presence — the
    # marker gates coverage/green claims, never the surfacing of an actual hit).
    for event in canonical_events:
        for hit in _iter_shadow_hits(event):
            symbol = str(hit.get("writer_symbol") or "").strip() or "<unknown>"
            fact = str(hit.get("fact") or "").strip() or "<unknown>"
            path = str(hit.get("path") or "").strip() or "<unknown>"
            scene = str(hit.get("scene") or "").strip() or "<unknown>"
            site = str(hit.get("site") or "").strip() or "<unknown>"
            per_writer.setdefault(symbol, {"count": 0})["count"] += 1
            per_fact[fact] = per_fact.get(fact, 0) + 1
            per_path[path] = per_path.get(path, 0) + 1
            per_scene[scene] = per_scene.get(scene, 0) + 1
            per_site[site] = per_site.get(site, 0) + 1
            if _is_compat_projection_read(hit):
                compat_reads += 1

    total_canonical_turns = len(canonical_events)
    has_hits = compat_reads > 0
    # Coverage guard FIRST: a window with hits is red even if (somehow) no marker
    # is present — but a window with NO hits can only be green if coverage is
    # proven (instrumented_turns > 0). Zero instrumented turns = not-measured.
    if has_hits:
        exit_code = 1
        coverage = (
            f"{instrumented_turns}/{total_canonical_turns} canonical turns instrumented; "
            "competing-writer hit(s) recorded"
        )
    elif instrumented_turns == 0:
        exit_code = 2  # fail-closed: no instrumented coverage cannot report green
        coverage = (
            f"NOT-MEASURED: 0/{total_canonical_turns} canonical turns carry the "
            f"instrumentation marker — window predates instrumentation or has no "
            f"instrumented turns; green cannot be claimed (fail-closed)"
        )
    else:
        exit_code = 0
        coverage = (
            f"{instrumented_turns}/{total_canonical_turns} canonical turns instrumented; "
            "no competing-writer hits → verified clean"
        )

    return {
        "exit_code": exit_code,
        "total_canonical_turns": total_canonical_turns,
        "instrumented_turns": instrumented_turns,
        "excluded_test_only_event_count": excluded_test_only,
        "compat_projection_production_reads": compat_reads,
        "per_writer": per_writer,
        "per_fact": per_fact,
        "per_path": per_path,
        "per_scene": per_scene,
        "per_site": per_site,
        "coverage": coverage,
        "window": {"days": days, "start_ts": start_ts, "end_ts": end_ts},
        "counting_method": _COUNTING_METHOD,
    }


def run_cli(argv: list[str] | None = None, *, event_log: TurnEventLog | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="window size in days (counting back from today); default 7",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=None,
        help="window start epoch seconds (use with --end; overrides --days)",
    )
    parser.add_argument(
        "--end",
        type=float,
        default=None,
        help="window end epoch seconds (use with --start; defaults to now)",
    )
    args = parser.parse_args(argv)

    start_ts = args.start
    end_ts = args.end
    if start_ts is not None and end_ts is None:
        end_ts = time.time()

    report = report_control_plane_shadow_hits(
        event_log=event_log,
        days=args.days if start_ts is None else None,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(report["exit_code"])


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
