from __future__ import annotations

import json

import pytest

from deeptutor.services.observability.evidence_bundle import (
    REQUIRED_COMPLETE_RECORDS,
    load_evidence_bundle,
    write_evidence_bundle,
)

RELEASE = {
    "release_id": "1.0.0+abc123+ff1",
    "service_version": "1.0.0",
    "git_sha": "abc123",
    "deployment_environment": "qa",
    "prompt_version": "git-abc123",
    "ff_snapshot_hash": "ff1",
    "git_dirty": "false",
    "deploy_manifest_hash": "manifest1",
}


def _complete_payloads() -> dict[str, dict]:
    return {
        kind: {"run_id": f"{kind}-1", "release": RELEASE}
        for kind in REQUIRED_COMPLETE_RECORDS
    }


def _live_authority() -> dict:
    return {
        "status": "PASS",
        "live_identity_verified": True,
        "expected_release": RELEASE,
        "runtime_release": RELEASE,
        "metrics_provenance": {
            "source": "live_metrics_endpoint",
            "fallback_used": False,
        },
    }


def test_blocked_bundle_is_self_contained_and_has_no_downstream_records(tmp_path) -> None:
    path = write_evidence_bundle(
        output_dir=tmp_path,
        status="BLOCKED",
        release=RELEASE,
        runtime_authority={"status": "BLOCKED", "reason": "metrics unavailable"},
        api_base_url="https://qa.example.test/",
        source_store_uri="file:///runtime/control-plane",
    )

    loaded = load_evidence_bundle(path)

    assert loaded["status"] == "BLOCKED"
    assert loaded["records"] == {}
    assert loaded["execution_surface"]["api_base_url"] == "https://qa.example.test"


def test_complete_bundle_detects_payload_tampering_and_lineage_drift(tmp_path) -> None:
    path = write_evidence_bundle(
        output_dir=tmp_path,
        status="COMPLETE",
        release=RELEASE,
        runtime_authority=_live_authority(),
        api_base_url="https://qa.example.test",
        source_store_uri="file:///runtime/control-plane",
        payloads=_complete_payloads(),
    )
    assert load_evidence_bundle(path)["payloads"]["daily_trends"]["run_id"] == "daily_trends-1"

    manifest = json.loads(path.read_text(encoding="utf-8"))
    record_path = path.parent / manifest["records"]["daily_trends"]["path"]
    record_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_evidence_bundle(path)


def test_bundle_rejects_foreign_record_path(tmp_path) -> None:
    path = write_evidence_bundle(
        output_dir=tmp_path,
        status="COMPLETE",
        release=RELEASE,
        runtime_authority=_live_authority(),
        api_base_url="https://qa.example.test",
        source_store_uri="file:///runtime/control-plane",
        payloads=_complete_payloads(),
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["records"]["daily_trends"]["path"] = "../foreign.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes bundle"):
        load_evidence_bundle(path)


def test_complete_bundle_rejects_partial_record_set(tmp_path) -> None:
    with pytest.raises(ValueError, match="canonical record set"):
        write_evidence_bundle(
            output_dir=tmp_path,
            status="COMPLETE",
            release=RELEASE,
            runtime_authority=_live_authority(),
            api_base_url="https://qa.example.test",
            source_store_uri="file:///runtime/control-plane",
            payloads={"daily_trends": {"run_id": "daily-1", "release": RELEASE}},
        )


def test_complete_bundle_rejects_blocked_authority(tmp_path) -> None:
    with pytest.raises(ValueError, match="authority PASS"):
        write_evidence_bundle(
            output_dir=tmp_path,
            status="COMPLETE",
            release=RELEASE,
            runtime_authority={"status": "BLOCKED"},
            api_base_url="https://qa.example.test",
            source_store_uri="file:///runtime/control-plane",
            payloads=_complete_payloads(),
        )


def test_complete_bundle_rejects_foreign_benchmark_release_spine(tmp_path) -> None:
    payloads = _complete_payloads()
    payloads["benchmark_runs"] = {
        "run_manifest": {"run_id": "benchmark-1"},
        "release_spine": {**RELEASE, "git_sha": "foreign"},
    }
    with pytest.raises(ValueError, match="benchmark_runs"):
        write_evidence_bundle(
            output_dir=tmp_path,
            status="COMPLETE",
            release=RELEASE,
            runtime_authority=_live_authority(),
            api_base_url="https://qa.example.test",
            source_store_uri="file:///runtime/control-plane",
            payloads=payloads,
        )


def test_complete_bundle_rejects_fallback_or_foreign_runtime(tmp_path) -> None:
    authority = _live_authority()
    authority["metrics_provenance"] = {
        "source": "metrics_json_artifact",
        "fallback_used": True,
    }
    with pytest.raises(ValueError, match="verified live"):
        write_evidence_bundle(
            output_dir=tmp_path,
            status="COMPLETE",
            release=RELEASE,
            runtime_authority=authority,
            api_base_url="https://qa.example.test",
            source_store_uri="file:///runtime/control-plane",
            payloads=_complete_payloads(),
        )


def test_complete_bundle_rejects_missing_or_tampered_run_id(tmp_path) -> None:
    payloads = _complete_payloads()
    payloads["oa_runs"].pop("run_id")
    with pytest.raises(ValueError, match="run_id is missing: oa_runs"):
        write_evidence_bundle(
            output_dir=tmp_path,
            status="COMPLETE",
            release=RELEASE,
            runtime_authority=_live_authority(),
            api_base_url="https://qa.example.test",
            source_store_uri="file:///runtime/control-plane",
            payloads=payloads,
        )

    path = write_evidence_bundle(
        output_dir=tmp_path,
        status="COMPLETE",
        release=RELEASE,
        runtime_authority=_live_authority(),
        api_base_url="https://qa.example.test",
        source_store_uri="file:///runtime/control-plane",
        payloads=_complete_payloads(),
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["records"]["oa_runs"]["run_id"] = "forged"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="run_id mismatch: oa_runs"):
        load_evidence_bundle(path)
