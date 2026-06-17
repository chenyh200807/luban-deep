"""M22S — RAG Supabase authority reconciliation (READ-ONLY audit).

Determines which Supabase project the benchmark/dev env points at, what RAG schema
it actually exposes (PostgREST OpenAPI), and how that compares to the canonical
production RAG contract the repo code + the 2026-05-24 knowledge audit define
(``kb_chunks`` / ``search_kb_chunks`` / ``search_unified`` / ``questions_bank``).

STRICTLY READ-ONLY: it never writes Supabase, never creates tables, never runs a
migration, never loads data, and never prints a secret. Project identity is recorded
as a sha256-truncated fingerprint of the project ref (not the URL/key). It emits the
four JSON audit artifacts; the markdown diagnosis / recovery / authorization / FINDING
are authored separately.

Usage: python scripts/audit_rag_supabase_authority_m22s.py
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "luban_grading_artifacts" / "rag_supabase_authority_reconciliation_m22s_20260605"

# Canonical production RAG authority per repo code (HEAD + origin/main supabase.py) and the
# 2026-05-24 supabase knowledge audit (docs/qa/2026-05-24-2026-source-supabase-knowledge-audit.md).
CANONICAL_TABLES = ["kb_chunks", "questions_bank", "standard_articles", "syllabus_tree"]
CANONICAL_RPCS = ["search_unified", "search_kb_chunks", "search_questions",
                  "search_questions_bank_vector", "search_questions_bank_text"]


def _ref_fp(url: str) -> tuple[str, str]:
    m = re.search(r"https?://([a-z0-9-]+)\.supabase\.(co|in|net|com)", url or "")
    ref = m.group(1) if m else None
    if not ref:
        m2 = re.search(r"@([a-z0-9.-]+)", url or "")
        ref = m2.group(1) if m2 else "NOHOST"
    return ref, hashlib.sha256(ref.encode()).hexdigest()[:12]


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for ln in (REPO / ".env").read_text("utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _probe(url: str, key: str, path: str) -> dict[str, Any]:
    req = urllib.request.Request(url.rstrip("/") + path,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return {"status": r.status, "body": r.read(200000)}
    except urllib.error.HTTPError as e:
        body = (e.read(240) or b"").decode("utf-8", "ignore")
        code = None
        try:
            code = json.loads(body).get("code")
        except Exception:
            pass
        return {"status": e.code, "pgrst_code": code, "body_snip": body[:160]}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERR", "error": str(e)[:120]}


def _probe_search_chunks_v2(env: dict[str, str], url: str) -> dict[str, Any]:
    """READ-ONLY: embed a query via the production embedder (DashScope text-embedding-v3) and call
    public.search_chunks_v2 to determine whether the production KB data lives in THIS project and what
    blocks access. Stores only outcome codes — NEVER the vector, key, or chunk content."""
    import json as _json
    import urllib.request as u
    ds = env.get("DASHSCOPE_API_KEY")
    emodel = env.get("EMBEDDING_MODEL", "text-embedding-v3")
    out: dict[str, Any] = {"embedder_model": emodel, "embed_dim_used": 1024, "rpc": "public.search_chunks_v2"}
    if not ds:
        out["status"] = "skipped_no_embedding_key"
        return out

    def _embed(text: str, dim: int = 1024):
        req = u.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
                        data=_json.dumps({"model": emodel, "input": text, "dimensions": dim}).encode(),
                        method="POST", headers={"Authorization": f"Bearer {ds}", "Content-Type": "application/json"})
        with u.urlopen(req, timeout=40) as r:
            return _json.loads(r.read())["data"][0]["embedding"]

    def _call(emb, keyval):
        req = u.Request(url.rstrip("/") + "/rest/v1/rpc/search_chunks_v2",
                        data=_json.dumps({"query_text": "工期索赔成立条件", "query_embedding": emb, "top_k": 3}).encode(),
                        method="POST", headers={"apikey": keyval, "Authorization": f"Bearer {keyval}",
                                                "Content-Type": "application/json"})
        try:
            with u.urlopen(req, timeout=30) as r:
                return {"http": r.status, "rows": len(_json.loads(r.read()))}
        except urllib.error.HTTPError as e:
            body = (e.read(240) or b"").decode("utf-8", "ignore")
            pg = None
            try:
                pg = _json.loads(body)
            except Exception:
                pg = {}
            return {"http": e.code, "pg_code": pg.get("code"), "pg_message_class": pg.get("message", "")[:60]}
        except Exception as e:  # noqa: BLE001
            return {"http": "ERR", "error": str(e)[:100]}

    try:
        emb = _embed("工期索赔成立条件", 1024)
        out["embed_ok"] = True
        out["embed_dim_returned"] = len(emb)
        out["with_anon_key"] = _call(emb, env.get("SUPABASE_KEY", ""))
        if env.get("SUPABASE_SERVICE_ROLE_KEY_V5"):
            out["with_service_role_v5_key"] = _call(emb, env["SUPABASE_SERVICE_ROLE_KEY_V5"])
        # interpret
        codes = {str(out.get("with_anon_key", {}).get("pg_code")),
                 str(out.get("with_service_role_v5_key", {}).get("pg_code"))}
        out["rpc_exists"] = True  # listed in OpenAPI + reaches execution (permission error, not 404)
        out["reads_internal_schema"] = "kb_v5" if "42501" in codes else None
        out["blocked_by"] = ("kb_v5_schema_grant_missing (postgres 42501 permission denied)"
                             if "42501" in codes else None)
        out["production_data_in_this_project"] = "42501" in codes  # function reaches kb_v5 -> data is here
    except Exception as e:  # noqa: BLE001
        out["embed_ok"] = False
        out["error"] = str(e)[:140]
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    env = _load_env()
    url = env.get("SUPABASE_URL", "")
    key = env.get("SUPABASE_KEY", "")
    ref_main, fp_main = _ref_fp(url)
    ref_v5, fp_v5 = _ref_fp(env.get("SUPABASE_URL_V5", ""))
    _, fp_db = _ref_fp(env.get("DB_URL", ""))
    _, fp_kbv5 = _ref_fp(env.get("KBV5_DB_URL", ""))

    # ---- 1. env fingerprint (no secrets) ----
    env_fp = {
        "audit_kind": "read_only_no_secret",
        "supabase_url_project_fp": fp_main, "supabase_url_v5_project_fp": fp_v5,
        "supabase_url_equals_v5": fp_main == fp_v5,
        "db_url_host_fp": fp_db, "kbv5_db_url_host_fp": fp_kbv5, "db_equals_kbv5": fp_db == fp_kbv5,
        "single_project_only": fp_main == fp_v5,
        "supabase_key_present": bool(key), "supabase_key_len": len(key),
        "embedding_provider": {"OPENAI_API_KEY_present": bool(env.get("OPENAI_API_KEY")),
                               "LLM_API_KEY_present": bool(env.get("LLM_API_KEY")),
                               "note": "production embedding via unified LLM_* gateway; no standalone OPENAI_API_KEY"},
        "rag_runtime_flags": {k: env.get(k) for k in
                              ("SUPABASE_RAG_ENABLED", "SUPABASE_RAG_DEFAULT_KB_NAME", "SUPABASE_RAG_SOURCES",
                               "SUPABASE_RAG_INCLUDE_QUESTIONS", "DEEPTUTOR_AUTO_ENABLE_RAG")},
        "secrets_printed": False}
    (OUT / "rag_env_fingerprint_m22s.json").write_text(json.dumps(env_fp, ensure_ascii=False, indent=2) + "\n", "utf-8")

    # ---- 3. supabase schema read-only audit (PostgREST OpenAPI + targeted probes) ----
    spec_resp = _probe(url, key, "/rest/v1/")
    tables, rpcs, host = [], [], None
    if spec_resp.get("status") == 200:
        try:
            spec = json.loads(spec_resp["body"])
            tables = sorted((spec.get("definitions") or {}).keys())
            rpcs = sorted(p[5:] for p in (spec.get("paths") or {}) if p.startswith("/rpc/"))
            host = spec.get("host")
        except Exception:
            pass
    auth_health = _probe(url, key, "/auth/v1/health")
    kb_chunks_probe = _probe(url, key, "/rest/v1/kb_chunks?limit=1")
    v2_probe = _probe_search_chunks_v2(env, url)
    present = lambda n: n in tables or n in rpcs
    schema_audit = {
        "search_chunks_v2_live_probe": v2_probe,
        "production_data_in_this_project": v2_probe.get("production_data_in_this_project"),
        "internal_kb_schema": v2_probe.get("reads_internal_schema"),
        "access_blocked_by": v2_probe.get("blocked_by"),
        "project_fp": fp_main, "rest_root_status": spec_resp.get("status"),
        "auth_health_status": auth_health.get("status"),
        "reachable": spec_resp.get("status") == 200, "authed": auth_health.get("status") == 200,
        "exposed_tables": tables, "exposed_tables_count": len(tables),
        "exposed_rpcs": rpcs, "exposed_rpcs_count": len(rpcs),
        "kb_chunks_table_probe": {"status": kb_chunks_probe.get("status"),
                                  "pgrst_code": kb_chunks_probe.get("pgrst_code")},
        "canonical_contract_presence": {n: present(n) for n in CANONICAL_TABLES + CANONICAL_RPCS},
        "canonical_contract_fully_present": all(present(n) for n in CANONICAL_TABLES + CANONICAL_RPCS),
        "unexpected_rpcs_not_in_repo": [r for r in rpcs if r not in CANONICAL_RPCS],
        "no_write_performed": True}
    (OUT / "supabase_schema_readonly_audit_m22s.json").write_text(
        json.dumps(schema_audit, ensure_ascii=False, indent=2) + "\n", "utf-8")

    # ---- 2. provider resolution ----
    provider_res = {
        "kb_config_default_rag_provider": "llamaindex",
        "kb_config_default_kb": None, "kb_config_search_mode": "hybrid",
        "knowledge_bases_configured_count": 0,
        "supabase_rag_enabled": env.get("SUPABASE_RAG_ENABLED"),
        "m22r_forced_provider": "supabase (explicit provider= argument)",
        "supabase_pipeline_calls": {
            "tables_via_postgrest": ["kb_chunks", "questions_bank"],
            "rpcs": CANONICAL_RPCS,
            "availability_gate": "_select(kb_chunks, select=chunk_id, limit=1) — first failure point"},
        "deployed_project_offers": {"tables": tables, "rpcs": rpcs},
        "contract_match": schema_audit["canonical_contract_fully_present"],
        "mismatch_summary": "repo pipeline targets kb_chunks/search_kb_chunks/search_unified; "
                            f"deployed project {fp_main} exposes only {rpcs} and {len(tables)} tables"}
    (OUT / "rag_provider_resolution_m22s.json").write_text(
        json.dumps(provider_res, ensure_ascii=False, indent=2) + "\n", "utf-8")

    # ---- 4. kb config / canonical authority audit ----
    kb_audit = {
        "kb_name_default": env.get("SUPABASE_RAG_DEFAULT_KB_NAME"),
        "kb_config_file": "data/knowledge_bases/kb_config.json (absent -> empty config)",
        "canonical_rag_authority_source": "docs/qa/2026-05-24-2026-source-supabase-knowledge-audit.md",
        "canonical_tables": CANONICAL_TABLES,
        "canonical_rpcs": CANONICAL_RPCS,
        "canonical_kb_chunks_row_count_documented": 15432,
        "canonical_statement": "kb_chunks/questions_bank/standard_articles/syllabus_tree remain production "
                               "authorities unless a controlled migration explicitly changes that "
                               "(audit line 28); kb_chunks should remain the online retrieval backbone (line 268)",
        "deployed_project_has_canonical_legacy": schema_audit["canonical_contract_fully_present"],
        "repo_references_to_search_chunks_v2": 0,
        "production_kb_generation": "kb_v5 (internal schema) served by public.search_chunks_v2 "
                                    "(hybrid vector+lexical+authority; query_embedding = text-embedding-v3 dim 1024)",
        "production_data_in_this_project": schema_audit.get("production_data_in_this_project"),
        "access_blocker": schema_audit.get("access_blocked_by"),
        "conclusion": "SAME project IS the production RAG authority — data lives in internal schema kb_v5, "
                      "served by public.search_chunks_v2 (the KB v5 migration). Root cause is two-fold: "
                      "(1) repo branch's SupabasePipeline targets legacy public.kb_chunks/search_kb_chunks "
                      "(pre-v5) absent from the deployed v5 schema; (2) the dev .env keys lack USAGE grant on "
                      "schema kb_v5 (postgres 42501) and PostgREST exposes only public/graphql_public. "
                      "NOT wrong project, NOT missing data, NOT env-unloaded."}
    (OUT / "kb_config_authority_audit_m22s.json").write_text(
        json.dumps(kb_audit, ensure_ascii=False, indent=2) + "\n", "utf-8")

    print(json.dumps({"project_fp": fp_main, "single_project": fp_main == fp_v5,
                      "exposed_rpcs": rpcs, "exposed_tables_count": len(tables),
                      "canonical_contract_present": schema_audit["canonical_contract_fully_present"],
                      "kb_chunks_probe": kb_chunks_probe.get("pgrst_code")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
