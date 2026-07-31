"""Read-only Supabase-backed RAG pipeline."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import contextvars
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Optional

import httpx

from deeptutor.logging import get_logger
from deeptutor.services.config import get_kb_config_service
from deeptutor.services.embedding import get_embedding_client
from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.rag.compiled_truth_source import materialize_compiled_truth_documents
from deeptutor.services.rag.evidence_bundle import build_evidence_bundle
from deeptutor.services.rag.exceptions import RAGError, RAGSearchError, wrap_rag_error
from deeptutor.services.rag.provenance import apply_provenance_ranking, build_ranking_trace
from deeptutor.services.rag.retrieval_plan import build_retrieval_plan

from .supabase_strategy import (
    build_exact_question_keyword_terms,
    build_exact_question_text_candidates,
    build_second_pass_queries,
    classify_query_shape,
    dedupe_ranked_results,
    exact_question_identity_corresponds,
    expand_query_variants,
    extract_case_subquestion_items,
    extract_node_code_prefix,
    is_question_like_query,
    matches_allowed_question_type,
    prepare_exact_question_probe,
    rerank_documents,
    resolve_group_weights,
    rewrite_query,
    select_sources,
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
_SUPABASE_AVAILABILITY_CACHE: dict[str, tuple[bool, float]] = {}
_SUPABASE_AVAILABILITY_TTL_S = 60.0
# Single-flight background availability refresh tasks (SWR), keyed by Supabase URL.
_SUPABASE_AVAILABILITY_REFRESH: dict[str, asyncio.Task] = {}
# Batch size for chunk_id existence checks — keeps the PostgREST GET URL
# (chunk_id=in.(...)) well under proxy/server URL-length limits when a golden
# set carries hundreds of expected chunk_ids.
_CHUNK_ID_EXISTS_BATCH_SIZE = 50


def _question_identity_surface(row: dict[str, Any]) -> str:
    """Canonical bank surface used by every exact-question candidate path."""
    return " ".join(
        value
        for value in [
            str(row.get("background_context") or "").strip(),
            str(row.get("stem") or row.get("question_stem") or "").strip(),
        ]
        if value
    )


def _safe_response_text(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    try:
        return str(response.text or "").strip()[:500]
    except Exception:
        return ""


def _extract_supabase_restriction_code(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
    except Exception:
        payload = None
    candidates: list[Any] = []
    if isinstance(payload, dict):
        candidates.extend(
            [
                payload.get("code"),
                payload.get("error"),
                payload.get("message"),
                payload.get("msg"),
                payload.get("description"),
            ]
        )
        details = payload.get("details")
        if isinstance(details, dict):
            candidates.extend(details.values())
        elif isinstance(details, list):
            candidates.extend(details)
    candidates.append(_safe_response_text(response))
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        match = re.search(r"(exceeded_[a-z0-9_]+|exceed_[a-z0-9_]+|overdue_payment)", text)
        if match:
            return match.group(1)
    return ""


def _wrap_supabase_http_status(exc: httpx.HTTPStatusError, *, stage: str) -> RAGSearchError:
    status_code = exc.response.status_code if exc.response is not None else 0
    if status_code == 402:
        restriction_code = _extract_supabase_restriction_code(exc.response)
        suffix = f": {restriction_code}" if restriction_code else ""
        return RAGSearchError(
            f"supabase retrieval failed: Supabase Data API service restricted (HTTP 402{suffix})",
            provider="supabase",
            stage=stage,
            retryable=False,
        )
    retryable = status_code in {408, 429} or status_code >= 500
    return RAGSearchError(
        f"supabase retrieval failed: Supabase Data API returned HTTP {status_code}",
        provider="supabase",
        stage=stage,
        retryable=retryable,
    )


def _is_supabase_service_restriction(exc: BaseException) -> bool:
    return (
        isinstance(exc, RAGSearchError)
        and exc.provider == "supabase"
        and exc.retryable is False
        and "HTTP 402" in str(exc)
    )


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


def _unified_rpc_timeout_s() -> float:
    """Battle2 S5-T5: per-RPC wall-clock budget for search_unified (the largest
    timeout source in production). Calibrated 2026-07-12 against Langfuse: recent
    5,900 successful search_unified calls show p50=0.53s / p95=5.26s / p99=12.7s,
    so the default is 6.0s — above the healthy p95 (5.26s) per commander ruling
    (never cut healthy-but-slow queries wholesale), below the 8.0s client-level
    timeout so a slow group degrades faster. <=0 disables the budget (falls back
    to the client default) — parameterized rollback, no redeploy needed.
    """
    return _env_float_compat("SUPABASE_RAG_UNIFIED_TIMEOUT_S", "", 6.0)


def _rerank_doc_char_cap() -> int:
    """Battle2 S5-T6: char cap applied to documents SENT to the reranker (the
    returned/ displayed content is never truncated). 0 = disabled (default,
    zero behavior change); gray-release by env only.
    """
    return _env_int_compat("SUPABASE_RAG_RERANK_DOC_CHAR_CAP", "", 0)


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


def _metadata_list(value: Any, *, max_items: int = 8) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    elif isinstance(value, dict):
        candidates = [f"{key}: {item}" for key, item in value.items()]
    else:
        candidates = [value]

    items: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        signature = _normalized_text_signature(text, limit=200)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        items.append(text)
        if len(items) >= max_items:
            break
    return items


def _format_metadata_section(title: str, values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return f"## {title}\n{values[0]}"
    return "## " + title + "\n" + "\n".join(f"- {item}" for item in values)


def _build_teaching_metadata_block(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return ""

    exam_matrix = metadata.get("exam_matrix")
    if not isinstance(exam_matrix, dict):
        exam_matrix = {}

    sections = [
        _format_metadata_section(
            "记忆口诀",
            _metadata_list(exam_matrix.get("mnemonics") or metadata.get("mnemonics"), max_items=4),
        ),
        _format_metadata_section(
            "采分点",
            _metadata_list(
                exam_matrix.get("grading_keywords") or metadata.get("grading_keywords"),
                max_items=10,
            ),
        ),
        _format_metadata_section(
            "易错点",
            [
                *_metadata_list(exam_matrix.get("trap_alert"), max_items=4),
                *_metadata_list(metadata.get("pitfalls"), max_items=6),
            ],
        ),
        _format_metadata_section(
            "思维链",
            _metadata_list(
                metadata.get("logic_chains") or metadata.get("logic_chain"),
                max_items=6,
            ),
        ),
        _format_metadata_section(
            "扣分红线",
            _metadata_list(exam_matrix.get("red_lines") or metadata.get("red_lines"), max_items=6),
        ),
        _format_metadata_section(
            "关键参数",
            _metadata_list(metadata.get("key_parameters") or metadata.get("key_numbers"), max_items=8),
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def _project_teaching_metadata(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for item in results:
        doc = dict(item)
        teaching_block = _build_teaching_metadata_block(doc.get("metadata"))
        if teaching_block:
            raw_content = str(doc.get("rag_content") or "").strip()
            if "_raw_rag_content" not in doc:
                doc["_raw_rag_content"] = raw_content
            if teaching_block not in raw_content:
                doc["rag_content"] = "\n\n".join(
                    block for block in [raw_content, teaching_block] if block
                )
            doc["_teaching_metadata_projected"] = True
        projected.append(doc)
    return projected


def _build_evidence_bundle(
    *,
    query: str,
    provider: str,
    kb_name: str,
    content_blocks: list[str],
    sources: list[dict[str, Any]],
    exact_question: dict[str, Any] | None,
    source_plan,
    retrieval_plan,
    ranking_trace: dict[str, Any],
    query_shape: str,
    rewritten,
    second_pass_queries: list[str],
    embedding_dim: int | None = None,
    retrieval_warnings: list[Any] | None = None,
) -> dict[str, Any]:
    # Thin adapter over the single-authority builder: maps the supabase lane's inputs to the
    # canonical contract + packs supabase-specific diagnostics (query rewrite / source plan)
    # into the bundle's ``trace`` bucket. retrieval_degraded/status/warning_count are derived
    # by the builder from ``retrieval_warnings`` (no post-mutation needed).
    return build_evidence_bundle(
        query=query,
        provider=provider,
        kb_name=kb_name,
        content_blocks=content_blocks,
        sources=sources,
        exact_question=exact_question,
        retrieval_plan=(retrieval_plan.to_dict() if hasattr(retrieval_plan, "to_dict") else {}),
        ranking_trace=ranking_trace,
        query_shape=query_shape,
        retrieval_warnings=retrieval_warnings,
        trace={
            "retrieval_query": str(rewritten.primary_query or query).strip(),
            "retrieval_runtime": {"embedding_dim": embedding_dim},
            "query_rewrite": {
                "normalized_query": str(rewritten.normalized_query or "").strip(),
                "keywords": list(rewritten.keywords or []),
                "standard_codes": list(rewritten.standard_codes or []),
                "reasons": list(rewritten.reasons or []),
                "second_pass_queries": list(second_pass_queries or []),
            },
            "source_plan": (
                source_plan.to_trace_dict() if hasattr(source_plan, "to_trace_dict") else {}
            ),
        },
    )


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
                doc["_source_group"] = str(doc.get("_source_group") or group)
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


def _pin_exact_question_results(
    results: list[dict[str, Any]],
    *,
    exact_question_present: bool,
) -> list[dict[str, Any]]:
    if not exact_question_present or not results:
        return results
    exact_groups = {"question_exact_text", "question_exact_vector"}
    exact_head = [
        item
        for item in results
        if str(item.get("_source_group") or "") in exact_groups
    ]
    if not exact_head:
        return results
    exact_ids = {id(item) for item in exact_head}
    return exact_head + [item for item in results if id(item) not in exact_ids]


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
    query_plan_trace_enabled: bool = True
    compiled_truth_shadow_enabled: bool = True
    compiled_truth_enabled: bool = False
    compiled_truth_max_documents: int = 6
    compiled_truth_max_chars_per_doc: int = 700
    compiled_truth_max_total_chars: int = 2400
    provenance_boost_enabled: bool = False
    query_variant_concurrency: int = 2


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

    async def check_chunk_ids_exist(
        self,
        chunk_ids: list[str],
        kb_name: str,
    ) -> set[str]:
        """Return the subset of chunk_ids that exist in the KB's kb_chunks table.

        Read-only batch existence check over PostgREST (chunk_id=in.(...)),
        reusing the _select read path (same pattern as _hydrate_sources). Backs
        the RAG eval preflight (1B): the caller computes
        ``missing = requested - found`` to detect a golden set gone stale after
        a KB reindex. kb_name selects the Supabase config (url/key/timeout);
        chunk_id is unique within a KB so no per-row kb_name filter is applied,
        consistent with _hydrate_sources and the availability gate. Supabase
        errors propagate as RAGSearchError so the preflight can tell infra-down
        (skip) apart from a truly stale set.
        """
        unique_ids = list(
            dict.fromkeys(
                str(cid).strip() for cid in chunk_ids if str(cid or "").strip()
            )
        )
        if not unique_ids:
            return set()

        config = self._load_search_config(kb_name=kb_name, kwargs={})
        client = await self._get_client(config.timeout_s)
        found: set[str] = set()
        for start in range(0, len(unique_ids), _CHUNK_ID_EXISTS_BATCH_SIZE):
            batch = unique_ids[start : start + _CHUNK_ID_EXISTS_BATCH_SIZE]
            quoted_ids = ",".join(f'"{cid}"' for cid in batch)
            rows = await self._select(
                client,
                table="kb_chunks",
                select="chunk_id",
                query={"chunk_id": f"in.({quoted_ids})"},
                config=config,
            )
            for row in rows:
                cid = str(row.get("chunk_id") or "").strip()
                if cid:
                    found.add(cid)
        return found

    async def search(
        self,
        query: str,
        kb_name: str,
        **kwargs,
    ) -> dict[str, Any]:
        total_started_at = time.perf_counter()
        stage_timings_ms: dict[str, float] = {}

        def record_stage(name: str, started_at: float) -> None:
            stage_timings_ms[name] = round((time.perf_counter() - started_at) * 1000, 1)

        query = str(query or "").strip()
        if not query:
            return {"query": "", "answer": "", "content": "", "sources": [], "provider": "supabase"}

        config = self._load_search_config(kb_name=kb_name, kwargs=kwargs)
        intent = str(kwargs.get("intent") or "").strip()
        question_type = str(kwargs.get("question_type") or "").strip()
        routing_metadata = kwargs.get("routing_metadata")
        routing_metadata = routing_metadata if isinstance(routing_metadata, dict) else {}
        compiled_learning_truth = kwargs.get("compiled_learning_truth")
        personalization_context = kwargs.get("personalization_context")
        personalization_context = personalization_context if isinstance(personalization_context, dict) else None
        self._last_query_embedding_dim: int | None = None
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
                routing_metadata=routing_metadata,
            )
            retrieval_plan = build_retrieval_plan(
                query,
                include_questions_default=config.include_questions,
                intent=intent,
                question_type=question_type,
                routing_metadata={
                    **routing_metadata,
                    "compiled_learning_truth_available": bool(compiled_learning_truth),
                    "personalization_context_available": bool(personalization_context)
                    or bool(routing_metadata.get("personalization_context_available")),
                },
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
            intent_fast_path = str(getattr(retrieval_plan, "intent", "") or "").strip() in {
                "weak_point_review",
                "next_training",
            }
            if intent_fast_path:
                primary_queries = primary_queries[:1]
            effective_second_pass_enabled = bool(config.second_pass_enabled and not intent_fast_path)
            effective_rerank_enabled = bool(config.rerank_enabled and not intent_fast_path)
            exact_text_plans: list[dict[str, Any]] = []
            retrieval_warnings: list[dict[str, str]] = []
            stage_started = time.perf_counter()
            compiled_truth_plan = self._compiled_truth_plan(
                retrieval_plan=retrieval_plan,
                compiled_learning_truth=compiled_learning_truth,
                personalization_context=personalization_context,
                config=config,
            )
            compiled_truth_final_enabled = self._compiled_truth_final_enabled(
                retrieval_plan=retrieval_plan,
                config=config,
            )
            final_compiled_truth_plan = (
                self._final_compiled_truth_plan(compiled_truth_plan)
                if compiled_truth_final_enabled
                else []
            )
            shadow_compiled_truth_sources = (
                self._plan_documents(compiled_truth_plan)
                if config.compiled_truth_shadow_enabled and not final_compiled_truth_plan
                else []
            )
            record_stage("compiled_truth_plan", stage_started)
            compiled_only_fast_path = (
                str(getattr(retrieval_plan, "intent", "") or "").strip() == "next_training"
                and bool(final_compiled_truth_plan)
            )
            primary_plan: list[dict[str, Any]] = []

            if compiled_only_fast_path:
                stage_timings_ms["availability_gate"] = 0.0
                stage_timings_ms["primary_plan"] = 0.0
                primary_queries = []
                effective_second_pass_enabled = False
                effective_rerank_enabled = False
            else:
                try:
                    stage_started = time.perf_counter()
                    client = await self._get_client(config.timeout_s)
                    await self._assert_data_api_available(client=client, config=config)
                    record_stage("availability_gate", stage_started)
                    exact_text_task: asyncio.Task[list[dict[str, Any]]] | None = None
                    exact_text_started_at: float | None = None
                    # case 粘贴的 probe query 恒长于 max_text_len（MCQ 时代校准的门），
                    # 此前把整个 text-first 任务连同 case_exact_queries 一起闷死——
                    # case 切片候选器成了永不消费的孤岛（1b live 实证：在库案例题
                    # 文本路径从未运行、exact 恒 miss）。case 候选在场即放行；长
                    # probe query 交给 build_exact_question_text_candidates 的
                    # case_like 切片，身份仍由 exact_question_identity_corresponds
                    # 单一裁决（候选供给变宽，采信权威不变）。
                    if (
                        exact_probe
                        and config.exact_question_text_first
                        and (
                            len(exact_probe.query) <= config.exact_question_max_text_len
                            or case_exact_queries
                        )
                    ):
                        exact_text_candidates = [exact_probe.query]
                        for candidate in case_exact_queries:
                            if candidate not in exact_text_candidates:
                                exact_text_candidates.append(candidate)
                        exact_text_started_at = time.perf_counter()
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
                    stage_started = time.perf_counter()
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
                    record_stage("primary_plan", stage_started)
                    if exact_text_task is not None:
                        exact_text_batches = await exact_text_task
                        if exact_text_started_at is not None:
                            record_stage("exact_text_probe", exact_text_started_at)
                        for batch_index, batch in enumerate(exact_text_batches):
                            exact_text_rows = batch.get("results") if isinstance(batch, dict) else None
                            if not exact_text_rows:
                                continue
                            # Identity-adjudicated rows mint the exact chapter;
                            # demoted candidates join the ordinary questions_bank
                            # group so they can never enter the exact payload or
                            # flip has_exact_question_hit.
                            identity_rows = [
                                row
                                for row in exact_text_rows
                                if str(row.get("_source_group") or "") == "question_exact_text"
                            ]
                            demoted_rows = [
                                row
                                for row in exact_text_rows
                                if str(row.get("_source_group") or "") != "question_exact_text"
                            ]
                            if identity_rows:
                                exact_text_plans.append(
                                    {
                                        "phase": "primary",
                                        "group_name": "question_exact_text",
                                        "query": str(batch.get("query") or exact_probe.query if exact_probe else query),
                                        "query_index": batch_index,
                                        "query_weight": 1.0,
                                        "results": identity_rows,
                                    }
                                )
                            if demoted_rows:
                                exact_text_plans.append(
                                    {
                                        "phase": "primary",
                                        "group_name": "questions_bank",
                                        "query": str(batch.get("query") or exact_probe.query if exact_probe else query),
                                        "query_index": batch_index,
                                        "query_weight": 1.0,
                                        "results": demoted_rows,
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

        stage_started = time.perf_counter()
        fused = self._fuse_plan_results(
            [*exact_text_plans, *primary_plan, *final_compiled_truth_plan],
            query=query,
            question_like=question_like,
            config=config,
        )
        record_stage("primary_fusion", stage_started)
        second_pass_plan: list[dict[str, Any]] = []

        second_pass_queries: list[str] = []
        has_exact_question_hit = any(
            plan.get("group_name") in {"question_exact_text", "question_exact_vector"}
            and bool(plan.get("results"))
            for plan in [*exact_text_plans, *primary_plan]
        )
        should_force_case_supplement = query_shape == "case_like"
        if (
            effective_second_pass_enabled
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
                    stage_started = time.perf_counter()
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
                    record_stage("second_pass_plan", stage_started)
                    stage_started = time.perf_counter()
                    fused = self._fuse_plan_results(
                        [*exact_text_plans, *primary_plan, *second_pass_plan, *final_compiled_truth_plan],
                        query=query,
                        question_like=question_like,
                        config=config,
                    )
                    record_stage("second_pass_fusion", stage_started)
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

        all_plans = [*exact_text_plans, *primary_plan, *second_pass_plan, *final_compiled_truth_plan]
        stage_started = time.perf_counter()
        exact_question = self._project_mcq_exact_question_to_query_surface(
            self._augment_case_exact_question_with_query(
                self._extract_exact_question_payload(
                    all_plans,
                    original_query=query,
                    exact_probe=exact_probe,
                ),
                query=query,
                query_shape=query_shape,
            ),
            query,
        )
        fused = dedupe_ranked_results(fused, max_items=config.fetch_count * 2)
        record_stage("dedupe_and_exact", stage_started)
        stage_started = time.perf_counter()
        enriched = await self._hydrate_sources(fused[: config.fetch_count], config=config)
        record_stage("hydrate_sources", stage_started)
        stage_started = time.perf_counter()
        enriched = self._filter_partial_case_results(enriched, exact_question=exact_question)
        enriched = _project_teaching_metadata(enriched)
        enriched = _enforce_doc_diversity(enriched, max_per_document=config.max_per_document)
        record_stage("post_hydrate_projection", stage_started)
        if effective_rerank_enabled:
            stage_started = time.perf_counter()
            reranked = await self._rerank_results(
                query=query,
                results=enriched,
                config=config,
            )
            record_stage("rerank", stage_started)
        else:
            reranked = list(enriched)
        reranked = self._filter_partial_case_results(reranked, exact_question=exact_question)
        final_results = dedupe_ranked_results(reranked, max_items=config.top_k)
        final_results = self._ensure_final_compiled_truth_presence(
            final_results,
            plans=final_compiled_truth_plan,
            max_items=config.top_k,
        )
        ranking_trace = build_ranking_trace(
            final_results,
            authority_order=list(getattr(retrieval_plan, "authority_order", []) or []),
            shadow_sources=shadow_compiled_truth_sources,
            ranking_policy={
                "query_plan_trace_enabled": config.query_plan_trace_enabled,
                "compiled_truth_shadow_enabled": config.compiled_truth_shadow_enabled,
                "compiled_truth_final_enabled": bool(final_compiled_truth_plan),
                "provenance_boost_enabled": config.provenance_boost_enabled,
            },
        )

        content_blocks = _dedupe_rendered_content_blocks(
            [str(item.get("rag_content") or "").strip() for item in final_results]
        )
        content = "\n\n".join(block for block in content_blocks if block)

        source_items: list[dict[str, Any]] = []
        for item in final_results:
            raw_metadata = item.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            source_items.append(
                {
                    "title": item.get("card_title") or item.get("title") or "Document",
                    "content": str(item.get("rag_content") or "")[:200],
                    "source": item.get("source") or item.get("source_doc") or item.get("card_title") or "",
                    "page": item.get("page_num") or item.get("page") or "",
                    "chunk_id": item.get("chunk_id") or item.get("id") or "",
                    "score": round(float(item.get("score") or 0.0), 4),
                    "source_type": item.get("source_type") or "",
                    "document_id": metadata.get("document_id") or metadata.get("doc_id") or item.get("document_id") or item.get("doc_id") or "",
                    "authority": metadata.get("authority") or item.get("authority") or {},
                    "subject": metadata.get("subject") or item.get("subject") or "",
                    "source_id": metadata.get("source_id") or item.get("source_id") or "",
                    "source_table": metadata.get("source_table") or item.get("_source_table") or item.get("source_table") or "",
                    "stable_id": metadata.get("stable_id") or item.get("stable_id") or "",
                    "source_span": metadata.get("source_span") or item.get("source_span") or {},
                    "content_hash": metadata.get("content_hash") or item.get("content_hash") or "",
                    "quote_hash": metadata.get("quote_hash") or item.get("quote_hash") or "",
                    "node_code": metadata.get("node_code") or item.get("node_code") or "",
                    "taxonomy_path": metadata.get("taxonomy_path") or item.get("taxonomy_path") or "",
                    "chapter": metadata.get("chapter") or item.get("chapter") or "",
                    "chapter_name": metadata.get("chapter_name") or item.get("chapter_name") or "",
                    "section": metadata.get("section") or item.get("section") or "",
                }
            )
        sources = _dedupe_source_items(source_items)
        evidence_bundle = _build_evidence_bundle(
            query=query,
            provider="supabase",
            kb_name=kb_name,
            content_blocks=content_blocks,
            sources=sources,
            exact_question=exact_question,
            source_plan=source_plan,
            retrieval_plan=retrieval_plan if config.query_plan_trace_enabled else None,
            ranking_trace=ranking_trace,
            query_shape=query_shape,
            rewritten=rewritten,
            second_pass_queries=second_pass_queries,
            embedding_dim=self._last_query_embedding_dim,
            # builder derives retrieval_degraded/status/warning_count from this (fully populated here)
            retrieval_warnings=retrieval_warnings,
        )
        stage_timings_ms["total"] = round((time.perf_counter() - total_started_at) * 1000, 1)
        performance_policy = {
            "intent_fast_path": bool(intent_fast_path),
            "compiled_only_fast_path": bool(compiled_only_fast_path),
            "rerank_enabled": bool(effective_rerank_enabled),
            "second_pass_enabled": bool(effective_second_pass_enabled),
            "primary_query_count": len(primary_queries),
        }
        # post-build diagnostics (total timing is only knowable after the bundle) → trace bucket
        evidence_bundle["trace"]["stage_timings_ms"] = dict(stage_timings_ms)
        evidence_bundle["trace"]["performance_policy"] = dict(performance_policy)

        payload = {
            "query": query,
            "answer": content,
            "content": content,
            "sources": evidence_bundle["sources"],
            "provider": "supabase",
            "kb_name": kb_name,
            "evidence_bundle": evidence_bundle,
            "retrieval_degraded": bool(retrieval_warnings),
            "retrieval_status": "partial" if retrieval_warnings else "ok",
        }
        if retrieval_warnings:
            payload["warnings"] = list(retrieval_warnings)
            payload["evidence_bundle"]["trace"]["warnings"] = list(retrieval_warnings)
        if exact_question:
            payload["exact_question"] = exact_question
        trace_metadata = {
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
            "retrieval_plan": retrieval_plan.to_dict(),
            "retrieval_plan_json": json.dumps(
                retrieval_plan.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "retrieval_plan_intent": str(getattr(retrieval_plan, "intent", "") or ""),
            "ranking_trace": ranking_trace,
            "ranking_trace_json": json.dumps(
                ranking_trace,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "ranking_trace_fusion": str(ranking_trace.get("fusion") or ""),
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
            "stage_timings_ms": dict(stage_timings_ms),
            "performance_policy": dict(performance_policy),
            "retrieval_degraded": bool(retrieval_warnings),
            "retrieval_status": str(payload["retrieval_status"]),
            "warning_count": len(retrieval_warnings),
        }
        observability.update_observation(
            observation,
            output_payload={
                "source_count": len(sources),
                "source_types": [item.get("source_type") or "" for item in sources],
            },
            metadata=trace_metadata,
        )
        return payload

    def _compiled_truth_plan(
        self,
        *,
        retrieval_plan,
        compiled_learning_truth: Any,
        personalization_context: Any = None,
        config: SupabaseSearchConfig | None = None,
    ) -> list[dict[str, Any]]:
        source_group = getattr(retrieval_plan, "source_groups", {}).get("compiled_learning_truth")
        if not source_group or not getattr(source_group, "enabled", False):
            return []
        documents = materialize_compiled_truth_documents(
            (
                compiled_learning_truth
                if isinstance(compiled_learning_truth, dict)
                else personalization_context
                if isinstance(personalization_context, dict)
                else None
            ),
            max_documents=config.compiled_truth_max_documents if config else 6,
            max_chars_per_doc=config.compiled_truth_max_chars_per_doc if config else 700,
            max_total_chars=config.compiled_truth_max_total_chars if config else 2400,
        )
        if not documents:
            return []
        return [
            {
                "phase": "context",
                "group_name": "compiled_learning_truth",
                "query": str(getattr(retrieval_plan, "primary_query", "") or ""),
                "query_index": 0,
                "query_weight": 0.85,
                "results": documents,
            }
        ]

    def _compiled_truth_final_enabled(
        self,
        *,
        retrieval_plan,
        config: SupabaseSearchConfig,
    ) -> bool:
        if not config.compiled_truth_enabled:
            return False
        intent = str(getattr(retrieval_plan, "intent", "") or "").strip()
        return intent in {"weak_point_review", "next_training"}

    def _final_compiled_truth_plan(self, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        final_plans: list[dict[str, Any]] = []
        for plan in plans:
            results = [
                item
                for item in list(plan.get("results") or [])
                if not bool(item.get("_compiled_truth_shadow_only"))
            ]
            if not results:
                continue
            next_plan = dict(plan)
            next_plan["results"] = results
            final_plans.append(next_plan)
        return final_plans

    def _plan_documents(self, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for plan in plans:
            documents.extend(list(plan.get("results") or []))
        return documents

    def _ensure_final_compiled_truth_presence(
        self,
        final_results: list[dict[str, Any]],
        *,
        plans: list[dict[str, Any]],
        max_items: int,
    ) -> list[dict[str, Any]]:
        if not plans:
            return final_results
        if any(str(item.get("_source_group") or item.get("source_type") or "") == "compiled_learning_truth" for item in final_results):
            return final_results
        candidates = self._plan_documents(plans)
        if not candidates:
            return final_results
        candidate = dict(candidates[0])
        candidate["_source_group"] = "compiled_learning_truth"
        candidate["_query_phase"] = candidate.get("_query_phase") or "context"
        candidate["_query_variant"] = candidate.get("_query_variant") or ""
        if final_results:
            lowest_score = min(float(item.get("score") or 0.0) for item in final_results)
            candidate["score"] = min(float(candidate.get("score") or 0.0), lowest_score)
        limit = max(1, int(max_items or (len(final_results) + 1)))
        if len(final_results) >= limit:
            merged = [*final_results[: limit - 1], candidate]
        else:
            merged = [*final_results, candidate]
        return dedupe_ranked_results(merged, max_items=limit)

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
        selected_sources = [
            source
            for source in config.sources
            if (
                (source == "textbook" and source_plan.search_textbook_chunks)
                or (source == "standard" and source_plan.search_standard_chunks)
                or (source == "exam" and source_plan.search_exam_chunks)
            )
        ]
        semaphore = asyncio.Semaphore(max(1, int(getattr(config, "query_variant_concurrency", 1) or 1)))
        query_embedding_dim = 0

        # T4①: prefetch embeddings for all distinct uncached variants in ONE
        # batch API call instead of one embed call per variant. Failure (or an
        # empty prefetch) falls back to the per-query embed path inside run_one
        # (original behavior).
        cache_enabled = _embedding_cache_enabled()
        pending_queries = [
            q
            for q in dict.fromkeys(str(item or "").strip() for item in queries)
            if q and not (cache_enabled and _get_cached_embedding(q))
        ]
        local_embeddings = await self._embed_queries_batch(pending_queries)

        async def run_one(query_index: int, item: str) -> tuple[int, list[dict[str, Any]]]:
            nonlocal query_embedding_dim
            current_query = str(item or "").strip()
            if not current_query:
                return query_index, []
            embedding = local_embeddings.get(current_query) or await self._embed_query(current_query)
            if not query_embedding_dim and embedding:
                query_embedding_dim = len(embedding)
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
            bank_search_scheduled = source_plan.search_questions_bank and (
                config.include_questions or question_like
            )
            exact_vector_wanted = bool(exact_probe) and query_index == 0 and bank_search_scheduled
            # T4②: the dedicated exact-vector call hits the SAME RPC as the
            # regular bank search (same embedding, higher threshold, count
            # min(fetch_count,5)) — a strict subset when rows are similarity-desc.
            # Derive it client-side from the bank rows and save one RPC per turn.
            # Falls back to the dedicated RPC when the superset preconditions
            # don't hold (small fetch_count, inverted thresholds) or the bank
            # rows arrive unsorted.
            derive_exact_from_bank = (
                exact_vector_wanted
                and config.fetch_count >= 5
                and config.match_threshold <= self._exact_vector_search_threshold(config)
            )
            bank_raw_rows: list[dict[str, Any]] = []
            if bank_search_scheduled:
                tasks.append(
                    self._search_questions(
                        client=client,
                        vector_literal=vector_literal,
                        config=config,
                        raw_sink=bank_raw_rows if derive_exact_from_bank else None,
                    )
                )
                task_groups.append("questions_bank")
            if exact_vector_wanted and not derive_exact_from_bank:
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
            query_plans: list[dict[str, Any]] = []
            for group_name, result in zip(task_groups, raw_results):
                if isinstance(result, Exception):
                    if _is_supabase_service_restriction(result):
                        raise result
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
                query_plans.append(
                    {
                        "phase": phase,
                        "group_name": group_name,
                        "query": current_query,
                        "query_index": query_index,
                        "query_weight": query_weight * max(0.45, 1.0 - (query_index * 0.12)),
                        "results": result,
                    }
                )

            if derive_exact_from_bank:
                bank_plan_index = next(
                    (
                        index
                        for index, plan in enumerate(query_plans)
                        if plan.get("group_name") == "questions_bank"
                    ),
                    None,
                )
                if bank_plan_index is None:
                    # Bank RPC itself failed (already in failure_sink); the
                    # dedicated exact call hits the same RPC and would fail the
                    # same way — nothing to derive.
                    self.logger.debug(
                        "Supabase exact-vector derivation skipped: questions_bank group failed"
                    )
                else:
                    derived = self._derive_exact_from_bank_rows(
                        bank_raw_rows,
                        allowed_question_types=exact_probe.allowed_question_types,
                        original_query=original_query,
                        option_validation_required=exact_probe.option_validation_required,
                        config=config,
                    )
                    if derived is None:
                        try:
                            derived = await self._search_exact_question_vector(
                                client=client,
                                vector_literal=vector_literal,
                                allowed_question_types=exact_probe.allowed_question_types,
                                original_query=original_query,
                                option_validation_required=exact_probe.option_validation_required,
                                config=config,
                            )
                        except Exception as exc:  # noqa: BLE001 — mirror group fail-soft
                            if _is_supabase_service_restriction(exc):
                                raise
                            derived = None
                            if failure_sink is not None:
                                failure_sink.append(
                                    _rag_warning_payload(
                                        phase=phase,
                                        group_name="question_exact_vector",
                                        query=current_query,
                                        exc=exc,
                                    )
                                )
                            self.logger.warning(
                                f"Supabase group 'question_exact_vector' failed for query "
                                f"'{current_query}': {exc}"
                            )
                    if derived is not None:
                        # Keep the plan position the dedicated task used to have
                        # (immediately after questions_bank).
                        query_plans.insert(
                            bank_plan_index + 1,
                            {
                                "phase": phase,
                                "group_name": "question_exact_vector",
                                "query": current_query,
                                "query_index": query_index,
                                "query_weight": query_weight * max(0.45, 1.0 - (query_index * 0.12)),
                                "results": derived,
                            },
                        )
            return query_index, query_plans

        async def run_guarded(query_index: int, item: str) -> tuple[int, list[dict[str, Any]]]:
            async with semaphore:
                return await run_one(query_index, item)

        batches = await asyncio.gather(
            *[
                run_guarded(query_index, item)
                for query_index, item in enumerate(queries)
            ]
        )
        plans: list[dict[str, Any]] = []
        for _query_index, query_plans in sorted(batches, key=lambda item: item[0]):
            plans.extend(query_plans)
        self._last_query_embedding_dim = query_embedding_dim or None
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
                item["_source_group"] = group_name
                item["_query_variant"] = str(plan.get("query") or "")
                item["_query_phase"] = phase

        fused = _weighted_rrf_fusion(results_map, weights)
        exact_question_present = any(
            str(plan.get("group_name") or "") in {"question_exact_text", "question_exact_vector"}
            and bool(plan.get("results"))
            for plan in plans
        )
        target_window = max(1, max(config.top_k, min(config.fetch_count, config.rerank_window)))
        fused = _apply_similarity_floor(fused, results_map, target_window=target_window)
        fused = _enrich_question_weights(fused, question_like=question_like, config=config)
        fused = apply_provenance_ranking(
            fused,
            exact_question_present=exact_question_present,
            enabled=config.provenance_boost_enabled,
        )
        fused = _pin_exact_question_results(
            fused,
            exact_question_present=exact_question_present,
        )
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

        # T6: optional char cap on the text SENT to the reranker only. The
        # candidate items (and everything returned/displayed) keep the full
        # rag_content — the index mapping below re-attaches the original item.
        cap = _rerank_doc_char_cap()
        rerank_docs = [
            (doc[:cap] if cap > 0 else doc)
            for doc in (str(item.get("rag_content") or "").strip() for item in rerank_candidates)
        ]
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

    async def _embed_queries_batch(self, queries: list[str]) -> dict[str, list[float]]:
        """T4①: ONE order-preserving batch embed call for the given (deduped,
        uncached) query variants. Returns {query: embedding}; an empty dict on
        failure or when fewer than 2 queries are pending — callers then use the
        per-query ``_embed_query`` path (the original behavior)."""
        if len(queries) < 2:
            return {}
        try:
            embeddings = await get_embedding_client().embed(list(queries))
        except Exception as exc:  # noqa: BLE001 — fail-open to per-query embeds
            self.logger.warning(
                f"Supabase batch embedding prefetch failed; per-query fallback: {exc}"
            )
            return {}
        cache_enabled = _embedding_cache_enabled()
        resolved: dict[str, list[float]] = {}
        for query, embedding in zip(queries, embeddings or []):
            if embedding:
                resolved[query] = embedding
                if cache_enabled:
                    _cache_embedding(query, embedding)
        return resolved

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
            "compiled_learning_truth": float(os.getenv("SUPABASE_RAG_WEIGHT_COMPILED_TRUTH", "0.65")),
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
            query_plan_trace_enabled=_env_flag("SUPABASE_RAG_QUERY_PLAN_TRACE_ENABLED", True),
            compiled_truth_shadow_enabled=_env_flag(
                "SUPABASE_RAG_COMPILED_TRUTH_SHADOW_ENABLED",
                True,
            ),
            compiled_truth_enabled=_env_flag("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", False),
            compiled_truth_max_documents=max(
                1,
                int(os.getenv("SUPABASE_RAG_COMPILED_TRUTH_MAX_DOCS", "6")),
            ),
            compiled_truth_max_chars_per_doc=max(
                120,
                int(os.getenv("SUPABASE_RAG_COMPILED_TRUTH_MAX_CHARS_PER_DOC", "700")),
            ),
            compiled_truth_max_total_chars=max(
                300,
                int(os.getenv("SUPABASE_RAG_COMPILED_TRUTH_MAX_TOTAL_CHARS", "2400")),
            ),
            provenance_boost_enabled=_env_flag("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", False),
            query_variant_concurrency=max(
                1,
                int(os.getenv("SUPABASE_RAG_QUERY_VARIANT_CONCURRENCY", "2")),
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
            # T5: search_unified is the dominant slow/timeout RPC — give it its
            # own budget so one slow group degrades (failure_sink) instead of
            # holding the whole plan to the 8s client timeout.
            timeout_s=_unified_rpc_timeout_s(),
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
        # Semantic-integrity collapse (2026-07-12): the direct-ILIKE and text-RPC
        # probes only SUPPLY candidates. Whether a candidate is the learner's
        # question is decided by the single identity adjudicator
        # exact_question_identity_corresponds. A candidate that fails any exact
        # gate degrades to an ordinary questions_bank retrieval row carrying its
        # real text_score (no fabricated confidence floor) so the turn falls
        # open to the main LLM with the row still available as context.
        demoted_rows: list[dict[str, Any]] = []
        demoted_ids: set[str] = set()

        def _demote(row: dict[str, Any]) -> None:
            row_id = str(row.get("id") or "").strip()
            if row_id and row_id in demoted_ids:
                return
            if row_id:
                demoted_ids.add(row_id)
            if len(demoted_rows) >= 5:
                return
            demoted_rows.append(
                self._normalize_question_result(
                    row,
                    source_group="questions_bank",
                    score=float(row.get("text_score") or 0.0),
                )
            )

        direct_rows = await self._search_exact_question_text_direct(
            client=client,
            probe_query=clean,
            config=config,
            warning_sink=warning_sink,
        )
        for row in direct_rows:
            if not matches_allowed_question_type(row.get("question_type"), allowed_question_types):
                _demote(row)
                continue
            if not validate_exact_question_options(
                original_query=original_query,
                options=row.get("options"),
                option_validation_required=option_validation_required,
            ):
                _demote(row)
                continue
            if not exact_question_identity_corresponds(
                original_query=original_query,
                matched_stem=_question_identity_surface(row),
                question_type=row.get("question_type"),
            ):
                _demote(row)
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
                        _demote(row)
                        continue
                    if not validate_exact_question_options(
                        original_query=original_query,
                        options=row.get("options"),
                        option_validation_required=option_validation_required,
                    ):
                        _demote(row)
                        continue
                    if not exact_question_identity_corresponds(
                        original_query=original_query,
                        matched_stem=_question_identity_surface(row),
                        question_type=row.get("question_type"),
                    ):
                        _demote(row)
                        continue
                    return [
                        self._normalize_question_result(
                            row,
                            source_group="question_exact_text",
                            # real text_score only — the 0.98 confidence floor
                            # fabricated authority for fuzzy full-text hits.
                            score=float(row.get("text_score") or 0.0),
                        )
                    ]
        return demoted_rows

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
            if isinstance(exc, RAGError):
                raise
            self.logger.debug(f"Supabase questions text RPC unavailable: {exc}")
            return []

    @staticmethod
    def _exact_vector_search_threshold(config: SupabaseSearchConfig) -> float:
        return min(0.70, config.exact_question_min_similarity - 0.1)

    def _filter_exact_question_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        allowed_question_types: list[str],
        original_query: str,
        option_validation_required: bool,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]]:
        """The exact-vector adoption filter chain, shared verbatim by the
        dedicated RPC path and the T4② bank-superset derivation path.

        Semantic-integrity collapse (2026-07-12): cosine similarity (and every
        other pre-gate here) is candidate supply, not identity authority. Only
        ``exact_question_identity_corresponds`` may mint ``question_exact_vector``.
        Rows that fail are dropped — NOT lost: the parallel ``_search_questions``
        pass hits the same RPC with a lower threshold and the same embedding, so
        every candidate seen here is already supplied downstream as an ordinary
        ``questions_bank`` row carrying its real similarity score.
        """
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
            if not exact_question_identity_corresponds(
                original_query=original_query,
                matched_stem=_question_identity_surface(row),
                question_type=row.get("question_type"),
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
        search_threshold = self._exact_vector_search_threshold(config)
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
        return self._filter_exact_question_rows(
            rows,
            allowed_question_types=allowed_question_types,
            original_query=original_query,
            option_validation_required=option_validation_required,
            config=config,
        )

    def _derive_exact_from_bank_rows(
        self,
        raw_rows: list[dict[str, Any]],
        *,
        allowed_question_types: list[str],
        original_query: str,
        option_validation_required: bool,
        config: SupabaseSearchConfig,
    ) -> list[dict[str, Any]] | None:
        """T4②: derive the question_exact_vector result from the regular
        questions_bank rows instead of issuing a second identical RPC.

        Both calls hit the SAME ``search_questions_bank_vector`` function with
        the SAME embedding; the dedicated exact call only differs by a HIGHER
        threshold and a count of min(fetch_count, 5). With rows ordered by
        similarity DESC, ``top-fetch_count @ match_threshold`` restricted to
        ``similarity >= exact_threshold`` and truncated to min(fetch_count, 5)
        is exactly ``top-min(fetch_count,5) @ exact_threshold`` — a strict
        superset derivation. Returns None when the desc-order precondition is
        violated at runtime (caller falls back to the dedicated RPC).
        """
        search_threshold = self._exact_vector_search_threshold(config)
        similarities = [float(row.get("similarity") or 0.0) for row in raw_rows]
        if any(a < b for a, b in zip(similarities, similarities[1:])):
            return None  # not similarity-desc — superset precondition broken
        eligible = [
            row
            for row, similarity in zip(raw_rows, similarities)
            if similarity >= search_threshold
        ][: min(config.fetch_count, 5)]
        return self._filter_exact_question_rows(
            eligible,
            allowed_question_types=allowed_question_types,
            original_query=original_query,
            option_validation_required=option_validation_required,
            config=config,
        )

    async def _search_questions(
        self,
        *,
        client: httpx.AsyncClient,
        vector_literal: str,
        config: SupabaseSearchConfig,
        raw_sink: list[dict[str, Any]] | None = None,
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
        if raw_sink is not None:
            # T4②: expose the raw RPC rows (order preserved) so q0 can derive
            # the exact-vector subset without a second identical RPC.
            raw_sink.extend(row for row in rows if isinstance(row, dict))
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
        priority = {
            "question_exact_text": 0,
            "question_exact_vector": 1,
            "question_bank_case_match": 2,
        }

        def _plan_exact_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
            # Identity-demoted candidates are re-grouped as questions_bank plans
            # upstream and can never reach here; this row-level guard keeps any
            # future demotion path from leaking into the exact payload.
            group_name = str(plan.get("group_name") or "")
            results = plan.get("results")
            if not isinstance(results, list):
                return []
            if group_name not in {"question_exact_text", "question_exact_vector"}:
                return list(results)
            return [
                row
                for row in results
                if str((row or {}).get("_source_group") or group_name) == group_name
            ]

        candidates = sorted(
            [
                {**plan, "results": exact_rows}
                for plan in plans
                if str(plan.get("group_name") or "") in priority
                and (exact_rows := _plan_exact_rows(plan))
            ],
            key=lambda item: priority[str(item.get("group_name") or "")],
        )
        if not candidates:
            promoted_row = self._select_option_matched_question_bank_row(
                plans,
                original_query=original_query,
                exact_probe=exact_probe,
            )
            if promoted_row is not None:
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
            else:
                promoted_case_rows = self._select_case_matched_question_bank_rows(
                    plans,
                    original_query=original_query,
                    exact_probe=exact_probe,
                )
                if not promoted_case_rows:
                    return None
                candidates = [
                    {
                        "phase": promoted_case_rows[0].get("_query_phase") or "primary",
                        "group_name": "question_bank_case_match",
                        "query": promoted_case_rows[0].get("_query_variant") or original_query,
                        "query_index": 0,
                        "query_weight": 1.0,
                        "results": promoted_case_rows,
                    }
                ]
        elif any(
            "case" in str((item or {}).get("question_type") or "").strip().lower()
            for plan in candidates
            for item in (plan.get("results") or [])
        ):
            promoted_case_rows = self._select_case_matched_question_bank_rows(
                plans,
                original_query=original_query,
                exact_probe=exact_probe,
            )
            if promoted_case_rows:
                candidates.append(
                    {
                        "phase": promoted_case_rows[0].get("_query_phase") or "primary",
                        "group_name": "question_bank_case_match",
                        "query": promoted_case_rows[0].get("_query_variant") or original_query,
                        "query_index": len(candidates),
                        "query_weight": 0.9,
                        "results": promoted_case_rows,
                    }
                )

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
                # tier1 可达性（2026-07-30）：顶层显式 question_id 与复合 qid 原料
                # （pgo bank 键 = f"{exam_year}::{source_chunk_id}::E{n}"）。
                "question_id": selected_row.get("id") or "",
                "source_chunk_id": str(selected_row.get("source_chunk_id") or "").strip(),
                "exam_year": selected_row.get("exam_year"),
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
                "source_group": str(
                    selected_row.get("_source_group")
                    or selected_row.get("source_group")
                    or "question_exact_text"
                ),
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
            "question_id": row.get("id") or "",
            "source_chunk_id": str(row.get("source_chunk_id") or "").strip(),
            "exam_year": row.get("exam_year"),
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

    @staticmethod
    def _project_mcq_exact_question_to_query_surface(
        exact_question: dict[str, Any] | None,
        query: str,
    ) -> dict[str, Any] | None:
        """Grade on the surface the learner actually saw.

        The bank stores its own option order (e.g. D=5%); a learner who pasted
        "A.5% B.2% ... 我选A" answered on THEIR surface. Without this, grading
        compares the learner's letter (A) against the bank letter (D) and marks a
        correct answer wrong. Reuse the single projection authority
        (_project_to_query_option_surface) to remap the bank correct-answer by VALUE
        onto the learner's option surface. MCQ-only; fail-safe: if the values do not
        correspond (rewritten/missing options, value-only surface) the projection
        keeps the bank surface and we leave the payload unchanged.
        """
        if not isinstance(exact_question, dict):
            return exact_question
        if str(exact_question.get("answer_kind") or "").strip().lower() != "mcq":
            return exact_question

        import json as _json

        from deeptutor.services.rag.historical_questions import (
            _normalize_options,
            _project_to_query_option_surface,
        )

        raw_options = exact_question.get("options")
        if isinstance(raw_options, str):
            try:
                raw_options = _json.loads(raw_options)
            except (ValueError, TypeError):
                return exact_question
        candidate_options = _normalize_options(raw_options)
        if len(candidate_options) < 2:
            return exact_question

        projected = _project_to_query_option_surface(
            {**exact_question, "options": candidate_options},
            query,
        )
        if (projected.get("metadata") or {}).get("option_surface") != "query":
            # Values did not map cleanly onto the learner's surface — keep bank surface.
            return exact_question

        result = dict(exact_question)
        result["correct_answer"] = projected.get("correct_answer")
        result["options"] = {
            str(opt.get("key") or "").strip().upper(): str(opt.get("value") or "").strip()
            for opt in (projected.get("options") or [])
            if isinstance(opt, dict) and str(opt.get("key") or "").strip()
        }
        metadata = dict(result.get("metadata") or {})
        metadata["canonical_correct_answer"] = (projected.get("metadata") or {}).get(
            "canonical_correct_answer"
        ) or str(exact_question.get("correct_answer") or "").strip()
        metadata["option_surface"] = "query"
        result["metadata"] = metadata
        return result

    def _select_case_matched_question_bank_rows(
        self,
        plans: list[dict[str, Any]],
        *,
        original_query: str,
        exact_probe: Any = None,
    ) -> list[dict[str, Any]]:
        query_surface = str(original_query or "").strip()
        if not query_surface and not exact_probe:
            return []

        query_shape = classify_query_shape(query_surface)
        if exact_probe is None and query_shape != "case_like":
            return []

        candidates: list[tuple[str, float, dict[str, Any]]] = []
        for plan in plans:
            if str(plan.get("group_name") or "") != "questions_bank":
                continue
            plan_query = str(plan.get("query") or "").strip()
            match_query = " ".join(item for item in [query_surface, plan_query] if item).strip()
            for item in plan.get("results") or []:
                row = dict(item or {})
                if str(row.get("_source_table") or "").strip() != "questions_bank":
                    continue
                if "case" not in str(row.get("question_type") or "").strip().lower():
                    continue
                if not row.get("correct_answer"):
                    continue
                source_type = str(row.get("source_type") or "").strip().lower()
                if source_type and "exam" not in source_type:
                    continue
                score = float(row.get("similarity") or row.get("score") or 0.0)
                if score < 0.70:
                    continue
                identity_surface = " ".join(
                    value
                    for value in [
                        str(row.get("background_context") or "").strip(),
                        str(row.get("stem") or row.get("question_stem") or "").strip(),
                    ]
                    if value
                )
                if not exact_question_identity_corresponds(
                    original_query=match_query,
                    matched_stem=identity_surface,
                    question_type=str(row.get("question_type") or ""),
                ):
                    continue
                row["_source_group"] = "question_bank_case_match"
                row["_query_phase"] = plan.get("phase") or "primary"
                row["_query_variant"] = plan_query or query_surface
                prompt_surface = str(row.get("stem") or row.get("question_stem") or row.get("card_title") or "")
                sub_items = extract_case_subquestion_items(prompt_surface, max_items=2)
                display_index = str((sub_items[0] if sub_items else {}).get("display_index") or "").strip()
                if display_index:
                    row["_display_index"] = display_index
                key = display_index or str(row.get("id") or row.get("chunk_id") or "")
                candidates.append((key, score, row))

        if not candidates:
            return []

        best_by_key: dict[str, tuple[float, dict[str, Any]]] = {}
        for key, score, row in candidates:
            existing = best_by_key.get(key)
            if existing is None or score >= existing[0]:
                best_by_key[key] = (score, row)

        return [
            row
            for _, row in sorted(
                best_by_key.values(),
                key=lambda item: (
                    int(str(item[1].get("_display_index") or "9999"))
                    if str(item[1].get("_display_index") or "").isdigit()
                    else 9999,
                    -item[0],
                ),
            )
        ]

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
                # Option overlap is a cheap pre-filter only; identity authority
                # for the promotion is the single adjudicator below. The bank
                # option values are passed as corroborating identity surface:
                # for an MCQ the identity surface is stem + options, so a short
                # stem with a typo but near-verbatim options still decides
                # honestly inside the same adjudicator.
                if not exact_question_identity_corresponds(
                    original_query=original_query,
                    matched_stem=_question_identity_surface(row),
                    question_type=row.get("question_type"),
                    matched_options=_option_values(options),
                ):
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
        if not isinstance(exact_question, dict):
            return exact_question
        if query_shape != "case_like":
            # 题型一致性 fail-closed(#23, 2026-06-23, DeepSeek-V4-Pro 异源核坐实):
            # case_study exact 命中代表"学生粘的就是这道题库案例题"。若学生 query 不是
            # 案例题(query_shape != case_like,如 mcq_like/standard_like——经 exact_probe
            # 文本相似度误命中一道案例 row),这不是同一道题:撤销命中(返回 None=无 exact
            # 命中,兜底走正常 RAG+LLM),否则 exact_authority 会把该案例题整段"标准作答"
            # (含别题背景数字如"中标价1.7亿")确定性拼给学生。非 case 命中(mcq/free_text
            # exact 无 covered_subquestions)不受影响,原样返回。
            is_case_hit = bool(exact_question.get("covered_subquestions")) or (
                str(exact_question.get("answer_kind") or "").strip().lower() == "case_study"
            )
            return None if is_case_hit else exact_question
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
        if exact_question["missing_subquestions"]:
            exact_question["coverage_state"] = (
                "single_subquestion_only"
                if len(covered_indexes) <= 1
                else "partial_multi_subquestion_exact"
            )
        else:
            exact_question["coverage_state"] = (
                "multi_subquestion_exact"
                if len(covered_indexes) > 1
                else "single_subquestion_only"
            )
        if isinstance(exact_question.get("case_bundle"), dict):
            exact_question["case_bundle"]["query_subquestions"] = query_items
            exact_question["case_bundle"]["missing_subquestions"] = exact_question["missing_subquestions"]
            exact_question["case_bundle"]["query_subquestion_count"] = len(query_items)
            exact_question["case_bundle"]["coverage_ratio"] = exact_question["coverage_ratio"]
            exact_question["case_bundle"]["coverage_state"] = exact_question["coverage_state"]
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

    async def _assert_data_api_available(
        self,
        *,
        client: httpx.AsyncClient,
        config: SupabaseSearchConfig,
    ) -> None:
        """Availability gate with stale-while-revalidate expiry (Battle2 S5-T3).

        The cached verdict is always served to the turn (available ⇒ pass,
        known-restricted 402 ⇒ fail-closed). When the entry is past TTL, a
        single-flight background task refreshes it — the user turn never waits
        on the ~0.3s probe again. Only a cold start (no cached state for this
        URL yet) probes inline, preserving the original first-query behavior.
        """
        # Some tests use lightweight client doubles that only exercise plan logic.
        if not hasattr(client, "get"):
            return
        cache_key = config.url.rstrip("/")
        now = time.monotonic()
        cached = _SUPABASE_AVAILABILITY_CACHE.get(cache_key)
        if cached is not None:
            is_available, checked_at = cached
            if now - checked_at >= _SUPABASE_AVAILABILITY_TTL_S:
                self._kick_availability_refresh(config)  # background, non-blocking
            if is_available:
                return
            raise RAGSearchError(
                "supabase retrieval failed: Supabase Data API service restricted (HTTP 402)",
                provider="supabase",
                stage="pipeline.data_api_healthcheck",
                retryable=False,
            )

        await self._probe_data_api(client=client, config=config)

    def _kick_availability_refresh(self, config: SupabaseSearchConfig) -> None:
        """Single-flight background availability refresh (SWR helper). Never
        blocks or fails the calling turn; the probe writes its verdict into
        _SUPABASE_AVAILABILITY_CACHE and a 402 raise is swallowed here (the
        refreshed False verdict fail-closes the NEXT turn instead)."""
        key = config.url.rstrip("/")
        existing = _SUPABASE_AVAILABILITY_REFRESH.get(key)
        if existing is not None and not existing.done():
            return

        async def _refresh() -> None:
            try:
                client = await self._get_client(config.timeout_s)
                await self._probe_data_api(client=client, config=config)
            except Exception:  # noqa: BLE001 — verdict already cached by the probe
                pass

        try:
            _SUPABASE_AVAILABILITY_REFRESH[key] = asyncio.create_task(
                _refresh(),
                name="supabase:availability-refresh",
                # Empty Context: the probe is not part of any turn's trace.
                context=contextvars.Context(),
            )
        except RuntimeError:
            # No running event loop — keep serving the cached verdict.
            pass

    async def _probe_data_api(
        self,
        *,
        client: httpx.AsyncClient,
        config: SupabaseSearchConfig,
    ) -> None:
        cache_key = config.url.rstrip("/")
        url = f"{cache_key}/rest/v1/kb_chunks"
        headers = {
            "apikey": config.service_key,
            "Authorization": f"Bearer {config.service_key}",
        }
        with observability.start_observation(
            name="supabase.data_api.health",
            as_type="retriever",
            input_payload={"table": "kb_chunks", "select": "chunk_id", "limit": 1},
            metadata={"table": "kb_chunks", "purpose": "availability_gate"},
        ) as observation:
            try:
                response = await client.get(
                    url,
                    headers=headers,
                    params={"select": "chunk_id", "limit": "1"},
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _SUPABASE_AVAILABILITY_CACHE[cache_key] = (False, time.monotonic())
                rag_error = _wrap_supabase_http_status(
                    exc,
                    stage="pipeline.data_api_healthcheck",
                )
                observability.update_observation(
                    observation,
                    level="ERROR",
                    status_message=str(rag_error),
                    metadata={
                        "table": "kb_chunks",
                        "purpose": "availability_gate",
                        "retryable": rag_error.retryable,
                    },
                )
                raise rag_error from exc
            _SUPABASE_AVAILABILITY_CACHE[cache_key] = (True, time.monotonic())
            observability.update_observation(
                observation,
                output_payload={"available": True},
                metadata={"table": "kb_chunks", "purpose": "availability_gate"},
            )

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        function_name: str,
        payload: dict[str, Any],
        *,
        timeout_s: float | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._base_url(payload).rstrip('/')}/rest/v1/rpc/{function_name}"
        headers = self._headers(payload)
        request_timeout = (
            timeout_s if (timeout_s is not None and timeout_s > 0) else httpx.USE_CLIENT_DEFAULT
        )
        with observability.start_observation(
            name=f"supabase.rpc.{function_name}",
            as_type="retriever",
            input_payload=payload,
            metadata={"function_name": function_name},
        ) as observation:
            response = await client.post(url, headers=headers, json=payload, timeout=request_timeout)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                rag_error = _wrap_supabase_http_status(exc, stage=f"pipeline.rpc.{function_name}")
                observability.update_observation(
                    observation,
                    metadata={
                        "function_name": function_name,
                        "retryable": rag_error.retryable,
                    },
                    level="ERROR",
                    status_message=str(rag_error),
                )
                raise rag_error from exc
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
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                rag_error = _wrap_supabase_http_status(exc, stage=f"pipeline.select.{table}")
                observability.update_observation(
                    observation,
                    metadata={"table": table, "retryable": rag_error.retryable},
                    level="ERROR",
                    status_message=str(rag_error),
                )
                raise rag_error from exc
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
