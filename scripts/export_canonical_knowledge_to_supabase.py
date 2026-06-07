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
GRAPH = _REPO / "artifacts" / "luban_grading_artifacts" / "knowledge_graph_20260606" / "knowledge_graph.json"
_DATA = Path(os.getenv("LUBAN_DATA_DIR", "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026"))
TAX_PATH = Path(os.getenv("LUBAN_TAX_PATH", str(_DATA / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json")))

_TAX_TABLE = "luban_canonical_taxonomy"
_CATALOG_TABLE = "luban_canonical_knowledge_catalog"
_EDGES_TABLE = "luban_canonical_knowledge_edges"


def _edge_rows() -> list[dict[str, Any]]:
    """Typed knowledge-graph edges from the built graph artifact (empty if not built yet)."""
    if not GRAPH.exists():
        return []
    g = json.loads(GRAPH.read_text("utf-8"))
    return [{"src": e["src"], "dst": e["dst"], "type": e["type"],
             "relation_detail": e.get("relation_detail"), "confidence": e.get("confidence"),
             "provenance": e.get("provenance") or []} for e in g.get("edges", [])]


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
    # the canonical tree has a few duplicate codes (e.g. 1A413000 appears under two L2 branches);
    # dedup by code (keep the first, prefer one carrying keywords) so the upsert PK holds.
    deduped: dict[str, dict[str, Any]] = {}
    for r in rows:
        cur = deduped.get(r["code"])
        if cur is None or (not cur.get("keywords") and r.get("keywords")):
            deduped[r["code"]] = r
    return list(deduped.values())


def _catalog_rows() -> list[dict[str, Any]]:
    bundle = json.loads(SUPPLY.read_text("utf-8"))
    from deeptutor.services.construction_grading.knowledge_unification import verify_unified_bundle
    if not verify_unified_bundle(bundle):
        raise SystemExit("ERROR: unified bundle failed integrity check — aborting export.")
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


def _apply(tax_rows: list[dict[str, Any]], cat_rows: list[dict[str, Any]],
           edge_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Idempotent apply via the direct Postgres connection (DATABASE_URL): create-if-not-exists DDL
    (additive — new catalog tables only, never touches existing data) + ON CONFLICT upsert."""
    url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not url:
        raise SystemExit("ERROR: --apply requires DATABASE_URL (or DB_URL) in env (.env).")
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import execute_values

    tax_ident, cat_ident = sql.Identifier(_TAX_TABLE), sql.Identifier(_CATALOG_TABLE)
    conn = psycopg2.connect(url, connect_timeout=30)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)  # create-if-not-exists, additive
            execute_values(
                cur,
                sql.SQL("insert into {} (code, parent_code, name, level, name_path, keywords, is_leaf) "
                        "values %s on conflict (code) do update set "
                        "parent_code=excluded.parent_code, name=excluded.name, level=excluded.level, "
                        "name_path=excluded.name_path, keywords=excluded.keywords, is_leaf=excluded.is_leaf"
                        ).format(tax_ident),
                [(r["code"], r["parent_code"], r["name"], r["level"], r["name_path"],
                  json.dumps(r["keywords"], ensure_ascii=False), r["is_leaf"]) for r in tax_rows],
            )
            execute_values(
                cur,
                sql.SQL("insert into {} (node_code, name_path, textbook_count, standard_count, "
                        "lecture_count, question_count, has_knowledge, has_question) values %s "
                        "on conflict (node_code) do update set name_path=excluded.name_path, "
                        "textbook_count=excluded.textbook_count, standard_count=excluded.standard_count, "
                        "lecture_count=excluded.lecture_count, question_count=excluded.question_count, "
                        "has_knowledge=excluded.has_knowledge, has_question=excluded.has_question"
                        ).format(cat_ident),
                [(r["node_code"], r["name_path"], r["textbook_count"], r["standard_count"],
                  r["lecture_count"], r["question_count"], r["has_knowledge"], r["has_question"])
                 for r in cat_rows],
            )
            if edge_rows:
                edge_ident = sql.Identifier(_EDGES_TABLE)
                # edges are a FULLY DERIVED set — full refresh (delete-then-insert in-txn) so removed
                # edges (cleaning pass drops cycles/siblings) don't linger as stale rows.
                cur.execute(sql.SQL("delete from {}").format(edge_ident))
                execute_values(
                    cur,
                    sql.SQL("insert into {} (src, dst, type, relation_detail, confidence, provenance) "
                            "values %s on conflict (src, dst, type) do update set "
                            "relation_detail=excluded.relation_detail, confidence=excluded.confidence, "
                            "provenance=excluded.provenance").format(edge_ident),
                    [(r["src"], r["dst"], r["type"], r["relation_detail"], r["confidence"],
                      json.dumps(r["provenance"], ensure_ascii=False)) for r in edge_rows],
                )
            conn.commit()
            cur.execute(sql.SQL("select count(*) from {}").format(tax_ident))
            n_tax = cur.fetchone()[0]
            cur.execute(sql.SQL("select count(*) from {}").format(cat_ident))
            n_cat = cur.fetchone()[0]
            cur.execute(sql.SQL("select count(*) from {}").format(sql.Identifier(_EDGES_TABLE)))
            n_edge = cur.fetchone()[0]
        return {"taxonomy_rows_in_db": n_tax, "catalog_rows_in_db": n_cat, "edge_rows_in_db": n_edge}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
-- typed knowledge-graph edges (hierarchy + authored + llm-mined prerequisite/related)
create table if not exists luban_canonical_knowledge_edges (
  src text not null,
  dst text not null,
  type text not null,
  relation_detail text,
  confidence real,
  provenance jsonb,
  primary key (src, dst, type)
);
create index if not exists idx_lkge_src on luban_canonical_knowledge_edges (src);
create index if not exists idx_lkge_dst on luban_canonical_knowledge_edges (dst);
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually upsert to Supabase (needs env creds)")
    args = ap.parse_args()
    if args.apply:
        try:
            from dotenv import load_dotenv
            load_dotenv(str(_REPO / ".env"))
        except ImportError:
            pass  # python-dotenv optional; rely on real env vars (DATABASE_URL etc.)

    tax_rows = _taxonomy_rows()
    cat_rows = _catalog_rows()
    edge_rows = _edge_rows()
    _write_dry_run(tax_rows, cat_rows)

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "taxonomy_rows": len(tax_rows),
        "catalog_rows": len(cat_rows),
        "edge_rows": len(edge_rows),
        "tables": [_TAX_TABLE, _CATALOG_TABLE, _EDGES_TABLE],
        "dry_run_output": str(OUT),
        "note": "catalog/graph layer only — grading authority stays on the local signed bundle.",
    }
    if args.apply:
        summary["applied"] = _apply(tax_rows, cat_rows, edge_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
