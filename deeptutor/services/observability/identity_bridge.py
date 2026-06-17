"""Bridge trace identities to BI member identities without owning member truth."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe_trace_identity(value: str) -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digest = hashlib.sha256(digits.encode("utf-8")).hexdigest()[:12]
        return f"phone:{digest}:last4:{digits[-4:]}"
    return raw


def enrich_trace_metadata_with_bi_identity(
    metadata: dict[str, Any],
    *,
    member_service: Any | None = None,
) -> dict[str, Any]:
    raw_user_id = str(metadata.get("user_id") or "").strip()
    if raw_user_id:
        metadata.setdefault("raw_user_id", _safe_trace_identity(raw_user_id))

    try:
        if member_service is None:
            from deeptutor.services.member_console import get_member_console_service

            member_service = get_member_console_service()
        resolver = getattr(member_service, "resolve_trace_identity_for_bi", None)
        if not callable(resolver):
            return metadata
        resolution = resolver(raw_user_id=raw_user_id, metadata=metadata)
    except Exception:
        logger.warning("Failed to resolve trace identity against BI member authority", exc_info=True)
        return metadata

    status = str(resolution.get("status") or "").strip() or "unmapped"
    metadata["identity_resolution_status"] = status
    metadata["identity_resolution_source"] = "member_console"

    canonical_user_id = str(resolution.get("canonical_user_id") or "").strip()
    if status == "resolved" and canonical_user_id:
        metadata["user_id"] = canonical_user_id
        member_user_id = str(resolution.get("member_user_id") or "").strip()
        if member_user_id:
            metadata["member_user_id"] = member_user_id
        matched_identity = str(resolution.get("matched_identity") or "").strip()
        if matched_identity:
            metadata["identity_matched"] = _safe_trace_identity(matched_identity)

    return metadata
