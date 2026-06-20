#!/usr/bin/env python3
"""Profile DeepTutor/Luban compiled assets referenced by the inventory docs."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions"
OUT_PATH = OUT_DIR / "2026-06-18-compiled-assets-current-profile.json"

SCOPE_ROOTS = {
    "knowledge_compiler_2026": REPO_ROOT / "artifacts" / "knowledge_compiler" / "2026",
    "luban_grading_artifacts": REPO_ROOT / "artifacts" / "luban_grading_artifacts",
    "runtime_supply": REPO_ROOT / "deeptutor" / "services" / "construction_grading" / "runtime_supply",
    "data_inventory_extractions": REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "extractions",
    "case_family_assets": REPO_ROOT / "artifacts" / "luban_case_family_assets",
}

EXCLUDED_PARTS = {".git", "__pycache__", "node_modules"}
EXCLUDED_FILES = {".DS_Store"}


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def extension(path: Path) -> str:
    return path.suffix.lower() or "[no_ext]"


def iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if set(path.relative_to(root).parts) & EXCLUDED_PARTS:
            continue
        files.append(path)
    return sorted(files)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def file_inventory() -> dict[str, Any]:
    rows = {}
    for name, root in SCOPE_ROOTS.items():
        files = iter_files(root)
        ext = Counter(extension(path) for path in files)
        rows[name] = {
            "path": rel(root),
            "exists": root.exists(),
            "files": len(files),
            "bytes": sum(path.stat().st_size for path in files),
            "extensions": dict(ext.most_common()),
            "largest_files": [
                {"path": rel(path), "bytes": path.stat().st_size}
                for path in sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:12]
            ],
        }
    return rows


def summarize_scoring_point_assets() -> dict[str, Any]:
    base = SCOPE_ROOTS["knowledge_compiler_2026"] / "scoring-point-assets-20260602"
    report_path = base / "quality_report.json"
    by_node_path = base / "scoring_point_assets_by_node.json"
    report = load_json(report_path)
    by_node = load_json(by_node_path)
    return {
        "path": rel(base),
        "schema_version": report.get("schema_version"),
        "quality_gate": report.get("quality_gate"),
        "asset_count": report.get("asset_count"),
        "chunk_count": report.get("chunk_count"),
        "node_count": report.get("node_count"),
        "seed_hit_rate": report.get("seed_hit_rate"),
        "textbook_anchor_rate_for_text_assets": report.get("textbook_anchor_rate_for_text_assets"),
        "jsonl_points": jsonl_count(base / "scoring_point_assets.jsonl"),
        "by_node_top_level_count": len(by_node) if isinstance(by_node, dict) else None,
        "fixture_warning": "pytest-scoring-point-assets is excluded from production interpretation; it is a test fixture.",
    }


def summarize_lecture_compile() -> dict[str, Any]:
    base = SCOPE_ROOTS["knowledge_compiler_2026"] / "lecture_compile_20260608"
    files = [
        "lecture_teaching_cards.jsonl",
        "rubric_candidates.jsonl",
        "standard_clauses.jsonl",
        "question_capsules.jsonl",
        "question_capsule_to_questions_bank.jsonl",
        "question_capsule_unmatched.jsonl",
        "option_reasoning_backfill.jsonl",
        "taxonomy_index.jsonl",
    ]
    return {
        "path": rel(base),
        "jsonl_counts": {name: jsonl_count(base / name) for name in files},
    }


def summarize_rich_leaf_runtime() -> dict[str, Any]:
    base = SCOPE_ROOTS["runtime_supply"] / "v_rich_leaf_context"
    pointer = load_json(base / "canonical_pointer.json")
    bundle = load_json(base / "rich_leaf_context_bundle.json")
    return {
        "path": rel(base),
        "canonical_pointer": pointer,
        "bundle_records": len(bundle.get("records") or []),
        "bundle_manifest_keys": list((bundle.get("manifest") or {}).keys()),
    }


def summarize_rich_leaf_v32() -> dict[str, Any]:
    path = SCOPE_ROOTS["luban_grading_artifacts"] / "rich_leaf_v32_scoring_point_compile_20260613" / "runtime_token_pack_v32_scoring_points.json"
    data = load_json(path)
    sp_summary = data.get("scoring_points_summary") or {}
    return {
        "path": rel(path),
        "schema": data.get("schema"),
        "version": data.get("version"),
        "status": data.get("status"),
        "summary": data.get("summary"),
        "scoring_points_summary": sp_summary,
        "runtime_token_pack_units": len(data.get("runtime_token_pack_units") or []),
    }


def summarize_deep_compile() -> dict[str, Any]:
    base = SCOPE_ROOTS["luban_grading_artifacts"] / "rich_leaf_full2026_llm_deep_compile_runner_20260612"
    path = base / "llm_deep_compile_runner_deepseek_full313_merged_candidates.json"
    data = load_json(path)
    return {
        "path": rel(path),
        "schema": data.get("schema"),
        "verdict": data.get("verdict"),
        "execution_mode": data.get("execution_mode"),
        "quality_claim_allowed": data.get("quality_claim_allowed"),
        "summary": data.get("summary"),
        "candidate_count": len(data.get("candidates") or []),
        "not_exercised": data.get("not_exercised"),
    }


def summarize_pgo() -> dict[str, Any]:
    base = SCOPE_ROOTS["luban_grading_artifacts"] / "per_question_grading_object_full_compile_20260614"
    summary = load_json(base / "summary.json")
    object_files = sorted((base / "objects").glob("*.json"))
    point_total = 0
    score_null = 0
    official_score_allowed = Counter()
    per_point_authority = Counter()
    for path in object_files:
        data = load_json(path)
        official_score_allowed[str(data.get("official_score_allowed"))] += 1
        per_point_authority[str(data.get("per_point_score_authority"))] += 1
        for subq in data.get("sub_questions") or []:
            for point in subq.get("scoring_points") or []:
                point_total += 1
                if point.get("score") is None:
                    score_null += 1
    return {
        "path": rel(base),
        "summary": summary,
        "object_files": len(object_files),
        "derived_scoring_points": point_total,
        "derived_score_null_points": score_null,
        "official_score_allowed_distribution": dict(official_score_allowed),
        "per_point_score_authority_distribution": dict(per_point_authority),
    }


def summarize_runtime_supply() -> dict[str, Any]:
    root = SCOPE_ROOTS["runtime_supply"]
    pointers = []
    for path in sorted(root.glob("v_*/canonical_pointer.json")):
        data = load_json(path)
        pointers.append({
            "bundle": path.parent.name,
            "path": rel(path.parent),
            "namespace": data.get("namespace"),
            "status": data.get("status"),
            "published": data.get("published"),
            "selected_counts": {
                key: data.get(key)
                for key in ["record_count", "card_count", "chunk_count", "node_count", "leaf_count", "signed_point_count", "quarantine_excluded_count"]
                if key in data
            },
        })
    published = Counter(str(row.get("published")) for row in pointers)
    return {
        "path": rel(root),
        "canonical_pointer_count": len(pointers),
        "published_distribution": dict(published),
        "canonical_pointers": pointers,
    }


def summarize_inventory_extractions() -> dict[str, Any]:
    root = SCOPE_ROOTS["data_inventory_extractions"]
    files = iter_files(root)
    return {
        "path": rel(root),
        "files": len(files),
        "jsonl_counts": {
            path.name: jsonl_count(path)
            for path in files
            if path.suffix == ".jsonl"
        },
        "json_files": [path.name for path in files if path.suffix == ".json"],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "scope_roots": {key: rel(path) for key, path in SCOPE_ROOTS.items()},
        "file_inventory": file_inventory(),
        "key_assets": {
            "scoring_point_assets": summarize_scoring_point_assets(),
            "lecture_compile": summarize_lecture_compile(),
            "rich_leaf_runtime_supply": summarize_rich_leaf_runtime(),
            "rich_leaf_v32_scoring_points": summarize_rich_leaf_v32(),
            "llm_deep_compile_runner": summarize_deep_compile(),
            "per_question_grading_object": summarize_pgo(),
            "runtime_supply": summarize_runtime_supply(),
            "data_inventory_extractions": summarize_inventory_extractions(),
        },
        "interpretation_guardrail": {
            "release_truth": "runtime_supply canonical pointers and production gates control runtime truth; artifact workbench outputs are shadow/workbench unless published and wired.",
            "official_scoring_authority": "PGO/rubric candidates remain pending when per-point scores are null or authority is pending_calibration_not_official.",
        },
    }
    OUT_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "profile": rel(OUT_PATH),
        "scope_roots": profile["scope_roots"],
        "runtime_published_distribution": profile["key_assets"]["runtime_supply"]["published_distribution"],
        "pgo_score_null_points": profile["key_assets"]["per_question_grading_object"]["derived_score_null_points"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
