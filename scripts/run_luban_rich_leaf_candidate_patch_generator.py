#!/usr/bin/env python3
"""Generate review-only candidate patches from RichLeaf source-gap candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash  # noqa: E402


DEFAULT_SOURCE_GAP_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_source_gap_candidates_20260611/source_gap_candidates.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_candidate_patches_20260611"
SCHEMA = "luban_rich_leaf_candidate_patch_batch.v1"
SUSPICIOUS_SUPPORT_PATH_MARKERS = (
    "真题",
    "答案解析",
    "学生答卷",
    "按学生答卷",
    "必刷",
    "千题",
    "题斩",
    "考证宝典",
    "mcq",
    "practice",
    "exercise",
    "question_data",
    "correct_answer",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_id(*parts: object, prefix: str) -> str:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _suspicious_candidate(row: dict[str, Any], candidate: dict[str, Any]) -> bool:
    source_lane = str(candidate.get("source_lane") or "")
    missing_lane = str(row.get("missing_lane") or "")
    source_path = str(candidate.get("source_path") or "")
    evidence_text = json.dumps(
        {
            "source_path": candidate.get("source_path"),
            "record_id": candidate.get("record_id"),
            "provenance": candidate.get("provenance"),
            "snippet": candidate.get("snippet"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if source_lane != missing_lane:
        return True
    if candidate.get("candidate_only") is not True or candidate.get("install_allowed") is not False:
        return True
    if not source_path or not candidate.get("record_id") or not candidate.get("span"):
        return True
    if source_lane != "question" and any(
        marker in evidence_text.lower() for marker in SUSPICIOUS_SUPPORT_PATH_MARKERS
    ):
        return True
    return False


def _source_ref_candidate(
    *,
    row: dict[str, Any],
    candidate: dict[str, Any],
    bundle_version: str,
) -> dict[str, Any]:
    span = str(candidate["span"])
    source_lane = str(candidate["source_lane"])
    source_path = str(candidate["source_path"])
    record_id = str(candidate["record_id"])
    return {
        "source_ref_id": _stable_id(row.get("leaf_id"), row.get("missing_lane"), source_path, record_id, prefix="src_patch"),
        "source_registry_id": "rich_leaf_source_gap_candidates",
        "source_dataset_id": source_lane,
        "source_version": bundle_version,
        "extractor_version": str(candidate.get("retrieval_stage") or "source_gap_candidate"),
        "source_lane": source_lane,
        "path": source_path,
        "record_id": record_id,
        "span": span,
        "span_hash": source_span_hash(span),
        "retrieval_hash": candidate.get("hash"),
        "retrieval_score": candidate.get("score"),
        "matched_terms": list(candidate.get("matched_terms") or []),
        "provenance": dict(candidate.get("provenance") or {}),
    }


def _candidate_patch(
    *,
    row: dict[str, Any],
    candidate: dict[str, Any],
    bundle_version: str,
) -> dict[str, Any]:
    source_ref = _source_ref_candidate(row=row, candidate=candidate, bundle_version=bundle_version)
    return {
        "patch_id": _stable_id(row.get("artifact_id"), row.get("missing_lane"), source_ref["source_ref_id"], prefix="patch"),
        "operation": "add_source_ref_candidate",
        "artifact_id": row.get("artifact_id"),
        "leaf_id": row.get("leaf_id"),
        "name_path": row.get("name_path"),
        "missing_lane": row.get("missing_lane"),
        "source_ref_candidate": source_ref,
        "candidate_only": True,
        "review_status": "pending_review",
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "review_packet": {
            "source_gap_status": row.get("status"),
            "strong_candidate_threshold": row.get("strong_candidate_threshold"),
            "query_context": row.get("query_context") or {},
            "question_source_only_not_support": bool(
                (row.get("query_context") or {}).get("question_source_only_not_support")
            ),
            "snippet": candidate.get("snippet"),
        },
    }


def build_candidate_patch_batch(*, source_gap_report: dict[str, Any], bundle_version: str) -> dict[str, Any]:
    patches: list[dict[str, Any]] = []
    skipped_non_strong_count = 0
    skipped_suspicious_count = 0

    for row in source_gap_report.get("source_gap_candidates") or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "strong_candidate_sources_found":
            skipped_non_strong_count += 1
            continue
        candidates = [c for c in row.get("candidates") or [] if isinstance(c, dict)]
        clean_candidates = [candidate for candidate in candidates if not _suspicious_candidate(row, candidate)]
        if not clean_candidates:
            skipped_suspicious_count += 1
            continue
        patches.append(_candidate_patch(row=row, candidate=clean_candidates[0], bundle_version=bundle_version))

    return {
        "schema": SCHEMA,
        "source_gap_schema": source_gap_report.get("schema"),
        "bundle_version": bundle_version,
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "patches_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "summary": {
            "source_gap_count": len(source_gap_report.get("source_gap_candidates") or []),
            "patch_count": len(patches),
            "skipped_non_strong_count": skipped_non_strong_count,
            "skipped_suspicious_count": skipped_suspicious_count,
        },
        "candidate_patches": patches,
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
    parser.add_argument("--source-gap-candidates", type=Path, default=DEFAULT_SOURCE_GAP_CANDIDATES)
    parser.add_argument("--bundle-version", default="v_rich_leaf_candidate_patches_20260611")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    source_gap_report = _read_json(args.source_gap_candidates)
    report = build_candidate_patch_batch(source_gap_report=source_gap_report, bundle_version=args.bundle_version)
    output_path = args.output_dir / "candidate_patches.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
