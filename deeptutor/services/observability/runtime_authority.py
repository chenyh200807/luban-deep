from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

RELEASE_IDENTITY_FIELDS = (
    "release_id",
    "service_version",
    "git_sha",
    "deployment_environment",
    "prompt_version",
    "ff_snapshot_hash",
    "deploy_manifest_hash",
    "git_dirty",
)
RUNTIME_AUTHORITY_FIELDS = RELEASE_IDENTITY_FIELDS
_GOVERNED_ENVIRONMENTS = {"aliyun", "prod", "production", "qa", "staging", "test2"}
_DEPLOY_MANIFEST_PATTERN = re.compile(r"^[0-9a-f]{12,64}$")


def release_identity_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    required_fields = tuple(field for field in RELEASE_IDENTITY_FIELDS if field != "service_version")
    expected_values = [str((expected or {}).get(field) or "").strip() for field in required_fields]
    actual_values = [str((actual or {}).get(field) or "").strip() for field in required_fields]
    expected_service_version = str((expected or {}).get("service_version") or "").strip()
    actual_service_version = str((actual or {}).get("service_version") or "").strip()
    service_version_matches = (
        expected_service_version == actual_service_version
        and (
            bool(expected_service_version)
            or (
                "service_version" not in (expected or {})
                and "service_version" not in (actual or {})
            )
        )
    )
    return (
        all(expected_values)
        and all(actual_values)
        and expected_values == actual_values
        and service_version_matches
    )


def evaluate_runtime_authority(
    *,
    expected_release: dict[str, Any],
    metrics_snapshot: dict[str, Any] | None,
    metrics_error: dict[str, Any] | None = None,
    expected_metrics_url: str | None = None,
    governed_metrics_urls: tuple[str, ...] = (),
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
    runtime_environment = str((runtime_release or {}).get("deployment_environment") or "").strip().lower()
    runtime_manifest = str((runtime_release or {}).get("deploy_manifest_hash") or "").strip().lower()
    governed_runtime = (
        runtime_environment in _GOVERNED_ENVIRONMENTS
        and _DEPLOY_MANIFEST_PATTERN.fullmatch(runtime_manifest) is not None
    )
    metrics_url = str(provenance.get("url") or "").strip()
    parsed_metrics_url = urlparse(metrics_url)
    governed_target = metrics_url in {
        str(item or "").strip()
        for item in governed_metrics_urls
        if str(item or "").strip()
    }
    live_source = (
        provenance.get("source") == "live_metrics_endpoint"
        and provenance.get("fallback_used") is False
        and provenance.get("status_code") == 200
        and parsed_metrics_url.scheme in {"http", "https"}
        and bool(parsed_metrics_url.netloc)
        and parsed_metrics_url.path.rstrip("/").endswith("/metrics")
        and (
            not expected_metrics_url
            or metrics_url == str(expected_metrics_url).strip()
        )
    )
    if metrics_error:
        status = "BLOCKED"
        reason = "live metrics could not be read; runtime authority is unknown"
    elif not live_source:
        status = "ARTIFACT_ONLY"
        reason = "metrics source is not a non-fallback live endpoint"
    elif not governed_target:
        status = "ARTIFACT_ONLY"
        reason = "metrics target is not registered as a governed runtime endpoint"
    elif mismatched_fields or not candidate_clean or not runtime_clean or not governed_runtime:
        status = "BLOCKED"
        reason = (
            "live runtime is not a governed deployment"
            if not governed_runtime
            else "live runtime identity does not match the clean candidate"
        )
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
        "governed_runtime": governed_runtime,
        "governed_target": governed_target,
        "reason": reason,
    }
