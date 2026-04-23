from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTS_DIR = PROJECT_ROOT / "tmp" / "observability" / "observer" / "events"


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
) -> dict[str, Any]:
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
        "metadata": dict(metadata or {}),
    }


class TurnEventLog:
    """Append-only JSONL log for derived turn observation facts."""

    def __init__(self, *, events_dir: Path | None = None) -> None:
        configured_dir = str(os.getenv("DEEPTUTOR_OBSERVER_EVENT_DIR", "") or "").strip()
        self.events_dir = (
            Path(configured_dir).expanduser().resolve()
            if configured_dir
            else (events_dir or DEFAULT_EVENTS_DIR).expanduser().resolve()
        )
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


_turn_event_log: TurnEventLog | None = None


def get_turn_event_log() -> TurnEventLog:
    global _turn_event_log
    if _turn_event_log is None:
        _turn_event_log = TurnEventLog()
    return _turn_event_log


def reset_turn_event_log(*, events_dir: Path | None = None) -> None:
    global _turn_event_log
    _turn_event_log = TurnEventLog(events_dir=events_dir)
