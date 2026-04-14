"""RAG provider registry and tool integration tests."""

from __future__ import annotations

import os

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
