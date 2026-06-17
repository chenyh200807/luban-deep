#!/usr/bin/env python3
"""Build review-only semantic audit packets for RichLeaf source-ref patches."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PATCHES = REPO / "artifacts/luban_grading_artifacts/rich_leaf_candidate_patches_20260611/candidate_patches.json"
DEFAULT_PATCH_AUDIT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_patch_evidence_audit_20260611/patch_evidence_audit.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_packets_20260612"
SCHEMA = "luban_rich_leaf_semantic_audit_packets.v1"
ALLOWED_DECISIONS = [
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _patch_index(patch_batch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(patch.get("patch_id")): patch
        for patch in patch_batch.get("candidate_patches") or []
        if isinstance(patch, dict) and patch.get("patch_id")
    }


def _machine_pass_audits(patch_audit_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        audit
        for audit in patch_audit_report.get("patch_audits") or []
        if isinstance(audit, dict) and audit.get("audit_decision") == "machine_precheck_pass"
    ]


def _review_questions(missing_lane: str) -> list[str]:
    return [
        "Does the source span semantically support this exact leaf, not only a parent path or generic topic?",
        "Is the source lane appropriate for the missing lane?",
        "Does the span provide reusable source evidence rather than exam/practice/question context?",
        "Would adding this source_ref reduce wrong-path retrieval for grading, tutoring, or next-action use?",
        f"If rejected, what stronger {missing_lane} source or leaf split is needed?",
    ]


def _packet(patch: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    source_ref = patch.get("source_ref_candidate") if isinstance(patch.get("source_ref_candidate"), dict) else {}
    review_packet = patch.get("review_packet") if isinstance(patch.get("review_packet"), dict) else {}
    query_context = review_packet.get("query_context") if isinstance(review_packet.get("query_context"), dict) else {}
    return {
        "packet_id": f"semantic_audit:{patch.get('patch_id')}",
        "patch_id": patch.get("patch_id"),
        "artifact_id": patch.get("artifact_id"),
        "leaf_id": patch.get("leaf_id"),
        "name_path": patch.get("name_path"),
        "missing_lane": patch.get("missing_lane"),
        "source_ref_candidate": {
            "source_ref_id": source_ref.get("source_ref_id"),
            "source_lane": source_ref.get("source_lane"),
            "path": source_ref.get("path"),
            "record_id": source_ref.get("record_id"),
            "span": source_ref.get("span"),
            "span_hash": source_ref.get("span_hash"),
            "matched_terms": list(source_ref.get("matched_terms") or []),
            "retrieval_score": source_ref.get("retrieval_score"),
            "provenance": dict(source_ref.get("provenance") or {}),
        },
        "query_context": {
            "question_source_only_not_support": bool(query_context.get("question_source_only_not_support")),
            "question_source_record_ids": list(query_context.get("question_source_record_ids") or []),
            "question_source_spans": list(query_context.get("question_source_spans") or []),
        },
        "machine_precheck": {
            "audit_decision": audit.get("audit_decision"),
            "reason_codes": list(audit.get("reason_codes") or []),
            "matched_terms": list(audit.get("matched_terms") or []),
            "name_path_terms_in_span": list(audit.get("name_path_terms_in_span") or []),
        },
        "review_questions": _review_questions(str(patch.get("missing_lane") or "")),
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "review_status": "semantic_review_pending",
        "semantic_verdict_recorded": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "candidate_only": True,
    }


def build_semantic_audit_packet_report(*, patch_batch: dict[str, Any], patch_audit_report: dict[str, Any]) -> dict[str, Any]:
    patches = _patch_index(patch_batch)
    machine_pass = _machine_pass_audits(patch_audit_report)
    packets = [_packet(patches[audit["patch_id"]], audit) for audit in machine_pass if audit.get("patch_id") in patches]
    input_patch_count = len(patch_batch.get("candidate_patches") or [])
    return {
        "schema": SCHEMA,
        "source_patch_schema": patch_batch.get("schema"),
        "source_patch_audit_schema": patch_audit_report.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "summary": {
            "input_patch_count": input_patch_count,
            "machine_precheck_pass_count": len(machine_pass),
            "packet_count": len(packets),
            "skipped_non_pass_count": input_patch_count - len(machine_pass),
        },
        "semantic_audit_packets": packets,
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
    parser.add_argument("--patches", type=Path, default=DEFAULT_PATCHES)
    parser.add_argument("--patch-audit", type=Path, default=DEFAULT_PATCH_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    patch_batch = _read_json(args.patches)
    patch_audit_report = _read_json(args.patch_audit)
    report = build_semantic_audit_packet_report(patch_batch=patch_batch, patch_audit_report=patch_audit_report)
    output_path = args.output_dir / "semantic_audit_packets.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
