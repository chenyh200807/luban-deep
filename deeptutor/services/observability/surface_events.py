from __future__ import annotations

import threading
import time
from collections import Counter
from collections import deque
from typing import Any

_ALLOWED_SURFACES = {
    "web",
    "wechat_miniprogram",
    "wechat_yousenwebview",
}

_ALLOWED_EVENT_NAMES = {
    "ws_connected",
    "start_turn_sent",
    "session_event_received",
    "first_visible_content_rendered",
    "done_rendered",
    "user_cancelled",
    "resume_attempted",
    "resume_succeeded",
    "surface_render_failed",
}


def _normalize_surface(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _ALLOWED_SURFACES:
        raise ValueError(f"Unsupported surface: {value!r}")
    return normalized


def _normalize_event_name(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in _ALLOWED_EVENT_NAMES:
        raise ValueError(f"Unsupported event_name: {value!r}")
    return normalized


class SurfaceEventStore:
    """Best-effort in-memory surface ACK aggregator for OM baseline."""

    def __init__(self, *, max_recent_events: int = 200, max_recent_event_ids: int = 4096) -> None:
        self._lock = threading.Lock()
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=max_recent_events)
        self._recent_event_ids: deque[str] = deque(maxlen=max_recent_event_ids)
        self._seen_event_ids: set[str] = set()
        self._event_status_counts: Counter[tuple[str, str, str]] = Counter()
        self._accepted_event_counts: Counter[tuple[str, str]] = Counter()

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("event_id is required")

        surface = _normalize_surface(str(payload.get("surface") or ""))
        event_name = _normalize_event_name(str(payload.get("event_name") or ""))
        session_id = str(payload.get("session_id") or "").strip()
        turn_id = str(payload.get("turn_id") or "").strip()
        user_id = str(payload.get("user_id") or "").strip()
        metadata = payload.get("metadata")
        normalized_metadata = metadata if isinstance(metadata, dict) else {}
        collected_at_ms = int(payload.get("collected_at_ms") or payload.get("client_timestamp_ms") or 0)
        sent_at_ms = int(payload.get("sent_at_ms") or 0)
        ingested_at_ms = int(time.time() * 1000)

        with self._lock:
            if event_id in self._seen_event_ids:
                self._event_status_counts[(surface, event_name, "duplicate")] += 1
                return {
                    "accepted": False,
                    "status": "duplicate",
                    "event_id": event_id,
                    "surface": surface,
                    "event_name": event_name,
                }

            if len(self._recent_event_ids) == self._recent_event_ids.maxlen:
                evicted = self._recent_event_ids.popleft()
                self._seen_event_ids.discard(evicted)
            self._recent_event_ids.append(event_id)
            self._seen_event_ids.add(event_id)

            self._event_status_counts[(surface, event_name, "accepted")] += 1
            self._accepted_event_counts[(surface, event_name)] += 1
            self._recent_events.appendleft(
                {
                    "event_id": event_id,
                    "surface": surface,
                    "event_name": event_name,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "user_id": user_id,
                    "collected_at_ms": collected_at_ms,
                    "sent_at_ms": sent_at_ms,
                    "ingested_at_ms": ingested_at_ms,
                    "metadata": normalized_metadata,
                }
            )
            return {
                "accepted": True,
                "status": "accepted",
                "event_id": event_id,
                "surface": surface,
                "event_name": event_name,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            event_counts = []
            for (surface, event_name, status), count in sorted(
                self._event_status_counts.items(),
                key=lambda item: (item[0][0], item[0][1], item[0][2]),
            ):
                event_counts.append(
                    {
                        "surface": surface,
                        "event_name": event_name,
                        "status": status,
                        "count": int(count),
                    }
                )

            coverage = []
            for surface in sorted(_ALLOWED_SURFACES):
                start_count = int(self._accepted_event_counts.get((surface, "start_turn_sent")) or 0)
                first_render_count = int(
                    self._accepted_event_counts.get((surface, "first_visible_content_rendered")) or 0
                )
                done_render_count = int(self._accepted_event_counts.get((surface, "done_rendered")) or 0)
                render_failed_count = int(
                    self._accepted_event_counts.get((surface, "surface_render_failed")) or 0
                )
                if start_count <= 0 and first_render_count <= 0 and done_render_count <= 0 and render_failed_count <= 0:
                    continue
                coverage.append(
                    {
                        "surface": surface,
                        "start_turn_sent": start_count,
                        "first_visible_content_rendered": first_render_count,
                        "done_rendered": done_render_count,
                        "surface_render_failed": render_failed_count,
                        "first_render_coverage_ratio": round(first_render_count / start_count, 4)
                        if start_count
                        else None,
                        "done_render_coverage_ratio": round(done_render_count / start_count, 4)
                        if start_count
                        else None,
                    }
                )

            return {
                "event_counts": event_counts,
                "coverage": coverage,
                "recent_events": list(self._recent_events),
            }

    def get_turn_summary(self, turn_id: str) -> dict[str, Any]:
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_turn_id:
            return {
                "turn_id": "",
                "event_counts": {},
                "first_visible_content_rendered": 0,
                "done_rendered": 0,
                "surface_render_failed": 0,
            }
        with self._lock:
            counts: Counter[str] = Counter()
            for event in self._recent_events:
                if str(event.get("turn_id") or "").strip() != normalized_turn_id:
                    continue
                counts[str(event.get("event_name") or "").strip()] += 1
            return {
                "turn_id": normalized_turn_id,
                "event_counts": {key: int(value) for key, value in sorted(counts.items(), key=lambda item: item[0])},
                "first_visible_content_rendered": int(counts.get("first_visible_content_rendered") or 0),
                "done_rendered": int(counts.get("done_rendered") or 0),
                "surface_render_failed": int(counts.get("surface_render_failed") or 0),
            }


_surface_event_store = SurfaceEventStore()


def get_surface_event_store() -> SurfaceEventStore:
    return _surface_event_store


def reset_surface_event_store() -> None:
    global _surface_event_store
    _surface_event_store = SurfaceEventStore()
