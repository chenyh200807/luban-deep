#!/usr/bin/env python3
"""Run Phase 0 RichLeafArtifact validation.

This is a read-only compiler gate. It validates candidate rich leaf artifacts
and optionally builds task-specific pack smoke outputs. It does not install a
runtime supply bundle, write canonical truth, grant official score, or touch DB.
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

from deeptutor.services.construction_grading.rich_leaf_artifacts import (  # noqa: E402
    build_compiled_context_pack,
    validate_rich_leaf_artifact,
)


DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_phase0_validator_20260611"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_artifacts(payload: Any) -> tuple[list[dict[str, Any]], str, str]:
    if isinstance(payload, list):
        return ([row for row in payload if isinstance(row, dict)], "", "")
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object or array")
    rows = payload.get("rich_leaf_artifacts")
    if rows is None:
        rows = payload.get("artifacts")
    if rows is None and payload.get("artifact_id"):
        rows = [payload]
    if not isinstance(rows, list):
        raise ValueError("input JSON must contain rich_leaf_artifacts array, artifacts array, or one artifact object")
    return (
        [row for row in rows if isinstance(row, dict)],
        str(payload.get("bundle_version") or ""),
        str(payload.get("manifest_hash") or ""),
    )


def build_phase0_validator_report(
    *,
    artifacts: list[dict[str, Any]],
    bundle_version: str = "",
    manifest_hash: str = "",
    pack_tasks: list[str] | None = None,
) -> dict[str, Any]:
    validation_reports: list[dict[str, Any]] = []
    valid_artifacts: list[dict[str, Any]] = []
    blocker_counts: dict[str, int] = {}

    for idx, artifact in enumerate(artifacts):
        report = validate_rich_leaf_artifact(artifact)
        artifact_id = str(artifact.get("artifact_id") or f"artifact_{idx}")
        leaf_id = str(artifact.get("leaf_id") or "")
        row = {
            "artifact_id": artifact_id,
            "leaf_id": leaf_id,
            "ok": report.ok,
            "candidate_status": artifact.get("candidate_status"),
            "blockers": list(report.blockers),
            "warnings": list(report.warnings),
            "accepted_field_ids": list(report.accepted_field_ids),
            "candidate_only_field_ids": list(report.candidate_only_field_ids),
            "rejected_field_ids": list(report.rejected_field_ids),
            "canonical_truth_written": report.canonical_truth_written,
            "official_score_allowed": report.official_score_allowed,
            "production_write_count": report.production_write_count,
        }
        validation_reports.append(row)
        if report.ok:
            valid_artifacts.append(artifact)
        for blocker in report.blockers:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    pack_smoke: dict[str, Any] = {}
    for task in pack_tasks or []:
        pack = build_compiled_context_pack(
            task=task,
            artifacts=valid_artifacts,
            bundle_version=bundle_version,
            manifest_hash=manifest_hash,
        )
        pack_smoke[task] = pack.to_dict()

    return {
        "schema": "luban_rich_leaf_phase0_validator_report.v1",
        "bundle_version": bundle_version,
        "manifest_hash": manifest_hash,
        "summary": {
            "artifact_count": len(artifacts),
            "valid_artifact_count": len(valid_artifacts),
            "invalid_artifact_count": len(artifacts) - len(valid_artifacts),
            "blocker_kind_count": len(blocker_counts),
        },
        "validation_reports": validation_reports,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "pack_smoke": pack_smoke,
        "classification": {
            "candidate_only": True,
            "review_required": True,
        },
        "safety": {
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "remote_write_performed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--bundle-version", default="")
    parser.add_argument("--manifest-hash", default="")
    parser.add_argument("--pack-task", action="append", default=[])
    args = parser.parse_args(argv)

    artifacts, payload_bundle_version, payload_manifest_hash = _load_artifacts(_read_json(args.input))
    report = build_phase0_validator_report(
        artifacts=artifacts,
        bundle_version=args.bundle_version or payload_bundle_version,
        manifest_hash=args.manifest_hash or payload_manifest_hash,
        pack_tasks=args.pack_task,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "rich_leaf_phase0_validator_report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
