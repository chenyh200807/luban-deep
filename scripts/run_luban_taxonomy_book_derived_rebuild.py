#!/usr/bin/env python3
"""Rebuild the taxonomy L5/L6 layer from the canonical textbook (candidate).

The canonical taxonomy's L1-L4 skeleton is kept as-is. The polluted L5/L6
supplement layer (multi-batch LLM output appended without dedup: code
collisions, near-duplicates, mis-parented subtrees) is REPLACED by leaves
derived deterministically from the textbook itself:

- every textbook chunk anchors to an L1-L4 node via its chunk_id code prefix
  (longest-prefix fallback when the exact code is absent);
- markdown headings (### .. ######, standalone bold lines) inside the chunk
  become leaf candidates, deduped by (anchor, normalized name);
- each leaf carries source_evidence provenance (chunk_id, page) and keywords
  from the chunk's knowledge_cards/assessment, plus keywords carried over from
  old-taxonomy leaves whose names match.

Old L5/L6 leaves are reconciled by name against the new leaves; unmapped old
leaves land in a deletion-candidate list for the owner. Output is a CANDIDATE
taxonomy — the canonical file is read-only here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "luban_taxonomy_book_derived_rebuild.v1"
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_BOOK_FILES = [
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/luban_taxonomy_book_derived_rebuild_20260612"

HEADING_RE = re.compile(r"^(#{3,6})\s+(.+?)\s*$")
BOLD_LINE_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*$")
NUMBERING_RE = re.compile(
    r"^(?:第[一二三四五六七八九十\d]+[章节]|[（(][\d一二三四五六七八九十]+[)）]|[\d一二三四五六七八九十]+[）)、.]|[\d]+(?:\.[\d]+)+|[\d]+\s)\s*"
)

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "book_derived_taxonomy_rebuild": True,
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
    "pdf_re_extraction_cross_check",
    "llm_leaf_name_refinement",
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
    if isinstance(payload, list):
        return {"content_blocks": payload}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object or list")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_heading(raw: str) -> str:
    text = raw.strip().strip("*").strip()
    while True:
        stripped = NUMBERING_RE.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    return text.rstrip("：:").strip()


def _extract_headings(content_markdown: str) -> list[dict[str, str]]:
    headings: list[dict[str, str]] = []
    for line in content_markdown.splitlines():
        line = line.strip()
        match = HEADING_RE.match(line)
        bold = BOLD_LINE_RE.match(line) if not match else None
        raw = match.group(2) if match else (bold.group(1) if bold else None)
        if raw is None:
            continue
        name = _normalize_heading(raw)
        if len(name) < 2 or name.isdigit():
            continue
        headings.append({"name": name, "raw": raw})
    return headings


def _index_l14(taxonomy: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Deep-copy the L1-L4 skeleton; return (roots, anchor index, old L5/L6 leaves)."""
    old_leaves: list[dict[str, Any]] = []

    def clone(node: dict[str, Any], depth: int) -> dict[str, Any] | None:
        level = int(node.get("level") or depth)
        if level >= 5:
            collect(node, depth)
            return None
        copied = {k: json.loads(json.dumps(v, ensure_ascii=False)) for k, v in node.items() if k != "children"}
        copied["children"] = [
            c for c in (clone(ch, depth + 1) for ch in node.get("children") or [] if isinstance(ch, dict)) if c
        ]
        return copied

    def collect(node: dict[str, Any], depth: int) -> None:
        old_leaves.append(
            {
                "code": str(node.get("code") or ""),
                "name": str(node.get("name") or ""),
                "level": node.get("level") or depth,
                "keywords": [str(k) for k in node.get("keywords") or []],
            }
        )
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                collect(ch, depth + 1)

    roots = [
        c for c in (clone(r, 1) for r in taxonomy.get("outline_structure") or [] if isinstance(r, dict)) if c
    ]
    anchors: dict[str, dict[str, Any]] = {}

    def index(node: dict[str, Any]) -> None:
        code = str(node.get("code") or "")
        if code:
            anchors.setdefault(code, node)
        for ch in node.get("children") or []:
            index(ch)

    for r in roots:
        index(r)
    return roots, anchors, old_leaves


def _resolve_anchor(prefix: str, anchors: dict[str, dict[str, Any]]) -> tuple[str, bool]:
    if prefix in anchors:
        return prefix, True
    best = ""
    for code in anchors:
        if prefix.startswith(code) and len(code) > len(best):
            best = code
    if best:
        return best, False
    for length in range(len(prefix) - 1, 5, -1):
        candidates = [c for c in anchors if c.startswith(prefix[:length])]
        if candidates:
            return sorted(candidates, key=len)[0], False
    return "", False


def build_book_derived_taxonomy_rebuild(
    *,
    taxonomy: dict[str, Any],
    book_files: list[Path],
) -> dict[str, Any]:
    blockers: list[str] = []
    roots, anchors, old_leaves = _index_l14(taxonomy)
    if not roots:
        blockers.append("taxonomy_outline_structure_empty")

    # 1) book pass: anchor every chunk, extract heading leaves
    leaves_by_anchor: dict[str, dict[str, dict[str, Any]]] = {}
    chunk_count = 0
    unanchored: list[str] = []
    for path in book_files:
        payload = _read_json(path)
        for block in payload.get("content_blocks") or []:
            if not isinstance(block, dict) or not block.get("chunk_id"):
                continue
            chunk_count += 1
            chunk_id = str(block["chunk_id"])
            prefix = chunk_id.split("_")[0]
            anchor_code, exact = _resolve_anchor(prefix, anchors)
            if not anchor_code:
                unanchored.append(chunk_id)
                continue
            content = str(block.get("content_markdown") or "")
            cards = [c for c in block.get("knowledge_cards") or [] if isinstance(c, dict)]
            assessment = block.get("assessment") if isinstance(block.get("assessment"), dict) else {}
            chunk_keywords: list[str] = []
            for card in cards:
                chunk_keywords.extend(str(k) for k in card.get("keywords") or [])
            chunk_keywords.extend(str(k) for k in assessment.get("grading_keywords") or [])
            page = (block.get("source_meta") or {}).get("page_num")
            bucket = leaves_by_anchor.setdefault(anchor_code, {})
            anchor_name = str(anchors[anchor_code].get("name") or "")
            for heading in _extract_headings(content):
                name = heading["name"]
                if name == anchor_name:
                    continue
                leaf = bucket.setdefault(
                    name,
                    {"name": name, "keywords": [], "source_evidence": [], "anchor_exact": exact},
                )
                evidence = {"chunk_id": chunk_id, "page_num": page, "source_file": path.name}
                if evidence not in leaf["source_evidence"]:
                    leaf["source_evidence"].append(evidence)
                for kw in chunk_keywords:
                    if kw not in leaf["keywords"]:
                        leaf["keywords"].append(kw)

    if chunk_count == 0:
        blockers.append("no_book_chunks_loaded")

    # 2) keyword carry-over from old leaves with matching names + reconciliation
    new_leaf_index: dict[str, tuple[str, str]] = {}
    total_new = 0
    if not blockers:
        for anchor_code, bucket in sorted(leaves_by_anchor.items()):
            anchor_node = anchors[anchor_code]
            anchor_level = int(anchor_node.get("level") or 4)
            children = []
            for seq, (name, leaf) in enumerate(sorted(bucket.items(), key=lambda kv: kv[0]), start=1):
                code = f"{anchor_code}-B{seq:03d}"
                children.append(
                    {
                        "code": code,
                        "name": name,
                        "level": anchor_level + 1,
                        "parent_code": anchor_code,
                        "keywords": leaf["keywords"][:12],
                        "source_evidence": leaf["source_evidence"],
                        "children": [],
                    }
                )
                new_leaf_index[name] = (code, anchor_code)
                total_new += 1
            anchor_node.setdefault("children", [])
            anchor_node["children"].extend(children)

    reconciliation: list[dict[str, Any]] = []
    mapped = 0
    for old in old_leaves:
        old_name = old["name"]
        hit = new_leaf_index.get(old_name)
        if hit is None:
            hit = next(
                (
                    entry
                    for name, entry in new_leaf_index.items()
                    if (name and old_name and (name in old_name or old_name in name))
                ),
                None,
            )
        if hit:
            mapped += 1
            new_code, anchor_code = hit
            reconciliation.append(
                {"old_code": old["code"], "old_name": old_name, "status": "mapped", "new_code": new_code, "anchor": anchor_code}
            )
            # carry old keywords onto the new leaf
            bucket = leaves_by_anchor.get(anchor_code) or {}
            for name, leaf in bucket.items():
                if (leaf and (name == old_name or name in old_name or old_name in name)):
                    for kw in old["keywords"]:
                        if kw not in leaf["keywords"]:
                            leaf["keywords"].append(kw)
                    break
        else:
            reconciliation.append(
                {"old_code": old["code"], "old_name": old_name, "status": "unmapped", "new_code": None, "anchor": None}
            )

    candidate: dict[str, Any] | None = None
    if not blockers:
        candidate = {
            "meta": {
                **(taxonomy.get("meta") or {}),
                "candidate_revision": "book_derived_rebuild_20260612",
                "candidate_only": True,
                "base_version": (taxonomy.get("meta") or {}).get("version"),
                "l5_l6_source": "FINAL_CLEANED_BOOK2026 textbook headings",
            },
            "stats": {
                "book_chunk_count": chunk_count,
                "book_derived_leaf_count": total_new,
                "anchored_chunk_count": chunk_count - len(unanchored),
            },
            "outline_structure": roots,
        }

    verdict = "PASS_BOOK_DERIVED_TAXONOMY_REBUILD" if candidate else "BLOCKED_BOOK_DERIVED_TAXONOMY_REBUILD"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "blockers": blockers,
        "candidate_taxonomy": candidate,
        "old_leaf_reconciliation": reconciliation,
        "unanchored_chunk_ids": unanchored,
        "summary": {
            "book_chunk_count": chunk_count,
            "unanchored_chunk_count": len(unanchored),
            "book_derived_leaf_count": total_new,
            "anchor_count": len(leaves_by_anchor),
            "old_leaf_count": len(old_leaves),
            "old_leaf_mapped_count": mapped,
            "old_leaf_unmapped_count": len(old_leaves) - mapped,
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
    parser.add_argument("--book-file", dest="book_files", type=Path, action="append", default=None)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "book_derived_rebuild_report.json")
    parser.add_argument(
        "--output-taxonomy", type=Path, default=DEFAULT_OUTPUT_DIR / "FINAL_CLEANED_TAXONOMY2026_book_derived_candidate.json"
    )
    args = parser.parse_args(argv)

    if args.output_taxonomy.resolve() == args.taxonomy.resolve():
        raise SystemExit("refusing to overwrite the canonical taxonomy in place")

    report = build_book_derived_taxonomy_rebuild(
        taxonomy=_read_json(args.taxonomy),
        book_files=args.book_files or DEFAULT_BOOK_FILES,
    )
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
