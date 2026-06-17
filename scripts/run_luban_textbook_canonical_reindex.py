#!/usr/bin/env python3
"""Re-pin the signed textbook bundle onto the CANONICAL taxonomy (manifest-only, signatures untouched).

Makes canonical (FINAL_CLEANED_TAXONOMY2026) the SINGLE routing taxonomy for the runtime: classifies
every signed textbook record onto a canonical leaf and writes a ``canonical_index`` + ``canonical_of_point``
into the bundle manifest. Records (and their verbatim signatures / content_hash) are NOT touched, so
``verify_lane_bundle`` still holds. The old block-derived ``node_index`` / ``path_index`` are kept for
back-compat; the runtime prefers ``canonical_index``.

NO re-sign, NO remote / DB / production. Re-runnable.

Usage:
  python scripts/run_luban_textbook_canonical_reindex.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_textbook_knowledge_full"
BUNDLE = SUPPLY / "textbook_knowledge_release_candidate.json"
TAX_PATH = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json")

from deeptutor.services.construction_grading import full_knowledge_compiler as FKC  # noqa: E402
from deeptutor.services.construction_grading import knowledge_unification as KU  # noqa: E402
from deeptutor.services.construction_grading.canonical_taxonomy import (
    CanonicalTaxonomy,  # noqa: E402
)

_NS = "textbook_knowledge_full"


def run() -> dict:
    bundle = json.loads(BUNDLE.read_text("utf-8"))
    before_hash = bundle["manifest"]["content_hash"]
    before_ok = FKC.verify_lane_bundle(bundle, _NS)

    tax = CanonicalTaxonomy.load(TAX_PATH)
    idx = KU.build_canonical_index(tax, bundle.get("records", []))

    bundle["manifest"]["canonical_index"] = idx["canonical_index"]
    bundle["manifest"]["canonical_of_point"] = idx["canonical_of_point"]
    bundle["manifest"]["canonical_taxonomy_version"] = "FINAL_CLEANED_TAXONOMY2026"
    bundle["manifest"]["canonical_stats"] = idx["canonical_stats"]

    after_hash = bundle["manifest"]["content_hash"]
    after_ok = FKC.verify_lane_bundle(bundle, _NS)

    BUNDLE.write_text(json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")

    n_records = len(bundle.get("records", []))
    indexed = len(idx["canonical_of_point"])
    return {
        "records": n_records,
        "canonical_indexed": indexed,
        "canonical_leaves": idx["canonical_leaves"],
        "canonical_stats": idx["canonical_stats"],
        "content_hash_unchanged": before_hash == after_hash,
        "verify_before": before_ok, "verify_after": after_ok,
        "ok": before_hash == after_hash and after_ok,
    }


def main() -> int:
    r = run()
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
