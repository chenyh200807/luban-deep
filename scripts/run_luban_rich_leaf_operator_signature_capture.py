#!/usr/bin/env python3
"""Capture a typed operator signature bound to a controlled-default authorization package.

The record attests an operator signature for the controlled-default scope only.
It mints no install/write authority: every write-allow flag stays False and the
release-governance packet consumes the record solely to resolve its
``operator_signature_missing`` / ``controlled_default_authorization_missing``
blockers when the content-hash binding verifies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "luban_rich_leaf_operator_signature_record.v1"
AUTHORIZATION_PACKAGE_SCHEMA = "luban_rich_leaf_controlled_default_authorization_package.v1"
SIGNED_TEMPLATE_SCHEMA = "luban_rich_leaf_signed_authorization_template.v1"
TEMPLATE_ID = "rich_leaf_controlled_default_operator_signature_v1"
REQUIRED_SIGNER_ROLE = "operator_or_governance_owner"


def content_hash(payload: dict[str, Any]) -> str:
    """Canonical sha256 over a parsed JSON payload (sorted keys, compact separators)."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _package_blockers(payload: dict[str, Any]) -> list[str]:
    """Full safety-invariant check on the authorization package (mirrors the signed template gate)."""
    blockers: list[str] = []
    if payload.get("schema") != AUTHORIZATION_PACKAGE_SCHEMA:
        blockers.append(f"authorization_package_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_OPERATOR_SIGNATURE":
        blockers.append(f"authorization_package_not_ready:{payload.get('verdict')}")
    decision = payload.get("authorization_decision") if isinstance(payload.get("authorization_decision"), dict) else {}
    for field in (
        "operator_signature_recorded",
        "controlled_default_authorized",
        "default_install_allowed",
        "canonical_pointer_write_allowed",
        "production_db_write_allowed",
        "remote_write_allowed",
        "release_truth_authorized",
    ):
        if decision.get(field) is not False:
            blockers.append(f"authorization_package:{field}_true")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if bool(summary.get("write_executed")):
        blockers.append("authorization_package:write_executed")
    for field in ("runtime_default_install_count", "canonical_pointer_write_count", "production_write_count", "remote_write_count"):
        if int(summary.get(field) or 0) != 0:
            blockers.append(f"authorization_package:{field}_nonzero")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for field in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(field) is True:
            blockers.append(f"authorization_package:classification_{field}_true")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(field) is True:
            blockers.append(f"authorization_package:safety_{field}_true")
    for field in ("production_write_count", "remote_write_count"):
        if int(safety.get(field) or 0) != 0:
            blockers.append(f"authorization_package:safety_{field}_nonzero")
    return blockers


def _template_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != SIGNED_TEMPLATE_SCHEMA:
        blockers.append(f"signed_template_schema_mismatch:{payload.get('schema')}")
    if payload.get("verdict") != "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE":
        blockers.append(f"signed_template_not_ready:{payload.get('verdict')}")
    templates = payload.get("signature_templates") if isinstance(payload.get("signature_templates"), dict) else {}
    operator_template = templates.get("controlled_default_operator") if isinstance(templates.get("controlled_default_operator"), dict) else {}
    if operator_template.get("template_id") != TEMPLATE_ID:
        blockers.append(f"signed_template_unexpected_template_id:{operator_template.get('template_id')}")
    if operator_template.get("signature_status") != "unsigned":
        blockers.append(f"signed_template_not_unsigned:{operator_template.get('signature_status')}")
    return blockers


def _identity_blockers(*, operator_id: str, statement: str, signed_at: str) -> list[str]:
    blockers: list[str] = []
    if not operator_id.strip():
        blockers.append("operator_id_missing")
    if not statement.strip():
        blockers.append("statement_missing")
    try:
        datetime.fromisoformat(signed_at)
    except (TypeError, ValueError):
        blockers.append(f"signed_at_not_iso8601:{signed_at}")
    return blockers


def run_operator_signature_capture(
    *,
    authorization_package: dict[str, Any],
    signed_template: dict[str, Any] | None = None,
    operator_id: str,
    statement: str,
    signed_at: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_package_blockers(authorization_package))
    if signed_template is not None:
        blockers.extend(_template_blockers(signed_template))
    blockers.extend(_identity_blockers(operator_id=operator_id, statement=statement, signed_at=signed_at))

    captured = not blockers
    verdict = "OPERATOR_SIGNATURE_CAPTURED" if captured else "BLOCKED_SIGNATURE_NOT_CAPTURED"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "execution_mode": "operator_signature_capture_only",
        "input_line": authorization_package.get("input_line") or "v1_legacy",
        "input_schemas": {
            "authorization_package": authorization_package.get("schema"),
            "signed_template": signed_template.get("schema") if signed_template is not None else None,
        },
        "signature": {
            "template_id": TEMPLATE_ID,
            "required_signer_role": REQUIRED_SIGNER_ROLE,
            "signature_status": "signed" if captured else "not_captured",
            "operator_id": operator_id,
            "statement": statement,
            "signed_at": signed_at,
        },
        "authorization_binding": {
            "authorization_package_schema": authorization_package.get("schema"),
            "authorization_package_verdict": authorization_package.get("verdict"),
            "authorization_package_content_hash": content_hash(authorization_package),
            "signed_template_content_hash": content_hash(signed_template) if signed_template is not None else None,
        },
        "granted_scope": {
            "controlled_default_operator_signature": captured,
            "runtime_default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "production_db_write_allowed": False,
            "remote_write_allowed": False,
            "release_truth_allowed": False,
        },
        "summary": {
            "blocker_count": len(blockers),
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
        "blockers": blockers,
        "not_exercised": [
            "runtime_default_install",
            "canonical_pointer_write",
            "production_db_write",
            "remote_write",
            "release_truth_claim",
            "official_score",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "operator_signature_record": True,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-package", type=Path, required=True)
    parser.add_argument("--signed-template", type=Path, default=None)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument("--signed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_operator_signature_capture(
        authorization_package=_read_json(args.authorization_package),
        signed_template=_read_json(args.signed_template) if args.signed_template is not None else None,
        operator_id=args.operator,
        statement=args.statement,
        signed_at=args.signed_at,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "OPERATOR_SIGNATURE_CAPTURED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
