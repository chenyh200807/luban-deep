from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

_REQUIRED_EVENT_NAMES = (
    "start_turn_sent",
    "first_visible_content_rendered",
    "done_rendered",
)


def _make_event_payload(
    *,
    surface: str,
    event_name: str,
    session_id: str,
    turn_id: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "event_id": f"surface-smoke-{event_name}-{uuid.uuid4().hex[:12]}",
        "surface": surface,
        "event_name": event_name,
        "session_id": session_id,
        "turn_id": turn_id,
        "collected_at_ms": now_ms,
        "sent_at_ms": now_ms,
        "metadata": {
            "smoke_test": True,
            **(metadata or {}),
        },
    }


def _find_surface_coverage(metrics_payload: dict[str, Any], surface: str) -> dict[str, Any] | None:
    coverage_entries = (metrics_payload.get("surface_events") or {}).get("coverage") or []
    for item in coverage_entries:
        if str(item.get("surface") or "").strip() == surface:
            return item
    return None


def run_surface_ack_smoke(
    *,
    api_base_url: str,
    surface: str,
    session_id: str,
    turn_id: str,
    metadata: dict[str, Any] | None = None,
    timeout_seconds: float = 3.0,
    poll_interval_seconds: float = 0.2,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    normalized_base_url = api_base_url.rstrip("/")
    ingest_url = f"{normalized_base_url}/api/v1/observability/surface-events"
    metrics_url = f"{normalized_base_url}/metrics"
    posted_events: list[dict[str, Any]] = []
    coverage: dict[str, Any] | None = None
    missing_requirements: list[str] = []
    deadline = time.time() + max(float(timeout_seconds), 0.1)

    with httpx.Client(timeout=5.0, trust_env=False, transport=transport) as client:
        for event_name in _REQUIRED_EVENT_NAMES:
            payload = _make_event_payload(
                surface=surface,
                event_name=event_name,
                session_id=session_id,
                turn_id=turn_id,
                metadata=metadata,
            )
            response = client.post(ingest_url, json=payload)
            response.raise_for_status()
            ack_payload = response.json()
            posted_events.append(
                {
                    "event_name": event_name,
                    "event_id": payload["event_id"],
                    "response": ack_payload,
                }
            )

        while time.time() <= deadline:
            response = client.get(metrics_url)
            response.raise_for_status()
            metrics_payload = response.json()
            coverage = _find_surface_coverage(metrics_payload, surface)
            if coverage is not None:
                break
            time.sleep(max(float(poll_interval_seconds), 0.01))

    if coverage is None:
        missing_requirements.append("missing_surface_coverage_entry")
    else:
        if int(coverage.get("start_turn_sent") or 0) < 1:
            missing_requirements.append("missing_start_turn_sent")
        if int(coverage.get("first_visible_content_rendered") or 0) < 1:
            missing_requirements.append("missing_first_visible_content_rendered")
        if int(coverage.get("done_rendered") or 0) < 1:
            missing_requirements.append("missing_done_rendered")

    return {
        "run_id": f"surface-smoke-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_base_url": normalized_base_url,
        "surface": surface,
        "session_id": session_id,
        "turn_id": turn_id,
        "metrics_url": metrics_url,
        "posted_events": posted_events,
        "coverage": coverage,
        "passed": not missing_requirements,
        "missing_requirements": missing_requirements,
    }

