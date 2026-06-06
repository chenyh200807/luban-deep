"""Read-only KB v5 direct-Postgres RAG pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from deeptutor.logging import get_logger
from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.rag.exceptions import RAGSearchError, wrap_rag_error
from deeptutor.services.rag.provenance import build_ranking_trace
from deeptutor.services.rag.retrieval_plan import build_retrieval_plan

EMBED_DIM = 1024
EMBED_MODEL_DEFAULT = "text-embedding-v3"
DEFAULT_DOC_TYPES = ("standard", "textbook", "exam")

observability = get_langfuse_observability()


@dataclass(frozen=True)
class _RetrievedChunk:
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
class _RetrievalResult:
    query: str
    chunks: list[_RetrievedChunk]
    latency_ms: float
    embed_dim: int
    doc_types: tuple[str, ...]


class _KbV5Unavailable(Exception):
    """Raised when the read-only KB v5 retrieval path cannot run."""


def _env_csv(name: str, default: str) -> tuple[str, ...]:
    raw = str(os.getenv(name, default) or "")
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or tuple(item.strip() for item in default.split(",") if item.strip())


def _dashscope_embed(
    text: str,
    *,
    dim: int = EMBED_DIM,
    model: str = EMBED_MODEL_DEFAULT,
    api_key: str | None = None,
) -> list[float]:
    key = api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise _KbV5Unavailable("DASHSCOPE_API_KEY absent for query embedding")
    body = json.dumps({"model": model, "input": text, "dimensions": dim}).encode("utf-8")
    req = urllib.request.Request(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as response:
        payload = json.loads(response.read())
    return list(payload["data"][0]["embedding"])


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in embedding) + "]"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retrieve_chunks(
    query: str,
    *,
    top_k: int,
    doc_types: tuple[str, ...],
    data_version: int,
    embedder: Callable[[str], list[float]] | None = None,
    db_url: str | None = None,
) -> _RetrievalResult:
    url = db_url or os.environ.get("KBV5_DB_URL")
    if not url:
        raise _KbV5Unavailable("KBV5_DB_URL absent")
    try:
        import psycopg2
    except Exception as exc:  # noqa: BLE001
        raise _KbV5Unavailable(f"psycopg2 unavailable: {exc}") from exc

    embedding = (embedder or _dashscope_embed)(query)
    if len(embedding) != EMBED_DIM and embedder is None:
        raise _KbV5Unavailable(f"unexpected embedding dim {len(embedding)} (expected {EMBED_DIM})")
    vector = _vector_literal(embedding)

    started = time.monotonic()
    conn = None
    try:
        conn = psycopg2.connect(url, connect_timeout=20)
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "select chunk_id, doc_id, doc_type, authority, loc, content, "
            "score_vector, score_lexical, score_final "
            "from public.search_chunks_v2("
            "query_text := %s, query_embedding := %s::vector, "
            "filter_data_version := %s, filter_doc_types := %s, top_k := %s)",
            (query, vector, data_version, list(doc_types), top_k),
        )
        columns = [item[0] for item in cur.description]
        rows = cur.fetchall()
        cur.close()
    except _KbV5Unavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _KbV5Unavailable(f"kb_v5 retrieval failed: {str(exc)[:160]}") from exc
    finally:
        if conn is not None:
            conn.close()

    chunks: list[_RetrievedChunk] = []
    for row in rows:
        data = dict(zip(columns, row))
        chunks.append(
            _RetrievedChunk(
                chunk_id=str(data.get("chunk_id") or ""),
                doc_id=str(data.get("doc_id") or ""),
                doc_type=str(data.get("doc_type") or ""),
                authority=_json_safe(data.get("authority")),
                loc=_json_safe(data.get("loc")),
                content=str(data.get("content") or ""),
                score_vector=_optional_float(data.get("score_vector")),
                score_lexical=_optional_float(data.get("score_lexical")),
                score_final=_optional_float(data.get("score_final")),
            )
        )
    return _RetrievalResult(
        query=query,
        chunks=chunks,
        latency_ms=round((time.monotonic() - started) * 1000.0, 1),
        embed_dim=len(embedding),
        doc_types=doc_types,
    )


def _source_title(chunk: _RetrievedChunk) -> str:
    loc = _json_safe(chunk.loc) if isinstance(chunk.loc, dict) else {}
    section = str(loc.get("section") or "").strip()
    chapter = str(loc.get("chapter") or "").strip()
    if section and chapter and section != chapter:
        return f"{chapter} / {section}"
    return section or chapter or chunk.doc_type or "KB v5 source"


def _source_span(chunk: _RetrievedChunk) -> str:
    loc = _json_safe(chunk.loc) if isinstance(chunk.loc, dict) else {}
    page = str(loc.get("page") or "").strip()
    section = str(loc.get("section") or "").strip()
    if page and section:
        return f"p.{page} {section}"
    if page:
        return f"p.{page}"
    return section


def _source_from_chunk(chunk: _RetrievedChunk) -> dict[str, Any]:
    loc = _json_safe(chunk.loc) if isinstance(chunk.loc, dict) else {}
    source_path = str(loc.get("source_path") or "").strip()
    score_final = _optional_float(chunk.score_final)
    score_vector = _optional_float(chunk.score_vector)
    score_lexical = _optional_float(chunk.score_lexical)
    return {
        "id": chunk.chunk_id,
        "source_id": chunk.chunk_id,
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "source_type": chunk.doc_type,
        "source_table": "kb_v5.chunks",
        "title": _source_title(chunk),
        "source_span": _source_span(chunk),
        "page": loc.get("page"),
        "chapter": loc.get("chapter"),
        "section": loc.get("section"),
        "source_path": source_path,
        "content": chunk.content,
        "rag_content": chunk.content,
        "score": score_final,
        "score_final": score_final,
        "score_vector": score_vector,
        "score_lexical": score_lexical,
        "authority": _json_safe(chunk.authority),
        "stable_id": chunk.chunk_id,
        "content_hash": hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()[:16],
    }


def _render_context(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "No relevant documents found."
    parts = ["KB v5 retrieval context:"]
    for index, source in enumerate(sources, start=1):
        title = str(source.get("title") or "source").strip()
        span = str(source.get("source_span") or "").strip()
        content = str(source.get("rag_content") or source.get("content") or "").strip()
        locator = f"{title} {span}".strip()
        parts.append(f"[{index}] {locator}\n{content}")
    return "\n\n".join(parts)


class KbV5Pipeline:
    """RAGService provider for the canonical KB v5 read-only retrieval path."""

    def __init__(self, **_: Any) -> None:
        self.logger = get_logger("KbV5Pipeline")

    async def initialize(self, kb_name: str, file_paths: list[str], **_: Any) -> bool:
        raise RAGSearchError(
            "kbv5 retrieval is read-only and cannot initialize knowledge bases",
            provider="kbv5",
            kb_name=kb_name,
            stage="pipeline.kbv5.initialize",
            retryable=False,
        )

    async def delete(self, kb_name: str) -> bool:
        self.logger.warning("Ignoring delete for read-only KB v5 knowledge base '{}'", kb_name)
        return False

    async def search(self, query: str, kb_name: str, **kwargs: Any) -> dict[str, Any]:
        top_k = int(kwargs.get("top_k") or os.getenv("KBV5_RAG_TOP_K", "6") or 6)
        doc_types = tuple(kwargs.get("doc_types") or _env_csv("SUPABASE_RAG_SOURCES", ",".join(DEFAULT_DOC_TYPES)))
        data_version = int(kwargs.get("data_version") or os.getenv("KBV5_RAG_DATA_VERSION", "2026") or 2026)
        retrieval_plan = build_retrieval_plan(
            query,
            include_questions_default=bool(kwargs.get("include_questions", True)),
            intent=str(kwargs.get("intent") or ""),
            question_type=str(kwargs.get("question_type") or ""),
            routing_metadata=(
                kwargs.get("routing_metadata")
                if isinstance(kwargs.get("routing_metadata"), dict)
                else {}
            ),
        )

        with observability.start_observation(
            name="rag.kbv5.search",
            as_type="retriever",
            input_payload={"query": query, "kb_name": kb_name},
            metadata={
                "kb_name": kb_name,
                "top_k": top_k,
                "doc_types": list(doc_types),
                "data_version": data_version,
                "transport": "direct_postgres_readonly",
            },
        ) as observation:
            try:
                result = await asyncio.to_thread(
                    _retrieve_chunks,
                    query,
                    top_k=top_k,
                    doc_types=doc_types,
                    data_version=data_version,
                )
            except Exception as exc:  # noqa: BLE001
                rag_error = wrap_rag_error(
                    exc,
                    provider="kbv5",
                    kb_name=kb_name,
                    query=query,
                    stage="pipeline.kbv5.search",
                    retryable=False,
                )
                observability.update_observation(
                    observation,
                    metadata={"kb_name": kb_name, "doc_types": list(doc_types)},
                    level="ERROR",
                    status_message=str(rag_error),
                )
                raise rag_error from exc

            sources = [_source_from_chunk(chunk) for chunk in result.chunks]
            content = _render_context(sources)
            ranking_trace = build_ranking_trace(sources)
            evidence_bundle = {
                "bundle_id": hashlib.sha256(f"{kb_name}:{query}:kbv5".encode("utf-8")).hexdigest()[:16],
                "query": query,
                "provider": "kbv5",
                "kb_name": kb_name,
                "content_blocks": [content],
                "sources": sources,
                "exact_question": {},
                "retrieval_plan": retrieval_plan.to_dict(),
                "ranking_trace": ranking_trace,
                "retrieval_empty": not bool(sources),
                "transport": "direct_postgres_readonly",
                "doc_types": list(result.doc_types),
                "embed_dim": result.embed_dim,
                "latency_ms": result.latency_ms,
            }
            observability.update_observation(
                observation,
                output_payload={"source_count": len(sources)},
                metadata={
                    "kb_name": kb_name,
                    "source_count": len(sources),
                    "retrieval_status": "ok" if sources else "empty",
                    "latency_ms": result.latency_ms,
                },
            )
            return {
                "query": query,
                "answer": content,
                "content": content,
                "sources": sources,
                "provider": "kbv5",
                "kb_name": kb_name,
                "retrieval_status": "ok" if sources else "empty",
                "retrieval_degraded": False,
                "evidence_bundle": evidence_bundle,
            }


__all__ = ["KbV5Pipeline"]
