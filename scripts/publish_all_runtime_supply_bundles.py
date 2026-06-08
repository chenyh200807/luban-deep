"""将所有 release_candidate bundles 标记为 published=True.

Safety scope:
- 只修改本地 JSON 文件的 published 字段
- 不写远端 DB / 不推代码 / 不修改任何运行时代码
- 每个 bundle 独立处理，出错不影响其他 bundle

运行:
    python scripts/publish_all_runtime_supply_bundles.py
    python scripts/publish_all_runtime_supply_bundles.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUPPLY_DIR = ROOT / "deeptutor/services/construction_grading/runtime_supply"

# Bundles to publish (all release_candidate bundles that are unpublished)
TARGETS = [
    ("v_case_rubric_scored", "case_rubric_scored.json"),
    ("v_textbook_knowledge_full", "textbook_knowledge_release_candidate.json"),
    ("v_canonical_knowledge_graph", "graph_adjacency.json"),
    ("v_canonical_unified_knowledge", "canonical_unified_knowledge.json"),
    ("v_canonical_taxonomy_index", "canonical_taxonomy_index.json"),
    ("v_standard_clauses", "standard_clauses.json"),
    ("v_lecture_teaching_cards", "lecture_teaching_cards.json"),
    ("v_kb_v5_chunks_full", "kb_v5_chunks_full.json"),
    ("v_topic_waterproof", None),       # auto-detect
    ("v_slice_case_rubric", None),      # auto-detect
    ("v_concept_registry", None),       # multi-file, skip main bundle
]


def _sha256_hex(obj) -> str:
    import decimal

    class _E(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, decimal.Decimal):
                return float(o)
            return super().default(o)

    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, cls=_E).encode("utf-8")
    ).hexdigest()


def _auto_detect_json(bundle_dir: Path) -> Path | None:
    """Find the main JSON file in a bundle dir (not canonical_pointer)."""
    for p in sorted(bundle_dir.glob("*.json")):
        if p.name != "canonical_pointer.json":
            return p
    return None


def publish_bundle(bundle_name: str, json_file: str | None, *, dry_run: bool) -> dict:
    bundle_dir = SUPPLY_DIR / bundle_name
    if not bundle_dir.exists():
        return {"bundle": bundle_name, "status": "skipped", "reason": "dir_not_found"}

    if json_file:
        json_path = bundle_dir / json_file
    else:
        json_path = _auto_detect_json(bundle_dir)

    if not json_path or not json_path.exists():
        return {"bundle": bundle_name, "status": "skipped", "reason": "bundle_file_not_found"}

    with open(json_path) as f:
        bundle = json.load(f)

    if not isinstance(bundle, dict):
        return {"bundle": bundle_name, "status": "skipped", "reason": "bundle_not_dict"}

    manifest = bundle.get("manifest", {})
    if not manifest:
        return {"bundle": bundle_name, "status": "skipped", "reason": "no_manifest"}

    already_published = manifest.get("published", False)
    if already_published:
        return {"bundle": bundle_name, "status": "already_published"}

    status = manifest.get("status", "")
    if status not in ("release_candidate", "released"):
        return {"bundle": bundle_name, "status": "skipped",
                "reason": f"status={status!r}_not_release_candidate"}

    if dry_run:
        return {"bundle": bundle_name, "status": "would_publish",
                "file": str(json_path.name)}

    # Update manifest
    bundle["manifest"]["published"] = True
    bundle["manifest"]["published_date"] = "2026-06-08"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    # Update canonical_pointer.json if exists
    ptr_path = bundle_dir / "canonical_pointer.json"
    if ptr_path.exists():
        with open(ptr_path) as f:
            ptr = json.load(f)
        ptr["published"] = True
        ptr["published_date"] = "2026-06-08"
        with open(ptr_path, "w") as f:
            json.dump(ptr, f, ensure_ascii=False, indent=2)

    return {"bundle": bundle_name, "status": "published", "file": str(json_path.name)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    results = []
    for bundle_name, json_file in TARGETS:
        result = publish_bundle(bundle_name, json_file, dry_run=args.dry_run)
        results.append(result)
        icon = {"published": "✓", "already_published": "=", "skipped": "✗",
                "would_publish": "~"}.get(result["status"], "?")
        print(f"  {icon} {bundle_name}: {result['status']}")

    published = sum(1 for r in results if r["status"] in ("published", "would_publish"))
    skipped = sum(1 for r in results if r["status"] == "skipped")
    already = sum(1 for r in results if r["status"] == "already_published")
    print(f"\nSummary: published={published}, already_published={already}, skipped={skipped}")
    if args.dry_run:
        print("[dry-run] No files modified.")


if __name__ == "__main__":
    main()
