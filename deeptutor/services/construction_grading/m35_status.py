from __future__ import annotations

from typing import Any


_V0_TO_M35 = {
    "published": "release_candidate",
    "draft": "shadow_candidate",
    "blocked": "blocked",
}


def m35_runtime_status_from_v0(artifact: dict[str, Any]) -> dict[str, Any]:
    legacy = str(artifact.get("status") or "").strip()
    return {
        "legacy_artifact_status": legacy,
        "m35_runtime_status": _V0_TO_M35.get(legacy, "blocked"),
        "official_score_allowed": False,
        "published_registry_authority": False,
    }


def official_score_allowed_for_m35(
    *,
    server_governed_registry_status: str,
    client_supplied_status: str,
    artifact_status: str,
) -> bool:
    _ = client_supplied_status, artifact_status
    return str(server_governed_registry_status or "").strip() == "published"


def m35_artifact_shadow_blocked(
    *,
    status_map: dict[str, Any],
    quality_gates: dict[str, Any],
) -> bool:
    """Single authority for "may this artifact be shadow-graded at all".

    Blocked status, score-sum mismatch, source pollution, or any compiler
    blocked_reason means the artifact must fail open: no point judging, no
    shadow score, only a work order.
    """
    if status_map.get("m35_runtime_status") == "blocked":
        return True
    if quality_gates.get("score_sum_ok") is False:
        return True
    try:
        if int(quality_gates.get("source_pollution_count") or 0) > 0:
            return True
    except (TypeError, ValueError):
        return True
    return bool(quality_gates.get("blocked_reasons"))


def m35_kill_switch_active() -> bool:
    """``LUBAN_M35_ARTIFACT_SHADOW_ENABLED`` set to an explicit false value
    force-disables every M35 shadow entry point, including internal kernel calls."""
    import os

    return os.environ.get("LUBAN_M35_ARTIFACT_SHADOW_ENABLED", "").strip().lower() in (
        "false",
        "0",
        "off",
        "no",
    )
