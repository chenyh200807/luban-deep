from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from deeptutor.services.observability.turn_event_log import TurnEventLog
from deeptutor.services.observability.turn_event_log import get_turn_event_log

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FAILED_TURN_DIR = PROJECT_ROOT / "tmp" / "observability" / "failed_turn_incidents"
_FAILED_STATUSES = {"failed", "error", "cancelled", "timeout"}


def _failure_reason(event: dict[str, Any]) -> str:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    for key in ("message", "error", "reason", "summary"):
        value = metadata.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return str(event.get("error_type") or event.get("status") or "failed_turn").strip()


def _candidate_from_event(event: dict[str, Any], *, incident_id: str) -> dict[str, Any]:
    return {
        "incident_id": incident_id,
        "source": "turn_event_log",
        "session_id": str(event.get("session_id") or ""),
        "turn_id": str(event.get("turn_id") or ""),
        "trace_id": str(event.get("trace_id") or ""),
        "status": str(event.get("status") or ""),
        "capability": str(event.get("capability") or ""),
        "route": str(event.get("route") or ""),
        "error_type": str(event.get("error_type") or ""),
        "reason": _failure_reason(event),
        "recommended_tier": "incident_replay",
    }


def build_failed_turn_incident_report(
    *,
    event_log: TurnEventLog | None = None,
    incident_id: str | None = None,
    days: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    turn_log = event_log or get_turn_event_log()
    events = turn_log.load_events_range(days=max(int(days or 1), 1))
    failed_events = [
        event
        for event in events
        if str(event.get("status") or "").strip().lower() in _FAILED_STATUSES
    ]
    failed_events = failed_events[: max(int(limit or 20), 1)]
    normalized_incident_id = str(incident_id or "").strip() or f"failed-turns-{int(time.time())}"
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    replay_candidates = [
        _candidate_from_event(event, incident_id=normalized_incident_id)
        for event in failed_events
    ]
    release = {}
    for event in failed_events:
        candidate_release = event.get("release")
        if isinstance(candidate_release, dict) and candidate_release:
            release = dict(candidate_release)
            break
    return {
        "run_manifest": {
            "run_id": f"failed-turn-incident-{int(time.time())}",
            "generated_at": generated_at,
            "incident_id": normalized_incident_id,
            "source": "turn_event_log",
            "window_days": max(int(days or 1), 1),
            "candidate_limit": max(int(limit or 20), 1),
        },
        "release_spine": release,
        "classification": {
            "failed_turn_count": len(failed_events),
            "replay_candidate_count": len(replay_candidates),
        },
        "replay_candidates": replay_candidates,
    }


def render_failed_turn_incident_markdown(payload: dict[str, Any]) -> str:
    manifest = payload.get("run_manifest") or {}
    classification = payload.get("classification") or {}
    lines = [
        "# Failed Turn Incident Candidates",
        "",
        f"- run_id: `{manifest.get('run_id')}`",
        f"- incident_id: `{manifest.get('incident_id')}`",
        f"- failed_turn_count: `{classification.get('failed_turn_count')}`",
        "",
        "## Replay Candidates",
        "",
    ]
    candidates = payload.get("replay_candidates") or []
    if not candidates:
        lines.append("- none")
    else:
        for item in candidates:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def write_failed_turn_incident_report(
    payload: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    target_dir = (output_dir or DEFAULT_FAILED_TURN_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = target_dir / f"failed_turn_incident_{stamp}.json"
    md_path = target_dir / f"failed_turn_incident_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_failed_turn_incident_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
