"""Battle2 S5-T6: optional char cap on the documents SENT to the reranker.

Default 0 = disabled = byte-for-byte the old behavior (gray-release by env
only). When enabled, only the rerank INPUT is truncated — the candidate items
and everything returned/displayed keep the full rag_content (the index
mapping re-attaches the original item).
"""

from __future__ import annotations

import pytest

from deeptutor.services.rag.pipelines import supabase as supabase_module


def _config(**overrides):
    values = dict(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=["standard"],
        include_questions=True,
        top_k=2,
        fetch_count=12,
        match_threshold=0.35,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={},
        question_weights={},
        max_per_document=2,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=False,
        second_pass_max_queries=1,
        second_pass_min_hits=1,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=True,
        rerank_window=12,
        rerank_timeout_s=2.0,
        exact_question_enabled=False,
        exact_question_text_first=False,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
    )
    values.update(overrides)
    return supabase_module.SupabaseSearchConfig(**values)


def _results():
    return [
        {"chunk_id": f"chunk-{index}", "rag_content": f"内容{index}-" + ("长" * 400), "score": 0.5}
        for index in range(4)
    ]


class _RerankSpy:
    def __init__(self, returned=None):
        self.calls: list[dict] = []
        self._returned = returned if returned is not None else [
            {"index": 1, "relevance_score": 0.99},
            {"index": 0, "relevance_score": 0.55},
        ]

    async def __call__(self, query, docs, *, top_n, timeout_s):
        self.calls.append({"query": query, "docs": list(docs), "top_n": top_n})
        return self._returned


@pytest.mark.asyncio
async def test_cap_truncates_sent_docs_but_not_returned_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_RAG_RERANK_DOC_CHAR_CAP", "100")
    spy = _RerankSpy()
    monkeypatch.setattr(supabase_module, "rerank_documents", spy)
    pipeline = supabase_module.SupabasePipeline()
    results = _results()

    reranked = await pipeline._rerank_results(query="q", results=results, config=_config())

    assert len(spy.calls) == 1
    sent_docs = spy.calls[0]["docs"]
    assert all(len(doc) <= 100 for doc in sent_docs)
    original_docs = [str(item["rag_content"]).strip() for item in results]
    assert sent_docs == [doc[:100] for doc in original_docs]
    # Returned items keep the FULL original content.
    assert reranked[0]["chunk_id"] == "chunk-1"
    assert reranked[0]["rag_content"] == results[1]["rag_content"]
    assert all(len(item["rag_content"]) > 100 for item in reranked)


@pytest.mark.asyncio
async def test_default_cap_zero_sends_full_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_RAG_RERANK_DOC_CHAR_CAP", raising=False)
    spy = _RerankSpy()
    monkeypatch.setattr(supabase_module, "rerank_documents", spy)
    pipeline = supabase_module.SupabasePipeline()
    results = _results()

    await pipeline._rerank_results(query="q", results=results, config=_config())

    # Byte-for-byte the old rerank input.
    assert spy.calls[0]["docs"] == [str(item["rag_content"]).strip() for item in results]


@pytest.mark.asyncio
async def test_out_of_range_rerank_indices_keep_existing_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_RAG_RERANK_DOC_CHAR_CAP", "100")
    spy = _RerankSpy(
        returned=[
            {"index": 99, "relevance_score": 0.9},  # out of range → ignored
            {"index": 2, "relevance_score": 0.8},
        ]
    )
    monkeypatch.setattr(supabase_module, "rerank_documents", spy)
    pipeline = supabase_module.SupabasePipeline()
    results = _results()

    reranked = await pipeline._rerank_results(query="q", results=results, config=_config())

    # Only the valid index is promoted; the rest keep their original order.
    assert [item["chunk_id"] for item in reranked] == [
        "chunk-2",
        "chunk-0",
        "chunk-1",
        "chunk-3",
    ]
    assert reranked[0]["rerank_score"] == 0.8
