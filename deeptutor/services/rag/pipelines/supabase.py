"""Read-only Supabase-backed RAG pipeline."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from deeptutor.logging import get_logger
from deeptutor.services.config import get_kb_config_service
from deeptutor.services.embedding import get_embedding_client
from deeptutor.services.observability import get_langfuse_observability

DEFAULT_KB_BASE_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "knowledge_bases"
)
observability = get_langfuse_observability()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = str(os.getenv(name, default) or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def _question_like_query(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    patterns = (
        "真题",
        "做题",
        "刷题",
        "案例题",
        "选择题",
        "多选",
        "单选",
        "题目",
        "题干",
        "答案",
        "解析",
        "下列",
        "哪项",
        "哪个",
        "不属于",
        "正确的是",
    )
    return any(token in lowered for token in patterns)


def _extract_node_code_prefix(query: str) -> str | None:
    text = str(query or "").strip()
    match = re.search(r"\b\d+(?:\.\d+){1,3}\b", text)
    if match:
        return match.group(0)
    return None


def _safe_json_dumps(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _weighted_rrf_fusion(
    results_by_group: dict[str, list[dict[str, Any]]],
    weights: dict[str, float],
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    doc_map: dict[str, dict[str, Any]] = {}

    for group, results in results_by_group.items():
        weight = float(weights.get(group, 1.0))
        for rank, doc in enumerate(results):
            doc_id = str(doc.get("chunk_id") or doc.get("id") or "").strip()
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + weight * (1.0 / (k + rank + 1))
            if doc_id not in doc_map:
                doc["_source_group"] = group
                doc_map[doc_id] = doc

    fused: list[dict[str, Any]] = []
    for doc_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        doc = doc_map.get(doc_id)
        if not doc:
            continue
        doc["weighted_rrf_score"] = score
        fused.append(doc)
    return fused


def _enforce_doc_diversity(
    results: list[dict[str, Any]],
    *,
    max_per_document: int = 2,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    head: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []

    for item in results:
        source_key = (
            str(item.get("source") or "").strip()
            or str(item.get("standard_code") or "").strip()
            or str(item.get("card_title") or "").strip()
            or str(item.get("chunk_id") or "").strip()
        )
        count = counts.get(source_key, 0)
        if count < max_per_document:
            head.append(item)
            counts[source_key] = count + 1
        else:
            tail.append(item)
    return head + tail


@dataclass(slots=True)
class SupabaseSearchConfig:
    url: str
    service_key: str
    timeout_s: float
    sources: list[str]
    include_questions: bool
    top_k: int
    fetch_count: int
    match_threshold: float
    vector_weight: float
    text_weight: float
    source_weights: dict[str, float]
    question_weights: dict[str, float]
    max_per_document: int


class SupabasePipeline:
    """Query a read-only Supabase knowledge base via PostgREST RPC."""

    def __init__(self, kb_base_dir: Optional[str] = None):
        self.logger = get_logger("SupabasePipeline")
        self.kb_base_dir = kb_base_dir or DEFAULT_KB_BASE_DIR

    async def initialize(self, kb_name: str, file_paths: list[str], **kwargs) -> bool:
        _ = (kb_name, file_paths, kwargs)
        raise RuntimeError("Supabase provider is read-only and does not support local indexing.")

    async def add_documents(self, kb_name: str, file_paths: list[str], **kwargs) -> bool:
        _ = (kb_name, file_paths, kwargs)
        raise RuntimeError("Supabase provider is read-only and does not support document uploads.")

    async def delete(self, kb_name: str) -> bool:
        _ = kb_name
        raise RuntimeError("Supabase provider is read-only and cannot delete remote knowledge.")

    async def search(
        self,
        query: str,
        kb_name: str,
        **kwargs,
    ) -> dict[str, Any]:
        query = str(query or "").strip()
        if not query:
            return {"query": "", "answer": "", "content": "", "sources": [], "provider": "supabase"}

        config = self._load_search_config(kb_name=kb_name, kwargs=kwargs)
        with observability.start_observation(
            name="rag.supabase.search",
            as_type="retriever",
            input_payload={"query": query, "kb_name": kb_name},
            metadata={
                "kb_name": kb_name,
                "top_k": config.top_k,
                "sources": config.sources,
                "include_questions": config.include_questions,
            },
        ) as observation:
            query_embedding = await self._embed_query(query)
            vector_literal = _vector_literal(query_embedding)
            precision_node_code = _extract_node_code_prefix(query)
            question_like = _question_like_query(query)

            try:
                async with httpx.AsyncClient(timeout=config.timeout_s) as client:
                    tasks = [
                        self._search_source(
                            client=client,
                            query=query,
                            vector_literal=vector_literal,
                            source_type=source,
                            config=config,
                        )
                        for source in config.sources
                    ]
                    if config.include_questions or question_like:
                        tasks.append(
                            self._search_questions(
                                client=client,
                                vector_literal=vector_literal,
                                config=config,
                            )
                        )
                    if precision_node_code:
                        tasks.append(
                            self._search_precision_standard(
                                client=client,
                                vector_literal=vector_literal,
                                node_code=precision_node_code,
                                config=config,
                            )
                        )

                    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as exc:
                observability.update_observation(
                    observation,
                    metadata={"kb_name": kb_name, "sources": config.sources},
                    level="ERROR",
                    status_message=str(exc),
                )
                self.logger.error("Supabase retrieval failed: %s", exc, exc_info=True)
                return {
                    "query": query,
                    "answer": f"Search failed: {exc}",
                    "content": "",
                    "sources": [],
                    "provider": "supabase",
                }

        results_map: dict[str, list[dict[str, Any]]] = {}
        task_groups = list(config.sources)
        if config.include_questions or question_like:
            task_groups.append("questions_bank")
        if precision_node_code:
            task_groups.append("standard_precision")

        for group_name, result in zip(task_groups, raw_results):
            if isinstance(result, Exception):
                self.logger.warning("Supabase group '%s' failed: %s", group_name, result)
                continue
            results_map[group_name] = result

        fused = _weighted_rrf_fusion(
            results_map,
            {
                **config.source_weights,
                **(config.question_weights if question_like else {}),
            },
        )
        fused = _enrich_question_weights(fused, question_like=question_like, config=config)

        enriched = await self._hydrate_sources(fused[: config.fetch_count], config=config)
        enriched = _enforce_doc_diversity(enriched, max_per_document=config.max_per_document)
        final_results = enriched[: config.top_k]

        content_blocks = [str(item.get("rag_content") or "").strip() for item in final_results]
        content = "\n\n".join(block for block in content_blocks if block)

        sources = [
            {
                "title": item.get("card_title") or item.get("title") or "Document",
                "content": str(item.get("rag_content") or "")[:200],
                "source": item.get("source") or item.get("source_doc") or item.get("card_title") or "",
                "page": item.get("page_num") or item.get("page") or "",
                "chunk_id": item.get("chunk_id") or item.get("id") or "",
                "score": round(float(item.get("score") or 0.0), 4),
                "source_type": item.get("source_type") or "",
            }
            for item in final_results
        ]

        payload = {
            "query": query,
            "answer": content,
            "content": content,
            "sources": sources,
            "provider": "supabase",
        }
        observability.update_observation(
            observation,
            output_payload={
                "source_count": len(sources),
                "source_types": [item.get("source_type") or "" for item in sources],
            },
            metadata={
                "kb_name": kb_name,
                "question_like": question_like,
                "precision_node_code": precision_node_code,
            },
        )
        return payload

    async def _embed_query(self, query: str) -> list[float]:
        embeddings = await get_embedding_client().embed([query])
        if not embeddings or not embeddings[0]:
            raise RuntimeError("Embedding API returned no query embedding.")
        return embeddings[0]

    def _load_search_config(self, *, kb_name: str, kwargs: dict[str, Any]) -> SupabaseSearchConfig:
        kb_config = get_kb_config_service().get_kb_config(kb_name)
        url = str(os.getenv("SUPABASE_URL", "") or "").strip()
        service_key = (
            str(os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
            or str(os.getenv("SUPABASE_KEY", "") or "").strip()
        )
        if not url or not service_key:
            raise RuntimeError("Supabase RAG is enabled but SUPABASE_URL / SUPABASE_KEY is missing.")

        sources = kb_config.get("supabase_sources")
        if not isinstance(sources, list) or not sources:
            sources = _env_csv("SUPABASE_RAG_SOURCES", "standard,textbook,exam")
        normalized_sources = []
        for source in sources:
            candidate = str(source or "").strip().lower()
            if candidate and candidate not in normalized_sources:
                normalized_sources.append(candidate)

        top_k = max(1, int(kwargs.get("top_k") or os.getenv("SUPABASE_RAG_TOP_K", "6")))
        fetch_count = max(top_k, int(os.getenv("SUPABASE_RAG_FETCH_COUNT", str(top_k * 2))))
        include_questions = bool(kb_config.get("supabase_include_questions", _env_flag("SUPABASE_RAG_INCLUDE_QUESTIONS", True)))

        source_weights = {
            "standard": float(os.getenv("SUPABASE_RAG_WEIGHT_STANDARD", "1.4")),
            "textbook": float(os.getenv("SUPABASE_RAG_WEIGHT_TEXTBOOK", "1.0")),
            "exam": float(os.getenv("SUPABASE_RAG_WEIGHT_EXAM", "0.7")),
            "questions_bank": float(os.getenv("SUPABASE_RAG_WEIGHT_QUESTIONS", "0.4")),
            "standard_precision": float(os.getenv("SUPABASE_RAG_WEIGHT_STANDARD_PRECISION", "2.2")),
        }
        question_weights = {
            **source_weights,
            "exam": float(os.getenv("SUPABASE_RAG_QUESTION_WEIGHT_EXAM", "1.2")),
            "questions_bank": float(os.getenv("SUPABASE_RAG_QUESTION_WEIGHT_QUESTIONS", "1.5")),
        }

        return SupabaseSearchConfig(
            url=url.rstrip("/"),
            service_key=service_key,
            timeout_s=float(os.getenv("SUPABASE_RAG_TIMEOUT_S", "8.0")),
            sources=normalized_sources or ["standard", "textbook", "exam"],
            include_questions=include_questions,
            top_k=top_k,
            fetch_count=fetch_count,
            match_threshold=float(os.getenv("SUPABASE_RAG_MATCH_THRESHOLD", "0.35")),
            vector_weight=float(os.getenv("SUPABASE_RAG_VECTOR_WEIGHT", "0.7")),
            text_weight=float(os.getenv("SUPABASE_RAG_TEXT_WEIGHT", "0.3")),
            source_weights=source_weights,
            question_weights=question_weights,
            max_per_document=max(1, int(os.getenv("SUPABASE_RAG_MAX_PER_DOCUMENT", "2"))),
        )

    async def _search_source(
        self,
        *,
        client: httpx.AsyncClient,
        query: str,
        vector_literal: str,
        source_type: str,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        rows = await self._rpc(
            client,
            "search_unified",
            {
                "p_query_embedding": vector_literal,
                "p_query_text": query,
                "p_match_count": config.fetch_count,
                "p_match_threshold": config.match_threshold,
                "p_vector_weight": config.vector_weight,
                "p_text_weight": config.text_weight,
                "p_source_type": source_type,
            },
        )
        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized.append(
                {
                    "chunk_id": row.get("chunk_id"),
                    "card_title": row.get("card_title") or row.get("standard_code") or source_type,
                    "rag_content": row.get("rag_content") or "",
                    "node_code": row.get("node_code") or "",
                    "source_type": row.get("source_type") or source_type,
                    "content_type": row.get("content_type") or "",
                    "standard_code": row.get("standard_code") or "",
                    "taxonomy_path": row.get("taxonomy_path") or "",
                    "page_num": row.get("page_num"),
                    "score": row.get("final_score") or row.get("vector_score") or row.get("text_score") or 0,
                    "_source_group": source_type,
                    "_source_table": "kb_chunks",
                }
            )
        return normalized

    async def _search_precision_standard(
        self,
        *,
        client: httpx.AsyncClient,
        vector_literal: str,
        node_code: str,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        rows = await self._rpc(
            client,
            "search_kb_chunks",
            {
                "query_embedding": vector_literal,
                "match_threshold": config.match_threshold,
                "match_count": config.fetch_count,
                "filter_source": "standard",
                "filter_node_code": node_code,
            },
        )
        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized.append(
                {
                    "chunk_id": row.get("chunk_id"),
                    "card_title": row.get("card_title") or row.get("standard_code") or node_code,
                    "rag_content": row.get("rag_content") or "",
                    "node_code": row.get("node_code") or "",
                    "source_type": row.get("source_type") or "standard",
                    "content_type": row.get("content_type") or "",
                    "standard_code": row.get("standard_code") or "",
                    "taxonomy_path": row.get("taxonomy_path") or "",
                    "page_num": row.get("page_num"),
                    "score": row.get("similarity") or 0,
                    "_source_group": "standard_precision",
                    "_source_table": "kb_chunks",
                }
            )
        return normalized

    async def _search_questions(
        self,
        *,
        client: httpx.AsyncClient,
        vector_literal: str,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        rows = await self._rpc(
            client,
            "search_questions_bank_vector",
            {
                "query_embedding": vector_literal,
                "match_threshold": config.match_threshold,
                "match_count": config.fetch_count,
                "filter_question_type": None,
                "filter_source_type": None,
            },
        )
        normalized: list[dict[str, Any]] = []
        for row in rows:
            stem = str(row.get("stem") or row.get("question_stem") or "").strip()
            options = _safe_json_dumps(row.get("options") or "")
            answer = _safe_json_dumps(row.get("correct_answer") or "")
            analysis = str(row.get("analysis") or "").strip()
            rag_content = (
                f"【题目】{stem}\n【选项】{options}\n【答案】{answer}\n【解析】{analysis}".strip()
            )
            normalized.append(
                {
                    "id": row.get("id"),
                    "chunk_id": f"question-{row.get('id')}",
                    "card_title": f"题目: {stem[:40]}" if stem else "题目",
                    "rag_content": rag_content,
                    "node_code": row.get("node_code") or "",
                    "source_type": row.get("source_type") or "exam",
                    "content_type": "question",
                    "page_num": row.get("exam_year"),
                    "score": row.get("similarity") or 0,
                    "_source_group": "questions_bank",
                    "_source_table": "questions_bank",
                }
            )
        return normalized

    async def _hydrate_sources(
        self,
        results: list[dict[str, Any]],
        *,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        if not results:
            return []

        kb_chunk_ids = [
            str(item.get("chunk_id") or "").strip()
            for item in results
            if item.get("_source_table") == "kb_chunks" and str(item.get("chunk_id") or "").strip()
        ]
        unique_chunk_ids = list(dict.fromkeys(kb_chunk_ids))
        if not unique_chunk_ids:
            return results

        quoted_ids = ",".join(f'"{item}"' for item in unique_chunk_ids)
        if not quoted_ids:
            return results

        try:
            async with httpx.AsyncClient(timeout=config.timeout_s) as client:
                rows = await self._select(
                    client,
                    table="kb_chunks",
                    select="chunk_id,source_doc,metadata,standard_code,page_num",
                    query={"chunk_id": f"in.({quoted_ids})"},
                    config=config,
                )
        except Exception as exc:
            self.logger.debug("Skipping source hydration after Supabase error: %s", exc)
            return results

        row_map = {str(row.get("chunk_id") or ""): row for row in rows}
        enriched: list[dict[str, Any]] = []
        for item in results:
            row = row_map.get(str(item.get("chunk_id") or ""))
            if row:
                item["source_doc"] = row.get("source_doc") or ""
                item["source"] = row.get("source_doc") or item.get("standard_code") or item.get("card_title") or ""
                if row.get("page_num") not in (None, ""):
                    item["page_num"] = row.get("page_num")
                metadata = row.get("metadata")
                if isinstance(metadata, dict):
                    item["metadata"] = metadata
            else:
                item["source"] = item.get("standard_code") or item.get("card_title") or ""
            enriched.append(item)
        return enriched

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        function_name: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        url = f"{self._base_url(payload).rstrip('/')}/rest/v1/rpc/{function_name}"
        headers = self._headers(payload)
        with observability.start_observation(
            name=f"supabase.rpc.{function_name}",
            as_type="retriever",
            input_payload=payload,
            metadata={"function_name": function_name},
        ) as observation:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            rows = data if isinstance(data, list) else []
            observability.update_observation(
                observation,
                output_payload={"row_count": len(rows)},
                metadata={"function_name": function_name},
            )
            return rows

    async def _select(
        self,
        client: httpx.AsyncClient,
        *,
        table: str,
        select: str,
        query: dict[str, str],
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        url = f"{config.url}/rest/v1/{table}"
        headers = {
            "apikey": config.service_key,
            "Authorization": f"Bearer {config.service_key}",
        }
        with observability.start_observation(
            name=f"supabase.select.{table}",
            as_type="retriever",
            input_payload={"table": table, "select": select, "query": query},
            metadata={"table": table},
        ) as observation:
            response = await client.get(url, headers=headers, params={"select": select, **query})
            response.raise_for_status()
            data = response.json()
            rows = data if isinstance(data, list) else []
            observability.update_observation(
                observation,
                output_payload={"row_count": len(rows)},
                metadata={"table": table},
            )
            return rows

    @staticmethod
    def _headers(payload: dict[str, Any]) -> dict[str, str]:
        service_key = (
            str(os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
            or str(os.getenv("SUPABASE_KEY", "") or "").strip()
        )
        return {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _base_url(payload: dict[str, Any]) -> str:
        _ = payload
        return str(os.getenv("SUPABASE_URL", "") or "").strip()


def _enrich_question_weights(
    results: list[dict[str, Any]],
    *,
    question_like: bool,
    config: SupabaseSearchConfig,
) -> list[dict[str, Any]]:
    if not question_like:
        return results

    for index, item in enumerate(results):
        group = str(item.get("_source_group") or "")
        if group == "questions_bank":
            item["weighted_rrf_score"] = float(item.get("weighted_rrf_score") or 0) + 0.02
        elif group == "exam":
            item["weighted_rrf_score"] = float(item.get("weighted_rrf_score") or 0) + 0.01
        item["_question_like_rank"] = index
    return sorted(results, key=lambda item: float(item.get("weighted_rrf_score") or 0), reverse=True)
