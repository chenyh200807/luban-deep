#!/usr/bin/env python3
"""Verify the tracked KnowQL PGO case-rubric runtime-supply slot.

Read-only gate: verifies bank hash, canonical pointer, release-candidate/default-off
status, no-mint records, and factory/source provenance. It does not flip
``LUBAN_CASE_RUBRIC_BANK_SLOT`` and does not write runtime files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.case_rubric_pgo_supply import (  # noqa: E402
    NAMESPACE,
    validate_pgo_runtime_supply,
)
from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex  # noqa: E402

DEFAULT_SLOT_DIR = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored_pgo"
)
BANK_NAME = "case_rubric_scored_pgo.json"
POINTER_NAME = "canonical_pointer.json"
SCHEMA = "luban_pgo_runtime_supply_verification.v1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_pgo_runtime_supply(slot_dir: Path = DEFAULT_SLOT_DIR) -> dict[str, Any]:
    slot_dir = Path(slot_dir)
    bank_path = slot_dir / BANK_NAME
    pointer_path = slot_dir / POINTER_NAME
    blockers: list[str] = []
    checks: dict[str, bool] = {}
    bundle: dict[str, Any] = {}
    pointer: dict[str, Any] = {}

    try:
        loaded = _load_json(bank_path)
        if isinstance(loaded, dict):
            bundle = loaded
        else:
            blockers.append("bank_not_object")
    except Exception as exc:  # noqa: BLE001
        blockers.append(f"bank_unreadable:{type(exc).__name__}")

    try:
        loaded_pointer = _load_json(pointer_path)
        if isinstance(loaded_pointer, dict):
            pointer = loaded_pointer
        else:
            blockers.append("canonical_pointer_not_object")
    except Exception as exc:  # noqa: BLE001
        blockers.append(f"canonical_pointer_unreadable:{type(exc).__name__}")

    manifest = bundle.get("manifest") or {}
    records = bundle.get("records") or []
    actual_hash = _sha256_hex(records) if isinstance(records, list) else ""
    manifest_hash = str(manifest.get("content_hash") or "")
    pointer_hash = str(pointer.get("expected_content_hash") or pointer.get("content_hash") or "")

    checks["content_hash_match"] = bool(actual_hash and actual_hash == manifest_hash)
    checks["canonical_pointer_match"] = bool(actual_hash and pointer_hash == actual_hash)
    checks["production_default_off"] = manifest.get("production_default") == "off"
    checks["published_false"] = manifest.get("published") is False
    checks["namespace_match"] = manifest.get("namespace") == NAMESPACE
    checks["source_provenance_present"] = bool(manifest.get("source_schemas"))
    checks["factory_provenance_present"] = bool(manifest.get("factory_resolution_lanes"))
    checks["no_minted_scores"] = all(
        isinstance(record, dict)
        and record.get("score") is None
        and record.get("max_score") is None
        and record.get("official_score_allowed") is False
        and record.get("canonical_write_allowed") is False
        for record in records
    ) if isinstance(records, list) else False

    if bundle:
        blockers.extend(validate_pgo_runtime_supply(bundle))
    if not checks["content_hash_match"]:
        blockers.append("content_hash_mismatch")
    if not checks["canonical_pointer_match"]:
        blockers.append("canonical_pointer_hash_mismatch")
    if not checks["source_provenance_present"]:
        blockers.append("missing_source_schemas")
    if not checks["factory_provenance_present"]:
        blockers.append("missing_factory_resolution_lanes")
    if not checks["no_minted_scores"]:
        blockers.append("minted_or_authority_record_found")

    return {
        "schema": SCHEMA,
        "status": "ok" if not blockers else "blocked",
        "slot_dir": str(slot_dir),
        "bank_path": str(bank_path),
        "pointer_path": str(pointer_path),
        "blockers": sorted(set(blockers)),
        "checks": checks,
        "manifest": {
            "namespace": manifest.get("namespace"),
            "status": manifest.get("status"),
            "published": manifest.get("published"),
            "production_default": manifest.get("production_default"),
            "question_count": manifest.get("question_count"),
            "scoring_point_count": manifest.get("scoring_point_count"),
            "content_hash": manifest_hash,
            "source_schemas": manifest.get("source_schemas") or [],
            "factory_resolution_lanes": manifest.get("factory_resolution_lanes") or [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-dir", type=Path, default=DEFAULT_SLOT_DIR)
    args = parser.parse_args(argv)

    report = verify_pgo_runtime_supply(args.slot_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
