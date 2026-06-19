#!/usr/bin/env python3
"""Build a reproducible ledger for cleaned JSON source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "extractions" / "json_source_ledger_v0"
SENTINEL_NAME = ".json_source_ledger_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "json_source_ledger_v0")
EXCLUDED_DIRS = {".git", "__pycache__", "node_modules"}
EXCLUDED_FILES = {".DS_Store"}
RUNTIME_GUARD = {
    "release_stage": "raw_source_ledger",
    "runtime_consumable": False,
    "installed_runtime_supply": False,
    "canonical_write_allowed": False,
    "learner_truth_write_allowed": False,
    "gbrain_write_allowed": False,
    "production_registry_write_allowed": False,
    "official_score_allowed": False,
}


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


def resolve_soft(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_id_for(source_root: Path, path: Path) -> str:
    rel_to_source = path.relative_to(source_root).as_posix()
    return f"json_src_{hashlib.sha256(rel_to_source.encode('utf-8')).hexdigest()[:16]}"


def validate_output_root(path: Path, source_root: Path) -> None:
    resolved = resolve_soft(path)
    resolved_source = resolve_soft(source_root)
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        (INVENTORY_ROOT / "extractions").resolve(),
        resolved_source,
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if is_relative_to(resolved_source, resolved) or is_relative_to(resolved, resolved_source):
        raise ValueError("output root must not overlap source root")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_json_source_ledger.py"
        or sentinel.get("kind") != "json_source_ledger"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {"manifest.json", "sources.jsonl", "summary.json", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "json_source_ledger",
        "generated_by": "build_json_source_ledger.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_json_files(source_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in source_root.rglob("*.json"):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if set(path.relative_to(source_root).parts) & EXCLUDED_DIRS:
            continue
        files.append(path)
    return sorted(files)


def classify_source(source_root: Path, path: Path) -> str:
    parts = path.relative_to(source_root).parts
    top = parts[0] if parts else ""
    path_text = path.as_posix()
    if top == "题库" and re.search(r"FINAL_CLEANED_EXAM_V\d{4}\.json$", path.name):
        return "exam_cleaned_json"
    if top == "题库" and "ZL500" in path.name:
        return "practice_zl500_json"
    if top == "题库" and "QIANTIZAN" in path.name:
        return "practice_qiantizan_json"
    if top == "2026教材":
        if "production_core" in path.name:
            return "textbook_core_json"
        if "production_enrichment" in path.name:
            return "textbook_enrichment_json"
        if "production_index" in path.name:
            return "textbook_index_json"
        return "textbook_cleaned_json"
    if top == "标准文件":
        return "standard_cleaned_json"
    if top == "讲义":
        return "lecture_cleaned_json"
    if top == "taxonomy":
        if "_backup_" in path_text or "_pre_" in path.name:
            return "taxonomy_backup_json"
        return "taxonomy_cleaned_json"
    return "other_cleaned_json"


def json_shape(data: Any) -> dict[str, Any]:
    shape: dict[str, Any] = {"top_type": type(data).__name__}
    if isinstance(data, dict):
        top_keys = list(data.keys())
        shape["top_keys"] = top_keys[:24]
        for key in [
            "chunks",
            "exercises",
            "content_blocks",
            "nodes",
            "unmatched_nodes",
            "rubric",
        ]:
            value = data.get(key)
            if isinstance(value, list):
                shape[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                shape[f"{key}_count"] = len(value)
        stats = data.get("stats")
        if isinstance(stats, dict):
            shape["stats_keys"] = list(stats.keys())[:24]
        chunks = data.get("chunks")
        if isinstance(chunks, list):
            exercises = 0
            for chunk in chunks:
                if isinstance(chunk, dict) and isinstance(chunk.get("exercises"), list):
                    exercises += len(chunk["exercises"])
            shape["nested_exercises_count"] = exercises
    elif isinstance(data, list):
        shape["items_count"] = len(data)
    return shape


def build_records(source_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in iter_json_files(source_root):
        data = json.loads(path.read_text(encoding="utf-8"))
        bucket = classify_source(source_root, path)
        record = {
            "schema": "luban_json_source_record.v0",
            "source_id": source_id_for(source_root, path),
            "source_path": display_path(path),
            "source_relpath_under_root": path.relative_to(source_root).as_posix(),
            "bucket": bucket,
            "authority_status": "raw_evidence_ledger",
            "source_claim_reviewed": False,
            "runtime_guard": RUNTIME_GUARD,
            "file": {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            },
            "json_shape": json_shape(data),
        }
        records.append(record)
    return records


def build_ledger(
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not source_root.exists() or not source_root.is_dir():
        raise ValueError(f"source root does not exist: {display_path(source_root)}")
    validate_output_root(output_root, source_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records = build_records(source_root)
    if not records:
        raise ValueError(f"no JSON sources found under: {display_path(source_root)}")

    bucket_counts = Counter(record["bucket"] for record in records)
    manifest = {
        "schema": "luban_json_source_ledger_manifest.v0",
        "generated_at": generated_at,
        "source_root": display_path(source_root),
        "authority_status": "raw_evidence_ledger",
        "runtime_guard": RUNTIME_GUARD,
        "artifact_refs": {
            "sources": "sources.jsonl",
            "summary": "summary.json",
        },
        "counts": {
            "json_sources": len(records),
            "buckets": dict(sorted(bucket_counts.items())),
        },
        "guardrails": [
            "ledger only; not runtime supply",
            "cleaned JSON is raw evidence until source claims are reviewed",
            "no official scoring claim",
            "no learner truth write",
        ],
    }
    summary = {
        "schema": "luban_json_source_ledger_summary.v0",
        "generated_at": generated_at,
        "source_root": display_path(source_root),
        "json_sources": len(records),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "largest_sources": sorted(
            (
                {
                    "source_id": record["source_id"],
                    "source_path": record["source_path"],
                    "bucket": record["bucket"],
                    "bytes": record["file"]["bytes"],
                }
                for record in records
            ),
            key=lambda item: item["bytes"],
            reverse=True,
        )[:20],
        "runtime_guard": RUNTIME_GUARD,
    }

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "sources.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "output_root": display_path(output_root),
        "manifest": manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO timestamp to write into generated artifacts; defaults to current UTC time.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_ledger(
        source_root=args.source_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
