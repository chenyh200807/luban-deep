from __future__ import annotations

from typing import Any


RELEASE_IDENTITY_FIELDS = (
    "release_id",
    "git_sha",
    "deployment_environment",
    "prompt_version",
    "ff_snapshot_hash",
    "deploy_manifest_hash",
    "git_dirty",
)
RUNTIME_AUTHORITY_FIELDS = (
    "git_sha",
    "deployment_environment",
    "ff_snapshot_hash",
    "deploy_manifest_hash",
)


def release_identity_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    expected_values = [str((expected or {}).get(field) or "").strip() for field in RELEASE_IDENTITY_FIELDS]
    actual_values = [str((actual or {}).get(field) or "").strip() for field in RELEASE_IDENTITY_FIELDS]
    return all(expected_values) and all(actual_values) and expected_values == actual_values


def evaluate_runtime_authority(
    *,
    expected_release: dict[str, Any],
    metrics_snapshot: dict[str, Any] | None,
    metrics_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = metrics_snapshot if isinstance(metrics_snapshot, dict) else {}
    runtime_release = snapshot.get("release") if isinstance(snapshot.get("release"), dict) else {}
    provenance = (
        dict(snapshot.get("observability_metrics_provenance") or {})
        if snapshot
        else dict(metrics_error or {})
    )
    mismatched_fields = [
        field
        for field in RUNTIME_AUTHORITY_FIELDS
        if not str((expected_release or {}).get(field) or "").strip()
        or str((expected_release or {}).get(field) or "").strip()
        != str((runtime_release or {}).get(field) or "").strip()
    ]
    candidate_clean = str((expected_release or {}).get("git_dirty") or "").strip().lower() == "false"
    runtime_clean = str((runtime_release or {}).get("git_dirty") or "").strip().lower() == "false"
    live_source = (
        provenance.get("source") == "live_metrics_endpoint"
        and provenance.get("fallback_used") is False
    )
    if metrics_error:
        status = "BLOCKED"
        reason = "live metrics could not be read; runtime authority is unknown"
    elif not live_source:
        status = "ARTIFACT_ONLY"
        reason = "metrics source is not a non-fallback live endpoint"
    elif mismatched_fields or not candidate_clean or not runtime_clean:
        status = "BLOCKED"
        reason = "live runtime identity does not match the clean candidate"
    else:
        status = "PASS"
        reason = "live runtime identity matches the clean candidate"
    return {
        "status": status,
        "matched": not mismatched_fields,
        "runtime_identity_matched": not mismatched_fields,
        "live_identity_verified": status == "PASS",
        "expected_release": dict(expected_release or {}),
        "runtime_release": dict(runtime_release or {}),
        "metrics_provenance": provenance,
        "mismatched_fields": mismatched_fields,
        "candidate_clean": candidate_clean,
        "runtime_clean": runtime_clean,
        "reason": reason,
    }
