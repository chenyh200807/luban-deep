#!/usr/bin/env python3
"""Build review-only reviewed RichLeaf candidates from semantic audit records."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_evidence_audit_record_20260612/semantic_evidence_audit_record.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_reviewed_candidates_20260612"
SCHEMA = "luban_rich_leaf_reviewed_candidate_batch.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _candidate_id(record: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(record.get("audit_item_id") or ""),
            str(record.get("leaf_id") or ""),
            str(record.get("missing_lane") or ""),
            str((record.get("source_candidate") or {}).get("record_id") or ""),
        ]
    )
    return f"reviewed_candidate_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _accepted_record(record: dict[str, Any]) -> bool:
    return (
        record.get("review_decision_status") == "recorded"
        and record.get("decision") == "accept_source_ref_candidate"
        and isinstance(record.get("source_candidate"), dict)
    )


def _reviewed_candidate(record: dict[str, Any]) -> dict[str, Any]:
    source_candidate = record["source_candidate"]
    return {
        "candidate_id": _candidate_id(record),
        "candidate_status": "reviewed_candidate",
        "leaf_id": record.get("leaf_id"),
        "artifact_id": record.get("artifact_id"),
        "missing_lane": record.get("missing_lane"),
        "audit_item_id": record.get("audit_item_id"),
        "field_patch": {
            "field": "source_refs",
            "operation": "add_source_ref",
            "source_ref": {
                "source_lane": source_candidate.get("source_lane"),
                "source_path": source_candidate.get("source_path"),
                "record_id": source_candidate.get("record_id"),
                "span": source_candidate.get("span"),
                "span_hash": source_candidate.get("span_hash"),
                "matched_terms": list(source_candidate.get("matched_terms") or []),
                "support_candidate": source_candidate.get("support_candidate") is True,
            },
        },
        "review_authority": {
            "review_decision_status": record.get("review_decision_status"),
            "decision": record.get("decision"),
            "reviewer_role": record.get("reviewer_role"),
            "reviewer_id": record.get("reviewer_id"),
            "rationale": record.get("rationale"),
            "confidence": record.get("confidence"),
        },
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "official_score_allowed": False,
    }


def build_reviewed_candidate_report(*, audit_record: dict[str, Any]) -> dict[str, Any]:
    records = [record for record in audit_record.get("semantic_evidence_audit_records") or [] if isinstance(record, dict)]
    accepted = [record for record in records if _accepted_record(record)]
    reviewed_candidates = [_reviewed_candidate(record) for record in accepted]
    return {
        "schema": SCHEMA,
        "semantic_evidence_audit_record_schema": audit_record.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_record_count": len(records),
            "accepted_source_ref_count": len(accepted),
            "reviewed_candidate_count": len(reviewed_candidates),
            "not_accepted_count": len(records) - len(accepted),
        },
        "reviewed_candidates": reviewed_candidates,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-record", type=Path, default=DEFAULT_AUDIT_RECORD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = build_reviewed_candidate_report(audit_record=_read_json(args.audit_record))
    output_path = args.output_dir / "reviewed_rich_leaf_candidates.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
