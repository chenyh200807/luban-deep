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
    performs NO remote write. The actual upsert requires ``--apply`` AND DATABASE_URL (or DB_URL)
    in the env — i.e. an explicit, credentialed, human-run direct-Postgres step.
  * This is the catalog layer only. The tutor's grading authority is the local signed textbook bundle;
    Supabase rows here are teaching/navigation metadata, never an answer-key source.

Usage:
  python scripts/export_canonical_knowledge_to_supabase.py              # dry-run (default, no remote)
  DATABASE_URL=postgresql://... \
      python scripts/export_canonical_knowledge_to_supabase.py --apply  # full refresh (idempotent)
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


REGISTRY = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_concept_registry" / "concept_registry.json"


def _taxonomy_rows() -> list[dict[str, Any]]:
    """Single authority: export from the governed concept_registry (the canonical SPINE), NOT the raw
    source tree. concept_id is the primary key; only ACTIVE concepts (dual-model-vetted, deprecated /
    merged excluded). This makes Supabase a projection of the same truth the runtime uses."""
    reg = json.loads(REGISTRY.read_text("utf-8"))
    rows: list[dict[str, Any]] = []
    for cid, c in (reg.get("concepts") or {}).items():
        if c.get("lifecycle", {}).get("status") != "active":
            continue
        rows.append({
            "concept_id": cid,
            "code": (c.get("alias_codes") or [None])[0],   # display alias; closure guard requires unique
            "parent_code": c.get("parent") or None,
            "name": c.get("canonical_name"),
            "level": c.get("level"),
            "name_path": c.get("canonical_path"),
            "keywords": [k["text"] for k in (c.get("keywords") or [])],
            "equivalence_status": c.get("equivalence_status"),
        })
    return rows


def _alias_to_display_code() -> dict[str, str]:
    """Map every active registry alias to the display code exported in taxonomy rows."""
    reg = json.loads(REGISTRY.read_text("utf-8"))
    out: dict[str, str] = {}
    for c in (reg.get("concepts") or {}).values():
        if c.get("lifecycle", {}).get("status") != "active":
            continue
        aliases = [a for a in (c.get("alias_codes") or []) if a]
        if not aliases:
            continue
        display_code = aliases[0]
        for alias in aliases:
            out[alias] = display_code
    return out


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


def _canonicalize_catalog_rows(
    cat_rows: list[dict[str, Any]],
    alias_to_display: dict[str, str],
) -> list[dict[str, Any]]:
    canonical: dict[str, dict[str, Any]] = {}
    for row in cat_rows:
        next_row = dict(row)
        next_row["node_code"] = alias_to_display.get(row["node_code"], row["node_code"])
        previous = canonical.get(next_row["node_code"])
        if previous is None:
            canonical[next_row["node_code"]] = next_row
            continue
        for key in ("textbook_count", "standard_count", "lecture_count", "question_count"):
            previous[key] = max(int(previous.get(key) or 0), int(next_row.get(key) or 0))
        previous["has_knowledge"] = bool(previous["has_knowledge"] or next_row["has_knowledge"])
        previous["has_question"] = bool(previous["has_question"] or next_row["has_question"])
    return list(canonical.values())


def _canonicalize_edge_rows(
    edge_rows: list[dict[str, Any]],
    alias_to_display: dict[str, str],
) -> list[dict[str, Any]]:
    canonical: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in edge_rows:
        src = alias_to_display.get(row["src"], row["src"])
        dst = alias_to_display.get(row["dst"], row["dst"])
        if src == dst:
            continue
        key = (src, dst, row["type"])
        next_row = dict(row)
        next_row["src"] = src
        next_row["dst"] = dst
        previous = canonical.get(key)
        if previous is None or float(next_row.get("confidence") or 0.0) > float(previous.get("confidence") or 0.0):
            canonical[key] = next_row
    return list(canonical.values())


def _validate_projection_closure(
    tax_rows: list[dict[str, Any]],
    cat_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
) -> None:
    codes = [r["code"] for r in tax_rows if r.get("code")]
    duplicate_codes = sorted({c for c in codes if codes.count(c) > 1})
    if duplicate_codes:
        raise SystemExit(f"ERROR: taxonomy display codes are not unique: {duplicate_codes[:10]}")

    code_set = set(codes)
    missing_catalog = sorted({r["node_code"] for r in cat_rows if r["node_code"] not in code_set})
    missing_edges = sorted({
        endpoint
        for r in edge_rows
        for endpoint in (r["src"], r["dst"])
        if endpoint not in code_set
    })
    selfloops = sorted({(r["src"], r["dst"], r["type"]) for r in edge_rows if r["src"] == r["dst"]})
    if missing_catalog or missing_edges or selfloops:
        raise SystemExit(json.dumps({
            "error": "canonical projection is not closed over taxonomy display codes",
            "missing_catalog_node_codes": missing_catalog[:20],
            "missing_edge_endpoint_codes": missing_edges[:20],
            "edge_selfloops": selfloops[:20],
        }, ensure_ascii=False, indent=2))


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
    """Idempotent full refresh via the direct Postgres connection (DATABASE_URL)."""
    url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not url:
        raise SystemExit("ERROR: --apply requires DATABASE_URL (or DB_URL) in env (.env).")
    import psycopg2
    from psycopg2.extras import execute_values

    conn = psycopg2.connect(url, connect_timeout=30)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)  # reconciles the projection schema before refreshing data
            cur.execute(
                "lock table public.luban_canonical_taxonomy, "
                "public.luban_canonical_knowledge_catalog, "
                "public.luban_canonical_knowledge_edges in access exclusive mode"
            )
            # full refresh: registry/bundle/graph artifacts are the single sources;
            # stale rows from old alias-keyed projections must not linger.
            cur.execute("delete from public.luban_canonical_knowledge_edges")
            cur.execute("delete from public.luban_canonical_knowledge_catalog")
            cur.execute("delete from public.luban_canonical_taxonomy")
            execute_values(
                cur,
                "insert into public.luban_canonical_taxonomy "
                "(concept_id, code, parent_code, name, level, name_path, keywords, equivalence_status) "
                "values %s on conflict (concept_id) do update set "
                "code=excluded.code, parent_code=excluded.parent_code, name=excluded.name, "
                "level=excluded.level, name_path=excluded.name_path, keywords=excluded.keywords, "
                "equivalence_status=excluded.equivalence_status",
                [(r["concept_id"], r["code"], r["parent_code"], r["name"], r["level"], r["name_path"],
                  json.dumps(r["keywords"], ensure_ascii=False), r["equivalence_status"]) for r in tax_rows],
            )
            execute_values(
                cur,
                "insert into public.luban_canonical_knowledge_catalog "
                "(node_code, name_path, textbook_count, standard_count, lecture_count, question_count, "
                "has_knowledge, has_question) values %s on conflict (node_code) do update set "
                "name_path=excluded.name_path, textbook_count=excluded.textbook_count, "
                "standard_count=excluded.standard_count, lecture_count=excluded.lecture_count, "
                "question_count=excluded.question_count, has_knowledge=excluded.has_knowledge, "
                "has_question=excluded.has_question",
                [(r["node_code"], r["name_path"], r["textbook_count"], r["standard_count"],
                  r["lecture_count"], r["question_count"], r["has_knowledge"], r["has_question"])
                 for r in cat_rows],
            )
            if edge_rows:
                execute_values(
                    cur,
                    "insert into public.luban_canonical_knowledge_edges "
                    "(src, dst, type, relation_detail, confidence, provenance) "
                    "values %s on conflict (src, dst, type) do update set "
                    "relation_detail=excluded.relation_detail, confidence=excluded.confidence, "
                    "provenance=excluded.provenance",
                    [(r["src"], r["dst"], r["type"], r["relation_detail"], r["confidence"],
                      json.dumps(r["provenance"], ensure_ascii=False)) for r in edge_rows],
                )
            conn.commit()
            cur.execute("select count(*) from public.luban_canonical_taxonomy")
            n_tax = cur.fetchone()[0]
            cur.execute("select count(*) from public.luban_canonical_knowledge_catalog")
            n_cat = cur.fetchone()[0]
            cur.execute("select count(*) from public.luban_canonical_knowledge_edges")
            n_edge = cur.fetchone()[0]
        return {"taxonomy_rows_in_db": n_tax, "catalog_rows_in_db": n_cat, "edge_rows_in_db": n_edge}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_SCHEMA_SQL = """\
-- canonical taxonomy spine = projection of the governed concept_registry (single authority).
-- concept_id is the durable primary key; code is the unique display alias used by catalog/edge projections.
-- the legacy code-keyed table (if present) is replaced so Supabase matches the runtime truth.
drop table if exists public.luban_canonical_taxonomy;
create table public.luban_canonical_taxonomy (
  concept_id text primary key,
  code text,
  parent_code text,
  name text,
  level int,
  name_path text,
  keywords jsonb,
  equivalence_status text
);
create index if not exists idx_lct_code on public.luban_canonical_taxonomy (code);
-- per-canonical-node coverage catalog (drives kmap / coverage dashboards)
create table if not exists public.luban_canonical_knowledge_catalog (
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
create table if not exists public.luban_canonical_knowledge_edges (
  src text not null,
  dst text not null,
  type text not null,
  relation_detail text,
  confidence real,
  provenance jsonb,
  primary key (src, dst, type)
);
create index if not exists idx_lkge_src on public.luban_canonical_knowledge_edges (src);
create index if not exists idx_lkge_dst on public.luban_canonical_knowledge_edges (dst);

-- catalog projection tables are ops-maintained via direct Postgres only.
-- They are public schema tables, so every refresh must restore the same
-- service-role-only RLS posture after create/drop.
alter table public.luban_canonical_taxonomy enable row level security;
alter table public.luban_canonical_knowledge_catalog enable row level security;
alter table public.luban_canonical_knowledge_edges enable row level security;
alter table public.luban_canonical_taxonomy force row level security;
alter table public.luban_canonical_knowledge_catalog force row level security;
alter table public.luban_canonical_knowledge_edges force row level security;
revoke all on table public.luban_canonical_taxonomy from anon, authenticated;
revoke all on table public.luban_canonical_knowledge_catalog from anon, authenticated;
revoke all on table public.luban_canonical_knowledge_edges from anon, authenticated;
comment on table public.luban_canonical_taxonomy is
  'Ops-maintained canonical taxonomy projection. RLS service-role-only; anon/authenticated revoked.';
comment on table public.luban_canonical_knowledge_catalog is
  'Ops-maintained canonical knowledge coverage projection. RLS service-role-only; anon/authenticated revoked.';
comment on table public.luban_canonical_knowledge_edges is
  'Ops-maintained canonical knowledge graph projection. RLS service-role-only; anon/authenticated revoked.';
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually upsert via DATABASE_URL/DB_URL")
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
    if args.apply and not GRAPH.exists():
        raise SystemExit(f"ERROR: --apply requires built graph artifact: {GRAPH}")
    alias_to_display = _alias_to_display_code()
    cat_rows = _canonicalize_catalog_rows(cat_rows, alias_to_display)
    edge_rows = _canonicalize_edge_rows(edge_rows, alias_to_display)
    _validate_projection_closure(tax_rows, cat_rows, edge_rows)
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
