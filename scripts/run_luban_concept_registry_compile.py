"""Compile the canonical taxonomy into a clean, tracked concept registry (source-root identity fix).

Reads the auto-gen canonical tree, compiles it into frozen concept identities (merge duplicates with
keyword provenance, disambiguate code collisions by name_path), and persists a TRACKED registry +
migration report under runtime_supply/v_concept_registry. This is the new identity source of truth;
the old code/position-id become aliases.

Boundary: identity repair only (NOT content-mapping recall, NOT pruning — 89% of 'empty' leaves are
real textbook concepts, verified). NO remote / DB.

Usage: python scripts/run_luban_concept_registry_compile.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_concept_registry"
TAX_PATH = Path(os.getenv("LUBAN_TAX_PATH", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"))

from deeptutor.services.construction_grading import concept_registry as CR  # noqa: E402


def _flatten(tree_path: Path) -> list[dict[str, Any]]:
    d = json.loads(tree_path.read_text("utf-8"))
    nodes: list[dict[str, Any]] = []

    def walk(n: dict[str, Any], parent: str, trail: list[str]) -> None:
        name = str(n.get("name") or "")
        np = " > ".join(t for t in (trail + [name]) if t)
        if n.get("code"):
            nodes.append({"code": str(n["code"]), "name": name, "parent": parent,
                          "name_path": np, "keywords": list(n.get("keywords") or []),
                          "level": n.get("level")})
        for c in n.get("children") or []:
            if isinstance(c, dict):
                walk(c, str(n.get("code") or ""), trail + [name])

    for r in d.get("outline_structure", []):
        if isinstance(r, dict):
            walk(r, "", [])
    return nodes


def run() -> dict[str, Any]:
    nodes = _flatten(TAX_PATH)
    reg = CR.compile_registry(nodes)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "concept_registry.json").write_text(
        json.dumps(reg, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    # migration report: old code -> concept_id, flag collided codes (need name_path to resolve)
    migration = {"old_code_to_concept": reg["alias_index"],
                 "collided_codes": sorted(k for k, v in reg["alias_index"].items() if isinstance(v, list))}
    (OUT / "migration_report.json").write_text(json.dumps(migration, ensure_ascii=False, indent=2), "utf-8")
    m = reg["manifest"]
    return {"input_nodes": m["input_nodes"], "concepts": m["concept_count"],
            "merged_concepts": m["merged_concepts"], "collided_codes": m["collided_codes"],
            "out": str(OUT)}


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
