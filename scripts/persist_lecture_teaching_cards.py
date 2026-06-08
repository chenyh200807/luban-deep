"""将讲义编译输出 (JSONL) 打包成 v_lecture_teaching_cards runtime supply bundle.

运行:
    python scripts/persist_lecture_teaching_cards.py --run-id lecture_compile_20260608
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BUNDLE_DIR = ROOT / "deeptutor/services/construction_grading/runtime_supply/v_lecture_teaching_cards"
ARTIFACTS_BASE = ROOT / "artifacts/knowledge_compiler/2026"


def _sha256_hex(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def persist(run_id: str) -> None:
    src = ARTIFACTS_BASE / run_id / "lecture_teaching_cards.jsonl"
    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(src) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"Loaded {len(records)} lecture cards from {src}")

    # Summarize bundle structure
    sources: set[str] = set()
    node_codes: set[str] = set()
    for r in records:
        sp = str(r.get("source_path") or "")
        if sp:
            # Extract lecture name from path (last directory component)
            parts = sp.split("/")
            for part in parts:
                if "专用讲义" in part or "讲义" in part:
                    sources.add(part[:40])
                    break
        nc = r.get("node_code")
        if nc:
            node_codes.add(nc)

    content_hash = _sha256_hex(records)
    namespace = "lecture_teaching_cards"
    status = "release_candidate"

    manifest = {
        "schema_version": "luban_lecture_compiler.v1",
        "namespace": namespace,
        "lane": "lecture_teaching_cards",
        "status": status,
        "published": False,
        "card_count": len(records),
        "source_bundle_count": len(sources),
        "run_id": run_id,
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, status]),
        "rollback_pointer": "no_prior_lecture_bundle",
    }

    bundle = {
        "manifest": manifest,
        "records": records,
    }

    out_path = BUNDLE_DIR / "lecture_teaching_cards.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    print(f"Wrote bundle: {out_path}")
    print(f"  card_count={len(records)}, source_bundles={len(sources)}")

    pointer = {
        "namespace": namespace,
        "status": status,
        "published": False,
        "card_count": len(records),
        "content_hash": content_hash,
        "bundle_file": "lecture_teaching_cards.json",
    }
    ptr_path = BUNDLE_DIR / "canonical_pointer.json"
    with open(ptr_path, "w", encoding="utf-8") as f:
        json.dump(pointer, f, ensure_ascii=False, indent=2)
    print(f"Wrote pointer: {ptr_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    persist(args.run_id)


if __name__ == "__main__":
    main()
