from __future__ import annotations

import base64
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
    probe_id: str = "",
    cycle_anchor: str = "",
) -> str:
    if not _valid_supply(supply_kind, supply_digest):
        raise ValueError("retest_selection_supply_invalid")
    normalized_mode, normalized_probe, normalized_cycle = _probe_cycle_identity(
        mode=mode,
        probe_id=probe_id,
        cycle_anchor=cycle_anchor,
    )
    body = _selection_body(
        pack_id=pack_id,
        day_index=day_index,
        mode=normalized_mode,
        variant_ids=variant_ids,
        supply_kind=supply_kind,
        supply_digest=supply_digest,
        probe_id=normalized_probe,
        cycle_anchor=normalized_cycle,
    )
    encoded = base64.urlsafe_b64encode(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return sign_attempt_ref(
        user_id=user_id,
        event_id=f"luban_retest_selection.v3:{encoded}",
        question_id="luban_retest_selection.v3",
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
    probe_id: str = "",
    cycle_anchor: str = "",
) -> bool:
    try:
        normalized_mode, normalized_probe, normalized_cycle = _probe_cycle_identity(
            mode=mode,
            probe_id=probe_id,
            cycle_anchor=cycle_anchor,
        )
    except ValueError:
        return False
    decoded = decode_retest_selection(token, user_id=user_id)
    if decoded is None or not _valid_supply(supply_kind, supply_digest):
        return False
    expected = _selection_body(
        pack_id=pack_id,
        day_index=day_index,
        mode=normalized_mode,
        variant_ids=variant_ids,
        supply_kind=supply_kind,
        supply_digest=supply_digest,
        probe_id=normalized_probe,
        cycle_anchor=normalized_cycle,
    )
    return decoded == expected


def decode_retest_selection(token: str, *, user_id: str) -> dict[str, object] | None:
    verified = verify_attempt_ref(token, user_id=user_id)
    if not verified or verified.get("question_id") != "luban_retest_selection.v3":
        return None
    event_id = str(verified.get("event_id") or "")
    prefix = "luban_retest_selection.v3:"
    if not event_id.startswith(prefix):
        return None
    try:
        encoded = event_id[len(prefix) :]
        raw = base64.urlsafe_b64decode((encoded + "=" * (-len(encoded) % 4)).encode("ascii"))
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(body, dict) or set(body) != {
        "pack_id",
        "day_index",
        "mode",
        "variant_ids",
        "supply_kind",
        "supply_digest",
        "probe_id",
        "cycle_anchor",
        "version",
    }:
        return None
    try:
        canonical = _selection_body(
            pack_id=str(body.get("pack_id") or ""),
            day_index=int(body.get("day_index")),
            mode=str(body.get("mode") or ""),
            variant_ids=list(body.get("variant_ids") or []),
            supply_kind=str(body.get("supply_kind") or ""),
            supply_digest=str(body.get("supply_digest") or ""),
            probe_id=str(body.get("probe_id") or ""),
            cycle_anchor=str(body.get("cycle_anchor") or ""),
        )
    except (TypeError, ValueError):
        return None
    return canonical if body == canonical else None


def _selection_body(
    *,
    pack_id: str,
    day_index: int,
    mode: str,
    variant_ids: list[str],
    supply_kind: str,
    supply_digest: str,
    probe_id: str = "",
    cycle_anchor: str = "",
) -> dict[str, object]:
    normalized_mode, normalized_probe, normalized_cycle = _probe_cycle_identity(
        mode=mode,
        probe_id=probe_id,
        cycle_anchor=cycle_anchor,
    )
    body: dict[str, object] = {
        "pack_id": str(pack_id or "").strip().upper(),
        "day_index": int(day_index),
        "mode": normalized_mode,
        "variant_ids": sorted(str(item or "").strip() for item in variant_ids if str(item or "").strip()),
        "supply_kind": str(supply_kind or "").strip(),
        "supply_digest": str(supply_digest or "").strip(),
        "probe_id": normalized_probe,
        "cycle_anchor": normalized_cycle,
        "version": 3,
    }
    if not body["pack_id"] or not body["variant_ids"] or not _valid_supply(supply_kind, supply_digest):
        raise ValueError("retest_selection_identity_invalid")
    return body


def _probe_cycle_identity(*, mode: str, probe_id: str, cycle_anchor: str) -> tuple[str, str, str]:
    normalized_mode = "forward" if str(mode or "").strip().lower() == "forward" else "review"
    normalized_probe = str(probe_id or "").strip()
    normalized_cycle = str(cycle_anchor or "").strip()
    if normalized_mode == "review":
        if not normalized_probe or not normalized_cycle:
            raise ValueError("retest_selection_probe_cycle_required")
        return normalized_mode, normalized_probe, normalized_cycle
    if normalized_probe or normalized_cycle:
        raise ValueError("retest_selection_forward_probe_cycle_forbidden")
    return normalized_mode, "", ""


def _valid_supply(kind: str, digest: str) -> bool:
    return str(kind or "").strip() in {"compiled_html", "signed_variant"} and bool(
        re.fullmatch(r"[0-9a-f]{64}", str(digest or "").strip())
    )


__all__ = ["decode_retest_selection", "issue_retest_selection", "verify_retest_selection"]
