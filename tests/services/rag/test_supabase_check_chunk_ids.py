"""Unit tests for SupabasePipeline.check_chunk_ids_exist (T1, 1B preflight).

check_chunk_ids_exist is a read-only batch existence check over PostgREST
(kb_chunks, chunk_id in.(...)). It backs the RAG eval preflight that detects a
stale golden set after a KB reindex — the caller computes
`missing = requested - found`. No backend SQL function is added; it reuses the
existing _select read path (same pattern as _hydrate_sources).
"""
from __future__ import annotations

import httpx
import pytest

from deeptutor.services.rag.exceptions import RAGSearchError
from deeptutor.services.rag.pipelines.supabase import (
    SupabasePipeline,
    SupabaseSearchConfig,
)


def _config() -> SupabaseSearchConfig:
    return SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=["standard"],
        include_questions=True,
        top_k=3,
        fetch_count=6,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={"standard": 1.0},
        question_weights={"questions_bank": 1.0},
        max_per_document=2,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=False,
        second_pass_max_queries=0,
        second_pass_min_hits=0,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=False,
        rerank_window=3,
        rerank_timeout_s=2.0,
        exact_question_enabled=False,
        exact_question_text_first=False,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
    )


def _parse_in_filter(value: str) -> list[str]:
    """'in.("a","b")' -> ['a', 'b'] (mirrors the PostgREST filter we send)."""
    inner = value[len("in.(") : -1] if value.startswith("in.(") else value
    return [tok.strip().strip('"') for tok in inner.split(",") if tok.strip().strip('"')]


class _FakeClient:
    """Returns kb_chunks rows only for the ids it 'has'; records each batch."""

    def __init__(self, existing: set[str]) -> None:
        self._existing = existing
        self.batches: list[list[str]] = []

    async def get(self, url, *, headers=None, params: dict[str, str] | None = None):
        assert params is not None  # _select always passes the chunk_id filter
        requested = _parse_in_filter(str(params["chunk_id"]))
        self.batches.append(requested)
        rows = [{"chunk_id": cid} for cid in requested if cid in self._existing]
        request = httpx.Request("GET", url, headers=headers, params=params)
        return httpx.Response(200, json=rows, request=request)


def _wire(pipeline, monkeypatch, client, config=None) -> None:
    config = config or _config()
    monkeypatch.setattr(pipeline, "_load_search_config", lambda **kwargs: config)

    async def _fake_get_client(*_args, **_kwargs):
        return client

    monkeypatch.setattr(pipeline, "_get_client", _fake_get_client)


@pytest.mark.asyncio
async def test_returns_all_when_every_chunk_exists(monkeypatch):
    pipeline = SupabasePipeline()
    client = _FakeClient({"a", "b", "c"})
    _wire(pipeline, monkeypatch, client)

    found = await pipeline.check_chunk_ids_exist(["a", "b", "c"], "construction-exam")

    assert found == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_returns_only_existing_subset_for_stale_golden_set(monkeypatch):
    pipeline = SupabasePipeline()
    client = _FakeClient({"a", "c"})  # "b" was dropped by a KB reindex
    _wire(pipeline, monkeypatch, client)

    found = await pipeline.check_chunk_ids_exist(["a", "b", "c"], "construction-exam")

    assert found == {"a", "c"}  # caller derives missing = {"a","b","c"} - found = {"b"}


@pytest.mark.asyncio
async def test_empty_input_makes_no_request(monkeypatch):
    pipeline = SupabasePipeline()
    client = _FakeClient(set())
    _wire(pipeline, monkeypatch, client)

    found = await pipeline.check_chunk_ids_exist([], "construction-exam")

    assert found == set()
    assert client.batches == []  # no network call for empty input


@pytest.mark.asyncio
async def test_deduplicates_and_strips_blank_ids(monkeypatch):
    pipeline = SupabasePipeline()
    client = _FakeClient({"a", "b"})
    _wire(pipeline, monkeypatch, client)

    found = await pipeline.check_chunk_ids_exist(
        ["a", " a ", "", "  ", "b", "a"], "construction-exam"
    )

    assert found == {"a", "b"}
    assert sorted(client.batches[0]) == ["a", "b"]  # only unique non-blank ids queried


@pytest.mark.asyncio
async def test_batches_large_id_sets_and_merges_results(monkeypatch):
    pipeline = SupabasePipeline()
    ids = [f"chunk-{i}" for i in range(120)]
    existing = set(ids) - {"chunk-7", "chunk-99"}  # two missing after reindex
    client = _FakeClient(existing)
    _wire(pipeline, monkeypatch, client)

    found = await pipeline.check_chunk_ids_exist(ids, "construction-exam")

    assert found == existing
    assert len(client.batches) >= 2  # split into multiple GETs to bound URL length
    queried = [cid for batch in client.batches for cid in batch]
    assert sorted(queried) == sorted(ids)  # every id queried exactly once


@pytest.mark.asyncio
async def test_supabase_error_propagates_as_rag_error(monkeypatch):
    """Errors must NOT be swallowed — preflight needs them to skip (infra), not
    silently report a 'stale' golden set."""
    pipeline = SupabasePipeline()

    class _FailingClient:
        async def get(self, url, *, headers=None, params=None):
            request = httpx.Request("GET", url, headers=headers, params=params)
            return httpx.Response(500, json={"message": "boom"}, request=request)

    _wire(pipeline, monkeypatch, _FailingClient())

    with pytest.raises(RAGSearchError):
        await pipeline.check_chunk_ids_exist(["a"], "construction-exam")
