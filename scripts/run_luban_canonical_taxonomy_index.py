"""Persist a TRACKED compact canonical-taxonomy resolution index (master-plan #2: canonical everywhere).

The canonical source tree (1.4MB, external /2026 path) must not be a runtime dependency. This carves it
into a compact, tracked index (L5/L6 leaves: code + name_path + keywords) under
``runtime_supply/v_canonical_taxonomy_index`` so ``canonical_resolution`` can normalize any system's key
(learner_state concept_id, question node, free text) to canonical at runtime. Build-time only.

NO remote / DB. Re-runnable.

Usage: python scripts/run_luban_canonical_taxonomy_index.py
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_canonical_taxonomy_index"
TAX_PATH = Path(os.getenv("LUBAN_TAX_PATH", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"))

from deeptutor.services.construction_grading.canonical_taxonomy import (
    CanonicalTaxonomy,  # noqa: E402
)


def run() -> dict[str, Any]:
    tax = CanonicalTaxonomy.load(TAX_PATH)
    leaves = [{"code": c, "name_path": tax.name_path(c),
               "keywords": list(tax.node(c).keywords)} for c in tax.leaf_codes()]
    content_hash = hashlib.sha256(
        json.dumps(leaves, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    doc = {"manifest": {"schema_version": "luban_canonical_taxonomy_index.v1",
                        "namespace": "canonical_taxonomy_index", "status": "release_candidate",
                        "published": False, "leaf_count": len(leaves), "content_hash": content_hash,
                        "canonical_taxonomy_version": "FINAL_CLEANED_TAXONOMY2026"},
           "leaves": leaves}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "canonical_taxonomy_index.json").write_text(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    return {"leaves": len(leaves), "out": str(OUT)}


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
