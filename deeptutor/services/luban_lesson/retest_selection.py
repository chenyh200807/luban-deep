from __future__ import annotations

import hashlib
import json
import re

from deeptutor.services.learner_state.attempt_refs import (
    sign_attempt_ref,
    verify_attempt_ref,
)


def issue_retest_selection(
    *,
    user_id: str,
    pack_id: str,
    day_index: int,
    mode: str,
    variant_ids: list[str],
    supply_kind: str,
    supply_digest: str,
) -> str:
    if not _valid_supply(supply_kind, supply_digest):
        raise ValueError("retest_selection_supply_invalid")
    digest = _selection_digest(
        pack_id=pack_id,
        day_index=day_index,
        mode=mode,
        variant_ids=variant_ids,
        supply_kind=supply_kind,
        supply_digest=supply_digest,
    )
    return sign_attempt_ref(
        user_id=user_id,
        event_id=f"luban_retest_selection:{digest}",
        question_id="luban_retest_selection.v2",
    )


def verify_retest_selection(
    token: str,
    *,
    user_id: str,
    pack_id: str,
    day_index: int,
    mode: str,
    variant_ids: list[str],
    supply_kind: str,
    supply_digest: str,
) -> bool:
    verified = verify_attempt_ref(token, user_id=user_id)
    if (
        not verified
        or verified.get("question_id") != "luban_retest_selection.v2"
        or not _valid_supply(supply_kind, supply_digest)
    ):
        return False
    digest = _selection_digest(
        pack_id=pack_id,
        day_index=day_index,
        mode=mode,
        variant_ids=variant_ids,
        supply_kind=supply_kind,
        supply_digest=supply_digest,
    )
    return verified.get("event_id") == f"luban_retest_selection:{digest}"


def _selection_digest(
    *,
    pack_id: str,
    day_index: int,
    mode: str,
    variant_ids: list[str],
    supply_kind: str,
    supply_digest: str,
) -> str:
    body = {
        "pack_id": str(pack_id or "").strip().upper(),
        "day_index": int(day_index),
        "mode": "forward" if str(mode or "").strip().lower() == "forward" else "review",
        "variant_ids": sorted(str(item or "").strip() for item in variant_ids if str(item or "").strip()),
        "supply_kind": str(supply_kind or "").strip(),
        "supply_digest": str(supply_digest or "").strip(),
        "version": 2,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_supply(kind: str, digest: str) -> bool:
    return str(kind or "").strip() in {"compiled_html", "signed_variant"} and bool(
        re.fullmatch(r"[0-9a-f]{64}", str(digest or "").strip())
    )


__all__ = ["issue_retest_selection", "verify_retest_selection"]
