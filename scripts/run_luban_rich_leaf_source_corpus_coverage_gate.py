#!/usr/bin/env python3
"""Check source-corpus coverage by current RichLeaf candidate artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_source_corpus_inventory_20260612/source_corpus_inventory.json"
)
DEFAULT_CANDIDATE_BUNDLES = [
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_skeleton_20260612/rich_leaf_skeleton_candidates.json",
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_source_evidence_agent_20260612/source_evidence_agent_candidates.json",
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_candidate_patches_20260612/candidate_patches.json",
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_reviewed_candidates_materialized_20260612/reviewed_rich_leaf_candidates.json",
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_artifact_candidates_materialized_20260612/rich_leaf_artifact_candidates.json",
]
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_source_corpus_coverage_gate_20260612/source_corpus_coverage_gate.json"
)
SCHEMA = "luban_rich_leaf_source_corpus_coverage_gate.v1"
INVENTORY_SCHEMA = "luban_rich_leaf_source_corpus_inventory.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _source_paths_from_bundle(bundle: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for item in _walk(bundle):
        if not isinstance(item, dict):
            continue
        for key in ("source_path", "path"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value.strip())
    return paths


def _normalize_candidate_path(value: str, *, source_root: str, inventory_paths: set[str]) -> str | None:
    normalized = value.replace("\\", "/").strip()
    if not normalized or normalized.startswith("nodes."):
        return None
    if normalized in inventory_paths:
        return normalized
    source_root_normalized = source_root.replace("\\", "/").rstrip("/")
    if source_root_normalized and normalized.startswith(source_root_normalized + "/"):
        relative = normalized[len(source_root_normalized) + 1 :]
        if relative in inventory_paths:
            return relative
    for relative in inventory_paths:
        if normalized.endswith("/" + relative):
            return relative
    return None


def _check_input_safety(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is True:
            blockers.append(f"{name}:classification_{key}_true")
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append(f"{name}:production_write_count_nonzero")
    if safety.get("release_truth_claimed") is True:
        blockers.append(f"{name}:release_truth_claimed")
    if safety.get("installed_runtime_supply") is True:
        blockers.append(f"{name}:installed_runtime_supply")
    return blockers


def _lane_summary(files: list[dict[str, Any]], covered_paths: set[str]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for item in files:
        lane = str(item.get("source_lane") or "unknown")
        relative = str(item.get("relative_path") or "")
        row = lanes.setdefault(lane, {"file_count": 0, "covered_file_count": 0, "missing_file_count": 0})
        row["file_count"] += 1
        if relative in covered_paths:
            row["covered_file_count"] += 1
        else:
            row["missing_file_count"] += 1
    return dict(sorted(lanes.items()))


def run_source_corpus_coverage_gate(
    *,
    source_corpus_inventory: dict[str, Any],
    candidate_bundles: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    if source_corpus_inventory.get("schema") != INVENTORY_SCHEMA:
        blockers.append(f"inventory_schema_mismatch:{source_corpus_inventory.get('schema')}")
    if source_corpus_inventory.get("verdict") != "PASS_SOURCE_CORPUS_INVENTORY":
        blockers.append(f"inventory_not_ready:{source_corpus_inventory.get('verdict')}")
    blockers.extend(_check_input_safety("source_corpus_inventory", source_corpus_inventory))
    for index, bundle in enumerate(candidate_bundles):
        blockers.extend(_check_input_safety(f"candidate_bundle_{index}", bundle))

    files = [
        item
        for item in source_corpus_inventory.get("files") or []
        if isinstance(item, dict) and item.get("relative_path")
    ]
    inventory_paths = {str(item["relative_path"]).replace("\\", "/") for item in files}
    source_root = str(source_corpus_inventory.get("source_root") or "")
    raw_candidate_paths: set[str] = set()
    for bundle in candidate_bundles:
        raw_candidate_paths.update(_source_paths_from_bundle(bundle))
    covered_paths = {
        normalized
        for raw in raw_candidate_paths
        for normalized in [_normalize_candidate_path(raw, source_root=source_root, inventory_paths=inventory_paths)]
        if normalized is not None
    }
    coverage_records = {
        str(item["relative_path"]).replace("\\", "/"): {
            "source_lane": item.get("source_lane"),
            "sha256": item.get("sha256"),
            "byte_count": int(item.get("byte_count") or 0),
            "covered": str(item["relative_path"]).replace("\\", "/") in covered_paths,
        }
        for item in files
    }
    missing_paths = [path for path, record in coverage_records.items() if not record["covered"]]
    gap_work_orders = [
        {
            "work_order_id": f"source_corpus_gap:{path}",
            "relative_path": path,
            "source_lane": coverage_records[path]["source_lane"],
            "sha256": coverage_records[path]["sha256"],
            "work_order_type": "rich_leaf_deep_compile_source_file",
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        }
        for path in missing_paths
    ]
    included_count = len(files)
    covered_count = len(covered_paths)
    coverage_rate = round(covered_count / included_count, 6) if included_count else 0.0
    if blockers:
        verdict = "NO_GO_INPUT_SAFETY_INVARIANT"
    elif missing_paths:
        verdict = "GAP_WORK_ORDERS_READY"
    else:
        verdict = "PASS_FULL_SOURCE_CORPUS_COVERAGE"
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "source_corpus_inventory": source_corpus_inventory.get("schema"),
            "candidate_bundles": [bundle.get("schema") for bundle in candidate_bundles],
        },
        "verdict": verdict,
        "quality_claim_allowed": False,
        "execution_mode": "coverage_gate_only",
        "summary": {
            "included_file_count": included_count,
            "candidate_bundle_count": len(candidate_bundles),
            "raw_candidate_source_path_count": len(raw_candidate_paths),
            "covered_file_count": covered_count,
            "missing_file_count": len(missing_paths),
            "coverage_rate": coverage_rate,
            "gap_work_order_count": len(gap_work_orders),
            "blocker_count": len(blockers),
            "production_write_count": 0,
            "runtime_install_count": 0,
        },
        "by_lane": _lane_summary(files, covered_paths),
        "coverage_records": coverage_records,
        "gap_work_orders": gap_work_orders,
        "blockers": blockers,
        "not_exercised": [
            "llm_rich_leaf_deep_compilation",
            "semantic_review",
            "runtime_default_install",
            "canonical_truth_write",
            "production_db_write",
            "release_truth_claim",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "source_corpus_coverage_gate": True,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--candidate-bundle", type=Path, action="append", default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    candidate_paths = args.candidate_bundle or [path for path in DEFAULT_CANDIDATE_BUNDLES if path.exists()]
    report = run_source_corpus_coverage_gate(
        source_corpus_inventory=_read_json(args.inventory),
        candidate_bundles=[_read_json(path) for path in candidate_paths],
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["verdict"] == "NO_GO_INPUT_SAFETY_INVARIANT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
