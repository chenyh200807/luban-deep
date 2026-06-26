from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTS_DIR = PROJECT_ROOT / "tmp" / "observability" / "observer" / "events"
_SYNTHETIC_SESSION_TOKENS = ("shadow",)
_SYNTHETIC_SURFACES = {"online_shadow"}

# --- Control-plane shadow-hit observe-only coverage marker --------------------
# Stamped UNCONDITIONALLY on every turn that flows through this canonical builder,
# regardless of whether a competing control-plane writer fired. A clean turn and
# a turn that simply predates this metric are otherwise byte-identical (neither
# carries control_plane_shadow_hits), so the report counter cannot tell "verified
# clean" from "never measured" without this marker. Its presence proves the turn
# ran code that *would* have recorded any competing-writer fire; its absence means
# not-measured (the counter fails closed on a window with zero marked turns).
#
# ASSUMPTION (documented per reviewer): all shadow-hit emit points and this marker
# ship in the same commit / same deployment, so a single version constant is
# sufficient to prove "this turn ran instrumentation version X". Bump the version
# whenever the set of emit points or the hit schema changes, so a window mixing
# pre/post-change turns is not silently aggregated as one coverage cohort.
INSTRUMENTATION_MARKER_KEY = "control_plane_shadow_instrumentation_version"
SHADOW_INSTRUMENTATION_VERSION = "1"


def _coerce_non_negative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _coerce_non_negative_float(value: Any) -> float:
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _infer_observation_flags(
    *,
    session_id: str,
    surface: str,
    metadata: dict[str, Any],
    observation_cohort: str,
    synthetic: bool | None,
    test_only: bool | None,
) -> tuple[str, bool, bool]:
    normalized_session_id = str(session_id or "").strip().lower()
    normalized_surface = str(surface or "").strip().lower()
    explicit_cohort = str(observation_cohort or "").strip().lower()
    metadata_source = str(metadata.get("source") or "").strip().lower()
    inferred_synthetic = any(token in normalized_session_id for token in _SYNTHETIC_SESSION_TOKENS)
    inferred_synthetic = inferred_synthetic or normalized_surface in _SYNTHETIC_SURFACES
    inferred_synthetic = inferred_synthetic or bool(metadata.get("smoke_test"))
    inferred_test_only = inferred_synthetic or metadata_source in {"run_prerelease_observability", "surface_ack_smoke"}
    resolved_synthetic = inferred_synthetic if synthetic is None else bool(synthetic)
    resolved_test_only = inferred_test_only if test_only is None else bool(test_only)
    if explicit_cohort:
        resolved_cohort = explicit_cohort
    elif resolved_synthetic:
        resolved_cohort = "synthetic"
    elif resolved_test_only:
        resolved_cohort = "test_only"
    else:
        resolved_cohort = "canonical"
    return resolved_cohort, resolved_synthetic, resolved_test_only


def event_is_test_only(event: dict[str, Any]) -> bool:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    _cohort, synthetic, test_only = _infer_observation_flags(
        session_id=str(event.get("session_id") or ""),
        surface=str(event.get("surface") or ""),
        metadata=metadata,
        observation_cohort=str(event.get("observation_cohort") or ""),
        synthetic=event.get("synthetic") if isinstance(event.get("synthetic"), bool) else None,
        test_only=event.get("test_only") if isinstance(event.get("test_only"), bool) else None,
    )
    return synthetic or test_only


def build_turn_observation_event(
    *,
    session_id: str = "",
    turn_id: str = "",
    trace_id: str = "",
    status: str = "unknown",
    capability: str = "",
    route: str = "",
    surface: str = "",
    user_id: str = "",
    latency_ms: float = 0.0,
    token_total: int = 0,
    retrieval_hit: bool | None = None,
    error_type: str = "",
    release: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: float | None = None,
    observation_cohort: str = "",
    synthetic: bool | None = None,
    test_only: bool | None = None,
) -> dict[str, Any]:
    normalized_metadata = dict(metadata or {})
    # Observe-only coverage marker: stamp unconditionally so every turn through the
    # canonical builder proves it ran the shadow-hit instrumentation. No control
    # flow change; this is metadata only.
    normalized_metadata[INSTRUMENTATION_MARKER_KEY] = SHADOW_INSTRUMENTATION_VERSION
    resolved_cohort, resolved_synthetic, resolved_test_only = _infer_observation_flags(
        session_id=str(session_id or "").strip(),
        surface=str(surface or "").strip(),
        metadata=normalized_metadata,
        observation_cohort=observation_cohort,
        synthetic=synthetic,
        test_only=test_only,
    )
    return {
        "type": "turn_observation",
        "timestamp": float(timestamp if timestamp is not None else time.time()),
        "release": dict(release or get_release_lineage_snapshot()),
        "session_id": str(session_id or "").strip(),
        "turn_id": str(turn_id or "").strip(),
        "trace_id": str(trace_id or "").strip(),
        "status": str(status or "unknown").strip() or "unknown",
        "capability": str(capability or "").strip(),
        "route": str(route or "").strip(),
        "surface": str(surface or "").strip(),
        "user_id": str(user_id or "").strip(),
        "latency_ms": _coerce_non_negative_float(latency_ms),
        "token_total": _coerce_non_negative_int(token_total),
        "retrieval_hit": retrieval_hit if isinstance(retrieval_hit, bool) else None,
        "error_type": str(error_type or "").strip(),
        "metadata": normalized_metadata,
        "observation_cohort": resolved_cohort,
        "synthetic": resolved_synthetic,
        "test_only": resolved_test_only,
    }


class TurnEventLog:
    """Append-only JSONL log for derived turn observation facts."""

    def __init__(self, *, events_dir: Path | None = None) -> None:
        # Precedence: an EXPLICIT events_dir argument is the caller's specific
        # intent and wins over the process-wide DEEPTUTOR_OBSERVER_EVENT_DIR
        # default. The env var only governs the no-argument case (the production
        # singleton). This lets a test-suite session fixture set the env to keep
        # bare instances out of the production default dir while a function-scoped
        # test that passes its own events_dir still isolates to that directory.
        configured_dir = str(os.getenv("DEEPTUTOR_OBSERVER_EVENT_DIR", "") or "").strip()
        if events_dir is not None:
            self.events_dir = Path(events_dir).expanduser().resolve()
        elif configured_dir:
            self.events_dir = Path(configured_dir).expanduser().resolve()
        else:
            self.events_dir = DEFAULT_EVENTS_DIR.expanduser().resolve()
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_write_error = ""
        self._append_success_total = 0
        self._append_failure_total = 0

    def _path_for_date(self, date_str: str) -> Path:
        return self.events_dir / f"turn_events_{date_str}.jsonl"

    def _today_path(self) -> Path:
        return self._path_for_date(datetime.now().strftime("%Y-%m-%d"))

    def append(self, event: dict[str, Any]) -> bool:
        with self._lock:
            try:
                with self._today_path().open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(dict(event), ensure_ascii=False) + "\n")
                self._last_write_error = ""
                self._append_success_total += 1
                return True
            except Exception as exc:
                self._last_write_error = f"{type(exc).__name__}: {exc}"
                self._append_failure_total += 1
                return False

    def load_events(self, date_str: str | None = None) -> list[dict[str, Any]]:
        target_date = date_str or datetime.now().strftime("%Y-%m-%d")
        path = self._path_for_date(target_date)
        if not path.exists():
            return []

        events: list[dict[str, Any]] = []
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    events.append(payload)
        except OSError:
            return []
        return events

    def load_events_range(self, *, days: int = 1) -> list[dict[str, Any]]:
        event_days = max(int(days or 1), 1)
        events: list[dict[str, Any]] = []
        for offset in range(event_days):
            date_str = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
            events.extend(self.load_events(date_str))
        return events

    def load_events_window(
        self,
        *,
        start_ts: float,
        end_ts: float,
        timezone: str = "Asia/Shanghai",
    ) -> list[dict[str, Any]]:
        tz = ZoneInfo(timezone)
        start_dt = datetime.fromtimestamp(float(start_ts), tz)
        end_dt = datetime.fromtimestamp(float(end_ts), tz)
        if end_dt < start_dt:
            return []

        events: list[dict[str, Any]] = []
        current = start_dt.date()
        final = end_dt.date()
        while current <= final:
            events.extend(self.load_events(current.isoformat()))
            current += timedelta(days=1)

        filtered: list[dict[str, Any]] = []
        for event in events:
            try:
                timestamp = float(event.get("timestamp") or 0.0)
            except (TypeError, ValueError):
                continue
            if float(start_ts) <= timestamp <= float(end_ts):
                filtered.append(event)
        return filtered

    def stats(self) -> dict[str, Any]:
        today_events = self.load_events()
        with self._lock:
            last_write_error = self._last_write_error
            append_success_total = self._append_success_total
            append_failure_total = self._append_failure_total
        return {
            "today_events": len(today_events),
            "file_exists": self._today_path().exists(),
            "file_path": str(self._today_path()),
            "last_write_error": last_write_error,
            "append_success_total": append_success_total,
            "append_failure_total": append_failure_total,
        }

    def stats_window(
        self,
        *,
        start_ts: float,
        end_ts: float,
        timezone: str = "Asia/Shanghai",
    ) -> dict[str, Any]:
        tz = ZoneInfo(timezone)
        start_dt = datetime.fromtimestamp(float(start_ts), tz)
        end_dt = datetime.fromtimestamp(float(end_ts), tz)
        date_strings: list[str] = []
        current = start_dt.date()
        final = end_dt.date()
        while current <= final:
            date_strings.append(current.isoformat())
            current += timedelta(days=1)

        file_paths = [self._path_for_date(date_str) for date_str in date_strings]
        events = self.load_events_window(start_ts=start_ts, end_ts=end_ts, timezone=timezone)
        with self._lock:
            last_write_error = self._last_write_error
            append_success_total = self._append_success_total
            append_failure_total = self._append_failure_total
        return {
            "window_date_strings": date_strings,
            "window_start_ts": float(start_ts),
            "window_end_ts": float(end_ts),
            "file_exists": any(path.exists() for path in file_paths),
            "file_path": str(file_paths[0]) if len(file_paths) == 1 else "",
            "file_paths": [str(path) for path in file_paths],
            "window_events": len(events),
            "last_write_error": last_write_error,
            "append_success_total": append_success_total,
            "append_failure_total": append_failure_total,
        }


_turn_event_log: TurnEventLog | None = None


def get_turn_event_log() -> TurnEventLog:
    global _turn_event_log
    if _turn_event_log is None:
        _turn_event_log = TurnEventLog()
    return _turn_event_log


def reset_turn_event_log(*, events_dir: Path | None = None) -> None:
    global _turn_event_log
    _turn_event_log = TurnEventLog(events_dir=events_dir)
