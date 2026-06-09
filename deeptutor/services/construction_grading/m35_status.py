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
