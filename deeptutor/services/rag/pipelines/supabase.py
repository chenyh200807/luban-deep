"""Read-only Supabase-backed RAG pipeline."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from deeptutor.logging import get_logger
from deeptutor.services.config import get_kb_config_service
from deeptutor.services.embedding import get_embedding_client
from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.rag.exceptions import wrap_rag_error
from .supabase_strategy import (
    build_exact_question_keyword_terms,
    build_exact_question_text_candidates,
    build_second_pass_queries,
    extract_case_subquestion_items,
    rewrite_query,
    dedupe_ranked_results,
    expand_query_variants,
    classify_query_shape,
    extract_node_code_prefix,
    is_question_like_query,
    matches_allowed_question_type,
    prepare_exact_question_probe,
    resolve_group_weights,
    select_sources,
    rerank_documents,
    should_run_second_pass,
    validate_exact_question_options,
)

DEFAULT_KB_BASE_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "knowledge_bases"
)
observability = get_langfuse_observability()
_QUESTION_SELECT = (
    "id,original_id,question_type,stem,question_stem,options,"
    "correct_answer,analysis,grading_keywords,grading_rubric,"
    "option_reasoning,node_code,source_type,exam_year,"
    "background_context,parent_id,source_chunk_id,structured_rules,logic_rule"
)

_EMBEDDING_CACHE: OrderedDict[str, tuple[list[float], float]] = OrderedDict()


def _coerce_options_payload(options: Any) -> Any:
    if isinstance(options, str):
        raw = options.strip()
        if raw.startswith(("[", "{")):
            try:
                return json.loads(raw)
            except Exception:
                return options
    return options


def _option_values(options: Any) -> list[str]:
    options = _coerce_options_payload(options)
    if isinstance(options, dict):
        return [str(value or "").strip() for value in options.values() if str(value or "").strip()]
    if isinstance(options, list):
        values: list[str] = []
        for item in options:
            if isinstance(item, dict):
                value = str(item.get("value") or item.get("text") or "").strip()
            else:
                value = re.sub(r"^[A-E][\.、．\)]\s*", "", str(item or "").strip())
            if value:
                values.append(value)
        return values
    return []


def _normalize_option_overlap_text(text: Any) -> str:
    clean = re.sub(r"^[A-E][\.、．\)]\s*", "", str(text or "").strip())
    clean = re.sub(r"[\s\W_]+", "", clean, flags=re.UNICODE)
    return clean.replace("的", "")


def _option_overlap_count(*, original_query: str, options: Any) -> int:
    query_surface = _normalize_option_overlap_text(original_query)
    count = 0
    for value in _option_values(options):
        clean = _normalize_option_overlap_text(value)
        min_len = 2 if re.search(r"[\u4e00-\u9fff]", clean) else 4
        if len(clean) >= min_len and clean[:12] in query_surface:
            count += 1
    return count


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float_compat(primary: str, fallback: str, default: float) -> float:
    raw = str(os.getenv(primary, "") or "").strip()
    if not raw:
        raw = str(os.getenv(fallback, "") or "").strip()
    try:
        return float(raw) if raw else float(default)
    except Exception:
        return float(default)


def _env_int_compat(primary: str, fallback: str, default: int) -> int:
    raw = str(os.getenv(primary, "") or "").strip()
    if not raw:
        raw = str(os.getenv(fallback, "") or "").strip()
    try:
        return int(raw) if raw else int(default)
    except Exception:
        return int(default)


def _embedding_cache_enabled() -> bool:
    return _env_flag(
        "SUPABASE_RAG_EMBEDDING_CACHE_ENABLED",
        _env_flag("FF_EMBEDDING_CACHE_ENABLED", True),
    )


def _get_cached_embedding(query: str) -> list[float] | None:
    ttl_s = _env_float_compat(
        "SUPABASE_RAG_EMBEDDING_CACHE_TTL_SECONDS",
        "EMBEDDING_CACHE_TTL_SECONDS",
        600.0,
    )
    key = hashlib.sha256(str(query or "").encode("utf-8")).hexdigest()
    entry = _EMBEDDING_CACHE.get(key)
    if entry and (time.time() - entry[1]) < ttl_s:
        try:
            _EMBEDDING_CACHE.move_to_end(key)
        except KeyError:
            pass
        return entry[0]
    if entry:
        _EMBEDDING_CACHE.pop(key, None)
    return None


def _cache_embedding(query: str, embedding: list[float]) -> None:
    max_entries = _env_int_compat(
        "SUPABASE_RAG_EMBEDDING_CACHE_MAX_ENTRIES",
        "EMBEDDING_CACHE_MAX_ENTRIES",
        1000,
    )
    key = hashlib.sha256(str(query or "").encode("utf-8")).hexdigest()
    if key in _EMBEDDING_CACHE:
        _EMBEDDING_CACHE[key] = (embedding, time.time())
        try:
            _EMBEDDING_CACHE.move_to_end(key)
        except KeyError:
            pass
        return
    if len(_EMBEDDING_CACHE) >= max_entries:
        try:
            _EMBEDDING_CACHE.popitem(last=False)
        except KeyError:
            pass
    _EMBEDDING_CACHE[key] = (embedding, time.time())


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = str(os.getenv(name, default) or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def _safe_json_dumps(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _rag_warning_payload(
    *,
    phase: str,
    group_name: str,
    query: str,
    exc: Exception,
) -> dict[str, str]:
    return {
        "phase": str(phase or "").strip() or "primary",
        "group_name": str(group_name or "").strip(),
        "query": str(query or "").strip(),
        "message": str(exc).strip() or exc.__class__.__name__,
    }


_CASE_SUPPORT_TOKEN_RE = re.compile(r"[A-Za-z0-9.%/_-]+|[\u4e00-\u9fff]{2,12}")
_CASE_SUPPORT_STOPWORDS = {
    "问题",
    "背景资料",
    "案例题",
    "案例",
    "工程",
    "施工",
    "项目",
    "计算",
    "列式",
    "步骤",
    "多少",
    "万元",
    "亿元",
    "答出",
    "说明理由",
}


def _normalized_text_signature(value: Any, *, limit: int = 400) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:limit]


def _dedupe_rendered_content_blocks(blocks: list[str]) -> list[str]:
    deduped: list[str] = []
    seen_signatures: set[str] = set()

    for block in blocks:
        clean = str(block or "").strip()
        if not clean:
            continue
        signature = _normalized_text_signature(clean, limit=600)
        if not signature or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped.append(clean)

    return deduped


def _dedupe_source_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or item.get("id") or "").strip()
        if chunk_id and chunk_id in seen_ids:
            continue
        title = _normalized_text_signature(item.get("title") or "")
        content = _normalized_text_signature(item.get("content") or "", limit=220)
        signature = f"{title}|{content}" if title or content else ""
        if signature and signature in seen_signatures:
            continue
        if chunk_id:
            seen_ids.add(chunk_id)
        if signature:
            seen_signatures.add(signature)
        deduped.append(item)

    return deduped


def _build_evidence_bundle(
    *,
    query: str,
    provider: str,
    kb_name: str,
    content_blocks: list[str],
    sources: list[dict[str, Any]],
    exact_question: dict[str, Any] | None,
    source_plan,
    query_shape: str,
    rewritten,
    second_pass_queries: list[str],
) -> dict[str, Any]:
    return {
        "bundle_id": hashlib.sha256(f"{kb_name}:{query}".encode("utf-8")).hexdigest()[:16],
        "query": query,
        "provider": provider,
        "kb_name": kb_name,
        "query_shape": query_shape,
        "retrieval_query": str(rewritten.primary_query or query).strip(),
        "query_rewrite": {
            "normalized_query": str(rewritten.normalized_query or "").strip(),
            "keywords": list(rewritten.keywords or []),
            "standard_codes": list(rewritten.standard_codes or []),
            "reasons": list(rewritten.reasons or []),
            "second_pass_queries": list(second_pass_queries or []),
        },
        "source_plan": (
            source_plan.to_trace_dict()
            if hasattr(source_plan, "to_trace_dict")
            else {}
        ),
        "content_blocks": list(content_blocks or []),
        "sources": list(sources or []),
        "exact_question": dict(exact_question or {}),
        "retrieval_empty": not bool(sources),
    }


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


def _apply_similarity_floor(
    fused: list[dict[str, Any]],
    results_map: dict[str, list[dict[str, Any]]],
    *,
    target_window: int,
) -> list[dict[str, Any]]:
    threshold = _env_float_compat("SUPABASE_RAG_SIM_FLOOR_THRESHOLD", "SIM_FLOOR_THRESHOLD", 0.72)
    boost_factor = _env_float_compat("SUPABASE_RAG_SIM_FLOOR_BOOST", "SIM_FLOOR_BOOST", 0.02)
    max_boosted = _env_int_compat("SUPABASE_RAG_SIM_FLOOR_MAX_BOOSTED", "SIM_FLOOR_MAX_BOOSTED", 3)
    hard_threshold = _env_float_compat(
        "SUPABASE_RAG_SIM_FLOOR_HARD_THRESHOLD",
        "SIM_FLOOR_HARD_THRESHOLD",
        0.82,
    )
    hard_max = _env_int_compat("SUPABASE_RAG_SIM_FLOOR_HARD_MAX", "SIM_FLOOR_HARD_MAX", 2)

    if target_window <= 0 or not fused:
        return fused

    chunk_best_sim: dict[str, float] = {}
    chunk_source_doc: dict[str, dict[str, Any]] = {}
    for source_results in results_map.values():
        for chunk in source_results:
            sim = chunk.get("similarity")
            if not isinstance(sim, (int, float)):
                sim = chunk.get("score") or 0.0
            sim = float(sim or 0.0)
            if sim < threshold:
                continue
            chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
            if not chunk_id:
                continue
            if sim > chunk_best_sim.get(chunk_id, 0.0):
                chunk_best_sim[chunk_id] = sim
                chunk_source_doc[chunk_id] = dict(chunk)

    if not chunk_best_sim:
        return fused

    eligible = sorted(chunk_best_sim.items(), key=lambda item: item[1], reverse=True)
    boost_ids = {chunk_id for chunk_id, _ in eligible[:max_boosted]}
    for chunk in fused:
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        if chunk_id not in boost_ids:
            continue
        sim = chunk_best_sim[chunk_id]
        original_score = float(chunk.get("weighted_rrf_score") or 0.0)
        chunk["weighted_rrf_score"] = original_score + (boost_factor * sim)
        chunk["_sim_floor_boosted"] = True
        chunk["_sim_floor_original_score"] = original_score

    fused.sort(key=lambda item: float(item.get("weighted_rrf_score") or 0.0), reverse=True)

    hard_candidates = [
        (chunk_id, sim)
        for chunk_id, sim in chunk_best_sim.items()
        if sim >= hard_threshold
    ]
    hard_candidates.sort(key=lambda item: item[1], reverse=True)

    for chunk_id, sim in hard_candidates[:hard_max]:
        window_end = min(target_window, len(fused))
        in_window = any(
            str(fused[index].get("chunk_id") or fused[index].get("id") or "").strip() == chunk_id
            for index in range(window_end)
        )
        if in_window:
            continue

        source_index = None
        for index, chunk in enumerate(fused):
            if str(chunk.get("chunk_id") or chunk.get("id") or "").strip() == chunk_id:
                source_index = index
                break

        if source_index is None and chunk_id in chunk_source_doc:
            doc = dict(chunk_source_doc[chunk_id])
            doc["weighted_rrf_score"] = boost_factor * sim
            fused.append(doc)
            source_index = len(fused) - 1

        if source_index is None:
            continue

        fused[source_index]["_sim_floor_guaranteed"] = True
        worst_index = None
        worst_score = float("inf")
        for index in range(window_end):
            if fused[index].get("_sim_floor_guaranteed"):
                continue
            score = float(fused[index].get("weighted_rrf_score") or 0.0)
            if score < worst_score:
                worst_score = score
                worst_index = index
        if worst_index is None or worst_index == source_index:
            continue
        fused[source_index], fused[worst_index] = fused[worst_index], fused[source_index]

    return fused


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
    query_expansion_enabled: bool
    max_query_variants: int
    second_pass_enabled: bool
    second_pass_max_queries: int
    second_pass_min_hits: int
    second_pass_max_dup_ratio: float
    rerank_enabled: bool
    rerank_window: int
    rerank_timeout_s: float
    exact_question_enabled: bool
    exact_question_text_first: bool
    exact_question_min_similarity: float
    exact_question_max_text_len: int
    exact_question_text_rpc_enabled: bool


class SupabasePipeline:
    """Query a read-only Supabase knowledge base via PostgREST RPC."""

    def __init__(self, kb_base_dir: Optional[str] = None):
        self.logger = get_logger("SupabasePipeline")
        self.kb_base_dir = kb_base_dir or DEFAULT_KB_BASE_DIR
        self._client: httpx.AsyncClient | None = None
        self._client_timeout_s: float | None = None

    async def _get_client(self, timeout_s: float) -> httpx.AsyncClient:
        normalized_timeout = float(timeout_s)
        if self._client is not None and self._client_timeout_s == normalized_timeout:
            return self._client
        if self._client is not None:
            await self._client.aclose()
        self._client = httpx.AsyncClient(timeout=normalized_timeout)
        self._client_timeout_s = normalized_timeout
        return self._client

    async def aclose(self) -> None:
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None
        self._client_timeout_s = None

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
        intent = str(kwargs.get("intent") or "").strip()
        question_type = str(kwargs.get("question_type") or "").strip()
        routing_metadata = kwargs.get("routing_metadata")
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
            precision_node_code = extract_node_code_prefix(query)
            rewritten = rewrite_query(query, max_variants=config.max_query_variants)
            question_like = is_question_like_query(query) or rewritten.query_shape == "mcq_like"
            source_plan = select_sources(
                query,
                include_questions_default=config.include_questions,
                intent=intent,
                question_type=question_type,
                routing_metadata=(
                    routing_metadata if isinstance(routing_metadata, dict) else None
                ),
            )
            query_shape = rewritten.query_shape or classify_query_shape(query)
            exact_probe = (
                prepare_exact_question_probe(query)
                if config.exact_question_enabled and source_plan.search_questions_bank
                else None
            )
            case_query_items = (
                extract_case_subquestion_items(query, max_items=8)
                if query_shape == "case_like" and exact_probe
                else []
            )
            case_exact_queries = [
                str(item.get("prompt") or "").strip()
                for item in case_query_items
                if isinstance(item, dict) and str(item.get("prompt") or "").strip()
            ]
            primary_queries = (
                expand_query_variants(query, max_variants=config.max_query_variants)
                if config.query_expansion_enabled
                else [rewritten.primary_query or query]
            ) or [rewritten.primary_query or query]
            exact_text_plans: list[dict[str, Any]] = []
            retrieval_warnings: list[dict[str, str]] = []

            try:
                client = await self._get_client(config.timeout_s)
                exact_text_task: asyncio.Task[list[dict[str, Any]]] | None = None
                if (
                    exact_probe
                    and config.exact_question_text_first
                    and len(exact_probe.query) <= config.exact_question_max_text_len
                ):
                    exact_text_candidates = [exact_probe.query]
                    for candidate in case_exact_queries:
                        if candidate not in exact_text_candidates:
                            exact_text_candidates.append(candidate)
                    exact_text_task = asyncio.create_task(
                        self._search_exact_question_text_batch(
                            client=client,
                            probe_queries=exact_text_candidates,
                            allowed_question_types=exact_probe.allowed_question_types,
                            original_query=query,
                            option_validation_required=exact_probe.option_validation_required,
                            config=config,
                            warning_sink=retrieval_warnings,
                        )
                    )
                primary_plan_task = asyncio.create_task(
                    self._run_query_plan(
                        client=client,
                        queries=primary_queries,
                        question_like=question_like,
                        source_plan=source_plan,
                        standard_codes=rewritten.standard_codes,
                        precision_node_code=precision_node_code,
                        exact_probe=exact_probe,
                        original_query=query,
                        config=config,
                        failure_sink=retrieval_warnings,
                    )
                )
                primary_plan = await primary_plan_task
                if exact_text_task is not None:
                    exact_text_batches = await exact_text_task
                    for batch_index, batch in enumerate(exact_text_batches):
                        exact_text_rows = batch.get("results") if isinstance(batch, dict) else None
                        if exact_text_rows:
                            exact_text_plans.append(
                                {
                                    "phase": "primary",
                                    "group_name": "question_exact_text",
                                    "query": str(batch.get("query") or exact_probe.query if exact_probe else query),
                                    "query_index": batch_index,
                                    "query_weight": 1.0,
                                    "results": exact_text_rows,
                                }
                            )
            except Exception as exc:
                rag_error = wrap_rag_error(
                    exc,
                    provider="supabase",
                    kb_name=kb_name,
                    query=query,
                    stage="pipeline.search",
                )
                observability.update_observation(
                    observation,
                    metadata={"kb_name": kb_name, "sources": config.sources},
                    level="ERROR",
                    status_message=str(rag_error),
                )
                self.logger.error(f"Supabase retrieval failed: {rag_error}")
                raise rag_error from exc

        fused = self._fuse_plan_results(
            [*exact_text_plans, *primary_plan],
            query=query,
            question_like=question_like,
            config=config,
        )
        second_pass_plan: list[dict[str, Any]] = []

        second_pass_queries: list[str] = []
        has_exact_question_hit = any(
            plan.get("group_name") in {"question_exact_text", "question_exact_vector"}
            and bool(plan.get("results"))
            for plan in [*exact_text_plans, *primary_plan]
        )
        should_force_case_supplement = query_shape == "case_like"
        if (
            config.second_pass_enabled
            and (
                should_force_case_supplement
                or (
                    not has_exact_question_hit
                    and should_run_second_pass(
                        query=query,
                        results=fused,
                        top_k=config.top_k,
                        min_hits=config.second_pass_min_hits,
                        max_dup_ratio=config.second_pass_max_dup_ratio,
                    )
                )
            )
        ):
            second_pass_budget = config.second_pass_max_queries
            if should_force_case_supplement:
                second_pass_budget = max(
                    config.second_pass_max_queries,
                    min(5, len(extract_case_subquestion_items(query, max_items=6)) or 3),
                )
            second_pass_queries = build_second_pass_queries(
                query,
                max_queries=second_pass_budget,
            )
            second_pass_queries = [item for item in second_pass_queries if item not in primary_queries]
            if second_pass_queries:
                try:
                    client = await self._get_client(config.timeout_s)
                    second_pass_plan = await self._run_query_plan(
                        client=client,
                        queries=second_pass_queries,
                        question_like=question_like,
                        source_plan=source_plan,
                        standard_codes=rewritten.standard_codes,
                        precision_node_code=precision_node_code,
                        exact_probe=exact_probe,
                        original_query=query,
                        config=config,
                        query_weight=0.72,
                        phase="second_pass",
                        failure_sink=retrieval_warnings,
                    )
                    fused = self._fuse_plan_results(
                        [*exact_text_plans, *primary_plan, *second_pass_plan],
                        query=query,
                        question_like=question_like,
                        config=config,
                    )
                except Exception as exc:
                    retrieval_warnings.append(
                        _rag_warning_payload(
                            phase="second_pass",
                            group_name="query_plan",
                            query=" | ".join(second_pass_queries),
                            exc=exc,
                        )
                    )
                    self.logger.warning(f"Supabase second-pass retrieval failed: {exc}")

        all_plans = [*exact_text_plans, *primary_plan, *second_pass_plan]
        exact_question = self._augment_case_exact_question_with_query(
            self._extract_exact_question_payload(
                all_plans,
                original_query=query,
                exact_probe=exact_probe,
            ),
            query=query,
            query_shape=query_shape,
        )
        fused = dedupe_ranked_results(fused, max_items=config.fetch_count * 2)
        enriched = await self._hydrate_sources(fused[: config.fetch_count], config=config)
        enriched = self._filter_partial_case_results(enriched, exact_question=exact_question)
        enriched = _enforce_doc_diversity(enriched, max_per_document=config.max_per_document)
        reranked = await self._rerank_results(
            query=query,
            results=enriched,
            config=config,
        )
        reranked = self._filter_partial_case_results(reranked, exact_question=exact_question)
        final_results = dedupe_ranked_results(reranked, max_items=config.top_k)

        content_blocks = _dedupe_rendered_content_blocks(
            [str(item.get("rag_content") or "").strip() for item in final_results]
        )
        content = "\n\n".join(block for block in content_blocks if block)

        sources = _dedupe_source_items([
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
        ])
        evidence_bundle = _build_evidence_bundle(
            query=query,
            provider="supabase",
            kb_name=kb_name,
            content_blocks=content_blocks,
            sources=sources,
            exact_question=exact_question,
            source_plan=source_plan,
            query_shape=query_shape,
            rewritten=rewritten,
            second_pass_queries=second_pass_queries,
        )

        payload = {
            "query": query,
            "answer": content,
            "content": content,
            "sources": sources,
            "provider": "supabase",
            "kb_name": kb_name,
            "evidence_bundle": evidence_bundle,
        }
        if retrieval_warnings:
            payload["warnings"] = list(retrieval_warnings)
            payload["evidence_bundle"]["warnings"] = list(retrieval_warnings)
        if exact_question:
            payload["exact_question"] = exact_question
        observability.update_observation(
            observation,
            output_payload={
                "source_count": len(sources),
                "source_types": [item.get("source_type") or "" for item in sources],
            },
            metadata={
                "kb_name": kb_name,
                "question_like": question_like,
                "query_shape": query_shape,
                "query_rewrite": {
                    "primary_query": rewritten.primary_query,
                    "keywords": rewritten.keywords,
                    "standard_codes": rewritten.standard_codes,
                    "reasons": rewritten.reasons,
                },
                "source_plan": {
                    **source_plan.to_trace_dict(),
                },
                "precision_node_code": precision_node_code,
                "primary_queries": primary_queries,
                "second_pass_queries": second_pass_queries,
                "exact_question_probe": {
                    "enabled": bool(exact_probe),
                    "probe_query": exact_probe.query if exact_probe else "",
                    "allowed_question_types": (
                        exact_probe.allowed_question_types if exact_probe else []
                    ),
                    "option_validation_required": (
                        exact_probe.option_validation_required if exact_probe else False
                    ),
                    "hit_groups": [
                        str(plan.get("group_name") or "")
                        for plan in all_plans
                        if plan.get("group_name") in {"question_exact_text", "question_exact_vector"}
                        and bool(plan.get("results"))
                    ],
                },
                "exact_question": exact_question or {},
            },
        )
        return payload

    async def _run_query_plan(
        self,
        *,
        client: httpx.AsyncClient,
        queries: list[str],
        question_like: bool,
        source_plan,
        standard_codes: list[str],
        precision_node_code: str | None,
        exact_probe,
        original_query: str,
        config: SupabaseSearchConfig,
        query_weight: float = 1.0,
        phase: str = "primary",
        failure_sink: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        selected_sources = [
            source
            for source in config.sources
            if (
                (source == "textbook" and source_plan.search_textbook_chunks)
                or (source == "standard" and source_plan.search_standard_chunks)
                or (source == "exam" and source_plan.search_exam_chunks)
            )
        ]
        for query_index, item in enumerate(queries):
            current_query = str(item or "").strip()
            if not current_query:
                continue
            embedding = await self._embed_query(current_query)
            vector_literal = _vector_literal(embedding)
            tasks = [
                self._search_source(
                    client=client,
                    query=current_query,
                    vector_literal=vector_literal,
                    source_type=source,
                    config=config,
                )
                for source in selected_sources
            ]
            task_groups = list(selected_sources)
            if source_plan.search_questions_bank and (config.include_questions or question_like):
                tasks.append(
                    self._search_questions(
                        client=client,
                        vector_literal=vector_literal,
                        config=config,
                    )
                )
                task_groups.append("questions_bank")
            if (
                exact_probe
                and query_index == 0
                and source_plan.search_questions_bank
                and (config.include_questions or question_like)
            ):
                tasks.append(
                    self._search_exact_question_vector(
                        client=client,
                        vector_literal=vector_literal,
                        allowed_question_types=exact_probe.allowed_question_types,
                        original_query=original_query,
                        option_validation_required=exact_probe.option_validation_required,
                        config=config,
                    )
                )
                task_groups.append("question_exact_vector")
            if standard_codes and source_plan.search_standard_chunks:
                tasks.append(
                    self._search_exact_standard(
                        client=client,
                        standard_code=standard_codes[0],
                        node_code=precision_node_code,
                        config=config,
                    )
                )
                task_groups.append("standard_code_exact")
            if precision_node_code and source_plan.search_standard_chunks:
                tasks.append(
                    self._search_precision_standard(
                        client=client,
                        vector_literal=vector_literal,
                        node_code=precision_node_code,
                        config=config,
                    )
                )
                task_groups.append("standard_precision")

            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            for group_name, result in zip(task_groups, raw_results):
                if isinstance(result, Exception):
                    if failure_sink is not None:
                        failure_sink.append(
                            _rag_warning_payload(
                                phase=phase,
                                group_name=group_name,
                                query=current_query,
                                exc=result,
                            )
                        )
                    self.logger.warning(
                        f"Supabase group '{group_name}' failed for query '{current_query}': {result}"
                    )
                    continue
                plans.append(
                    {
                        "phase": phase,
                        "group_name": group_name,
                        "query": current_query,
                        "query_index": query_index,
                        "query_weight": query_weight * max(0.45, 1.0 - (query_index * 0.12)),
                        "results": result,
                    }
                )
        return plans

    def _fuse_plan_results(
        self,
        plans: list[dict[str, Any]],
        *,
        query: str,
        question_like: bool,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        results_map: dict[str, list[dict[str, Any]]] = {}
        weights: dict[str, float] = {}
        base_weights = resolve_group_weights(
            query,
            base_source_weights=config.source_weights,
            base_question_weights=config.question_weights,
        )

        for plan in plans:
            group_name = str(plan.get("group_name") or "").strip()
            phase = str(plan.get("phase") or "primary").strip()
            query_index = int(plan.get("query_index") or 0)
            query_key = f"{phase}:{group_name}:q{query_index}"
            results_map[query_key] = list(plan.get("results") or [])
            weights[query_key] = float(base_weights.get(group_name, 1.0)) * float(
                plan.get("query_weight") or 1.0
            )
            for item in results_map[query_key]:
                item["_query_variant"] = str(plan.get("query") or "")
                item["_query_phase"] = phase

        fused = _weighted_rrf_fusion(results_map, weights)
        target_window = max(1, max(config.top_k, min(config.fetch_count, config.rerank_window)))
        fused = _apply_similarity_floor(fused, results_map, target_window=target_window)
        fused = _enrich_question_weights(fused, question_like=question_like, config=config)
        return dedupe_ranked_results(fused)

    async def _rerank_results(
        self,
        *,
        query: str,
        results: list[dict[str, Any]],
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        if not config.rerank_enabled or not results:
            return results

        rerank_candidates = [
            item for item in results[: config.rerank_window] if str(item.get("rag_content") or "").strip()
        ]
        if len(rerank_candidates) < 2:
            return results

        rerank_docs = [str(item.get("rag_content") or "").strip() for item in rerank_candidates]
        rerank_results = await rerank_documents(
            query,
            rerank_docs,
            top_n=min(config.top_k, len(rerank_docs)),
            timeout_s=config.rerank_timeout_s,
        )
        if not rerank_results:
            return results

        reranked: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in rerank_results:
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(rerank_candidates):
                continue
            doc = dict(rerank_candidates[idx])
            score = float(item.get("relevance_score") or 0.0)
            doc["rerank_score"] = score
            doc["score"] = score
            doc["_reranked"] = True
            doc_id = str(doc.get("chunk_id") or doc.get("id") or "").strip()
            if doc_id:
                seen_ids.add(doc_id)
            reranked.append(doc)

        for item in results:
            doc_id = str(item.get("chunk_id") or item.get("id") or "").strip()
            if doc_id and doc_id in seen_ids:
                continue
            reranked.append(item)
        return reranked

    async def _embed_query(self, query: str) -> list[float]:
        if _embedding_cache_enabled():
            cached = _get_cached_embedding(query)
            if cached:
                return cached
        embeddings = await get_embedding_client().embed([query])
        if not embeddings or not embeddings[0]:
            raise RuntimeError("Embedding API returned no query embedding.")
        result = embeddings[0]
        if _embedding_cache_enabled():
            _cache_embedding(query, result)
        return result

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
            "standard_code_exact": float(os.getenv("SUPABASE_RAG_WEIGHT_STANDARD_CODE_EXACT", "3.0")),
            "question_exact_text": float(os.getenv("SUPABASE_RAG_WEIGHT_QUESTION_EXACT_TEXT", "4.2")),
            "question_exact_vector": float(os.getenv("SUPABASE_RAG_WEIGHT_QUESTION_EXACT_VECTOR", "3.4")),
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
            query_expansion_enabled=_env_flag("SUPABASE_RAG_QUERY_EXPANSION", True),
            max_query_variants=max(1, int(os.getenv("SUPABASE_RAG_MAX_QUERY_VARIANTS", "4"))),
            second_pass_enabled=_env_flag("SUPABASE_RAG_SECOND_PASS", True),
            second_pass_max_queries=max(1, int(os.getenv("SUPABASE_RAG_SECOND_PASS_QUERIES", "2"))),
            second_pass_min_hits=max(1, int(os.getenv("SUPABASE_RAG_SECOND_PASS_MIN_HITS", "2"))),
            second_pass_max_dup_ratio=float(
                os.getenv("SUPABASE_RAG_SECOND_PASS_MAX_DUP_RATIO", "0.5")
            ),
            rerank_enabled=_env_flag("SUPABASE_RAG_ENABLE_RERANK", True),
            rerank_window=max(top_k, int(os.getenv("SUPABASE_RAG_RERANK_WINDOW", str(fetch_count)))),
            rerank_timeout_s=float(os.getenv("SUPABASE_RAG_RERANK_TIMEOUT_S", "6.0")),
            exact_question_enabled=_env_flag("SUPABASE_RAG_ENABLE_EXACT_QUESTION", True),
            exact_question_text_first=_env_flag("SUPABASE_RAG_EXACT_QUESTION_TEXT_FIRST", True),
            exact_question_min_similarity=float(
                os.getenv("SUPABASE_RAG_EXACT_QUESTION_MIN_SIMILARITY", "0.9")
            ),
            exact_question_max_text_len=max(
                32, int(os.getenv("SUPABASE_RAG_EXACT_QUESTION_MAX_TEXT_LEN", "100"))
            ),
            exact_question_text_rpc_enabled=_env_flag(
                "SUPABASE_RAG_EXACT_QUESTION_TEXT_RPC", True
            ),
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

    async def _search_exact_standard(
        self,
        *,
        client: httpx.AsyncClient,
        standard_code: str,
        node_code: str | None,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        code = str(standard_code or "").strip()
        if not code:
            return []
        code_suffix = code.split("/", 1)[-1]
        code_suffix = code_suffix.replace("GB", "").replace("JGJ", "").replace("CJJ", "").replace("DBJ", "").replace("DB", "").strip()
        query = {
            "source_type": "eq.standard",
            "standard_code": f"ilike.*{code_suffix}*",
        }
        if node_code:
            query["node_code"] = f"eq.{node_code}"
        rows = await self._select(
            client,
            table="kb_chunks",
            select="chunk_id,card_title,rag_content,node_code,source_type,content_type,standard_code,taxonomy_path,page_num,source_doc,metadata",
            query=query,
            config=config,
        )
        normalized: list[dict[str, Any]] = []
        for row in rows[: config.fetch_count]:
            normalized.append(
                {
                    "chunk_id": row.get("chunk_id"),
                    "card_title": row.get("card_title") or row.get("standard_code") or code,
                    "rag_content": row.get("rag_content") or "",
                    "node_code": row.get("node_code") or "",
                    "source_type": row.get("source_type") or "standard",
                    "content_type": row.get("content_type") or "",
                    "standard_code": row.get("standard_code") or code,
                    "taxonomy_path": row.get("taxonomy_path") or "",
                    "page_num": row.get("page_num"),
                    "source_doc": row.get("source_doc") or "",
                    "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else None,
                    "source": row.get("source_doc") or row.get("standard_code") or code,
                    "score": 1.0,
                    "_source_group": "standard_code_exact",
                    "_source_table": "kb_chunks",
                }
            )
        return normalized

    async def _search_exact_question_text(
        self,
        *,
        client: httpx.AsyncClient,
        probe_query: str,
        allowed_question_types: list[str],
        original_query: str,
        option_validation_required: bool,
        config: SupabaseSearchConfig,
        warning_sink: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        clean = str(probe_query or "").strip()
        if not clean:
            return []
        direct_rows = await self._search_exact_question_text_direct(
            client=client,
            probe_query=clean,
            config=config,
            warning_sink=warning_sink,
        )
        for row in direct_rows:
            if not matches_allowed_question_type(row.get("question_type"), allowed_question_types):
                continue
            if not validate_exact_question_options(
                original_query=original_query,
                options=row.get("options"),
                option_validation_required=option_validation_required,
            ):
                continue
            return [self._normalize_question_result(row, source_group="question_exact_text", score=1.0)]

        if config.exact_question_text_rpc_enabled:
            keyword_terms = build_exact_question_keyword_terms(clean, max_terms=3)
            rpc_queries = [
                candidate
                for candidate in [clean, *build_exact_question_text_candidates(clean), *keyword_terms]
                if candidate
            ]
            seen_queries: set[str] = set()
            for candidate in rpc_queries:
                normalized_candidate = str(candidate).strip()
                if not normalized_candidate or normalized_candidate in seen_queries:
                    continue
                seen_queries.add(normalized_candidate)
                rpc_rows = await self._search_questions_text_rpc(
                    client=client,
                    search_text=normalized_candidate,
                    config=config,
                    limit_count=5,
                )
                for row in rpc_rows:
                    if not matches_allowed_question_type(
                        row.get("question_type"), allowed_question_types
                    ):
                        continue
                    if not validate_exact_question_options(
                        original_query=original_query,
                        options=row.get("options"),
                        option_validation_required=option_validation_required,
                    ):
                        continue
                    return [
                        self._normalize_question_result(
                            row,
                            source_group="question_exact_text",
                            score=max(float(row.get("text_score") or 0.0), 0.98),
                        )
                    ]
        return []

    async def _search_exact_question_text_batch(
        self,
        *,
        client: httpx.AsyncClient,
        probe_queries: list[str],
        allowed_question_types: list[str],
        original_query: str,
        option_validation_required: bool,
        config: SupabaseSearchConfig,
        warning_sink: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        batches: list[dict[str, Any]] = []
        seen_queries: set[str] = set()
        for candidate in probe_queries:
            clean = str(candidate or "").strip()
            if not clean or clean in seen_queries:
                continue
            seen_queries.add(clean)
            rows = await self._search_exact_question_text(
                client=client,
                probe_query=clean,
                allowed_question_types=allowed_question_types,
                original_query=original_query,
                option_validation_required=option_validation_required,
                config=config,
                warning_sink=warning_sink,
            )
            batches.append({"query": clean, "results": rows})
        return batches

    async def _search_exact_question_text_direct(
        self,
        *,
        client: httpx.AsyncClient,
        probe_query: str,
        config: SupabaseSearchConfig,
        warning_sink: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        candidates = build_exact_question_text_candidates(probe_query, max_candidates=6)
        merged_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for candidate in candidates:
            escaped = str(candidate or "").replace("*", " ").replace("%", " ").strip()
            if not escaped:
                continue
            question_stem_task = self._select(
                client,
                table="questions_bank",
                select=_QUESTION_SELECT,
                query={"question_stem": f"ilike.*{escaped}*", "limit": "3"},
                config=config,
            )
            stem_task = self._select(
                client,
                table="questions_bank",
                select=_QUESTION_SELECT,
                query={"stem": f"ilike.*{escaped}*", "limit": "3"},
                config=config,
            )
            question_rows, stem_rows = await asyncio.gather(
                question_stem_task, stem_task, return_exceptions=True
            )
            for group_name, batch in (
                ("question_stem", question_rows),
                ("stem", stem_rows),
            ):
                if isinstance(batch, Exception):
                    if warning_sink is not None:
                        warning_sink.append(
                            _rag_warning_payload(
                                phase="primary",
                                group_name=f"question_exact_text.{group_name}",
                                query=escaped,
                                exc=batch,
                            )
                        )
                    continue
                for row in batch:
                    row_id = str(row.get("id") or "").strip()
                    if row_id and row_id in seen_ids:
                        continue
                    if row_id:
                        seen_ids.add(row_id)
                    merged_rows.append(row)
            if merged_rows:
                break
        return merged_rows

    async def _search_questions_text_rpc(
        self,
        *,
        client: httpx.AsyncClient,
        search_text: str,
        config: SupabaseSearchConfig,
        limit_count: int = 5,
    ) -> list[dict[str, Any]]:
        try:
            return await self._rpc(
                client,
                "search_questions_bank_text",
                {
                    "search_text": str(search_text or "").strip(),
                    "limit_count": max(1, min(limit_count, 20)),
                    "filter_source_type": None,
                    "filter_question_type": None,
                },
            )
        except Exception as exc:
            self.logger.debug(f"Supabase questions text RPC unavailable: {exc}")
            return []

    async def _search_exact_question_vector(
        self,
        *,
        client: httpx.AsyncClient,
        vector_literal: str,
        allowed_question_types: list[str],
        original_query: str,
        option_validation_required: bool,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        search_threshold = min(0.70, config.exact_question_min_similarity - 0.1)
        rows = await self._rpc(
            client,
            "search_questions_bank_vector",
            {
                "query_embedding": vector_literal,
                "match_threshold": search_threshold,
                "match_count": min(config.fetch_count, 5),
                "filter_question_type": None,
                "filter_source_type": None,
            },
        )
        for row in rows:
            similarity = float(row.get("similarity") or 0.0)
            if similarity < config.exact_question_min_similarity:
                continue
            if not matches_allowed_question_type(row.get("question_type"), allowed_question_types):
                continue
            if not validate_exact_question_options(
                original_query=original_query,
                options=row.get("options"),
                option_validation_required=option_validation_required,
            ):
                continue
            return [
                self._normalize_question_result(
                    row,
                    source_group="question_exact_vector",
                    score=similarity,
                )
            ]
        return []

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
            normalized.append(
                self._normalize_question_result(
                    row,
                    source_group="questions_bank",
                    score=float(row.get("similarity") or 0.0),
                )
            )
        return normalized

    def _normalize_question_result(
        self,
        row: dict[str, Any],
        *,
        source_group: str,
        score: float,
    ) -> dict[str, Any]:
        stem = str(row.get("stem") or row.get("question_stem") or "").strip()
        options = _safe_json_dumps(row.get("options") or "")
        answer = _safe_json_dumps(row.get("correct_answer") or "")
        analysis = str(row.get("analysis") or "").strip()
        rag_content = f"【题目】{stem}\n【选项】{options}\n【答案】{answer}\n【解析】{analysis}".strip()
        return {
            "id": row.get("id"),
            "original_id": row.get("original_id") or "",
            "chunk_id": f"question-{row.get('id')}",
            "card_title": f"题目: {stem[:40]}" if stem else "题目",
            "rag_content": rag_content,
            "stem": row.get("stem") or "",
            "question_stem": row.get("question_stem") or "",
            "node_code": row.get("node_code") or "",
            "source_type": row.get("source_type") or "exam",
            "content_type": "question",
            "page_num": row.get("exam_year"),
            "score": score,
            "similarity": float(row.get("similarity") or score or 0.0),
            "options": row.get("options"),
            "correct_answer": row.get("correct_answer"),
            "analysis": row.get("analysis"),
            "question_type": row.get("question_type") or "",
            "background_context": row.get("background_context"),
            "parent_id": row.get("parent_id"),
            "source_chunk_id": row.get("source_chunk_id") or "",
            "grading_rubric": row.get("grading_rubric"),
            "structured_rules": row.get("structured_rules"),
            "logic_rule": row.get("logic_rule"),
            "_source_group": source_group,
            "_source_table": "questions_bank",
        }

    @staticmethod
    def _detect_answer_kind(question_type: Any, correct_answer: Any, options: Any) -> str:
        normalized_type = str(question_type or "").strip().lower()
        answer_text = str(correct_answer or "").strip()
        if "case" in normalized_type:
            return "case_study"
        if options not in (None, "", [], {}):
            return "mcq"
        if any(marker in answer_text for marker in ("1.", "1、", "1．", "\n2.", "\n2、")):
            return "case_bundle"
        if answer_text:
            return "free_text"
        return "unknown"

    @staticmethod
    def _build_case_authority_bundle(
        *,
        row: dict[str, Any],
        exact_stem: str,
        correct_answer: Any,
        analysis: Any,
    ) -> dict[str, Any] | None:
        answer_text = str(correct_answer or "").strip()
        analysis_text = str(analysis or "").strip()
        source_surface = str(row.get("stem") or row.get("question_stem") or exact_stem or "").strip()
        row_subquestions = extract_case_subquestion_items(source_surface, max_items=8)
        if not row_subquestions:
            return None

        covered: list[dict[str, Any]] = []
        first = row_subquestions[0]
        covered.append(
            {
                "display_index": first.get("display_index") or "1",
                "prompt": first.get("prompt") or "",
                "surface": first.get("surface") or "",
                "authoritative_answer": answer_text,
                "analysis": analysis_text,
                "coverage": "exact_question",
            }
        )
        return {
            "coverage_state": "single_subquestion_only",
            "covered_subquestions": covered,
            "covered_indexes": [item["display_index"] for item in covered if item.get("display_index")],
            "raw_subquestion_count": len(row_subquestions),
        }

    @staticmethod
    def _case_support_tokens(text: str) -> list[str]:
        tokens: list[str] = []
        for token in _CASE_SUPPORT_TOKEN_RE.findall(str(text or "")):
            clean = str(token or "").strip()
            if not clean or clean in _CASE_SUPPORT_STOPWORDS:
                continue
            if clean not in tokens:
                tokens.append(clean)
        return tokens

    def _matches_missing_case_prompt(
        self,
        item: dict[str, Any],
        missing_subquestions: list[dict[str, Any]],
    ) -> bool:
        haystack = " ".join(
            [
                str(item.get("card_title") or ""),
                str(item.get("rag_content") or ""),
                str(item.get("source") or ""),
            ]
        )
        lowered = haystack.lower()
        for prompt in missing_subquestions:
            if not isinstance(prompt, dict):
                continue
            tokens = self._case_support_tokens(str(prompt.get("prompt") or ""))
            if not tokens:
                continue
            overlap = 0
            for token in tokens[:8]:
                if token.lower() in lowered:
                    overlap += 1
            if overlap >= min(2, len(tokens)):
                return True
        return False

    def _filter_partial_case_results(
        self,
        results: list[dict[str, Any]],
        *,
        exact_question: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not results or not isinstance(exact_question, dict):
            return results
        if str(exact_question.get("answer_kind") or "").strip().lower() != "case_study":
            return results
        missing_subquestions = exact_question.get("missing_subquestions")
        if not isinstance(missing_subquestions, list) or not missing_subquestions:
            return results

        exact_chunk_id = str(exact_question.get("chunk_id") or "").strip()
        filtered: list[dict[str, Any]] = []
        for item in results:
            chunk_id = str(item.get("chunk_id") or item.get("id") or "").strip()
            source_type = str(item.get("source_type") or "").strip().lower()
            source_table = str(item.get("_source_table") or "").strip().lower()
            if chunk_id and chunk_id == exact_chunk_id:
                filtered.append(item)
                continue
            if source_type in {"standard", "textbook"}:
                filtered.append(item)
                continue
            if source_table == "kb_chunks" and source_type not in {"exam"}:
                filtered.append(item)
                continue
            if source_table == "questions_bank" and self._matches_missing_case_prompt(item, missing_subquestions):
                filtered.append(item)
                continue
        return filtered or results

    def _extract_exact_question_payload(
        self,
        plans: list[dict[str, Any]],
        *,
        original_query: str = "",
        exact_probe: Any = None,
    ) -> dict[str, Any] | None:
        priority = {"question_exact_text": 0, "question_exact_vector": 1}
        candidates = sorted(
            [
                plan
                for plan in plans
                if str(plan.get("group_name") or "") in priority
                and isinstance(plan.get("results"), list)
                and plan.get("results")
            ],
            key=lambda item: priority[str(item.get("group_name") or "")],
        )
        if not candidates:
            promoted_row = self._select_option_matched_question_bank_row(
                plans,
                original_query=original_query,
                exact_probe=exact_probe,
            )
            if promoted_row is None:
                return None
            candidates = [
                {
                    "phase": promoted_row.get("_query_phase") or "primary",
                    "group_name": "question_bank_option_match",
                    "query": promoted_row.get("_query_variant") or original_query,
                    "query_index": 0,
                    "query_weight": 1.0,
                    "results": [promoted_row],
                }
            ]

        case_rows: list[dict[str, Any]] = []
        for plan in candidates:
            for item in plan.get("results") or []:
                row = dict(item or {})
                if "case" in str(row.get("question_type") or "").strip().lower():
                    row["_plan_query"] = str(plan.get("query") or "")
                    case_rows.append(row)

        if case_rows:
            seen_by_index: dict[str, dict[str, Any]] = {}
            ordered_rows: list[dict[str, Any]] = []
            for row in case_rows:
                prompt_surface = str(row.get("stem") or row.get("question_stem") or row.get("card_title") or "")
                sub_items = extract_case_subquestion_items(prompt_surface, max_items=2)
                item = sub_items[0] if sub_items else {}
                display_index = str(item.get("display_index") or "").strip()
                prompt = str(item.get("prompt") or row.get("_plan_query") or "").strip()
                key = display_index or prompt
                if not key:
                    continue
                current_score = float(row.get("similarity") or row.get("score") or 0.0)
                existing = seen_by_index.get(key)
                existing_score = float(existing.get("similarity") or existing.get("score") or 0.0) if existing else -1.0
                if existing is None or current_score >= existing_score:
                    row["_display_index"] = display_index
                    row["_prompt"] = prompt
                    seen_by_index[key] = row
            ordered_rows = sorted(
                seen_by_index.values(),
                key=lambda item: (
                    int(str(item.get("_display_index") or "9999")) if str(item.get("_display_index") or "").isdigit() else 9999,
                    -float(item.get("similarity") or item.get("score") or 0.0),
                ),
            )
            selected_row = ordered_rows[0] if ordered_rows else {}
            covered_subquestions = [
                {
                    "display_index": str(row.get("_display_index") or "").strip() or str(index + 1),
                    "prompt": str(row.get("_prompt") or "").strip(),
                    "surface": str(row.get("stem") or row.get("question_stem") or "").strip(),
                    "authoritative_answer": row.get("correct_answer") or "",
                    "analysis": row.get("analysis") or "",
                    "coverage": "exact_question",
                    "question_id": row.get("id") or "",
                }
                for index, row in enumerate(ordered_rows)
            ]
            return {
                "id": selected_row.get("id") or "",
                "chunk_id": selected_row.get("chunk_id") or "",
                "stem": str(
                    selected_row.get("stem")
                    or selected_row.get("question_stem")
                    or str(selected_row.get("card_title") or "").replace("题目: ", "", 1)
                    or ""
                ).strip(),
                "question_type": selected_row.get("question_type") or "case_study",
                "correct_answer": selected_row.get("correct_answer") or "",
                "analysis": selected_row.get("analysis") or "",
                "options": selected_row.get("options") or "",
                "source_type": selected_row.get("source_type") or "",
                "source_group": "question_exact_text",
                "confidence": max(float(row.get("similarity") or row.get("score") or 0.0) for row in ordered_rows),
                "answer_kind": "case_study",
                "matched_question_ids": [row.get("id") for row in ordered_rows if row.get("id") is not None],
                "covered_subquestions": covered_subquestions,
                "covered_indexes": [item["display_index"] for item in covered_subquestions if item.get("display_index")],
                "coverage_state": "multi_subquestion_exact" if len(covered_subquestions) > 1 else "single_subquestion_only",
                "case_bundle": {
                    "coverage_state": "multi_subquestion_exact" if len(covered_subquestions) > 1 else "single_subquestion_only",
                    "covered_subquestions": covered_subquestions,
                    "covered_indexes": [item["display_index"] for item in covered_subquestions if item.get("display_index")],
                    "raw_subquestion_count": len(covered_subquestions),
                },
            }

        selected_plan = candidates[0]
        row = dict((selected_plan.get("results") or [None])[0] or {})
        if not row:
            return None
        stem = str(
            row.get("stem")
            or row.get("question_stem")
            or str(row.get("card_title") or "").replace("题目: ", "", 1)
            or ""
        ).strip()
        question_type = row.get("question_type") or ""
        correct_answer = row.get("correct_answer") or ""
        analysis = row.get("analysis") or ""
        options = row.get("options") or ""
        payload: dict[str, Any] = {
            "id": row.get("id") or row.get("chunk_id") or "",
            "chunk_id": row.get("chunk_id") or "",
            "stem": stem,
            "question_type": question_type,
            "correct_answer": correct_answer,
            "analysis": analysis,
            "options": options,
            "source_type": row.get("source_type") or "",
            "source_group": str(selected_plan.get("group_name") or row.get("_source_group") or ""),
            "confidence": float(row.get("similarity") or row.get("score") or 0.0),
            "answer_kind": self._detect_answer_kind(question_type, correct_answer, options),
        }
        case_bundle = None
        if payload["answer_kind"] == "case_study":
            case_bundle = self._build_case_authority_bundle(
                row=row,
                exact_stem=stem,
                correct_answer=correct_answer,
                analysis=analysis,
            )
        if case_bundle:
            payload["case_bundle"] = case_bundle
            payload["covered_subquestions"] = case_bundle.get("covered_subquestions") or []
            payload["coverage_state"] = case_bundle.get("coverage_state") or ""
            payload["covered_indexes"] = case_bundle.get("covered_indexes") or []
        return payload

    def _select_option_matched_question_bank_row(
        self,
        plans: list[dict[str, Any]],
        *,
        original_query: str,
        exact_probe: Any = None,
    ) -> dict[str, Any] | None:
        if not exact_probe or not original_query:
            return None

        candidates: list[tuple[int, float, dict[str, Any]]] = []
        for plan in plans:
            if str(plan.get("group_name") or "") != "questions_bank":
                continue
            for item in plan.get("results") or []:
                row = dict(item or {})
                if str(row.get("_source_table") or "").strip() != "questions_bank":
                    continue
                options = _coerce_options_payload(row.get("options"))
                if not row.get("correct_answer") or not options:
                    continue
                source_type = str(row.get("source_type") or "").strip().lower()
                if source_type and "exam" not in source_type:
                    continue
                if not matches_allowed_question_type(
                    row.get("question_type"),
                    getattr(exact_probe, "allowed_question_types", None),
                ):
                    continue
                if not validate_exact_question_options(
                    original_query=original_query,
                    options=options,
                    option_validation_required=bool(
                        getattr(exact_probe, "option_validation_required", False)
                    ),
                ):
                    continue
                option_count = len(_option_values(options))
                overlap_count = _option_overlap_count(
                    original_query=original_query,
                    options=options,
                )
                required_overlap = min(3, option_count) if option_count else 2
                if overlap_count < required_overlap:
                    continue
                score = float(row.get("similarity") or row.get("score") or 0.0)
                if score < 0.55:
                    continue
                row["_source_group"] = "question_bank_option_match"
                row["options"] = options
                candidates.append((overlap_count, score, row))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    @staticmethod
    def _augment_case_exact_question_with_query(
        exact_question: dict[str, Any] | None,
        *,
        query: str,
        query_shape: str,
    ) -> dict[str, Any] | None:
        if not isinstance(exact_question, dict) or query_shape != "case_like":
            return exact_question
        query_items = extract_case_subquestion_items(query, max_items=8)
        if not query_items:
            return exact_question
        covered_indexes = {
            str(item.get("display_index") or "").strip()
            for item in exact_question.get("covered_subquestions") or []
            if str(item.get("display_index") or "").strip()
        }
        exact_question["query_subquestions"] = query_items
        exact_question["query_subquestion_count"] = len(query_items)
        exact_question["missing_subquestions"] = [
            item for item in query_items
            if str(item.get("display_index") or "").strip() not in covered_indexes
        ]
        exact_question["coverage_ratio"] = round(
            len(covered_indexes) / max(len(query_items), 1),
            4,
        )
        if isinstance(exact_question.get("case_bundle"), dict):
            exact_question["case_bundle"]["query_subquestions"] = query_items
            exact_question["case_bundle"]["missing_subquestions"] = exact_question["missing_subquestions"]
            exact_question["case_bundle"]["query_subquestion_count"] = len(query_items)
            exact_question["case_bundle"]["coverage_ratio"] = exact_question["coverage_ratio"]
        return exact_question

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
            client = await self._get_client(config.timeout_s)
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
