"""Battle2 S5-T5: search_unified gets its own per-RPC timeout budget so one
slow group degrades early (failure_sink, fusion continues) instead of holding
the whole plan to the 8s client-level timeout. Other RPCs keep the client
default. Default 6.0s — calibrated against production Langfuse (recent 5,900
successful search_unified calls: p50=0.53s / p95=5.26s / p99=12.7s; the
commander gate forbids a default below the healthy p95).
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from deeptutor.services.rag.pipelines import supabase as supabase_module


def _config(**overrides):
    values = dict(
        url="https://example.supabase.co",
        service_key="test-key",  # pragma: allowlist secret
        timeout_s=8.0,
        sources=["standard", "textbook"],
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
        rerank_enabled=False,
        rerank_window=2,
        rerank_timeout_s=2.0,
        exact_question_enabled=False,
        exact_question_text_first=False,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
    )
    values.update(overrides)
    return supabase_module.SupabaseSearchConfig(**values)


class _FakeResponse:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._rows


class _RecordingClient:
    """Records post kwargs; optionally times out search_unified."""

    def __init__(self, *, timeout_functions: set[str] | None = None) -> None:
        self.posts: list[tuple[str, object]] = []
        self._timeout_functions = timeout_functions or set()

    async def post(self, url, headers=None, json=None, timeout=None):
        _ = headers
        function_name = url.rsplit("/", 1)[-1]
        self.posts.append((function_name, timeout))
        if function_name in self._timeout_functions:
            raise httpx.ReadTimeout("simulated slow search_unified")
        return _FakeResponse([])


def _default_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_RAG_UNIFIED_TIMEOUT_S", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")


@pytest.mark.asyncio
async def test_search_unified_carries_budget_and_other_rpcs_keep_client_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _default_env(monkeypatch)
    pipeline = supabase_module.SupabasePipeline()
    client = _RecordingClient()
    config = _config()

    await pipeline._search_source(
        client=client,
        query="混凝土养护",
        vector_literal="[0.1,0.2]",
        source_type="standard",
        config=config,
    )
    await pipeline._search_questions(client=client, vector_literal="[0.1,0.2]", config=config)

    posts = dict(client.posts)
    assert posts["search_unified"] == 6.0  # calibrated default budget
    assert posts["search_questions_bank_vector"] is httpx.USE_CLIENT_DEFAULT


@pytest.mark.asyncio
async def test_env_override_and_invalid_and_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    _default_env(monkeypatch)
    pipeline = supabase_module.SupabasePipeline()
    config = _config()

    monkeypatch.setenv("SUPABASE_RAG_UNIFIED_TIMEOUT_S", "2.5")
    client = _RecordingClient()
    await pipeline._search_source(
        client=client, query="q", vector_literal="[0.1]", source_type="standard", config=config
    )
    assert dict(client.posts)["search_unified"] == 2.5

    monkeypatch.setenv("SUPABASE_RAG_UNIFIED_TIMEOUT_S", "not-a-number")
    client = _RecordingClient()
    await pipeline._search_source(
        client=client, query="q", vector_literal="[0.1]", source_type="standard", config=config
    )
    assert dict(client.posts)["search_unified"] == 6.0  # invalid → default

    monkeypatch.setenv("SUPABASE_RAG_UNIFIED_TIMEOUT_S", "0")
    client = _RecordingClient()
    await pipeline._search_source(
        client=client, query="q", vector_literal="[0.1]", source_type="standard", config=config
    )
    # <=0 disables the budget: parameterized rollback to the client default.
    assert dict(client.posts)["search_unified"] is httpx.USE_CLIENT_DEFAULT


@pytest.mark.asyncio
async def test_unified_timeout_degrades_one_group_and_keeps_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _default_env(monkeypatch)
    pipeline = supabase_module.SupabasePipeline()

    class _OneVectorEmbeddingClient:
        async def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(
        supabase_module, "get_embedding_client", lambda: _OneVectorEmbeddingClient()
    )

    bank_row = {
        "id": "q-1",
        "stem": "题干",
        "question_type": "single_choice",
        "options": [{"key": "A", "value": "x"}],
        "correct_answer": "A",
        "analysis": "解析",
        "similarity": 0.8,
        "source_type": "REAL_EXAM",
    }

    class _TimeoutThenRowsClient(_RecordingClient):
        async def post(self, url, headers=None, json=None, timeout=None):
            function_name = url.rsplit("/", 1)[-1]
            self.posts.append((function_name, timeout))
            if function_name == "search_unified":
                raise httpx.ReadTimeout("simulated slow search_unified")
            return _FakeResponse([dict(bank_row)])

    client = _TimeoutThenRowsClient()
    failure_sink: list[dict[str, str]] = []

    plans = await pipeline._run_query_plan(
        client=client,
        queries=["混凝土养护"],
        question_like=True,
        source_plan=SimpleNamespace(
            search_textbook_chunks=True,
            search_standard_chunks=True,
            search_exam_chunks=False,
            search_questions_bank=True,
        ),
        standard_codes=[],
        precision_node_code=None,
        exact_probe=None,
        original_query="混凝土养护",
        config=_config(),
        failure_sink=failure_sink,
    )

    # Both search_unified groups timed out and were recorded as degradations…
    failed_groups = {entry["group_name"] for entry in failure_sink}
    assert failed_groups == {"standard", "textbook"}
    # …while the questions_bank group survived and produced results.
    bank_plans = [plan for plan in plans if plan["group_name"] == "questions_bank"]
    assert len(bank_plans) == 1
    assert [item["id"] for item in bank_plans[0]["results"]] == ["q-1"]
