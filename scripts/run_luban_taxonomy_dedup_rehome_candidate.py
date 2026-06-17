#!/usr/bin/env python3
"""Materialize taxonomy owner decisions as a CANDIDATE taxonomy (never in place).

Two owner decisions, executed deterministically:

1. Dedup —
   Rule A: identical siblings (same parent, same code, same name) are merged
   (first occurrence kept, children unioned by (code, name)).
   Rule B: remaining code collisions (same code, different name anywhere in the
   tree) keep the first occurrence's code; later occurrences are re-coded with
   a stable ``x2``/``x3`` suffix. Every re-code lands in a remap table.
2. Re-home — an explicit move list relocates the mis-parented subtrees under
   1A413061 (labour subcontracting, green construction, energy saving,
   construction-informatization) to their semantically correct parents. Moved
   nodes get ``{target}-m{NN}`` codes; descendants keep their own codes (then
   Rule B guarantees global uniqueness).

Outputs: candidate taxonomy JSON + decision artifact with remap table. The
canonical FINAL_CLEANED_TAXONOMY2026.json is read-only here; promotion is a
separate explicit owner action.
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

SCHEMA = "luban_taxonomy_dedup_rehome_candidate.v1"
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/luban_taxonomy_dedup_rehome_candidate_20260612"

# Owner re-home decisions: direct children of SOURCE_PARENT whose name matches
# a prefix/exact rule move to the target parent code.
SOURCE_PARENT = "1A413061"
REHOME_RULES: list[dict[str, Any]] = [
    {
        "target_parent": "1A438030",
        "target_parent_name": "劳动用工管理",
        "name_prefixes": ["劳动力", "劳务", "建筑工人实名制", "实名制管理卡"],
        "reason": "劳务/用工管理整章错挂在轻质隔墙工程施工下",
    },
    {
        "target_parent": "1A437010",
        "target_parent_name": "绿色建造及信息化技术应用管理",
        "name_prefixes": ["绿色施工信息化系统应用", "施工现场监管信息系统"],
        "reason": "绿色施工信息化系统错挂在轻质隔墙工程施工下",
    },
    {
        "target_parent": "1A437020",
        "target_parent_name": "绿色施工及环境保护",
        "name_prefixes": [
            "节能与能源利用要点",
            "节材与材料资源利用要点",
            "节水与水资源利用要点",
            "节地与土地保护要点",
            "绿色施工与环境保护",
            "绿色施工管理体系",
            "绿色施工方案与场地管理",
            "绿色施工创新技术",
            "施工现场环境保护技术要点",
            "施工现场卫生防疫与职业健康",
            "文明施工与成品保护",
            "地基与基础施工绿色技术",
        ],
        "reason": "绿色施工/四节一环保要点错挂在轻质隔墙工程施工下",
    },
    {
        "target_parent": "1A437030",
        "target_parent_name": "施工现场消防",
        "name_prefixes": ["施工现场防火安全管理"],
        "reason": "施工现场防火错挂在轻质隔墙工程施工下",
    },
    {
        "target_parent": "1A425050",
        "target_parent_name": "绿色建造的相关规定",
        "name_prefixes": [
            "建筑节能与可再生能源利用通用规范",
            "建筑节能工程质量验收要求",
            "绿色建筑评价标准",
            "建筑碳排放计算标准",
        ],
        "reason": "绿色建造相关标准条目错挂在轻质隔墙工程施工下",
    },
]

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "taxonomy_dedup_rehome_candidate": True,
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


def _merge_identical_siblings(node: dict[str, Any], merges: list[dict[str, Any]], path: str) -> None:
    children = node.get("children")
    if not isinstance(children, list):
        return
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        key = (str(child.get("code")), str(child.get("name")))
        if key in seen:
            holder = seen[key]
            holder.setdefault("children", [])
            holder["children"].extend(child.get("children") or [])
            existing = {str(k) for k in holder.get("keywords") or []}
            for kw in child.get("keywords") or []:
                if str(kw) not in existing:
                    holder.setdefault("keywords", []).append(kw)
                    existing.add(str(kw))
            merges.append({"code": key[0], "name": key[1], "parent_path": path})
        else:
            seen[key] = child
            kept.append(child)
    node["children"] = kept
    for child in kept:
        _merge_identical_siblings(child, merges, f"{path} > {child.get('name')}")


def _find_nodes_by_code(roots: list[dict[str, Any]], code: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        if str(node.get("code")) == code:
            found.append(node)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    for root in roots:
        walk(root)
    return found


def _rehome(roots: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    moves: list[dict[str, Any]] = []
    blockers: list[str] = []
    sources = _find_nodes_by_code(roots, SOURCE_PARENT)
    if not sources:
        blockers.append(f"rehome_source_parent_not_found:{SOURCE_PARENT}")
        return moves, blockers

    targets: dict[str, dict[str, Any]] = {}
    for rule in REHOME_RULES:
        candidates = _find_nodes_by_code(roots, str(rule["target_parent"]))
        named = [c for c in candidates if str(c.get("name")) == rule["target_parent_name"]] or candidates
        if named:
            targets[str(rule["target_parent"])] = named[0]

    move_seq: dict[str, int] = {}
    for source in sources:
        remaining: list[dict[str, Any]] = []
        for child in source.get("children") or []:
            name = str(child.get("name") or "")
            rule = next(
                (
                    r
                    for r in REHOME_RULES
                    if any(name.startswith(prefix) for prefix in r["name_prefixes"])
                ),
                None,
            )
            if rule is None:
                remaining.append(child)
                continue
            target_code = str(rule["target_parent"])
            target = targets.get(target_code)
            if target is None:
                blocker = f"rehome_target_parent_not_found:{target_code}"
                if blocker not in blockers:
                    blockers.append(blocker)
                remaining.append(child)
                continue
            move_seq[target_code] = move_seq.get(target_code, 0) + 1
            old_code = str(child.get("code"))
            new_code = f"{target_code}-m{move_seq[target_code]:02d}"
            child["code"] = new_code
            child["parent_code"] = target_code
            target.setdefault("children", []).append(child)
            moves.append(
                {
                    "name": name,
                    "old_code": old_code,
                    "new_code": new_code,
                    "old_parent": SOURCE_PARENT,
                    "new_parent": target_code,
                    "new_parent_name": str(rule["target_parent_name"]),
                    "reason": str(rule["reason"]),
                }
            )
        source["children"] = remaining
    return moves, blockers


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
                new_code = f"{code}-x{suffix_seq[code]}"
                node["code"] = new_code
                recodes.append({"old_code": code, "new_code": new_code, "name": name, "parent_path": path})
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, f"{path} > {name}" if name else path)

    for root in roots:
        walk(root, "")
    return recodes


def build_taxonomy_dedup_rehome_candidate(*, taxonomy: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(json.dumps(taxonomy, ensure_ascii=False))
    roots = [n for n in candidate.get("outline_structure") or [] if isinstance(n, dict)]
    blockers: list[str] = []
    if not roots:
        blockers.append("outline_structure_empty")

    merges: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []
    recodes: list[dict[str, Any]] = []
    if not blockers:
        synthetic_root = {"children": roots}
        _merge_identical_siblings(synthetic_root, merges, "")
        candidate["outline_structure"] = synthetic_root["children"]
        roots = synthetic_root["children"]
        moves, rehome_blockers = _rehome(roots)
        blockers.extend(rehome_blockers)
        recodes = _recode_collisions(roots)
        candidate["meta"] = {
            **(candidate.get("meta") or {}),
            "candidate_revision": "dedup_rehome_candidate_20260612",
            "candidate_only": True,
            "base_version": (taxonomy.get("meta") or {}).get("version"),
        }

    remap = [
        {"old_code": r["old_code"], "new_code": r["new_code"], "name": r["name"], "kind": "recode"}
        for r in recodes
    ] + [
        {"old_code": m["old_code"], "new_code": m["new_code"], "name": m["name"], "kind": "rehome"}
        for m in moves
    ]
    verdict = "PASS_TAXONOMY_DEDUP_REHOME_CANDIDATE" if not blockers else "BLOCKED_TAXONOMY_DEDUP_REHOME"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "blockers": blockers,
        "candidate_taxonomy": candidate if not blockers else None,
        "merged_identical_siblings": merges,
        "rehomed_subtrees": moves,
        "recoded_collisions": recodes,
        "remap_table": remap,
        "summary": {
            "merged_identical_sibling_count": len(merges),
            "rehomed_subtree_count": len(moves),
            "recoded_collision_count": len(recodes),
            "remap_entry_count": len(remap),
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
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "taxonomy_dedup_rehome_decision.json")
    parser.add_argument(
        "--output-taxonomy", type=Path, default=DEFAULT_OUTPUT_DIR / "FINAL_CLEANED_TAXONOMY2026_dedup_rehome_candidate.json"
    )
    args = parser.parse_args(argv)

    if args.output_taxonomy.resolve() == args.taxonomy.resolve():
        raise SystemExit("refusing to overwrite the canonical taxonomy in place")

    report = build_taxonomy_dedup_rehome_candidate(taxonomy=_read_json(args.taxonomy))
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
