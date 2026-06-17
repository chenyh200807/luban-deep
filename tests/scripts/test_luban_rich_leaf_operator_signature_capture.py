from __future__ import annotations

import json
from pathlib import Path

OWNER_STATEMENT = "authorized_by_owner_20260613, scope: rich-leaf frozen v1 controlled default"
SIGNED_AT = "2026-06-13T00:00:00+08:00"


def _authorization_package() -> dict:
    return {
        "schema": "luban_rich_leaf_controlled_default_authorization_package.v1",
        "verdict": "READY_FOR_OPERATOR_SIGNATURE",
        "quality_claim_allowed": False,
        "input_line": "frozen_v1",
        "authorization_decision": {
            "operator_signature_recorded": False,
            "controlled_default_authorized": False,
            "default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "production_db_write_allowed": False,
            "remote_write_allowed": False,
            "release_truth_authorized": False,
        },
        "candidate_scope": {
            "runtime_token_pack_unit_count": 1534,
            "supply_unit_count": 1513,
            "streaming_sample_count": 16,
            "streaming_provider_call_count": 32,
            "streaming_ttft_delta_ms": -43.57,
            "semantic_live_ab_verdict": "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB",
        },
        "summary": {
            "blocker_count": 0,
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "remote_write_count": 0,
        },
    }


def _signed_template() -> dict:
    return {
        "schema": "luban_rich_leaf_signed_authorization_template.v1",
        "verdict": "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE",
        "signature_templates": {
            "controlled_default_operator": {
                "template_id": "rich_leaf_controlled_default_operator_signature_v1",
                "signature_status": "unsigned",
                "required_signer_role": "operator_or_governance_owner",
            },
        },
    }


def test_operator_signature_capture_produces_bound_signed_record() -> None:
    from scripts.run_luban_rich_leaf_operator_signature_capture import (
        content_hash,
        run_operator_signature_capture,
    )

    package = _authorization_package()
    report = run_operator_signature_capture(
        authorization_package=package,
        signed_template=_signed_template(),
        operator_id="owner",
        statement=OWNER_STATEMENT,
        signed_at=SIGNED_AT,
    )

    assert report["schema"] == "luban_rich_leaf_operator_signature_record.v1"
    assert report["verdict"] == "OPERATOR_SIGNATURE_CAPTURED"
    assert report["blockers"] == []
    signature = report["signature"]
    assert signature["signature_status"] == "signed"
    assert signature["template_id"] == "rich_leaf_controlled_default_operator_signature_v1"
    assert signature["required_signer_role"] == "operator_or_governance_owner"
    assert signature["operator_id"] == "owner"
    assert signature["statement"] == OWNER_STATEMENT
    assert signature["signed_at"] == SIGNED_AT
    binding = report["authorization_binding"]
    assert binding["authorization_package_content_hash"] == content_hash(package)
    assert binding["authorization_package_schema"] == "luban_rich_leaf_controlled_default_authorization_package.v1"
    assert binding["authorization_package_verdict"] == "READY_FOR_OPERATOR_SIGNATURE"
    # the signature grants controlled-default operator signature only; it mints no write authority
    granted = report["granted_scope"]
    assert granted["controlled_default_operator_signature"] is True
    assert granted["runtime_default_install_allowed"] is False
    assert granted["canonical_pointer_write_allowed"] is False
    assert granted["production_db_write_allowed"] is False
    assert granted["remote_write_allowed"] is False
    assert granted["release_truth_allowed"] is False
    assert report["summary"]["write_executed"] is False
    assert report["summary"]["production_write_count"] == 0
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["operator_signature_record"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["production_default"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["safety"]["canonical_truth_written"] is False
    assert report["safety"]["release_truth_claimed"] is False


def test_operator_signature_capture_blocks_when_package_not_ready() -> None:
    from scripts.run_luban_rich_leaf_operator_signature_capture import run_operator_signature_capture

    package = _authorization_package()
    package["verdict"] = "BLOCKED"
    report = run_operator_signature_capture(
        authorization_package=package,
        signed_template=_signed_template(),
        operator_id="owner",
        statement=OWNER_STATEMENT,
        signed_at=SIGNED_AT,
    )

    assert report["verdict"] == "BLOCKED_SIGNATURE_NOT_CAPTURED"
    assert report["signature"]["signature_status"] == "not_captured"
    assert "authorization_package_not_ready:BLOCKED" in report["blockers"]


def test_operator_signature_capture_blocks_on_package_safety_drift() -> None:
    from scripts.run_luban_rich_leaf_operator_signature_capture import run_operator_signature_capture

    package = _authorization_package()
    package["authorization_decision"]["default_install_allowed"] = True
    report = run_operator_signature_capture(
        authorization_package=package,
        signed_template=_signed_template(),
        operator_id="owner",
        statement=OWNER_STATEMENT,
        signed_at=SIGNED_AT,
    )

    assert report["verdict"] == "BLOCKED_SIGNATURE_NOT_CAPTURED"
    assert "authorization_package:default_install_allowed_true" in report["blockers"]


def test_operator_signature_capture_blocks_on_missing_identity_or_bad_timestamp() -> None:
    from scripts.run_luban_rich_leaf_operator_signature_capture import run_operator_signature_capture

    report = run_operator_signature_capture(
        authorization_package=_authorization_package(),
        signed_template=_signed_template(),
        operator_id="  ",
        statement="",
        signed_at="not-a-timestamp",
    )

    assert report["verdict"] == "BLOCKED_SIGNATURE_NOT_CAPTURED"
    assert "operator_id_missing" in report["blockers"]
    assert "statement_missing" in report["blockers"]
    assert "signed_at_not_iso8601:not-a-timestamp" in report["blockers"]


def test_operator_signature_capture_blocks_on_template_not_ready() -> None:
    from scripts.run_luban_rich_leaf_operator_signature_capture import run_operator_signature_capture

    template = _signed_template()
    template["verdict"] = "BLOCKED_INPUT_SAFETY_INVARIANT"
    report = run_operator_signature_capture(
        authorization_package=_authorization_package(),
        signed_template=template,
        operator_id="owner",
        statement=OWNER_STATEMENT,
        signed_at=SIGNED_AT,
    )

    assert report["verdict"] == "BLOCKED_SIGNATURE_NOT_CAPTURED"
    assert "signed_template_not_ready:BLOCKED_INPUT_SAFETY_INVARIANT" in report["blockers"]


def test_operator_signature_capture_cli_writes_record(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_operator_signature_capture import main

    package_path = tmp_path / "authorization_package.json"
    template_path = tmp_path / "signed_template.json"
    output = tmp_path / "operator_signature_record.json"
    package_path.write_text(json.dumps(_authorization_package(), ensure_ascii=False), encoding="utf-8")
    template_path.write_text(json.dumps(_signed_template(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--authorization-package",
            str(package_path),
            "--signed-template",
            str(template_path),
            "--operator",
            "owner",
            "--statement",
            OWNER_STATEMENT,
            "--signed-at",
            SIGNED_AT,
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["verdict"] == "OPERATOR_SIGNATURE_CAPTURED"
    assert payload["signature"]["operator_id"] == "owner"
    assert payload["summary"]["write_executed"] is False
