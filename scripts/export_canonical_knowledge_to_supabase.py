#!/usr/bin/env python3
"""Export the canonical taxonomy + unified knowledge CATALOG to Supabase (canonical-keyed).

Builds two canonical-keyed row sets for the Supabase knowledge base — the CATALOG / graph layer, NOT
the grading authority (which stays on the local verbatim signed bundle):

  * ``luban_canonical_taxonomy``         — the L1-L6 spine: code, parent_code, name, level, name_path,
                                            keywords, is_leaf. (the single taxonomy everything pins to)
  * ``luban_canonical_knowledge_catalog``— per canonical node: name_path + how many textbook / standard
                                            / lecture / question units cover it (coverage for the
                                            kmap / syllabus_graph prototypes + content ops).

RED LINES (AGENTS §3.7 + authority discipline):
  * DEFAULT is ``--dry-run``: builds the rows, writes them to a local JSONL, prints a summary, and
    performs NO remote write. The actual upsert requires ``--apply`` AND SUPABASE_URL +
    SUPABASE_SERVICE_ROLE_KEY in the env — i.e. an explicit, credentialed, human-run step.
  * This is the catalog layer only. The tutor's grading authority is the local signed textbook bundle;
    Supabase rows here are teaching/navigation metadata, never an answer-key source.

Usage:
  python scripts/export_canonical_knowledge_to_supabase.py              # dry-run (default, no remote)
  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
      python scripts/export_canonical_knowledge_to_supabase.py --apply  # upsert (idempotent)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "supabase_canonical_export_20260606"
SUPPLY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_canonical_unified_knowledge" / "canonical_unified_knowledge.json"
TAX_PATH = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json")

_TAX_TABLE = "luban_canonical_taxonomy"
_CATALOG_TABLE = "luban_canonical_knowledge_catalog"


def _taxonomy_rows() -> list[dict[str, Any]]:
    doc = json.loads(TAX_PATH.read_text("utf-8"))
    rows: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], parent: str, trail: list[str]) -> None:
        code = str(node.get("code") or "")
        name = str(node.get("name") or "")
        name_path = " > ".join(t for t in (trail + [name]) if t)
        kids = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        if code:
            rows.append({
                "code": code, "parent_code": parent or None, "name": name,
                "level": node.get("level"), "name_path": name_path,
                "keywords": list(node.get("keywords") or []), "is_leaf": not kids,
            })
        for c in kids:
            walk(c, code, trail + [name])

    for root in doc.get("outline_structure", []):
        if isinstance(root, dict):
            walk(root, "", [])
    return rows


def _catalog_rows() -> list[dict[str, Any]]:
    bundle = json.loads(SUPPLY.read_text("utf-8"))
    rows: list[dict[str, Any]] = []
    for code, n in (bundle.get("nodes") or {}).items():
        c = n.get("counts") or {}
        rows.append({
            "node_code": code, "name_path": n.get("name_path"),
            "textbook_count": c.get("textbook", 0), "standard_count": c.get("standard", 0),
            "lecture_count": c.get("lecture", 0), "question_count": c.get("question", 0),
            "has_knowledge": bool(c.get("textbook") or c.get("standard") or c.get("lecture")),
            "has_question": bool(c.get("question")),
        })
    return rows


def _write_dry_run(tax_rows: list[dict[str, Any]], cat_rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "taxonomy_rows.jsonl").open("w", encoding="utf-8") as fh:
        for r in tax_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (OUT / "catalog_rows.jsonl").open("w", encoding="utf-8") as fh:
        for r in cat_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "schema.sql").write_text(_SCHEMA_SQL, "utf-8")


def _apply(tax_rows: list[dict[str, Any]], cat_rows: list[dict[str, Any]]) -> dict[str, Any]:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise SystemExit("ERROR: --apply requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in env.")
    from supabase import create_client  # lazy: only needed for a real write

    client = create_client(url, key)
    n_tax = 0
    for i in range(0, len(tax_rows), 500):
        client.table(_TAX_TABLE).upsert(tax_rows[i:i + 500], on_conflict="code").execute()
        n_tax += len(tax_rows[i:i + 500])
    n_cat = 0
    for i in range(0, len(cat_rows), 500):
        client.table(_CATALOG_TABLE).upsert(cat_rows[i:i + 500], on_conflict="node_code").execute()
        n_cat += len(cat_rows[i:i + 500])
    return {"taxonomy_upserted": n_tax, "catalog_upserted": n_cat}


_SCHEMA_SQL = """\
-- canonical taxonomy spine (the single taxonomy everything pins to)
create table if not exists luban_canonical_taxonomy (
  code text primary key,
  parent_code text,
  name text,
  level int,
  name_path text,
  keywords jsonb,
  is_leaf boolean
);
-- per-canonical-node coverage catalog (drives kmap / coverage dashboards)
create table if not exists luban_canonical_knowledge_catalog (
  node_code text primary key,
  name_path text,
  textbook_count int,
  standard_count int,
  lecture_count int,
  question_count int,
  has_knowledge boolean,
  has_question boolean
);
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually upsert to Supabase (needs env creds)")
    args = ap.parse_args()

    tax_rows = _taxonomy_rows()
    cat_rows = _catalog_rows()
    _write_dry_run(tax_rows, cat_rows)

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "taxonomy_rows": len(tax_rows),
        "catalog_rows": len(cat_rows),
        "tables": [_TAX_TABLE, _CATALOG_TABLE],
        "dry_run_output": str(OUT),
        "note": "catalog/graph layer only — grading authority stays on the local signed bundle.",
    }
    if args.apply:
        summary["applied"] = _apply(tax_rows, cat_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
