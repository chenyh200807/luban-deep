from __future__ import annotations

import hashlib
import json

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
) -> str:
    digest = _selection_digest(
        pack_id=pack_id,
        day_index=day_index,
        mode=mode,
        variant_ids=variant_ids,
    )
    return sign_attempt_ref(
        user_id=user_id,
        event_id=f"luban_retest_selection:{digest}",
        question_id="luban_retest_selection.v1",
    )


def verify_retest_selection(
    token: str,
    *,
    user_id: str,
    pack_id: str,
    day_index: int,
    mode: str,
    variant_ids: list[str],
) -> bool:
    verified = verify_attempt_ref(token, user_id=user_id)
    if not verified or verified.get("question_id") != "luban_retest_selection.v1":
        return False
    digest = _selection_digest(
        pack_id=pack_id,
        day_index=day_index,
        mode=mode,
        variant_ids=variant_ids,
    )
    return verified.get("event_id") == f"luban_retest_selection:{digest}"


def _selection_digest(
    *,
    pack_id: str,
    day_index: int,
    mode: str,
    variant_ids: list[str],
) -> str:
    body = {
        "pack_id": str(pack_id or "").strip().upper(),
        "day_index": int(day_index),
        "mode": "forward" if str(mode or "").strip().lower() == "forward" else "review",
        "variant_ids": sorted(str(item or "").strip() for item in variant_ids if str(item or "").strip()),
        "version": 1,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = ["issue_retest_selection", "verify_retest_selection"]
