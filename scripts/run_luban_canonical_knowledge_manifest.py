#!/usr/bin/env python3
"""Build the canonical knowledge-compilation manifest (master plan §0.26.14 contract).

Pins the /2026 SOURCE corpus into a source_inventory_hash (taxonomy + textbook + standards + lectures +
questions) and indexes the signed runtime-supply lane shards (objective_answer_key / case_rubric /
source_context / concept_graph / learning_mapping) into ONE canonical manifest with hash + signature +
rollback_pointer + version + producer. Persists to runtime_supply/v_canonical_knowledge_manifest and
verifies fail-closed. Makes the knowledge-compilation pillar contract-conformant + auditable; M32's
topic shards plug in under this manifest.

NO remote / DB / production write. Re-runnable.

Usage: python scripts/run_luban_canonical_knowledge_manifest.py
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
SUPPLY_ROOT = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply"
OUT_DIR = SUPPLY_ROOT / "v_canonical_knowledge_manifest"
DATA = Path(os.getenv("LUBAN_DATA_DIR", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026"))

from deeptutor.services.construction_grading import canonical_knowledge_manifest as M  # noqa: E402


def _source_files() -> list[Path]:
    """The /2026 source corpus to pin (taxonomy + textbook + standards + lectures + questions)."""
    files: list[Path] = []
    files += [Path(p) for p in glob.glob(str(DATA / "taxonomy" / "*.json"))]
    files += [Path(p) for p in glob.glob(str(DATA / "2026教材" / "**" / "*fixed.json"), recursive=True)]
    files += [Path(p) for p in glob.glob(str(DATA / "标准文件" / "*.json"))]
    files += [Path(p) for p in glob.glob(str(DATA / "讲义" / "**" / "*.json"), recursive=True)]
    files += [Path(p) for p in glob.glob(str(DATA / "题库" / "**" / "*.json"), recursive=True)]
    return files


def run() -> dict[str, Any]:
    inv = M.source_inventory(_source_files())
    shards = M.enumerate_shards(SUPPLY_ROOT)
    manifest = M.build_manifest(
        shards, inv,
        version="2026.06.07",
        producer="run_luban_canonical_knowledge_manifest",
        rollback_pointer="legacy (no canonical manifest -> runtime uses per-shard pointers)",
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "canonical_knowledge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    # source inventory persisted separately (large file list kept out of the lean manifest)
    (OUT_DIR / "source_inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2), "utf-8")
    ok, reason = M.verify_manifest(manifest, SUPPLY_ROOT)
    return {
        "source_files_pinned": inv["file_count"],
        "source_inventory_hash": inv["inventory_hash"][:16],
        "shards": [{"lane": s["lane"], "namespace": s["namespace"], "records": s["record_count"],
                    "tier": s["tier"]} for s in shards],
        "shard_count": len(shards),
        "verify_ok": ok, "verify_reason": reason,
        "out": str(OUT_DIR),
    }


def main() -> int:
    r = run()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["verify_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
