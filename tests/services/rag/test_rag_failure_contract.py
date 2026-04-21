"""RAG failure contract tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_rag_service_wraps_pipeline_failure_as_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.exceptions import RAGSearchError
    from deeptutor.services.rag import service as rag_service_module

    class _BrokenPipeline:
        async def search(self, **kwargs):
            _ = kwargs
            raise RuntimeError("vector backend exploded")

    monkeypatch.setattr(rag_service_module, "get_pipeline", lambda *args, **kwargs: _BrokenPipeline())
    monkeypatch.setattr(
        rag_service_module.RAGService,
        "_get_provider_for_kb",
        lambda self, kb_name: "supabase",
    )

    service = rag_service_module.RAGService(provider="supabase")

    with pytest.raises(RAGSearchError) as exc_info:
        await service.search(query="防水等级", kb_name="construction-exam")

    err = exc_info.value
    assert err.provider == "supabase"
    assert err.kb_name == "construction-exam"
    assert err.query == "防水等级"
    assert err.stage == "service.search"
    assert "vector backend exploded" in str(err)


@pytest.mark.asyncio
async def test_rag_tool_preserves_typed_rag_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.exceptions import RAGSearchError
    import deeptutor.tools.rag_tool as rag_tool_module

    typed_error = RAGSearchError(
        "Supabase retrieval failed: timeout",
        provider="supabase",
        kb_name="construction-exam",
        query="防水等级",
        stage="pipeline.search",
        retryable=True,
    )

    async def _raise_typed_error(*args, **kwargs):
        _ = (args, kwargs)
        raise typed_error

    monkeypatch.setattr(rag_tool_module.RAGService, "search", _raise_typed_error)

    with pytest.raises(RAGSearchError) as exc_info:
        await rag_tool_module.rag_search(query="防水等级", kb_name="construction-exam")

    assert exc_info.value is typed_error


@pytest.mark.asyncio
async def test_supabase_search_raises_typed_error_on_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.exceptions import RAGSearchError
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=["textbook"],
        include_questions=False,
        top_k=3,
        fetch_count=6,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={"textbook": 1.0},
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

    monkeypatch.setattr(pipeline, "_load_search_config", lambda **kwargs: config)
    async def _fake_get_client(*args, **kwargs):
        _ = (args, kwargs)
        return object()

    monkeypatch.setattr(pipeline, "_get_client", _fake_get_client)
    monkeypatch.setattr(
        supabase_module,
        "rewrite_query",
        lambda query, max_variants=1: SimpleNamespace(
            primary_query=query,
            query_shape="concept_like",
            standard_codes=[],
            keywords=[],
            reasons=[],
        ),
    )
    monkeypatch.setattr(supabase_module, "is_question_like_query", lambda query: False)
    monkeypatch.setattr(
        supabase_module,
        "select_sources",
        lambda *args, **kwargs: SimpleNamespace(
            search_textbook_chunks=True,
            search_standard_chunks=False,
            search_exam_chunks=False,
            search_questions_bank=False,
            to_trace_dict=lambda: {},
            selection_reasons=[],
        ),
    )
    monkeypatch.setattr(supabase_module, "classify_query_shape", lambda query: "concept_like")
    monkeypatch.setattr(supabase_module, "expand_query_variants", lambda query, max_variants=1: [query])
    monkeypatch.setattr(pipeline, "_run_query_plan", _raise_runtime_error)

    with pytest.raises(RAGSearchError) as exc_info:
        await pipeline.search(query="防水等级", kb_name="construction-exam")

    err = exc_info.value
    assert err.provider == "supabase"
    assert err.kb_name == "construction-exam"
    assert err.query == "防水等级"
    assert err.stage == "pipeline.search"
    assert "primary plan exploded" in str(err)


async def _raise_runtime_error(*args, **kwargs):
    _ = (args, kwargs)
    raise RuntimeError("primary plan exploded")


@pytest.mark.asyncio
async def test_supabase_run_query_plan_collects_partial_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=["textbook"],
        include_questions=False,
        top_k=3,
        fetch_count=6,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={"textbook": 1.0},
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

    async def _embed_query(query: str) -> list[float]:
        _ = query
        return [0.1, 0.2]

    async def _broken_source(**kwargs):
        _ = kwargs
        raise RuntimeError("textbook source timeout")

    monkeypatch.setattr(pipeline, "_embed_query", _embed_query)
    monkeypatch.setattr(pipeline, "_search_source", _broken_source)

    warnings: list[dict[str, object]] = []
    plans = await pipeline._run_query_plan(
        client=object(),
        queries=["防水等级"],
        question_like=False,
        source_plan=SimpleNamespace(
            search_textbook_chunks=True,
            search_standard_chunks=False,
            search_exam_chunks=False,
            search_questions_bank=False,
        ),
        standard_codes=[],
        precision_node_code=None,
        exact_probe=None,
        original_query="防水等级",
        config=config,
        failure_sink=warnings,
    )

    assert plans == []
    assert warnings == [
        {
            "phase": "primary",
            "group_name": "textbook",
            "query": "防水等级",
            "message": "textbook source timeout",
        }
    ]
