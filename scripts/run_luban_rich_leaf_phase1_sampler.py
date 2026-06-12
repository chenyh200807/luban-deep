#!/usr/bin/env python3
"""Build the deterministic RichLeaf Phase 1 sample manifest.

This selects leaves for review/A-B preparation only. It does not compile rich
artifacts, install runtime supply, or grant release/score authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY_INDEX = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_taxonomy_index/canonical_taxonomy_index.json"
)
DEFAULT_UNIFIED_BUNDLE = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/canonical_unified_knowledge.json"
)
DEFAULT_SOURCE_ALIGNMENT_REPAIRS = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/source_alignment_repairs.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_phase1_sampler_20260611"
DEFAULT_SEED = "rich_leaf_phase1_20260611"

BUCKET_ORDER = [
    "weak/polluted/sparse",
    "question-bank-strong",
    "standard-strong",
    "textbook-strong",
    "lecture-strong",
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _content_hash(payload: dict[str, Any]) -> str:
    manifest = payload.get("manifest") if isinstance(payload, dict) else {}
    for key in ("content_hash", "hash", "bundle_content_hash"):
        if isinstance(manifest, dict) and manifest.get(key):
            return str(manifest[key])
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _taxonomy_by_leaf(taxonomy_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for leaf in taxonomy_index.get("leaves") or []:
        if isinstance(leaf, dict) and leaf.get("code"):
            out[str(leaf["code"])] = leaf
    return out


def _counts(node: dict[str, Any] | None) -> dict[str, int]:
    raw = (node or {}).get("counts") or {}
    return {name: int(raw.get(name) or 0) for name in ("textbook", "standard", "lecture", "question")}


def _negative_leaf_ids(source_alignment_repairs: dict[str, Any], unified_bundle: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("negative_hits", "source_pollution_work_orders", "work_orders", "repairs"):
        for row in source_alignment_repairs.get(key) or []:
            if isinstance(row, dict):
                leaf = row.get("leaf_id") or row.get("node_code") or row.get("canonical_leaf")
                reason = str(row.get("reason") or row.get("pollution_risk") or row.get("status") or "")
                if leaf and any(token in reason for token in ("pollution", "wrong_path", "weak")):
                    out.add(str(leaf))
    coverage = (unified_bundle.get("manifest") or {}).get("coverage") or {}
    out.update(str(leaf) for leaf in coverage.get("leaves_question_no_knowledge") or [])
    return out


def _bucket_for_leaf(leaf_id: str, counts: dict[str, int], negative_leaf_ids: set[str]) -> str | None:
    if leaf_id in negative_leaf_ids or not any(counts.values()):
        return "weak/polluted/sparse"
    if counts["question"] > 0:
        return "question-bank-strong"
    if counts["standard"] > 0:
        return "standard-strong"
    if counts["textbook"] > 0:
        return "textbook-strong"
    if counts["lecture"] > 0:
        return "lecture-strong"
    return None


def _stable_sample_key(seed: str, leaf_id: str) -> str:
    return hashlib.sha256(f"{seed}:{leaf_id}".encode("utf-8")).hexdigest()


def _candidate_row(
    *,
    leaf_id: str,
    bucket: str,
    taxonomy_leaf: dict[str, Any] | None,
    counts: dict[str, int],
    seed: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "leaf_id": leaf_id,
        "bucket": bucket,
        "name_path": str((taxonomy_leaf or {}).get("name_path") or leaf_id),
        "keywords": list((taxonomy_leaf or {}).get("keywords") or [])[:12],
        "counts": counts,
        "selection_key": _stable_sample_key(seed, leaf_id),
        "reason": reason,
        "task_pairs": [],
    }


def build_sample_manifest(
    *,
    taxonomy_index: dict[str, Any],
    unified_bundle: dict[str, Any],
    source_alignment_repairs: dict[str, Any],
    seed: str = DEFAULT_SEED,
    per_bucket: int = 10,
    candidate_pool_size: int = 30,
) -> dict[str, Any]:
    taxonomy = _taxonomy_by_leaf(taxonomy_index)
    nodes = unified_bundle.get("nodes") or {}
    negative_ids = _negative_leaf_ids(source_alignment_repairs, unified_bundle)

    candidate_pools: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKET_ORDER}
    all_leaf_ids = set(taxonomy) | {str(k) for k in nodes} | negative_ids
    for leaf_id in sorted(all_leaf_ids):
        c = _counts(nodes.get(leaf_id) if isinstance(nodes, dict) else {})
        bucket = _bucket_for_leaf(leaf_id, c, negative_ids)
        if not bucket:
            continue
        candidate_pools[bucket].append(
            _candidate_row(
                leaf_id=leaf_id,
                bucket=bucket,
                taxonomy_leaf=taxonomy.get(leaf_id),
                counts=c,
                seed=seed,
                reason="negative_or_sparse" if bucket == "weak/polluted/sparse" else "source_lane_count",
            )
        )

    selected: list[dict[str, Any]] = []
    selected_leaf_ids: set[str] = set()
    for bucket in BUCKET_ORDER:
        pool = sorted(
            candidate_pools[bucket],
            key=lambda row: (row["selection_key"], row["leaf_id"]),
        )[:candidate_pool_size]
        candidate_pools[bucket] = pool
        picked = 0
        for row in pool:
            if row["leaf_id"] in selected_leaf_ids:
                continue
            selected.append(row)
            selected_leaf_ids.add(row["leaf_id"])
            picked += 1
            if picked >= per_bucket:
                break

    selected.sort(key=lambda row: (BUCKET_ORDER.index(row["bucket"]), row["selection_key"], row["leaf_id"]))
    bucket_counts = {bucket: sum(1 for row in selected if row["bucket"] == bucket) for bucket in BUCKET_ORDER}

    return {
        "schema": "luban_rich_leaf_phase1_sample_manifest.v1",
        "seed": seed,
        "input_hashes": {
            "canonical_taxonomy_index": _content_hash(taxonomy_index),
            "canonical_unified_knowledge": _content_hash(unified_bundle),
            "source_alignment_repairs": _content_hash(source_alignment_repairs),
        },
        "bucket_rules": {
            "weak/polluted/sparse": "repair negative hit, source pollution, question_without_knowledge, or all source counts zero",
            "question-bank-strong": "counts.question > 0 and no weak/polluted marker",
            "standard-strong": "counts.standard > 0 and no higher-risk bucket",
            "textbook-strong": "counts.textbook > 0 and no higher-risk bucket",
            "lecture-strong": "counts.lecture > 0 and no higher-risk bucket",
        },
        "candidate_pool_size": candidate_pool_size,
        "per_bucket": per_bucket,
        "candidate_pools": candidate_pools,
        "selected_leaves": selected,
        "summary": {
            "bucket_count": len(BUCKET_ORDER),
            "selected_count": len(selected),
            "bucket_counts": bucket_counts,
        },
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
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy-index", type=Path, default=DEFAULT_TAXONOMY_INDEX)
    parser.add_argument("--unified-bundle", type=Path, default=DEFAULT_UNIFIED_BUNDLE)
    parser.add_argument("--source-alignment-repairs", type=Path, default=DEFAULT_SOURCE_ALIGNMENT_REPAIRS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--per-bucket", type=int, default=10)
    parser.add_argument("--candidate-pool-size", type=int, default=30)
    args = parser.parse_args(argv)

    manifest = build_sample_manifest(
        taxonomy_index=_read_json(args.taxonomy_index),
        unified_bundle=_read_json(args.unified_bundle),
        source_alignment_repairs=_read_json(args.source_alignment_repairs),
        seed=args.seed,
        per_bucket=args.per_bucket,
        candidate_pool_size=args.candidate_pool_size,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "sample_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "summary": manifest["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
