"""RAG provider registry and tool integration tests."""

from __future__ import annotations

import json
import math
import os
import sys
from types import SimpleNamespace
import asyncio

import httpx
import pytest


@pytest.fixture(autouse=True)
def _clear_supabase_availability_cache():
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    supabase_module._SUPABASE_AVAILABILITY_CACHE.clear()
    yield
    supabase_module._SUPABASE_AVAILABILITY_CACHE.clear()


def _disable_supabase_availability_gate(
    monkeypatch: pytest.MonkeyPatch,
    pipeline,
) -> None:
    async def _available(**kwargs):
        _ = kwargs

    monkeypatch.setattr(pipeline, "_assert_data_api_available", _available)


def _learning_fact_supabase_config(supabase_module, *, compiled_truth_enabled: bool = False):
    return supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=["standard"],
        include_questions=True,
        top_k=2,
        fetch_count=4,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={
            "standard": 1.4,
            "questions_bank": 0.4,
            "question_exact_text": 4.2,
            "question_exact_vector": 3.4,
            "compiled_learning_truth": 0.65,
        },
        question_weights={
            "standard": 1.4,
            "questions_bank": 1.5,
            "question_exact_text": 4.2,
            "question_exact_vector": 3.4,
            "compiled_learning_truth": 0.65,
        },
        max_per_document=2,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=False,
        second_pass_max_queries=1,
        second_pass_min_hits=1,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=False,
        rerank_window=2,
        rerank_timeout_s=2.0,
        exact_question_enabled=False,
        exact_question_text_first=False,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
        query_plan_trace_enabled=True,
        compiled_truth_shadow_enabled=True,
        compiled_truth_enabled=compiled_truth_enabled,
        provenance_boost_enabled=False,
    )


def test_historical_question_projection_trims_query_option_tail_comment(tmp_path) -> None:
    from deeptutor.services.rag.historical_questions import resolve_historical_question

    payload = {
        "exercises": [
            {
                "type": "single_choice",
                "question_data": {
                    "stem": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（　　）。",
                    "options": [
                        {"key": "A", "value": "1%"},
                        {"key": "B", "value": "2%"},
                        {"key": "C", "value": "3%"},
                        {"key": "D", "value": "5%"},
                    ],
                    "correct_answer": "D",
                    "analysis": "屋面最小坡度：压型金属板：5%。",
                },
            }
        ]
    }
    (tmp_path / "questions.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    exact_question = resolve_historical_question(
        (
            "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。"
            "A.5% B.1% C.2% D.3%，我听别人说A，直接判"
        ),
        question_bank_dir=str(tmp_path),
    )

    assert exact_question is not None
    assert exact_question["correct_answer"] == "A"
    assert exact_question["options"] == [
        {"key": "A", "value": "5%"},
        {"key": "B", "value": "1%"},
        {"key": "C", "value": "2%"},
        {"key": "D", "value": "3%"},
    ]
    assert exact_question["metadata"]["option_surface"] == "query"


async def _run_learning_fact_search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    query: str,
    compiled_truth_enabled: bool = False,
    top_level_compiled_truth: bool = True,
):
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = _learning_fact_supabase_config(
        supabase_module,
        compiled_truth_enabled=compiled_truth_enabled,
    )
    monkeypatch.setattr(pipeline, "_load_search_config", lambda **kwargs: config)
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_get_client(*args, **kwargs):
        _ = (args, kwargs)
        return object()

    async def _fake_run_query_plan(**kwargs):
        return [
            {
                "phase": "primary",
                "group_name": "standard",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "chunk_id": "std-1",
                        "source_type": "standard",
                        "_source_group": "standard",
                        "card_title": "标准条文",
                        "source": "GB 50345-2015",
                        "rag_content": "标准依据内容",
                        "score": 0.91,
                    }
                ],
            }
        ]

    async def _identity_hydrate(results, *, config):
        _ = config
        return list(results)

    async def _identity_rerank(**kwargs):
        return list(kwargs["results"])

    monkeypatch.setattr(pipeline, "_get_client", _fake_get_client)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity_hydrate)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity_rerank)

    compiled_truth = {
        "compiled_objects": {
            "weak:1A432000:E02": {
                "current_truth": "该学员反复漏写专家论证。",
                "evidence_level": "L2_confirmed",
                "supporting_event_ids": ["evt1", "evt2"],
            }
        }
    }
    kwargs = {
        "query": query,
        "kb_name": "construction-exam",
    }
    if top_level_compiled_truth:
        kwargs["compiled_learning_truth"] = compiled_truth
    else:
        kwargs["routing_metadata"] = {
            "compiled_learning_truth_available": True,
            "compiled_learning_truth": compiled_truth,
        }

    return await pipeline.search(**kwargs)


async def _run_learning_fact_search_with_hooks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    query: str,
    second_pass_enabled: bool = True,
    rerank_enabled: bool = True,
):
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = _learning_fact_supabase_config(
        supabase_module,
        compiled_truth_enabled=True,
    )
    config.second_pass_enabled = second_pass_enabled
    config.rerank_enabled = rerank_enabled
    config.query_expansion_enabled = True
    config.max_query_variants = 4
    monkeypatch.setattr(pipeline, "_load_search_config", lambda **kwargs: config)
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    calls = {"query_plans": [], "rerank": 0}

    async def _fake_get_client(*args, **kwargs):
        _ = (args, kwargs)
        return object()

    async def _fake_run_query_plan(**kwargs):
        calls["query_plans"].append(
            {
                "phase": kwargs.get("phase", "primary"),
                "queries": list(kwargs["queries"]),
            }
        )
        return [
            {
                "phase": kwargs.get("phase", "primary"),
                "group_name": "standard",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "chunk_id": f"std-{kwargs.get('phase', 'primary')}",
                        "source_type": "standard",
                        "_source_group": "standard",
                        "card_title": "标准条文",
                        "rag_content": "标准依据内容",
                        "score": 0.91,
                    }
                ],
            }
        ]

    async def _identity_hydrate(results, *, config):
        _ = config
        return list(results)

    async def _counting_rerank(**kwargs):
        calls["rerank"] += 1
        return list(kwargs["results"])

    monkeypatch.setattr(pipeline, "_get_client", _fake_get_client)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity_hydrate)
    monkeypatch.setattr(pipeline, "_rerank_results", _counting_rerank)

    result = await pipeline.search(
        query=query,
        kb_name="construction-exam",
        compiled_learning_truth={
            "compiled_objects": {
                "weak:1A432000:E02": {
                    "current_truth": "该学员反复漏写专家论证。",
                    "evidence_level": "L2_confirmed",
                    "supporting_event_ids": ["evt1", "evt2"],
                }
            }
        },
    )
    return result, calls


def test_list_available_providers() -> None:
    """Provider list should expose local and Supabase retrieval backends."""
    from deeptutor.tools.rag_tool import get_available_providers

    providers = get_available_providers()
    assert [p["id"] for p in providers] == ["llamaindex", "supabase", "kbv5"]


def test_factory_has_pipeline() -> None:
    """Factory should report supported providers only."""
    from deeptutor.services.rag.factory import has_pipeline

    assert has_pipeline("llamaindex") is True
    assert has_pipeline("supabase") is True
    assert has_pipeline("lightrag") is False
    assert has_pipeline("raganything") is False
    assert has_pipeline("nonexistent") is False


def test_normalize_legacy_provider_aliases() -> None:
    """Legacy provider names should normalize to llamaindex."""
    from deeptutor.services.rag.factory import normalize_provider_name

    assert normalize_provider_name("llamaindex") == "llamaindex"
    assert normalize_provider_name("lightrag") == "llamaindex"
    assert normalize_provider_name("raganything") == "llamaindex"
    assert normalize_provider_name("raganything_docling") == "llamaindex"


def test_get_current_provider_normalizes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Current provider should normalize legacy env values."""
    from deeptutor.tools.rag_tool import get_current_provider

    monkeypatch.setenv("RAG_PROVIDER", "lightrag")
    assert get_current_provider() == "llamaindex"

    monkeypatch.setenv("RAG_PROVIDER", "llamaindex")
    assert get_current_provider() == "llamaindex"

    monkeypatch.delenv("RAG_PROVIDER", raising=False)
    assert get_current_provider() == "llamaindex"


def test_get_pipeline_llamaindex_interface() -> None:
    """LlamaIndex pipeline should be constructible with optional dependency installed."""
    from deeptutor.services.rag.factory import get_pipeline

    try:
        pipeline = get_pipeline("llamaindex")
    except ValueError as exc:
        pytest.skip(f"LlamaIndex optional dependency missing: {exc}")

    assert hasattr(pipeline, "initialize")
    assert hasattr(pipeline, "search")
    assert hasattr(pipeline, "delete")


@pytest.mark.asyncio
async def test_query_plan_trace_only_does_not_change_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run_learning_fact_search(
        monkeypatch,
        query="我老是案例题采分点漏写怎么办",
        compiled_truth_enabled=False,
    )

    assert [item["chunk_id"] for item in result["sources"]] == ["std-1"]
    evidence = result["evidence_bundle"]
    assert evidence["retrieval_plan"]["intent"] == "weak_point_review"
    assert evidence["ranking_trace"]["ranking_policy"]["compiled_truth_final_enabled"] is False


@pytest.mark.asyncio
async def test_supabase_search_uses_single_canonical_retriever_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    class _FakeObservation:
        pass

    class _FakeObservability:
        def __init__(self) -> None:
            self.started: list[dict[str, object]] = []
            self.updated: list[dict[str, object]] = []

        class _Context:
            def __init__(self, outer: "_FakeObservability", kwargs: dict[str, object]) -> None:
                self._outer = outer
                self._kwargs = kwargs

            def __enter__(self) -> _FakeObservation:
                self._outer.started.append(self._kwargs)
                return _FakeObservation()

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        def start_observation(self, **kwargs):
            return self._Context(self, kwargs)

        def update_observation(self, observation, **kwargs) -> None:
            _ = observation
            self.updated.append(kwargs)

    fake_observability = _FakeObservability()
    monkeypatch.setattr(supabase_module, "observability", fake_observability)

    await _run_learning_fact_search(
        monkeypatch,
        query="我老是案例题采分点漏写怎么办",
        compiled_truth_enabled=False,
    )

    search_observations = [
        item for item in fake_observability.started
        if item.get("name") == "rag.supabase.search"
    ]
    assert len(search_observations) == 1
    assert search_observations[0]["as_type"] == "retriever"
    assert search_observations[0]["metadata"].get("trace_observation_role") is None
    assert all(
        (item.get("metadata") or {}).get("trace_observation_role") != "retrieval_ranking_trace"
        for item in fake_observability.started
    )
    update = fake_observability.updated[-1]
    assert update["output_payload"]["source_count"] == 1
    assert update["metadata"]["retrieval_plan_intent"] == "weak_point_review"
    assert update["metadata"]["retrieval_plan_json"]
    assert update["metadata"]["ranking_trace_json"]
    assert update["metadata"]["ranking_trace_fusion"] == "weighted_rrf_with_provenance"


@pytest.mark.asyncio
async def test_compiled_truth_shadow_not_returned_in_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run_learning_fact_search(
        monkeypatch,
        query="我老是案例题采分点漏写怎么办",
        compiled_truth_enabled=False,
    )

    assert all(item["source_type"] != "compiled_learning_truth" for item in result["sources"])
    trace = result["evidence_bundle"]["ranking_trace"]
    assert trace["shadow_source_count"] == 1
    assert trace["shadow_sources"][0]["source_group"] == "compiled_learning_truth"


@pytest.mark.asyncio
async def test_routing_metadata_compiled_truth_payload_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run_learning_fact_search(
        monkeypatch,
        query="我老是案例题采分点漏写怎么办",
        compiled_truth_enabled=True,
        top_level_compiled_truth=False,
    )

    assert all(item["source_type"] != "compiled_learning_truth" for item in result["sources"])
    trace = result["evidence_bundle"]["ranking_trace"]
    assert trace["shadow_source_count"] == 0
    assert trace["ranking_policy"]["compiled_truth_final_enabled"] is False


@pytest.mark.asyncio
async def test_standard_clause_not_personalized_as_compiled_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run_learning_fact_search(
        monkeypatch,
        query="GB 50345-2015 第3.0.1条对屋面防水等级怎么规定",
        compiled_truth_enabled=True,
    )

    source_groups = {
        item["name"]: item["enabled"]
        for item in result["evidence_bundle"]["retrieval_plan"]["source_groups"]
    }
    assert source_groups["compiled_learning_truth"] is False
    assert [item["chunk_id"] for item in result["sources"]] == ["std-1"]
    assert result["evidence_bundle"]["ranking_trace"]["shadow_source_count"] == 0


@pytest.mark.asyncio
async def test_compiled_truth_final_enablement_is_weak_point_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run_learning_fact_search(
        monkeypatch,
        query="我老是案例题采分点漏写怎么办",
        compiled_truth_enabled=True,
    )

    source_types = [item["source_type"] for item in result["sources"]]
    assert "compiled_learning_truth" in source_types
    assert result["evidence_bundle"]["ranking_trace"]["ranking_policy"]["compiled_truth_final_enabled"] is True


@pytest.mark.asyncio
async def test_learning_fact_search_records_stage_timings_and_skips_heavy_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, calls = await _run_learning_fact_search_with_hooks(
        monkeypatch,
        query="根据我的薄弱点安排下一道训练题，不要讲通用知识。",
    )

    timings = result["evidence_bundle"]["stage_timings_ms"]
    assert timings["total"] >= 0
    assert "primary_plan" in timings
    assert result["evidence_bundle"]["performance_policy"] == {
        "intent_fast_path": True,
        "compiled_only_fast_path": True,
        "rerank_enabled": False,
        "second_pass_enabled": False,
        "primary_query_count": 0,
    }
    assert calls["query_plans"] == []
    assert calls["rerank"] == 0


def test_compiled_truth_final_presence_appends_after_authoritative_sources() -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    final = pipeline._ensure_final_compiled_truth_presence(
        [
            {"chunk_id": "std-1", "source_type": "standard", "score": 0.9},
            {"chunk_id": "textbook-1", "source_type": "textbook", "score": 0.7},
        ],
        plans=[
            {
                "group_name": "compiled_learning_truth",
                "results": [
                    {
                        "chunk_id": "compiled-truth:weak-point:1A432000:E02",
                        "source_type": "compiled_learning_truth",
                        "rag_content": "学员反复漏写专家论证。",
                    }
                ],
            }
        ],
        max_items=3,
    )

    assert [item["chunk_id"] for item in final] == [
        "std-1",
        "textbook-1",
        "compiled-truth:weak-point:1A432000:E02",
    ]


@pytest.mark.asyncio
async def test_run_query_plan_bounds_query_variant_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = _learning_fact_supabase_config(supabase_module)
    config.sources = ["standard"]
    config.query_variant_concurrency = 2

    active = 0
    max_active = 0

    async def _fake_embed_query(query: str):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return [0.1, 0.2, 0.3]

    async def _fake_search_source(**kwargs):
        return [
            {
                "chunk_id": f"std-{kwargs['query']}",
                "source_type": kwargs["source_type"],
                "rag_content": kwargs["query"],
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(pipeline, "_embed_query", _fake_embed_query)
    monkeypatch.setattr(pipeline, "_search_source", _fake_search_source)

    plans = await pipeline._run_query_plan(
        client=object(),
        queries=["q1", "q2", "q3", "q4"],
        question_like=False,
        source_plan=SimpleNamespace(
            search_textbook_chunks=False,
            search_standard_chunks=True,
            search_exam_chunks=False,
            search_questions_bank=False,
        ),
        standard_codes=[],
        precision_node_code=None,
        exact_probe=None,
        original_query="q",
        config=config,
    )

    assert max_active == 2
    assert [plan["query"] for plan in plans] == ["q1", "q2", "q3", "q4"]


def test_get_pipeline_invalid_raises() -> None:
    """Unknown provider names should raise explicit error."""
    from deeptutor.services.rag.factory import get_pipeline

    with pytest.raises(ValueError, match="Unknown pipeline"):
        get_pipeline("nonexistent")


@pytest.mark.asyncio
async def test_llamaindex_search_rejects_invalid_persisted_embeddings(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines import llamaindex as llamaindex_module
    from deeptutor.services.rag.exceptions import RAGSearchError

    storage_dir = tmp_path / "demo" / "llamaindex_storage"
    storage_dir.mkdir(parents=True)
    (storage_dir / "docstore.json").write_text("{}", encoding="utf-8")

    class _RetrieverShouldNotRun:
        def retrieve(self, _query: str):  # pragma: no cover - assertion helper
            raise AssertionError("retriever should not run for invalid vectors")

    fake_index = SimpleNamespace(
        vector_store=SimpleNamespace(
            data=SimpleNamespace(embedding_dict={"bad-node": [0.1, math.nan, 0.3]})
        ),
        as_retriever=lambda similarity_top_k=5: _RetrieverShouldNotRun(),
    )

    monkeypatch.setattr(
        llamaindex_module.StorageContext,
        "from_defaults",
        lambda persist_dir: object(),
    )
    monkeypatch.setattr(llamaindex_module, "load_index_from_storage", lambda _ctx: fake_index)
    monkeypatch.setattr(
        llamaindex_module,
        "get_embedding_config",
        lambda: SimpleNamespace(model="test-embed", dim=3, binding="test"),
    )
    monkeypatch.setattr(
        llamaindex_module,
        "get_embedding_client",
        lambda: SimpleNamespace(config=SimpleNamespace(binding="test", model="test-embed")),
    )

    pipeline = llamaindex_module.LlamaIndexPipeline(kb_base_dir=str(tmp_path))
    with pytest.raises(RAGSearchError) as exc_info:
        await pipeline.search(query="what is this?", kb_name="demo")

    assert "invalid embedding vectors" in str(exc_info.value)
    assert exc_info.value.stage == "pipeline.search"


@pytest.mark.asyncio
async def test_builtin_rag_tool_emits_summary_metadata_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.tools.builtin import RAGTool
    import deeptutor.tools.rag_tool as rag_tool_module

    async def _fake_rag_search(**kwargs):
        assert kwargs["query"] == "防水等级"
        return {
            "query": "防水等级",
            "provider": "supabase",
            "kb_name": "construction-exam",
            "sources": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
            "exact_question": {"id": "q1"},
            "evidence_bundle": {
                "bundle_id": "bundle-1",
                "kb_name": "construction-exam",
                "provider": "supabase",
                "query_shape": "concept_like",
                "retrieval_empty": False,
                "content_blocks": ["A", "B", "C"],
                "sources": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
                "exact_question": {"id": "q1"},
            },
            "answer": "答案",
        }

    monkeypatch.setattr(rag_tool_module, "rag_search", _fake_rag_search)

    tool = RAGTool()
    result = await tool.execute(query="防水等级", kb_name="construction-exam")

    assert result.content == "答案"
    assert result.metadata["tool_source_count"] == 2
    assert result.metadata["evidence_bundle_summary"] == {
        "bundle_id": "bundle-1",
        "kb_name": "construction-exam",
        "provider": "supabase",
        "query_shape": "concept_like",
        "retrieval_empty": False,
        "source_count": 2,
        "content_block_count": 3,
        "exact_question": True,
    }
    assert "evidence_bundle" not in result.metadata


@pytest.mark.asyncio
async def test_builtin_rag_tool_rejects_empty_query_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.tools.builtin import RAGTool
    import deeptutor.tools.rag_tool as rag_tool_module

    called = False

    async def _unexpected_rag_search(**_kwargs):
        nonlocal called
        called = True
        return {"answer": "should not run"}

    monkeypatch.setattr(rag_tool_module, "rag_search", _unexpected_rag_search)

    with pytest.raises(ValueError, match="non-empty"):
        await RAGTool().execute(query="   ", kb_name="construction-exam")

    assert called is False


@pytest.mark.asyncio
async def test_rag_search_rejects_empty_query_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag import service as rag_service_module
    from deeptutor.tools.rag_tool import rag_search

    called = False

    async def _unexpected_search(self, **_kwargs):
        nonlocal called
        called = True
        return {"answer": "should not run"}

    monkeypatch.setattr(rag_service_module.RAGService, "search", _unexpected_search)

    with pytest.raises(ValueError, match="non-empty"):
        await rag_search(query="\n\t", kb_name="construction-exam")

    assert called is False


@pytest.mark.asyncio
async def test_builtin_rag_tool_degrades_typed_retrieval_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.exceptions import RAGSearchError
    from deeptutor.tools.builtin import RAGTool
    import deeptutor.tools.rag_tool as rag_tool_module

    async def _broken_rag_search(**_kwargs):
        raise RAGSearchError(
            "Supabase retrieval failed: timeout detail",
            provider="supabase",
            kb_name="construction-exam",
            query="防水等级",
            stage="pipeline.search",
            retryable=True,
        )

    events: list[tuple[str, str, dict[str, object]]] = []

    async def _event_sink(event_type: str, content: str, metadata=None):
        events.append((event_type, content, dict(metadata or {})))

    monkeypatch.setattr(rag_tool_module, "rag_search", _broken_rag_search)

    result = await RAGTool().execute(
        query="防水等级",
        kb_name="construction-exam",
        event_sink=_event_sink,
    )

    assert result.success is False
    assert "timeout detail" not in result.content
    assert result.metadata["retrieval_degraded"] is True
    assert result.metadata["retrieval_status"] == "failed"
    assert result.metadata["provider"] == "supabase"
    assert result.metadata["kb_name"] == "construction-exam"
    assert result.metadata["stage"] == "pipeline.search"
    assert result.metadata["retryable"] is True
    assert events[-1][0] == "status"
    assert events[-1][2]["retrieval_degraded"] is True


@pytest.mark.asyncio
async def test_supabase_search_fail_closes_on_data_api_402_before_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.exceptions import RAGSearchError
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",
        timeout_s=5.0,
        sources=["textbook", "standard"],
        include_questions=True,
        top_k=3,
        fetch_count=6,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={"textbook": 1.0, "standard": 1.0},
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

    class _RestrictedClient:
        calls = 0

        async def get(self, url, *, headers=None, params=None):
            self.calls += 1
            request = httpx.Request("GET", url, headers=headers, params=params)
            return httpx.Response(
                402,
                json={"code": "exceeded_db_size_quota"},
                request=request,
            )

    client = _RestrictedClient()
    supabase_module._SUPABASE_AVAILABILITY_CACHE.clear()
    monkeypatch.setattr(pipeline, "_load_search_config", lambda **kwargs: config)

    async def _fake_get_client(*_args, **_kwargs):
        return client

    monkeypatch.setattr(pipeline, "_get_client", _fake_get_client)

    async def _unexpected_query_plan(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("query fanout should not run after a project-level 402")

    monkeypatch.setattr(pipeline, "_run_query_plan", _unexpected_query_plan)

    with pytest.raises(RAGSearchError) as exc_info:
        await pipeline.search(query="防水等级", kb_name="construction-exam")

    err = exc_info.value
    assert err.provider == "supabase"
    assert err.stage == "pipeline.data_api_healthcheck"
    assert err.retryable is False
    assert "HTTP 402" in str(err)
    assert "exceeded_db_size_quota" in str(err)
    assert "example.supabase.co" not in str(err)
    assert client.calls == 1


@pytest.mark.asyncio
async def test_supabase_run_query_plan_propagates_project_level_402(
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

    async def _embed_query(query: str) -> list[float]:
        _ = query
        return [0.1, 0.2]

    async def _restricted_source(**kwargs):
        _ = kwargs
        raise RAGSearchError(
            "supabase retrieval failed: Supabase Data API service restricted (HTTP 402)",
            provider="supabase",
            stage="pipeline.rpc.search_unified",
            retryable=False,
        )

    monkeypatch.setattr(pipeline, "_embed_query", _embed_query)
    monkeypatch.setattr(pipeline, "_search_source", _restricted_source)

    with pytest.raises(RAGSearchError) as exc_info:
        await pipeline._run_query_plan(
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
        )

    assert exc_info.value.stage == "pipeline.rpc.search_unified"


@pytest.mark.asyncio
async def test_rag_search_invalid_provider_falls_back_to_kb_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool wrapper should defer to KB-resolved provider (llamaindex-only runtime)."""
    from deeptutor.services.rag import service as rag_service_module
    from deeptutor.tools.rag_tool import rag_search

    class _FakePipeline:
        async def search(self, **kwargs):
            return {
                "query": kwargs["query"],
                "answer": "ok",
                "content": "ok",
                "provider": "llamaindex",
            }

    monkeypatch.setattr(
        rag_service_module.RAGService,
        "_get_provider_for_kb",
        lambda self, kb_name: "llamaindex",
    )
    monkeypatch.setattr(rag_service_module, "get_pipeline", lambda *args, **kwargs: _FakePipeline())

    result = await rag_search(
        query="hello",
        kb_name="demo",
        provider="nonexistent",
        kb_base_dir=os.getcwd(),
    )
    assert result["provider"] == "llamaindex"


@pytest.mark.asyncio
async def test_supabase_search_prioritizes_parallel_exact_question_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)
    full_exact_stem = "确定屋面防水工程的防水等级应根据什么，且不得被 card_title 截断"

    async def _fake_search_exact_question_text(**kwargs):
        assert kwargs["probe_query"] == "确定屋面防水工程的防水等级应根据什么"
        return [
            {
                "id": "q-exact",
                "chunk_id": "question-q-exact",
                "card_title": f"题目: {full_exact_stem[:18]}",
                "stem": full_exact_stem,
                "options": [{"key": "A", "value": "建筑物类别"}],
                "correct_answer": "A",
                "analysis": "以题库原题为准。",
                "rag_content": "【题目】确定屋面防水工程的防水等级应根据什么\n【答案】建筑物类别",
                "source_type": "textbook_assessment",
                "score": 1.0,
                "_source_group": "question_exact_text",
                "_source_table": "questions_bank",
            }
        ]

    async def _fake_run_query_plan(**kwargs):
        assert kwargs["exact_probe"] is not None
        return [
            {
                "phase": "primary",
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "id": "q-fuzzy",
                        "chunk_id": "question-q-fuzzy",
                        "card_title": "题目: 地下工程防水等级",
                        "rag_content": "【题目】地下工程防水等级应根据什么\n【答案】埋置深度",
                        "source_type": "real_exam",
                        "score": 0.83,
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                        "metadata": {
                            "source_id": "question_2026_roof_001",
                            "source_table": "questions_bank",
                            "stable_id": "question_2026_roof_001:stem",
                            "source_span": {"question": "Q1", "section": "roof"},
                            "content_hash": "hash-question-roof",
                            "quote_hash": "quote-question-roof",
                        },
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_search_exact_question_text", _fake_search_exact_question_text)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积",
        kb_name="construction-exam",
    )

    assert result["provider"] == "supabase"
    assert result["sources"][0]["chunk_id"] == "question-q-exact"
    assert result["sources"][0]["source_type"] == "textbook_assessment"
    assert result["exact_question"]["chunk_id"] == "question-q-exact"
    assert result["exact_question"]["source_group"] == "question_exact_text"
    assert result["exact_question"]["stem"] == full_exact_stem
    assert result["exact_question"]["options"] == [{"key": "A", "value": "建筑物类别"}]


@pytest.mark.asyncio
async def test_supabase_search_promotes_option_matched_real_exam_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)
    options = [
        {"key": "A", "value": "单跨构件宜从跨端一侧向另一侧吊装"},
        {"key": "B", "value": "单跨结构可从跨中间向两端吊装"},
        {"key": "C", "value": "单跨结构不可从跨两端向中间吊装"},
        {"key": "D", "value": "多跨结构宜先吊副跨后吊主跨"},
        {"key": "E", "value": "多台起重设备共同作业时，可多跨同时吊装"},
    ]

    async def _empty_exact_text(**kwargs):
        _ = kwargs
        return []

    async def _fake_run_query_plan(**kwargs):
        assert kwargs["exact_probe"] is not None
        return [
            {
                "phase": "primary",
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "id": "17438",
                        "chunk_id": "question-17438",
                        "card_title": "题目: 关于单跨钢结构吊装顺序的说法，正确的有（　　）。",
                        "stem": "关于单跨钢结构吊装顺序的说法，正确的有（　　）。",
                        "options": json.dumps(options, ensure_ascii=False),
                        "correct_answer": "ABE",
                        "analysis": "C 错误；D 错误。",
                        "question_type": "multi",
                        "rag_content": "【题目】关于单跨钢结构吊装顺序的说法，正确的有（　　）。\n【答案】ABE",
                        "source_type": "REAL_EXAM",
                        "score": 0.7284,
                        "similarity": 0.7284,
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_search_exact_question_text", _empty_exact_text)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query=(
            "关于单层钢结构吊装顺序的说法，正确的有（ ）。\n"
            "A.单跨构宜从跨端一侧向另一侧吊装\n"
            "B.单跨结构可从跨中间向两端吊装\n"
            "C.单跨结构不可从跨两端向中间吊装\n"
            "D.多跨结构宜先吊副跨后吊主跨\n"
            "E.多台起重设备共同作业时，可多跨同时吊装；"
        ),
        kb_name="construction-exam",
    )

    assert result["exact_question"]["chunk_id"] == "question-17438"
    assert result["exact_question"]["source_group"] == "question_bank_option_match"
    assert result["exact_question"]["correct_answer"] == "ABE"
    assert result["exact_question"]["answer_kind"] == "mcq"


@pytest.mark.asyncio
async def test_supabase_search_emits_evidence_bundle_and_respects_routing_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_run_query_plan(**kwargs):
        source_plan = kwargs["source_plan"]
        assert source_plan.search_questions_bank is True
        assert "force_qbank_by_question_type" in source_plan.selection_reasons
        return [
            {
                "phase": "primary",
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "id": "q-fuzzy",
                        "chunk_id": "question-q-fuzzy",
                        "card_title": "题目: 屋面防水等级",
                        "rag_content": "【题目】屋面防水等级应根据什么\n【答案】建筑物类别",
                        "source_type": "textbook_assessment",
                        "score": 0.83,
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                        "metadata": {
                            "source_id": "question_2026_roof_001",
                            "source_table": "questions_bank",
                            "stable_id": "question_2026_roof_001:stem",
                            "source_span": {"question": "Q1", "section": "roof"},
                            "content_hash": "hash-question-roof",
                            "quote_hash": "quote-question-roof",
                        },
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="屋面防水等级",
        kb_name="construction-exam",
        question_type="single_choice",
        routing_metadata={"preferred_question_type": "choice"},
    )

    assert result["evidence_bundle"]["kb_name"] == "construction-exam"
    assert result["evidence_bundle"]["retrieval_empty"] is False
    assert result["evidence_bundle"]["source_plan"]["search_questions_bank"] is True
    assert result["evidence_bundle"]["sources"][0]["chunk_id"] == "question-q-fuzzy"
    assert result["evidence_bundle"]["sources"][0]["source_id"] == "question_2026_roof_001"
    assert result["evidence_bundle"]["sources"][0]["source_table"] == "questions_bank"
    assert result["evidence_bundle"]["sources"][0]["stable_id"] == "question_2026_roof_001:stem"
    assert result["evidence_bundle"]["sources"][0]["source_span"] == {"question": "Q1", "section": "roof"}
    assert result["evidence_bundle"]["sources"][0]["content_hash"] == "hash-question-roof"
    assert result["evidence_bundle"]["sources"][0]["quote_hash"] == "quote-question-roof"


@pytest.mark.asyncio
async def test_rerank_documents_records_langfuse_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase_strategy

    class _FakeObservation:
        pass

    class _FakeObservability:
        def __init__(self) -> None:
            self.started: list[dict[str, object]] = []
            self.updated: list[dict[str, object]] = []

        class _Context:
            def __init__(self, outer: "_FakeObservability", kwargs: dict[str, object]) -> None:
                self._outer = outer
                self._kwargs = kwargs

            def __enter__(self) -> _FakeObservation:
                self._outer.started.append(self._kwargs)
                return _FakeObservation()

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        def start_observation(self, **kwargs):
            return self._Context(self, kwargs)

        def update_observation(self, observation, **kwargs) -> None:
            _ = observation
            self.updated.append(kwargs)

        def estimate_usage_details(self, *, input_payload, output_payload=None):
            _ = output_payload
            return {
                "input": float(len(str(input_payload))),
                "output": 0.0,
                "total": float(len(str(input_payload))),
            }

        def estimate_cost_details(self, *, model, usage_details):
            return {"model": model, "total": usage_details["total"]}

    class _FakeDashscopeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.usage = SimpleNamespace(total_tokens=80)
            self.output = {
                "results": [
                    {"index": 1, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.81},
                ]
            }

    class _FakeTextReRank:
        @staticmethod
        def call(**kwargs):
            assert kwargs["model"] == "gte-rerank"
            assert kwargs["top_n"] == 2
            return _FakeDashscopeResponse()

    fake_observability = _FakeObservability()
    monkeypatch.setattr(supabase_strategy, "observability", fake_observability)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_RERANK_MODEL", "gte-rerank")
    monkeypatch.setitem(sys.modules, "dashscope", SimpleNamespace(TextReRank=_FakeTextReRank))

    results = await supabase_strategy.rerank_documents(
        "abc",
        ["xx", "yyyy"],
        top_n=2,
        timeout_s=1.0,
    )

    assert [item["index"] for item in results] == [1, 0]
    assert fake_observability.started[0]["name"] == "rerank.dashscope"
    assert fake_observability.started[0]["model"] == "gte-rerank"
    assert fake_observability.updated[-1]["usage_details"] == {
        "input": 80.0,
        "output": 0.0,
        "total": 80.0,
    }
    assert fake_observability.updated[-1]["usage_source"] == "provider"
    assert fake_observability.updated[-1]["cost_details"] == {
        "model": "gte-rerank",
        "total": 80.0,
    }


@pytest.mark.asyncio
async def test_supabase_search_builds_partial_case_authority_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "true")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS_QUERIES", "2")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)
    captured_queries: list[str] = []

    async def _fake_search_exact_question_text(**kwargs):
        return [
            {
                "id": 9717,
                "chunk_id": "question-9717",
                "card_title": "题目: 某旧城改造工程案例题",
                "stem": "【问题】\n1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                "rag_content": "【题目】1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？\n【答案】（1）潜在投标人数量较多；（2）合格制、有限数量制。",
                "source_type": "REAL_EXAM",
                "score": 0.98,
                "similarity": 0.98,
                "question_type": "case_study",
                "correct_answer": "（1）潜在投标人数量较多；（2）合格制、有限数量制。",
                "analysis": "第1问标准答案。",
                "options": "",
                "_source_group": "question_exact_text",
                "_source_table": "questions_bank",
            }
        ]

    async def _fake_run_query_plan(**kwargs):
        captured_queries.extend(kwargs["queries"])
        return [
            {
                "phase": kwargs.get("phase", "primary"),
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": kwargs.get("query_weight", 1.0),
                "results": [
                    {
                        "id": 9717,
                        "chunk_id": "question-9717",
                        "card_title": "题目: 1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                        "stem": "【问题】\n1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                        "rag_content": "【题目】1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？\n【答案】（1）潜在投标人数量较多；（2）合格制、有限数量制。",
                        "source_type": "REAL_EXAM",
                        "score": 0.98,
                        "similarity": 0.98,
                        "question_type": "case_study",
                        "correct_answer": "（1）潜在投标人数量较多；（2）合格制、有限数量制。",
                        "analysis": "第1问标准答案。",
                        "options": "",
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_search_exact_question_text", _fake_search_exact_question_text)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query=(
            "背景资料：某旧城改造工程。\n问题：\n"
            "1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？\n"
            "2. 按照完全成本法计算的工程施工项目成本是多少亿元？\n"
            "3. 分步骤列式计算钢结构装饰架的造价是多少万元？"
        ),
        kb_name="construction-exam",
    )

    assert result["exact_question"]["answer_kind"] == "case_study"
    assert result["exact_question"]["coverage_state"] == "single_subquestion_only"
    assert result["exact_question"]["query_subquestion_count"] == 3
    assert result["exact_question"]["coverage_ratio"] == pytest.approx(1 / 3, rel=1e-4)
    assert len(result["exact_question"]["missing_subquestions"]) == 2
    assert any("完全成本法" in item["prompt"] for item in result["exact_question"]["missing_subquestions"])
    assert any("钢结构装饰架" in query for query in captured_queries)


@pytest.mark.asyncio
async def test_supabase_search_promotes_high_confidence_case_question_bank_match_from_case_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_run_query_plan(**kwargs):
        return [
            {
                "phase": kwargs.get("phase", "primary"),
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": kwargs.get("query_weight", 1.0),
                "results": [
                    {
                        "id": 17468,
                        "chunk_id": "question-17468",
                        "card_title": "题目: 某旧城改造工程钢结构装饰架造价",
                        "stem": (
                            "【背景资料】某旧城改造工程，应甲方要求，在相关单位工程顶部新增钢结构装饰架。"
                            "分部分项工程工程量 2200t，措施费为分部分项工程费的 10%，"
                            "总承包管理费 70 万元，计日工 26 万元，规费费率 2%，增值税税率 9%。"
                            "【问题】5. 分步列式计算钢结构装饰架的造价是多少万元？"
                        ),
                        "rag_content": (
                            "【题目】5. 分步列式计算钢结构装饰架的造价是多少万元？\n"
                            "【答案】3335.40 万元。"
                        ),
                        "source_type": "REAL_EXAM",
                        "score": 0.7361,
                        "similarity": 0.7361,
                        "question_type": "case_study",
                        "correct_answer": "3335.40 万元。",
                        "analysis": "分部分项、措施、其他项目、规费、增值税依次计算。",
                        "options": "",
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query=(
            "背景资料：某旧城改造工程，应甲方要求，在相关单位工程顶部新增钢结构装饰架。"
            "分部分项工程工程量 2200t，措施费为分部分项工程费的 10%，"
            "总承包管理费 70 万元，计日工 26 万元，规费费率 2%，增值税税率 9%。"
            "问题：\n1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？\n"
            "5. 分步骤列式计算钢结构装饰架的造价是多少万元？"
        ),
        kb_name="construction-exam",
    )

    assert result["exact_question"]["chunk_id"] == "question-17468"
    assert result["exact_question"]["source_group"] == "question_bank_case_match"
    assert result["exact_question"]["answer_kind"] == "case_study"
    assert result["exact_question"]["covered_subquestions"][0]["display_index"] == "5"
    assert result["exact_question"]["covered_subquestions"][0]["authoritative_answer"] == "3335.40 万元。"


@pytest.mark.asyncio
async def test_supabase_search_does_not_promote_case_match_from_keyword_only_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_run_query_plan(**kwargs):
        return [
            {
                "phase": kwargs.get("phase", "primary"),
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": kwargs.get("query_weight", 1.0),
                "results": [
                    {
                        "id": 17468,
                        "chunk_id": "question-17468",
                        "card_title": "题目: 某旧城改造工程钢结构装饰架造价",
                        "stem": (
                            "【背景资料】某旧城改造工程，应甲方要求，在相关单位工程顶部新增钢结构装饰架。"
                            "分部分项工程工程量 2200t，措施费为分部分项工程费的 10%，"
                            "总承包管理费 70 万元，计日工 26 万元，规费费率 2%，增值税税率 9%。"
                            "【问题】5. 分步列式计算钢结构装饰架的造价是多少万元？"
                        ),
                        "rag_content": "【题目】5. 钢结构装饰架造价\n【答案】3335.40 万元。",
                        "source_type": "REAL_EXAM",
                        "score": 0.7361,
                        "similarity": 0.7361,
                        "question_type": "case_study",
                        "correct_answer": "3335.40 万元。",
                        "analysis": "第5问标准答案。",
                        "options": "",
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="钢结构装饰架造价计算 分部分项工程费 措施费 总承包管理费 计日工 规费 增值税",
        kb_name="construction-exam",
    )

    assert result.get("exact_question") is None
    assert result["evidence_bundle"]["exact_question"] == {}


@pytest.mark.asyncio
async def test_supabase_search_merges_case_exact_text_with_question_bank_case_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_search_exact_question_text(**kwargs):
        if "资格预审" not in str(kwargs.get("probe_query") or ""):
            return []
        return [
            {
                "id": 17464,
                "chunk_id": "question-17464",
                "card_title": "题目: 某旧城改造工程资格预审",
                "stem": "【问题】1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？",
                "rag_content": "【题目】1. 资格预审特点与方法\n【答案】潜在投标人数量较多；合格制、有限数量制。",
                "source_type": "REAL_EXAM",
                "score": 0.99,
                "similarity": 0.99,
                "question_type": "case_study",
                "correct_answer": "潜在投标人数量较多；合格制、有限数量制。",
                "analysis": "第1问标准答案。",
                "options": "",
                "_source_group": "question_exact_text",
                "_source_table": "questions_bank",
            }
        ]

    async def _fake_run_query_plan(**kwargs):
        return [
            {
                "phase": kwargs.get("phase", "primary"),
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": kwargs.get("query_weight", 1.0),
                "results": [
                    {
                        "id": 17468,
                        "chunk_id": "question-17468",
                        "card_title": "题目: 某旧城改造工程钢结构装饰架造价",
                        "stem": (
                            "【背景资料】某旧城改造工程，应甲方要求，在相关单位工程顶部新增钢结构装饰架。"
                            "分部分项工程工程量 2200t，措施费为分部分项工程费的 10%，"
                            "总承包管理费 70 万元，计日工 26 万元，规费费率 2%，增值税税率 9%。"
                            "【问题】5. 分步列式计算钢结构装饰架的造价是多少万元？"
                        ),
                        "rag_content": "【题目】5. 钢结构装饰架造价\n【答案】3335.40 万元。",
                        "source_type": "REAL_EXAM",
                        "score": 0.74,
                        "similarity": 0.74,
                        "question_type": "case_study",
                        "correct_answer": "3335.40 万元。",
                        "analysis": "第5问标准答案。",
                        "options": "",
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_search_exact_question_text", _fake_search_exact_question_text)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query=(
            "背景资料：某旧城改造工程。\n问题：\n"
            "1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？\n"
            "4. 按照完全成本法计算的工程施工项目成本是多少亿元？\n"
            "5. 分步骤列式计算钢结构装饰架的造价是多少万元？"
        ),
        kb_name="construction-exam",
    )

    covered_indexes = {
        item["display_index"] for item in result["exact_question"]["covered_subquestions"]
    }
    assert covered_indexes == {"1", "5"}
    assert result["exact_question"]["coverage_state"] == "partial_multi_subquestion_exact"
    assert result["exact_question"]["coverage_ratio"] == pytest.approx(2 / 3, rel=1e-4)
    assert any("完全成本法" in item["prompt"] for item in result["exact_question"]["missing_subquestions"])
    from deeptutor.services.rag.exact_authority import build_exact_authority_response

    rendered = build_exact_authority_response(result["exact_question"])
    assert "**采分点：**" in rendered
    assert "## 记忆口诀" in rendered


@pytest.mark.asyncio
async def test_supabase_search_does_not_promote_low_confidence_case_question_bank_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_run_query_plan(**kwargs):
        return [
            {
                "phase": kwargs.get("phase", "primary"),
                "group_name": "questions_bank",
                "query": kwargs["queries"][0],
                "query_index": 0,
                "query_weight": kwargs.get("query_weight", 1.0),
                "results": [
                    {
                        "id": 17381,
                        "chunk_id": "question-17381",
                        "card_title": "题目: 另一道施工合同案例题",
                        "stem": "【背景资料】某施工单位承接一工程。【问题】1. 计算进度款。",
                        "rag_content": "【题目】另一道施工合同案例题\n【答案】其他标准答案。",
                        "source_type": "REAL_EXAM",
                        "score": 0.5628,
                        "similarity": 0.5628,
                        "question_type": "case_study",
                        "correct_answer": "其他标准答案。",
                        "analysis": "",
                        "options": "",
                        "_source_group": "questions_bank",
                        "_source_table": "questions_bank",
                    }
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="钢结构装饰架造价计算 分部分项工程费 措施费 总承包管理费 计日工 规费 增值税",
        kb_name="construction-exam",
    )

    assert result.get("exact_question") is None
    assert result["evidence_bundle"]["exact_question"] == {}


def test_filter_partial_case_results_prunes_unrelated_exam_noise() -> None:
    from deeptutor.services.rag.pipelines.supabase import SupabasePipeline

    pipeline = SupabasePipeline()
    exact_question = {
        "chunk_id": "question-9717",
        "answer_kind": "case_study",
        "missing_subquestions": [
            {"display_index": "4", "prompt": "按照完全成本法计算的工程施工项目成本是多少亿元"},
            {"display_index": "5", "prompt": "分步骤列式计算钢结构装饰架的造价是多少万元"},
        ],
    }
    results = [
        {
            "chunk_id": "question-9717",
            "card_title": "题目: 某旧城改造工程案例题",
            "rag_content": "【题目】1. 资格预审特点与方法",
            "source_type": "REAL_EXAM",
            "_source_table": "questions_bank",
        },
        {
            "chunk_id": "EXAM-noise",
            "card_title": "真题 2017",
            "rag_content": "### 案例四：工程总承包合同与预付款",
            "source_type": "exam",
            "_source_table": "kb_chunks",
        },
        {
            "chunk_id": "STD-1",
            "card_title": "工程总承包管理",
            "rag_content": "工程总承包不得将设计和施工一并分包给其他单位。",
            "source_type": "standard",
            "_source_table": "kb_chunks",
        },
    ]

    filtered = pipeline._filter_partial_case_results(results, exact_question=exact_question)

    assert [item["chunk_id"] for item in filtered] == ["question-9717", "STD-1"]


@pytest.mark.asyncio
async def test_supabase_pipeline_reuses_async_client_until_timeout_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    created_clients: list[float] = []

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            self.timeout = timeout
            self.closed = False
            created_clients.append(timeout)

        async def aclose(self) -> None:
            self.closed = True

    monkeypatch.setattr(supabase_module.httpx, "AsyncClient", _FakeAsyncClient)

    pipeline = supabase_module.SupabasePipeline()
    client_one = await pipeline._get_client(12.0)
    client_two = await pipeline._get_client(12.0)
    client_three = await pipeline._get_client(18.0)

    assert client_one is client_two
    assert client_three is not client_one
    assert created_clients == [12.0, 18.0]

    await pipeline.aclose()
    assert client_three.closed is True


@pytest.mark.asyncio
async def test_supabase_search_dedupes_duplicate_rendered_content_and_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_run_query_plan(**kwargs):
        _ = kwargs
        return [
            {
                "phase": "primary",
                "group_name": "standards",
                "query": "建筑构造是什么",
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "id": "std-1",
                        "chunk_id": "std-1",
                        "card_title": "GB 50016-2019 §6.13.1 建筑构造",
                        "rag_content": "【6.13.1】地面的基本构造层宜为面层、垫层和地基。",
                        "source_type": "standard",
                        "score": 0.99,
                        "_source_group": "standards",
                        "_source_table": "kb_chunks",
                    },
                    {
                        "id": "std-dup",
                        "chunk_id": "std-dup",
                        "card_title": "GB 50016-2019 §6.13.1 建筑构造",
                        "rag_content": "【6.13.1】地面的基本构造层宜为面层、垫层和地基。",
                        "source_type": "standard",
                        "score": 0.98,
                        "_source_group": "standards",
                        "_source_table": "kb_chunks",
                    },
                    {
                        "id": "std-2",
                        "chunk_id": "std-2",
                        "card_title": "GB 50016-2019 §6.13.1 建筑构造",
                        "rag_content": "【6.13.1】楼面的基本构造层宜为面层和楼板。",
                        "source_type": "standard",
                        "score": 0.97,
                        "_source_group": "standards",
                        "_source_table": "kb_chunks",
                    },
                ],
            }
        ]

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    async def _empty_exact_text(**kwargs):
        _ = kwargs
        return []

    monkeypatch.setattr(pipeline, "_search_exact_question_text", _empty_exact_text)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="建筑构造是什么？",
        kb_name="construction-exam",
    )

    assert result["answer"].count("地面的基本构造层宜为面层、垫层和地基") == 1
    assert result["answer"].count("楼面的基本构造层宜为面层和楼板") == 1
    assert len(result["sources"]) == 2
    assert [item["chunk_id"] for item in result["sources"]] == ["std-1", "std-2"]


@pytest.mark.asyncio
async def test_supabase_search_projects_teaching_metadata_into_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            _ = kb_name
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())

    pipeline = supabase_module.SupabasePipeline()
    _disable_supabase_availability_gate(monkeypatch, pipeline)

    async def _fake_run_query_plan(**kwargs):
        _ = kwargs
        return [
            {
                "phase": "primary",
                "group_name": "textbook",
                "query": "模板安装 起拱要求",
                "query_index": 0,
                "query_weight": 1.0,
                "results": [
                    {
                        "id": "LEC_1A413040_P0005_002",
                        "chunk_id": "LEC_1A413040_P0005_002",
                        "card_title": "模板安装",
                        "rag_content": "### 模板安装核心要求\n对跨度≥4m的梁、板应按设计要求起拱。",
                        "source_type": "textbook",
                        "score": 0.98,
                        "_source_group": "textbook",
                        "_source_table": "kb_chunks",
                    }
                ],
            }
        ]

    async def _hydrate_sources(results, **kwargs):
        _ = kwargs
        enriched = []
        for item in results:
            row = dict(item)
            row["metadata"] = {
                "logic_chains": [
                    "跨度≥4m且设计无要求 -> 起拱高度为跨度的1/1000~3/1000 -> 防止构件下挠"
                ],
                "exam_matrix": {
                    "mnemonics": "四米起拱千一三",
                    "grading_keywords": ["起拱", "1/1000~3/1000", "独立设置"],
                    "trap_alert": "注意起拱的起算跨度是4m，不是2m或8m。",
                    "red_lines": ["支架立柱不得混用"],
                },
            }
            enriched.append(row)
        return enriched

    async def _identity(results, **kwargs):
        _ = kwargs
        return results

    async def _empty_exact_text(**kwargs):
        _ = kwargs
        return []

    monkeypatch.setattr(pipeline, "_search_exact_question_text", _empty_exact_text)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _hydrate_sources)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="模板安装 起拱要求",
        kb_name="construction-exam",
    )

    assert "## 记忆口诀" in result["answer"]
    assert "四米起拱千一三" in result["answer"]
    assert "## 采分点" in result["answer"]
    assert "1/1000~3/1000" in result["answer"]
    assert "## 易错点" in result["answer"]
    assert "起算跨度是4m" in result["answer"]
    assert "## 思维链" in result["answer"]
    assert "防止构件下挠" in result["answer"]
    assert "## 扣分红线" in result["answer"]
    assert "支架立柱不得混用" in result["answer"]


def test_exact_question_review_notes_project_numeric_pitfalls() -> None:
    from deeptutor.services.rag.exact_authority import build_mcq_review_notes_from_exact_question

    notes = build_mcq_review_notes_from_exact_question(
        {
            "answer_kind": "mcq",
            "stem": "一般环境中，直接接触土体浇筑的构件，其钢筋的混凝土保护层厚度不应小于（ ）mm。",
            "options": {"A": "55", "B": "60", "C": "65", "D": "70"},
            "correct_answer": "D",
            "analysis": "直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。",
        }
    )

    assert notes["option_analysis"][0]["analysis"] == "55 低于标准值 70，不能满足题干中的“不应小于”要求。"
    assert notes["option_analysis"][-1]["analysis"] == (
        "70 对应题库标准答案；直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。"
    )
    assert "抓住标准答案对应的规范数值：D. 70。" in notes["scoring_points"]
    assert notes["mnemonic"] == "直接接土先加厚，保护层记 70。"


@pytest.mark.asyncio
async def test_supabase_pipeline_embedding_cache_reuses_same_query_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    supabase_module._EMBEDDING_CACHE.clear()
    monkeypatch.setenv("SUPABASE_RAG_EMBEDDING_CACHE_ENABLED", "true")
    calls: list[list[str]] = []

    class _FakeEmbeddingClient:
        async def embed(self, queries: list[str]) -> list[list[float]]:
            calls.append(list(queries))
            return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(supabase_module, "get_embedding_client", lambda: _FakeEmbeddingClient())

    pipeline = supabase_module.SupabasePipeline()
    first = await pipeline._embed_query("2026教材变化")
    second = await pipeline._embed_query("2026教材变化")

    assert first == [0.1, 0.2, 0.3]
    assert second == [0.1, 0.2, 0.3]
    assert calls == [["2026教材变化"]]


def test_supabase_similarity_floor_guarantees_high_similarity_chunk_into_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_RAG_SIM_FLOOR_THRESHOLD", "0.72")
    monkeypatch.setenv("SUPABASE_RAG_SIM_FLOOR_BOOST", "0.02")
    monkeypatch.setenv("SUPABASE_RAG_SIM_FLOOR_HARD_THRESHOLD", "0.82")
    monkeypatch.setenv("SUPABASE_RAG_SIM_FLOOR_HARD_MAX", "1")

    fused = [
        {"chunk_id": "rrf-low", "weighted_rrf_score": 0.0200, "score": 0.62},
        {"chunk_id": "high-sim", "weighted_rrf_score": 0.0190, "score": 0.91},
    ]
    results_map = {
        "primary:textbook:q0": [
            {"chunk_id": "rrf-low", "score": 0.62},
            {"chunk_id": "high-sim", "score": 0.91},
        ]
    }

    adjusted = supabase_module._apply_similarity_floor(
        fused,
        results_map,
        target_window=1,
    )

    assert adjusted[0]["chunk_id"] == "high-sim"
    assert adjusted[0].get("_sim_floor_boosted") or adjusted[0].get("_sim_floor_guaranteed")
