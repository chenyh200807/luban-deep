#!/usr/bin/env python3
"""Reconcile docs/2026 source authority with Nexus-like runtime supply shards.

This is a read-only compiler control-plane audit. It does not publish, promote,
write production DBs, or mint release truth.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path(
    os.getenv(
        "LUBAN_DATA_DIR",
        "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026",
    )
)
DEFAULT_SUPPLY_ROOT = REPO / "deeptutor/services/construction_grading/runtime_supply"
DEFAULT_ARTIFACTS_ROOT = REPO / "artifacts/luban_grading_artifacts"
DEFAULT_OUTPUT_DIR = DEFAULT_ARTIFACTS_ROOT / "docs2026_runtime_reconciliation_20260611"


SOURCE_LANES: dict[str, list[str]] = {
    "taxonomy": ["taxonomy/*.json"],
    "textbook": ["2026教材/第二次加强/*fixed.json"],
    "standards": ["标准文件/*.json"],
    "lectures": ["讲义/**/*.json"],
    "question_bank": ["题库/**/FINAL_CLEANED*.json"],
    "student_answers": ["题库/近三年案例题_按学生答卷排版.md", "题库/近三年案例题_按学生答卷排版.docx"],
}

RUNTIME_LANES: dict[str, list[tuple[str, str]]] = {
    "taxonomy": [
        ("v_canonical_taxonomy_index", "canonical_taxonomy_index.json"),
        ("v_concept_registry", "concept_registry.json"),
        ("v_canonical_knowledge_graph", "graph_adjacency.json"),
    ],
    "textbook": [("v_textbook_knowledge_full", "textbook_knowledge_release_candidate.json")],
    "standards": [("v_standard_clauses", "standard_clauses.json")],
    "lectures": [("v_lecture_teaching_cards", "lecture_teaching_cards.json")],
    "question_bank": [
        ("v_kb_v5_chunks_full", "kb_v5_chunks_full.json"),
        ("v_case_rubric_scored", "case_rubric_scored.json"),
        ("v3_objective_records_released_m31", "objective_answer_key_release_candidate_m31.json"),
    ],
    "student_answers": [],
    "unified_context": [("v_canonical_unified_knowledge", "canonical_unified_knowledge.json")],
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _count_records(payload: dict[str, Any]) -> int | None:
    for key in ("records", "nodes", "cards", "chunks", "items", "rubrics", "question_records"):
        value = payload.get(key)
        if isinstance(value, (list, dict)):
            return len(value)
    if isinstance(payload.get("adjacency"), dict):
        return len(payload["adjacency"])
    return None


def _source_files(source_root: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in source_root.glob(pattern) if path.is_file())
    return sorted(set(files))


def _runtime_shards(supply_root: Path, lane: str) -> list[dict[str, Any]]:
    shards: list[dict[str, Any]] = []
    for shard_dir, filename in RUNTIME_LANES.get(lane, []):
        path = supply_root / shard_dir / filename
        payload = _read_json(path)
        manifest = payload.get("manifest") or {}
        pointer = _read_json(supply_root / shard_dir / "canonical_pointer.json")
        record_count = _count_records(payload)
        shards.append(
            {
                "path": str(path),
                "exists": bool(payload),
                "namespace": manifest.get("namespace") or pointer.get("namespace"),
                "status": manifest.get("status") or pointer.get("status"),
                "published": pointer.get("published"),
                "tier": manifest.get("tier"),
                "official_score_allowed": manifest.get("official_score_allowed"),
                "record_count": record_count,
                "content_hash": manifest.get("content_hash") or pointer.get("content_hash") or pointer.get("expected_content_hash"),
            }
        )
    return shards


def _runtime_record_count(shards: list[dict[str, Any]]) -> int:
    return sum(int(shard.get("record_count") or 0) for shard in shards)


def _lane_status(lane: str, source_count: int, shards: list[dict[str, Any]]) -> str:
    if lane == "student_answers":
        return "source_available_not_release_truth" if source_count else "missing_source"
    if not source_count:
        return "missing_source"
    if not shards or not any(shard["exists"] for shard in shards):
        return "source_available_runtime_missing"
    if all((shard.get("status") == "release_candidate") for shard in shards if shard["exists"]):
        return "compiled_release_candidate"
    return "compiled_mixed_status"


def _load_unified_coverage(artifacts_root: Path) -> dict[str, Any]:
    coverage = (_read_json(artifacts_root / "canonical_unified_knowledge_20260606" / "coverage_report.json").get("coverage") or {})
    total = int(coverage.get("canonical_leaves_total") or 0)
    populated = int(coverage.get("leaves_populated") or 0)
    return {
        "canonical_leaves_total": total,
        "leaves_populated": populated,
        "populated_leaf_rate": (populated / total) if total else None,
        "leaves_with_textbook": coverage.get("leaves_with_textbook"),
        "leaves_with_standard": coverage.get("leaves_with_standard"),
        "leaves_with_lecture": coverage.get("leaves_with_lecture"),
        "leaves_with_question": coverage.get("leaves_with_question"),
    }


def _load_m34_gate(artifacts_root: Path) -> dict[str, Any]:
    gate = _read_json(artifacts_root / "general_knowledge_dividend_m34_repair_safe_subset_20260611" / "go_no_go_m34.json")
    coverage = _read_json(
        artifacts_root / "general_knowledge_dividend_m34_repair_safe_subset_20260611" / "coverage_report_m34.json"
    )
    return {
        "verdict": gate.get("verdict"),
        "blockers": gate.get("blockers") or [],
        "teaching_context_hit_rate": coverage.get("teaching_context_hit_rate"),
        "threshold": coverage.get("threshold"),
        "calibration_pass_rate": coverage.get("calibration_pass_rate"),
        "compiler_source_work_order_count": coverage.get("compiler_source_work_order_count"),
    }


def _load_m35_gate(artifacts_root: Path) -> dict[str, Any]:
    decision = _read_json(artifacts_root / "nexus_compilation_decision_20260611" / "decision_package.json")
    return {
        "phase1_shadow_verdict": decision.get("phase1_shadow_verdict"),
        "release_verdict": decision.get("release_verdict"),
        "quality_claim_allowed": decision.get("quality_claim_allowed"),
        "not_exercised": decision.get("not_exercised") or [],
    }


def build_reconciliation(
    *,
    source_root: Path,
    supply_root: Path,
    artifacts_root: Path,
) -> dict[str, Any]:
    source_lanes: dict[str, Any] = {}
    for lane, patterns in SOURCE_LANES.items():
        files = _source_files(source_root, patterns)
        shards = _runtime_shards(supply_root, lane)
        source_lanes[lane] = {
            "source_file_count": len(files),
            "sample_sources": [str(path.relative_to(source_root)) for path in files[:8]],
            "runtime_shards": shards,
            "runtime_record_count": _runtime_record_count(shards),
            "status": _lane_status(lane, len(files), shards),
        }

    unified_coverage = _load_unified_coverage(artifacts_root)
    m34_gate = _load_m34_gate(artifacts_root)
    m35_gate = _load_m35_gate(artifacts_root)

    blockers: list[str] = []
    rate = unified_coverage.get("populated_leaf_rate")
    if rate is not None and rate < 0.8:
        blockers.append("canonical_unified_knowledge_partial_leaf_coverage")
    if m34_gate.get("verdict") != "GO":
        for blocker in m34_gate.get("blockers") or ["m34_not_go"]:
            blockers.append(f"m34_{blocker}")
    if m35_gate.get("release_verdict") and m35_gate.get("release_verdict") != "GO":
        blockers.append("m35_release_not_go")
    if source_lanes["student_answers"]["status"] == "source_available_not_release_truth":
        blockers.append("student_answers_source_available_but_not_release_truth")

    next_compile_work_orders = [
        {
            "id": "unified_knowledge_expand_leaf_coverage",
            "reason": "canonical unified knowledge is the Nexus-like learning_mapping context, but populated leaves are below system-wide coverage.",
            "current": unified_coverage,
        },
        {
            "id": "m34_live_shadow_gate",
            "reason": "general compiled teaching context still has live gate and calibration blockers.",
            "current": m34_gate,
        },
        {
            "id": "student_answer_authority_lane",
            "reason": "student answer files are raw/source answer material; they are not release truth and need separate gold/governance handling.",
            "current": source_lanes["student_answers"],
        },
        {
            "id": "knowql_like_query_contract",
            "reason": "Nexus-like runtime should expose explicit ask/where/ground/shape/confidence/budget semantics across grader and teaching context.",
            "current": "not_yet_single_system_wide_contract",
        },
    ]

    return {
        "schema": "luban_docs2026_runtime_reconciliation.v1",
        "purpose": "Map docs/2026 source authority to runtime_supply compiled artifacts without claiming release truth.",
        "source_root": str(source_root),
        "runtime_supply_root": str(supply_root),
        "source_lanes": source_lanes,
        "coverage": {"canonical_unified_knowledge": unified_coverage, "m34_general_knowledge": m34_gate, "m35_scoring": m35_gate},
        "blockers": sorted(set(blockers)),
        "next_compile_work_orders": next_compile_work_orders,
        "safety": {
            "read_only_audit": True,
            "production_write_count": 0,
            "canonical_truth_written": False,
            "release_truth_claimed": False,
        },
        "overall_status": (
            "compiled_assets_present_but_not_system_wide_complete"
            if blockers
            else "compiled_assets_reconciled_no_blockers_found"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--supply-root", type=Path, default=DEFAULT_SUPPLY_ROOT)
    parser.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = build_reconciliation(
        source_root=args.source_root,
        supply_root=args.supply_root,
        artifacts_root=args.artifacts_root,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "reconciliation_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "overall_status": report["overall_status"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
