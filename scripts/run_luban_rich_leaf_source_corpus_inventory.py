#!/usr/bin/env python3
"""Inventory the 2026 source corpus before full RichLeaf compilation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_source_corpus_inventory_20260612/source_corpus_inventory.json"
)
SCHEMA = "luban_rich_leaf_source_corpus_inventory.v1"
SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lane_for(relative_path: str) -> str:
    lowered = relative_path.lower()
    if any(marker in relative_path for marker in ("教材", "规范", "标准", "图集")):
        return "source_truth"
    if any(marker in relative_path for marker in ("讲义", "课件", "课程", "笔记")):
        return "teaching_evidence"
    if any(marker in relative_path for marker in ("题库", "真题", "案例题", "试题", "答案", "答卷")):
        return "assessment_evidence"
    if any(marker in lowered for marker in ("textbook", "standard", "code", "spec")):
        return "source_truth"
    if any(marker in lowered for marker in ("lecture", "course", "note", "slides")):
        return "teaching_evidence"
    if any(marker in lowered for marker in ("question", "exam", "answer", "rubric")):
        return "assessment_evidence"
    return "unclassified_review_required"


def _empty_lane_summary() -> dict[str, Any]:
    return {"file_count": 0, "byte_count": 0}


def run_source_corpus_inventory(*, source_root: Path) -> dict[str, Any]:
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"source root not found: {source_root}")

    included: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    by_lane = {
        "source_truth": _empty_lane_summary(),
        "teaching_evidence": _empty_lane_summary(),
        "assessment_evidence": _empty_lane_summary(),
        "unclassified_review_required": _empty_lane_summary(),
    }

    all_files = sorted(path for path in source_root.rglob("*") if path.is_file())
    for path in all_files:
        relative = path.relative_to(source_root).as_posix()
        size = path.stat().st_size
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            unsupported.append(
                {
                    "relative_path": relative,
                    "suffix": path.suffix.lower(),
                    "byte_count": size,
                    "reason": "unsupported_suffix",
                }
            )
            continue
        lane = _lane_for(relative)
        by_lane[lane]["file_count"] += 1
        by_lane[lane]["byte_count"] += size
        included.append(
            {
                "relative_path": relative,
                "source_lane": lane,
                "suffix": path.suffix.lower(),
                "byte_count": size,
                "sha256": _sha256(path),
            }
        )

    return {
        "schema": SCHEMA,
        "source_root": str(source_root),
        "verdict": "PASS_SOURCE_CORPUS_INVENTORY",
        "quality_claim_allowed": False,
        "execution_mode": "read_only_inventory",
        "summary": {
            "total_file_count": len(all_files),
            "included_file_count": len(included),
            "unsupported_file_count": len(unsupported),
            "unclassified_file_count": by_lane["unclassified_review_required"]["file_count"],
            "source_truth_file_count": by_lane["source_truth"]["file_count"],
            "teaching_evidence_file_count": by_lane["teaching_evidence"]["file_count"],
            "assessment_evidence_file_count": by_lane["assessment_evidence"]["file_count"],
            "production_write_count": 0,
            "runtime_install_count": 0,
        },
        "by_lane": by_lane,
        "files": included,
        "unsupported_files": unsupported,
        "not_exercised": [
            "rich_leaf_deep_compilation",
            "semantic_review",
            "runtime_default_install",
            "canonical_truth_write",
            "production_db_write",
            "release_truth_claim",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "source_corpus_inventory": True,
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
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_source_corpus_inventory(source_root=args.source_root)
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
