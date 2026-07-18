from __future__ import annotations

from typing import Any
import uuid


def canonical_event_id(value: Any) -> str:
    """Return the one learner-state identity form for an event reference.

    UUID-shaped identifiers are represented as lowercase compact hex. Opaque
    identifiers remain opaque; only surrounding whitespace is removed.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return uuid.UUID(raw).hex
    except (AttributeError, ValueError):
        return raw


__all__ = ["canonical_event_id"]
