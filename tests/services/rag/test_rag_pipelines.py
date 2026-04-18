"""RAG provider registry and tool integration tests."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest


def test_list_available_providers() -> None:
    """Provider list should expose local and Supabase retrieval backends."""
    from deeptutor.tools.rag_tool import get_available_providers

    providers = get_available_providers()
    assert [p["id"] for p in providers] == ["llamaindex", "supabase"]


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


def test_get_pipeline_invalid_raises() -> None:
    """Unknown provider names should raise explicit error."""
    from deeptutor.services.rag.factory import get_pipeline

    with pytest.raises(ValueError, match="Unknown pipeline"):
        get_pipeline("nonexistent")


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
async def test_rag_search_invalid_provider_falls_back_to_kb_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool wrapper should defer to KB-resolved provider (llamaindex-only runtime)."""
    from deeptutor.services.rag import service as rag_service_module
    from deeptutor.tools.rag_tool import rag_search

    monkeypatch.setattr(
        rag_service_module.RAGService,
        "_get_provider_for_kb",
        lambda self, kb_name: "llamaindex",
    )

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

    async def _fake_search_exact_question_text(**kwargs):
        assert kwargs["probe_query"] == "确定屋面防水工程的防水等级应根据什么"
        return [
            {
                "id": "q-exact",
                "chunk_id": "question-q-exact",
                "card_title": "题目: 确定屋面防水工程的防水等级应根据什么",
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
