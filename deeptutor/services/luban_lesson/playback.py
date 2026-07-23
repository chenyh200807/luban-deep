"""Canonical validation for hosted microlesson playback facts.

The publisher owns the deterministic episode/section projection.  Browser
cards may report a state transition, but they cannot choose the learner,
episode, content revision, section bounds, or BI identity written to the
product-behavior ledger.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_PUBLIC_PREVIEW_ROOT = _REPO / "web" / "public" / "luban-preview"
_PLAYBACK_MANIFEST_NAME = "playback-manifest.json"
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
PLAYBACK_ACTIONS = frozenset(
    {
        "play",
        "pause",
        "seek",
        "section_enter",
        "checkpoint",
        "exit",
        "complete",
        "replay",
    }
)
_MAX_SEQUENCE = 1_000_000
_MAX_WATCHED_DELTA_MS = 60_000
_POSITION_TOLERANCE_MS = 1_000


class PlaybackFactInvalid(ValueError):
    """The browser fact does not match the published playback projection."""


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise PlaybackFactInvalid(f"{field} must be an integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlaybackFactInvalid(f"{field} must be an integer") from exc
    return normalized


def _load_manifest(pack_id: str) -> dict[str, Any]:
    normalized_pack = str(pack_id or "").strip().upper()
    if not normalized_pack:
        raise PlaybackFactInvalid("pack_id is required")
    path = (
        _PUBLIC_PREVIEW_ROOT
        / normalized_pack.lower()
        / _PLAYBACK_MANIFEST_NAME
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlaybackFactInvalid("playback manifest unavailable") from exc
    if str(payload.get("pack_id") or "").strip().upper() != normalized_pack:
        raise PlaybackFactInvalid("playback manifest pack mismatch")
    return payload


def resolve_published_playback_episode(
    *,
    pack_id: str,
    object_id: str,
) -> dict[str, Any]:
    """Resolve one episode only from the publisher-generated manifest."""
    normalized_object = str(object_id or "").strip()
    manifest = _load_manifest(pack_id)
    episode = next(
        (
            item
            for item in manifest.get("episodes") or []
            if str(item.get("object_id") or "").strip() == normalized_object
        ),
        None,
    )
    if not isinstance(episode, dict):
        raise PlaybackFactInvalid("playback episode not published")
    duration_ms = _as_int(episode.get("duration_ms"), field="duration_ms")
    if duration_ms <= 0:
        raise PlaybackFactInvalid("published duration is invalid")
    sections = episode.get("sections")
    if not isinstance(sections, list) or not sections:
        raise PlaybackFactInvalid("published sections are unavailable")
    return episode


def normalize_playback_fact(
    payload: dict[str, Any],
    *,
    pack_id: str,
    object_id: str,
) -> dict[str, Any]:
    """Validate one low-authority browser fact against published bounds."""
    episode = resolve_published_playback_episode(
        pack_id=pack_id,
        object_id=object_id,
    )
    client_object = str(payload.get("object_id") or "").strip()
    if client_object and client_object != object_id:
        raise PlaybackFactInvalid("object_id does not match entry capability")
    content_revision = str(episode.get("content_revision") or "").strip()
    if (
        str(payload.get("content_revision") or "").strip()
        != content_revision
    ):
        raise PlaybackFactInvalid("content revision mismatch")

    action = str(payload.get("action") or "").strip()
    if action not in PLAYBACK_ACTIONS:
        raise PlaybackFactInvalid("unsupported playback action")
    event_id = str(payload.get("event_id") or "").strip()
    playback_session_id = str(payload.get("playback_session_id") or "").strip()
    if _EVENT_ID.fullmatch(event_id) is None:
        raise PlaybackFactInvalid("invalid event_id")
    if _SESSION_ID.fullmatch(playback_session_id) is None:
        raise PlaybackFactInvalid("invalid playback_session_id")
    sequence = _as_int(payload.get("sequence"), field="sequence")
    if sequence < 1 or sequence > _MAX_SEQUENCE:
        raise PlaybackFactInvalid("sequence out of range")

    duration_ms = _as_int(episode.get("duration_ms"), field="duration_ms")
    positions = {
        field: _as_int(payload.get(field) or 0, field=field)
        for field in ("position_ms", "from_position_ms", "to_position_ms")
    }
    max_position = duration_ms + _POSITION_TOLERANCE_MS
    if any(value < 0 or value > max_position for value in positions.values()):
        raise PlaybackFactInvalid("playback position out of range")
    watched_delta_ms = _as_int(
        payload.get("watched_delta_ms") or 0,
        field="watched_delta_ms",
    )
    if not 0 <= watched_delta_ms <= _MAX_WATCHED_DELTA_MS:
        raise PlaybackFactInvalid("watched_delta_ms out of range")
    if action != "checkpoint" and watched_delta_ms:
        raise PlaybackFactInvalid(f"{action} cannot claim watched time")
    if action == "checkpoint" and watched_delta_ms <= 0:
        raise PlaybackFactInvalid("checkpoint requires watched time")

    section_id = str(payload.get("section") or "").strip()
    section = next(
        (
            item
            for item in episode.get("sections") or []
            if str(item.get("id") or "").strip() == section_id
        ),
        None,
    )
    if not isinstance(section, dict):
        raise PlaybackFactInvalid("section is not published for this episode")
    section_start = _as_int(section.get("start_ms"), field="section.start_ms")
    section_end = _as_int(section.get("end_ms"), field="section.end_ms")
    if section_start < 0 or section_end <= section_start or section_end > duration_ms:
        raise PlaybackFactInvalid("published section bounds are invalid")
    if (
        action not in {"seek", "exit"}
        and not section_start - _POSITION_TOLERANCE_MS
        <= positions["position_ms"]
        <= section_end + _POSITION_TOLERANCE_MS
    ):
        raise PlaybackFactInvalid("position does not match section")
    if action == "checkpoint":
        if (
            positions["to_position_ms"] != positions["position_ms"]
            or positions["to_position_ms"] < positions["from_position_ms"]
            or (
                positions["to_position_ms"] - positions["from_position_ms"]
                != watched_delta_ms
            )
        ):
            raise PlaybackFactInvalid(
                "checkpoint interval does not match watched time"
            )
        if (
            positions["from_position_ms"] < section_start
            or positions["to_position_ms"] > section_end
        ):
            raise PlaybackFactInvalid(
                "checkpoint interval crosses a section boundary"
            )

    reason = str(payload.get("reason") or "").strip()[:32]
    if reason not in {
        "",
        "auto",
        "chip",
        "scrub",
        "user",
        "visibility",
        "pagehide",
        "unmount",
        "ask",
        "ended",
    }:
        raise PlaybackFactInvalid("unsupported playback reason")
    progress_pct = min(
        100,
        max(0, round(positions["position_ms"] * 100 / duration_ms)),
    )
    section_progress_pct = min(
        100,
        max(
            0,
            round(
                (positions["position_ms"] - section_start)
                * 100
                / (section_end - section_start)
            ),
        ),
    )
    return {
        "event_id": event_id,
        "action": action,
        "playback_session_id": playback_session_id,
        "sequence": sequence,
        "object_id": object_id,
        "section": section_id,
        "content_revision": content_revision,
        "lesson_file": str(episode.get("lesson_file") or ""),
        "position_ms": positions["position_ms"],
        "from_position_ms": positions["from_position_ms"],
        "to_position_ms": positions["to_position_ms"],
        "watched_delta_ms": watched_delta_ms,
        "duration_ms": duration_ms,
        "progress_pct": progress_pct,
        "section_index": _as_int(section.get("index"), field="section.index"),
        "section_label": str(section.get("label") or "")[:80],
        "section_group": str(section.get("group") or "")[:32],
        "section_start_ms": section_start,
        "section_end_ms": section_end,
        "section_progress_pct": section_progress_pct,
        "reason": reason,
    }


__all__ = [
    "PLAYBACK_ACTIONS",
    "PlaybackFactInvalid",
    "normalize_playback_fact",
    "resolve_published_playback_episode",
]
