#!/usr/bin/env python3
"""Repair the L1-L4 skeleton of the (book-derived) canonical taxonomy.

The legacy skeleton carried multi-generation parallel duplicate branches
(whole 1A412010..1A413070 series appearing twice) plus a handful of
different-name code collisions. Deterministic repair rules:

1. Deep merge — nodes with identical (code, name) anywhere in the tree are
   merged into the first-walk occurrence (children merged recursively by
   (code, name); keywords and source_evidence unioned).
2. Semantic merges — an explicit owner list folds known mis-coded chapter
   copies into their true nodes (e.g. the "智能建造新技术" copy that squatted
   on 1A413000 merges into 1A413070).
3. Rule B recode — remaining same-code-different-name collisions keep the
   first occurrence; later ones get a stable ``x2``/``x3`` suffix.

Output is a candidate file + decision artifact; promotion to the canonical
path is a separate explicit step (the CLI refuses to write in place).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "luban_taxonomy_skeleton_repair.v1"
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/luban_taxonomy_skeleton_repair_20260612"

# (code, name) -> (target_code, target_name)
SEMANTIC_MERGES: dict[tuple[str, str], tuple[str, str]] = {
    ("1A413000", "智能建造新技术"): ("1A413070", "智能建造新技术"),
    ("1A422000", "第5章 相关标准"): ("1A425000", "相关标准"),
    ("1A431000", "建筑工程企业资质与施工组织"): ("1A431010", "建筑工程企业资质与施工组织"),
}

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "taxonomy_skeleton_repair": True,
    "runtime_install_allowed": False,
    "production_default": False,
    "canonical_pointer_written": False,
    "release_truth_claimed": False,
    "quality_claim_allowed": False,
}
SAFETY = {
    "canonical_truth_written": False,
    "official_score_allowed": False,
    "installed_runtime_supply": False,
    "production_write_count": 0,
    "release_truth_claimed": False,
}
NOT_EXERCISED = [
    "canonical_taxonomy_overwrite",
    "downstream_consumer_migration",
    "production_rag_runtime",
    "runtime_default_install",
    "canonical_truth_write",
    "official_score",
    "production_db_write",
    "release_truth_claim",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _merge_node_into(holder: dict[str, Any], node: dict[str, Any]) -> None:
    for key in ("keywords",):
        existing = [str(v) for v in holder.get(key) or []]
        for value in node.get(key) or []:
            if str(value) not in existing:
                holder.setdefault(key, []).append(value)
                existing.append(str(value))
    for key in ("source_evidence",):
        existing_list = holder.get(key) or []
        for value in node.get(key) or []:
            if value not in existing_list:
                holder.setdefault(key, []).append(value)
    holder.setdefault("children", []).extend(node.get("children") or [])


def _deep_merge_duplicates(children: list[dict[str, Any]], merges: list[dict[str, Any]], path: str) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        key = (str(child.get("code")), str(child.get("name")))
        if key in seen:
            _merge_node_into(seen[key], child)
            merges.append({"code": key[0], "name": key[1], "parent_path": path})
        else:
            seen[key] = child
            kept.append(child)
    for child in kept:
        child["children"] = _deep_merge_duplicates(
            child.get("children") or [], merges, f"{path} > {child.get('name')}"
        )
    return kept


def _collect_global_duplicates(roots: list[dict[str, Any]], merges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge identical (code, name) nodes across branches: first walk occurrence wins."""
    index: dict[tuple[str, str], dict[str, Any]] = {}

    def walk(node: dict[str, Any], parent_children: list[dict[str, Any]], path: str) -> bool:
        key = (str(node.get("code")), str(node.get("name")))
        holder = index.get(key)
        if holder is not None and holder is not node:
            _merge_node_into(holder, node)
            merges.append({"code": key[0], "name": key[1], "parent_path": path, "scope": "cross_branch"})
            return False
        index[key] = node
        kept_children = []
        for child in node.get("children") or []:
            if isinstance(child, dict) and walk(child, kept_children, f"{path} > {node.get('name')}"):
                kept_children.append(child)
        node["children"] = kept_children
        return True

    kept_roots = []
    for root in roots:
        if walk(root, kept_roots, ""):
            kept_roots.append(root)
    return kept_roots


def _apply_semantic_merges(roots: list[dict[str, Any]], applied: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[tuple[str, str], dict[str, Any]] = {}

    def index(node: dict[str, Any]) -> None:
        targets.setdefault((str(node.get("code")), str(node.get("name"))), node)
        for ch in node.get("children") or []:
            index(ch)

    for r in roots:
        index(r)

    def prune(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept = []
        for child in children:
            key = (str(child.get("code")), str(child.get("name")))
            target_key = SEMANTIC_MERGES.get(key)
            target = targets.get(target_key) if target_key else None
            if target is not None and target is not child:
                _merge_node_into(target, child)
                applied.append({"from": list(key), "into": list(target_key)})
                continue
            child["children"] = prune(child.get("children") or [])
            kept.append(child)
        return kept

    return prune(roots)


def _recode_collisions(roots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    holders: dict[str, str] = {}
    suffix_seq: dict[str, int] = {}
    recodes: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], path: str) -> None:
        code = str(node.get("code") or "")
        name = str(node.get("name") or "")
        if code:
            if code not in holders:
                holders[code] = name
            elif holders[code] != name:
                suffix_seq[code] = suffix_seq.get(code, 1) + 1
                new_code = f"{code}x{suffix_seq[code]}"
                node["code"] = new_code
                recodes.append({"old_code": code, "new_code": new_code, "name": name, "parent_path": path})
        for child in node.get("children") or []:
            walk(child, f"{path} > {name}" if name else path)

    for root in roots:
        walk(root, "")
    return recodes


def _count_evidence_leaves(roots: list[dict[str, Any]]) -> int:
    count = 0

    def walk(node: dict[str, Any]) -> None:
        nonlocal count
        if node.get("source_evidence"):
            count += 1
        for ch in node.get("children") or []:
            walk(ch)

    for r in roots:
        walk(r)
    return count


def build_taxonomy_skeleton_repair(*, taxonomy: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(json.dumps(taxonomy, ensure_ascii=False))
    roots = [n for n in candidate.get("outline_structure") or [] if isinstance(n, dict)]
    blockers: list[str] = []
    if not roots:
        blockers.append("outline_structure_empty")

    evidence_before = _count_evidence_leaves(roots)
    merges: list[dict[str, Any]] = []
    semantic_applied: list[dict[str, Any]] = []
    recodes: list[dict[str, Any]] = []
    if not blockers:
        roots = _collect_global_duplicates(roots, merges)
        roots = _apply_semantic_merges(roots, semantic_applied)
        # cross-branch merges can re-introduce sibling duplicates; sweep again
        roots = _deep_merge_duplicates(roots, merges, "")
        recodes = _recode_collisions(roots)
        candidate["outline_structure"] = roots
        candidate["meta"] = {
            **(candidate.get("meta") or {}),
            "skeleton_repair": "skeleton_repair_20260612",
        }
        evidence_after = _count_evidence_leaves(roots)
        if evidence_after != evidence_before:
            blockers.append(f"evidence_leaf_count_changed:{evidence_before}->{evidence_after}")

    verdict = "PASS_TAXONOMY_SKELETON_REPAIR" if not blockers else "BLOCKED_TAXONOMY_SKELETON_REPAIR"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "blockers": blockers,
        "candidate_taxonomy": candidate if not blockers else None,
        "deep_merges": merges,
        "semantic_merges_applied": semantic_applied,
        "recoded_collisions": recodes,
        "summary": {
            "deep_merged_count": len(merges),
            "semantic_merged_count": len(semantic_applied),
            "recoded_collision_count": len(recodes),
            "evidence_leaf_count": evidence_before,
            "blocker_count": len(blockers),
            "production_write_count": 0,
        },
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "skeleton_repair_decision.json")
    parser.add_argument(
        "--output-taxonomy", type=Path, default=DEFAULT_OUTPUT_DIR / "FINAL_CLEANED_TAXONOMY2026_skeleton_repaired_candidate.json"
    )
    args = parser.parse_args(argv)

    if args.output_taxonomy.resolve() == args.taxonomy.resolve():
        raise SystemExit("refusing to overwrite the canonical taxonomy in place")

    report = build_taxonomy_skeleton_repair(taxonomy=_read_json(args.taxonomy))
    candidate = report.pop("candidate_taxonomy", None)
    report["candidate_taxonomy_path"] = str(args.output_taxonomy) if candidate else None
    _write_json(args.output_report, report)
    if candidate is not None:
        _write_json(args.output_taxonomy, candidate)
    print(
        json.dumps(
            {
                "output_report": str(args.output_report),
                "output_taxonomy": str(args.output_taxonomy) if candidate else None,
                "verdict": report["verdict"],
                "summary": report["summary"],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["verdict"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
