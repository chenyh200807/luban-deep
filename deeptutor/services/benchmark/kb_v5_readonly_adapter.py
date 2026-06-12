"""KB v5 direct read-only retrieval adapter — BENCHMARK ONLY.

Minimal read-only adapter for the M24 A/B benchmark's RAG baseline recovery sub-step.
It connects via ``KBV5_DB_URL`` (the project's existing direct-Postgres credential,
role ``postgres`` which has USAGE on schema ``kb_v5``) and calls the production
retrieval function ``public.search_chunks_v2`` to fetch context chunks.

HARD scope guards (this is NOT a second RAG authority):
- READ-ONLY: only SELECT through ``search_chunks_v2``; never INSERT/UPDATE/DELETE/DDL,
  never GRANT, never a migration. A read-only transaction is used.
- BENCHMARK-ONLY: lives under ``services/benchmark`` (an eval surface), is never wired
  into the runtime ``RAGService``/``SupabasePipeline``, and is used only as a
  retrieval/context baseline — it never signs a scoring point or grades anything.
- NO SECRET PRINT: never logs the DB URL/key/embedding vector.

Why this path: the runtime ``SupabasePipeline`` uses the PostgREST Data API whose role
lacks USAGE on schema ``kb_v5`` (PostgreSQL 42501), so it 404/403s. The direct DB path
(role ``postgres``) reaches ``kb_v5`` and is how production retrieves. See M22S.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Single authority for bounding the lexical (tsquery) side of a kb_v5 query;
# guards against Postgres "tsquery stack too small" on long/markdown queries.
from deeptutor.services.rag.pipelines.kbv5 import lexical_query_text

EMBED_DIM = 1024
EMBED_MODEL_DEFAULT = "text-embedding-v3"
# default doc types mirror SUPABASE_RAG_SOURCES (standard,textbook,exam) + lecture (function default)
DEFAULT_DOC_TYPES = ("standard", "textbook", "exam")


class KbV5Unavailable(Exception):
    """Raised when the adapter cannot run (no driver / no url / unreachable). Fail-closed."""


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    doc_type: str
    authority: Any
    loc: Any
    content: str
    score_vector: float | None
    score_lexical: float | None
    score_final: float | None


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    latency_ms: float
    embed_dim: int
    doc_types: tuple[str, ...]
    transport: str = "kbv5_direct_postgres_readonly"
    produces_point_decision: bool = False
    role: str = "retrieval_context_baseline_not_grading_authority"


def _dashscope_embed(text: str, *, dim: int = EMBED_DIM,
                     model: str = EMBED_MODEL_DEFAULT, api_key: Optional[str] = None) -> list[float]:
    key = api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise KbV5Unavailable("DASHSCOPE_API_KEY absent for query embedding")
    body = json.dumps({"model": model, "input": text, "dimensions": dim}).encode("utf-8")
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())["data"][0]["embedding"]


def _vector_literal(emb: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in emb) + "]"


def available() -> dict[str, Any]:
    """Read-only availability probe (no query). Never writes."""
    url = os.environ.get("KBV5_DB_URL")
    try:
        import psycopg2  # noqa: F401
        drv = True
    except Exception:  # noqa: BLE001
        drv = False
    return {"kbv5_db_url_present": bool(url), "psycopg2_present": drv,
            "dashscope_key_present": bool(os.environ.get("DASHSCOPE_API_KEY")),
            "ready": bool(url and drv and os.environ.get("DASHSCOPE_API_KEY"))}


def retrieve(query: str, *, top_k: int = 5,
             doc_types: tuple[str, ...] = DEFAULT_DOC_TYPES,
             data_version: int = 2026,
             embedder: Optional[Callable[[str], list[float]]] = None,
             db_url: Optional[str] = None) -> RetrievalResult:
    """Read-only retrieval via KBV5 direct Postgres -> public.search_chunks_v2.

    ``embedder`` lets tests inject a deterministic vector (no live DashScope call). The DB
    connection is opened read-only and a SELECT-through-function is the ONLY statement run.
    """
    url = db_url or os.environ.get("KBV5_DB_URL")
    if not url:
        raise KbV5Unavailable("KBV5_DB_URL absent")
    try:
        import psycopg2
    except Exception as exc:  # noqa: BLE001
        raise KbV5Unavailable(f"psycopg2 unavailable: {exc}") from exc

    emb = (embedder or _dashscope_embed)(query)
    if len(emb) != EMBED_DIM:
        # tolerate test embedders of a different dim only if caller injected one deliberately
        if embedder is None:
            raise KbV5Unavailable(f"unexpected embedding dim {len(emb)} (expected {EMBED_DIM})")
    vec = _vector_literal(emb)

    t0 = time.monotonic()
    conn = None
    try:
        conn = psycopg2.connect(url, connect_timeout=20)
        conn.set_session(readonly=True, autocommit=True)  # hard read-only guard
        cur = conn.cursor()
        cur.execute(
            "select chunk_id, doc_id, doc_type, authority, loc, content, "
            "score_vector, score_lexical, score_final "
            "from public.search_chunks_v2("
            "query_text := %s, query_embedding := %s::vector, "
            "filter_data_version := %s, filter_doc_types := %s, top_k := %s)",
            (lexical_query_text(query), vec, data_version, list(doc_types), top_k))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
    except KbV5Unavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-closed
        raise KbV5Unavailable(f"kb_v5 retrieval failed: {str(exc)[:160]}") from exc
    finally:
        if conn is not None:
            conn.close()
    latency = (time.monotonic() - t0) * 1000.0

    chunks = []
    for r in rows:
        d = dict(zip(cols, r))
        chunks.append(RetrievedChunk(
            chunk_id=str(d.get("chunk_id")), doc_id=str(d.get("doc_id")),
            doc_type=str(d.get("doc_type")), authority=d.get("authority"), loc=d.get("loc"),
            content=str(d.get("content") or ""),
            score_vector=d.get("score_vector"), score_lexical=d.get("score_lexical"),
            score_final=d.get("score_final")))
    return RetrievalResult(query=query, chunks=chunks, latency_ms=round(latency, 1),
                           embed_dim=len(emb), doc_types=doc_types)


__all__ = ["retrieve", "available", "RetrievalResult", "RetrievedChunk",
           "KbV5Unavailable", "EMBED_DIM", "DEFAULT_DOC_TYPES"]
