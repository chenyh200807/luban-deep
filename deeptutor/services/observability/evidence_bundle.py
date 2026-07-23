from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping
import uuid

SCHEMA_ID = "deeptutor_observability_evidence_bundle.v1"
MANIFEST_FIELDS = (
    "schema_id",
    "bundle_id",
    "status",
    "generated_at_unix",
    "execution_surface",
    "release",
    "runtime_authority",
    "records",
)
RELEASE_FIELDS = (
    "release_id",
    "service_version",
    "git_sha",
    "deployment_environment",
    "prompt_version",
    "ff_snapshot_hash",
    "git_dirty",
    "deploy_manifest_hash",
)
REQUIRED_COMPLETE_RECORDS = frozenset(
    {
        "om_runs",
        "arr_runs",
        "benchmark_runs",
        "aae_composite_runs",
        "observer_snapshots",
        "change_impact_runs",
        "oa_runs",
        "plan_completion_audits",
        "readiness_checks",
        "release_gate_runs",
        "daily_trends",
    }
)
AUTHORITY_IDENTITY_FIELDS = tuple(field for field in RELEASE_FIELDS if field != "service_version")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_release(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    release = payload.get("release") or payload.get("release_spine")
    if isinstance(release, Mapping):
        return release
    run_manifest = payload.get("run_manifest")
    if isinstance(run_manifest, Mapping):
        nested = run_manifest.get("release") or run_manifest.get("release_spine")
        if isinstance(nested, Mapping):
            return nested
    return None


def _payload_run_id(payload: Mapping[str, Any]) -> str:
    run_id = str(payload.get("run_id") or "").strip()
    if run_id:
        return run_id
    run_manifest = payload.get("run_manifest")
    return str(run_manifest.get("run_id") or "").strip() if isinstance(run_manifest, Mapping) else ""


def _runtime_authority_is_live_pass(
    runtime_authority: Mapping[str, Any], release: Mapping[str, Any]
) -> bool:
    provenance = runtime_authority.get("metrics_provenance")
    expected = runtime_authority.get("expected_release")
    runtime = runtime_authority.get("runtime_release")
    return bool(
        runtime_authority.get("status") == "PASS"
        and runtime_authority.get("live_identity_verified") is True
        and isinstance(provenance, Mapping)
        and provenance.get("source") == "live_metrics_endpoint"
        and provenance.get("fallback_used") is False
        and isinstance(expected, Mapping)
        and isinstance(runtime, Mapping)
        and all(expected.get(field) == release.get(field) for field in AUTHORITY_IDENTITY_FIELDS)
        and all(runtime.get(field) == release.get(field) for field in AUTHORITY_IDENTITY_FIELDS)
    )


def write_evidence_bundle(
    *,
    output_dir: Path,
    status: str,
    release: Mapping[str, Any],
    runtime_authority: Mapping[str, Any],
    api_base_url: str,
    source_store_uri: str,
    payloads: Mapping[str, Mapping[str, Any]] | None = None,
) -> Path:
    """Write one immutable, self-contained cross-surface evidence handoff.

    This is deliberately not an importer into another runtime's control-plane
    store. The manifest is the authority for transport; the source store remains
    the authority for the runtime that produced the evidence.
    """
    normalized_status = str(status).upper()
    if normalized_status not in {"BLOCKED", "COMPLETE"}:
        raise ValueError(f"unsupported evidence bundle status: {status!r}")
    release_snapshot = {field: release.get(field, "") for field in RELEASE_FIELDS}
    if any(not str(release_snapshot[field]).strip() for field in RELEASE_FIELDS):
        raise ValueError("release lineage must contain the complete non-empty runtime spine")
    if normalized_status == "BLOCKED" and payloads:
        raise ValueError("BLOCKED evidence bundle cannot contain downstream payloads")
    if normalized_status == "COMPLETE" and set(payloads or {}) != REQUIRED_COMPLETE_RECORDS:
        raise ValueError("COMPLETE evidence bundle must contain the canonical record set")
    if normalized_status == "COMPLETE" and not _runtime_authority_is_live_pass(
        runtime_authority, release_snapshot
    ):
        raise ValueError("COMPLETE evidence bundle requires verified live runtime authority PASS")

    bundle_id = f"observability-{int(time.time())}-{uuid.uuid4().hex[:12]}"
    bundle_dir = output_dir / "evidence_bundles" / bundle_id
    records_dir = bundle_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=False)

    records: dict[str, dict[str, Any]] = {}
    for kind, payload in sorted((payloads or {}).items()):
        payload_release = _payload_release(payload)
        if normalized_status == "COMPLETE" and (
            payload_release is None
            or any(payload_release.get(field) != release_snapshot[field] for field in RELEASE_FIELDS)
        ):
            raise ValueError(f"payload release lineage mismatch: {kind}")
        payload_run_id = _payload_run_id(payload)
        if normalized_status == "COMPLETE" and not payload_run_id:
            raise ValueError(f"payload run_id is missing: {kind}")
        data = _json_bytes(payload)
        relative_path = Path("records") / f"{kind}.json"
        (bundle_dir / relative_path).write_bytes(data)
        records[kind] = {
            "path": relative_path.as_posix(),
            "sha256": _sha256(data),
            "run_id": payload_run_id,
        }

    manifest = {
        "schema_id": SCHEMA_ID,
        "bundle_id": bundle_id,
        "status": normalized_status,
        "generated_at_unix": int(time.time()),
        "execution_surface": {
            "deployment_environment": release_snapshot["deployment_environment"],
            "api_base_url": str(api_base_url).rstrip("/"),
            "source_store_uri": source_store_uri,
        },
        "release": release_snapshot,
        "runtime_authority": dict(runtime_authority),
        "records": records,
    }
    manifest_path = bundle_dir / "manifest.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(manifest_path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(_json_bytes(manifest))
    return manifest_path


def load_evidence_bundle(manifest_path: Path) -> dict[str, Any]:
    """Validate hashes and lineage before an automation consumes a bundle."""
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_id") != SCHEMA_ID:
        raise ValueError("unsupported evidence bundle format")
    status = manifest.get("status")
    if status not in {"BLOCKED", "COMPLETE"}:
        raise ValueError("invalid evidence bundle status")
    release = manifest.get("release") or {}
    if any(field not in release or not str(release[field]).strip() for field in RELEASE_FIELDS):
        raise ValueError("incomplete release lineage")
    records = manifest.get("records") or {}
    if status == "BLOCKED" and records:
        raise ValueError("BLOCKED evidence bundle contains downstream payloads")
    if status == "COMPLETE" and set(records) != REQUIRED_COMPLETE_RECORDS:
        raise ValueError("COMPLETE evidence bundle is missing canonical records")
    if status == "COMPLETE" and not _runtime_authority_is_live_pass(
        manifest.get("runtime_authority") or {}, release
    ):
        raise ValueError("COMPLETE evidence bundle requires verified live runtime authority PASS")
    bundle_dir = manifest_path.parent
    loaded: dict[str, Any] = {}
    for kind, record in records.items():
        path = (bundle_dir / str(record.get("path") or "")).resolve()
        if path.parent != (bundle_dir / "records").resolve():
            raise ValueError(f"record path escapes bundle: {kind}")
        data = path.read_bytes()
        if _sha256(data) != record.get("sha256"):
            raise ValueError(f"record hash mismatch: {kind}")
        payload = json.loads(data)
        payload_run_id = _payload_run_id(payload)
        if status == "COMPLETE" and (
            not str(record.get("run_id") or "").strip()
            or record.get("run_id") != payload_run_id
        ):
            raise ValueError(f"record run_id mismatch: {kind}")
        payload_release = _payload_release(payload)
        if status == "COMPLETE" and (
            payload_release is None
            or any(payload_release.get(field) != release.get(field) for field in RELEASE_FIELDS)
        ):
            raise ValueError(f"record release lineage mismatch: {kind}")
        loaded[kind] = payload
    manifest["payloads"] = loaded
    return manifest
