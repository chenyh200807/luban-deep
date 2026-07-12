"""Battle2 S5-T4: retrieval fan-out dedup.

T4① — one order-preserving batch embed call per query plan instead of one
embed API call per variant.

T4② — the q0 dedicated exact-vector RPC is derived client-side from the
regular questions_bank rows (same RPC, same embedding, higher threshold,
count=min(fetch_count,5) ⇒ strict subset when rows are similarity-desc).

Commander hard gate: the oracle tests below assert the derivation equals the
old dedicated-RPC path FIELD-BY-FIELD (including empty hits, similarity-desc
ordering, truncation semantics). If these ever fail, T4② must be dropped —
never loosened to "approximately equal".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.rag.pipelines import supabase as supabase_module


@pytest.fixture(autouse=True)
def _clear_embedding_cache():
    supabase_module._EMBEDDING_CACHE.clear()
    yield
    supabase_module._EMBEDDING_CACHE.clear()


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
        max_query_variants=4,
        second_pass_enabled=False,
        second_pass_max_queries=1,
        second_pass_min_hits=1,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=False,
        rerank_window=2,
        rerank_timeout_s=2.0,
        exact_question_enabled=True,
        exact_question_text_first=False,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
    )
    values.update(overrides)
    return supabase_module.SupabaseSearchConfig(**values)


_BANK_STEM = (
    "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，"
    "实际价是200元/m3，此时进度偏差为（　　）万元。"
)
_ALLOWED_TYPES = ["calculation", "single", "multi", "free_text"]


def _bank_row(row_id: str, similarity: float, *, question_type: str = "single_choice", stem: str = _BANK_STEM):
    return {
        "id": row_id,
        "stem": stem,
        "question_type": question_type,
        "options": [
            {"key": "A", "value": "45"},
            {"key": "B", "value": "60"},
            {"key": "C", "value": "-30"},
            {"key": "D", "value": "30"},
        ],
        "correct_answer": "C",
        "analysis": "进度偏差=3000×150-5000×150=-300000元。",
        "similarity": similarity,
        "source_type": "REAL_EXAM",
        "exam_year": 2023,
    }


def _exact_probe():
    return SimpleNamespace(
        query=_BANK_STEM,
        allowed_question_types=_ALLOWED_TYPES,
        option_validation_required=False,
    )


def _source_plan():
    return SimpleNamespace(
        search_textbook_chunks=False,
        search_standard_chunks=True,
        search_exam_chunks=False,
        search_questions_bank=True,
    )


class _CountingEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [[0.1 * (index + 1), 0.2, 0.3] for index in range(len(texts))]


async def _run_plan(pipeline, *, queries, config, exact_probe=None):
    return await pipeline._run_query_plan(
        client=object(),
        queries=queries,
        question_like=True,
        source_plan=_source_plan(),
        standard_codes=[],
        precision_node_code=None,
        exact_probe=exact_probe,
        original_query=_BANK_STEM,
        config=config,
    )


# ── T4①: batch embed ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_four_variants_use_one_ordered_batch_embed_call(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    embedding_client = _CountingEmbeddingClient()
    monkeypatch.setattr(supabase_module, "get_embedding_client", lambda: embedding_client)

    rpc_payloads: list[tuple[str, dict]] = []

    async def _fake_rpc(client, function_name, payload, **kwargs):
        _ = (client, kwargs)
        rpc_payloads.append((function_name, payload))
        return []

    monkeypatch.setattr(pipeline, "_rpc", _fake_rpc)

    queries = ["查询一", "查询二", "查询三", "查询四"]
    await _run_plan(pipeline, queries=queries, config=_config())

    assert embedding_client.calls == [queries]  # ONE batch call, input order preserved

    # Each variant's RPCs must carry that variant's own embedding (order intact).
    expected_literals = {
        query: supabase_module._vector_literal([0.1 * (index + 1), 0.2, 0.3])
        for index, query in enumerate(queries)
    }
    unified_payloads = [p for name, p in rpc_payloads if name == "search_unified"]
    assert len(unified_payloads) == len(queries)
    for payload in unified_payloads:
        assert payload["p_query_embedding"] == expected_literals[payload["p_query_text"]]


@pytest.mark.asyncio
async def test_batch_embed_failure_falls_back_to_per_query_embeds(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()

    class _FlakyEmbeddingClient:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def embed(self, texts):
            self.calls.append(list(texts))
            if len(texts) > 1:
                raise RuntimeError("batch endpoint down")
            return [[0.5, 0.5, 0.5]]

    embedding_client = _FlakyEmbeddingClient()
    monkeypatch.setattr(supabase_module, "get_embedding_client", lambda: embedding_client)

    async def _fake_rpc(client, function_name, payload, **kwargs):
        _ = (client, function_name, payload, kwargs)
        return []

    monkeypatch.setattr(pipeline, "_rpc", _fake_rpc)

    plans = await _run_plan(pipeline, queries=["查询一", "查询二"], config=_config())

    assert isinstance(plans, list)
    # 1 failed batch call + 2 per-query fallback calls (original behavior).
    assert embedding_client.calls[0] == ["查询一", "查询二"]
    assert [call for call in embedding_client.calls[1:]] == [["查询一"], ["查询二"]]


# ── T4②: oracle — derivation ≡ old dedicated RPC, field by field ────────────


def _old_path_result(pipeline, all_rows, config):
    """What the dedicated RPC path returns: the DB applies threshold+count,
    the client applies the adoption filter chain."""
    search_threshold = pipeline._exact_vector_search_threshold(config)
    db_rows = [row for row in all_rows if float(row.get("similarity") or 0.0) >= search_threshold]
    db_rows = db_rows[: min(config.fetch_count, 5)]
    return pipeline._filter_exact_question_rows(
        db_rows,
        allowed_question_types=_ALLOWED_TYPES,
        original_query=_BANK_STEM,
        option_validation_required=False,
        config=config,
    )


def _new_path_result(pipeline, all_rows, config):
    """What the derivation sees: the regular bank query's rows (lower
    threshold, count=fetch_count) — then derives the exact subset."""
    bank_rows = [
        row
        for row in all_rows
        if float(row.get("similarity") or 0.0) >= config.match_threshold
    ][: config.fetch_count]
    return pipeline._derive_exact_from_bank_rows(
        bank_rows,
        allowed_question_types=_ALLOWED_TYPES,
        original_query=_BANK_STEM,
        option_validation_required=False,
        config=config,
    )


@pytest.mark.asyncio
async def test_oracle_hit_case_field_by_field_equal() -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    rows = [
        _bank_row("q-98", 0.98),
        _bank_row("q-95", 0.95),
        _bank_row("q-80", 0.80),
        _bank_row("q-60", 0.60),
        _bank_row("q-40", 0.40),
    ]

    old = _old_path_result(pipeline, rows, config)
    new = _new_path_result(pipeline, rows, config)

    assert new == old  # full dict equality, every field
    assert len(old) == 1 and old[0]["id"] == "q-98"
    assert old[0]["_source_group"] == "question_exact_vector"


@pytest.mark.asyncio
async def test_oracle_filter_chain_skips_to_next_eligible_row() -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    rows = [
        _bank_row("q-type-mismatch", 0.98, question_type="case_study"),  # fails type filter
        _bank_row("q-95", 0.95),
        _bank_row("q-72", 0.72),
        _bank_row("q-50", 0.50),
    ]

    old = _old_path_result(pipeline, rows, config)
    new = _new_path_result(pipeline, rows, config)

    assert new == old
    assert len(old) == 1 and old[0]["id"] == "q-95"


@pytest.mark.asyncio
async def test_oracle_empty_hit_case() -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    # All rows below exact_question_min_similarity (0.9) → both paths empty.
    rows = [_bank_row("q-85", 0.85), _bank_row("q-72", 0.72), _bank_row("q-40", 0.40)]

    old = _old_path_result(pipeline, rows, config)
    new = _new_path_result(pipeline, rows, config)

    assert old == [] and new == []


@pytest.mark.asyncio
async def test_oracle_truncation_semantics_match() -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    # Six rows above the search threshold; only the SIXTH would pass the
    # adoption filter — but the dedicated RPC never returned it
    # (count=min(fetch_count,5)), so BOTH paths must return empty.
    rows = [
        _bank_row("q-1", 0.98, question_type="case_study"),
        _bank_row("q-2", 0.97, question_type="case_study"),
        _bank_row("q-3", 0.96, question_type="case_study"),
        _bank_row("q-4", 0.95, question_type="case_study"),
        _bank_row("q-5", 0.94, question_type="case_study"),
        _bank_row("q-6", 0.93),  # would pass, but sits past the top-5 cut
    ]

    old = _old_path_result(pipeline, rows, config)
    new = _new_path_result(pipeline, rows, config)

    assert old == [] and new == []


def test_unsorted_bank_rows_disable_derivation() -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    rows = [_bank_row("q-72", 0.72), _bank_row("q-98", 0.98)]  # not similarity-desc

    assert (
        pipeline._derive_exact_from_bank_rows(
            rows,
            allowed_question_types=_ALLOWED_TYPES,
            original_query=_BANK_STEM,
            option_validation_required=False,
            config=config,
        )
        is None
    )


# ── T4②: RPC count + plan shape through _run_query_plan ─────────────────────


@pytest.mark.asyncio
async def test_q0_issues_single_bank_vector_rpc_and_still_emits_exact_plan(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    monkeypatch.setattr(supabase_module, "get_embedding_client", lambda: _CountingEmbeddingClient())

    rpc_calls: list[str] = []
    bank_rows = [_bank_row("q-98", 0.98), _bank_row("q-60", 0.60)]

    async def _fake_rpc(client, function_name, payload, **kwargs):
        _ = (client, payload, kwargs)
        rpc_calls.append(function_name)
        if function_name == "search_questions_bank_vector":
            return [dict(row) for row in bank_rows]
        return []

    monkeypatch.setattr(pipeline, "_rpc", _fake_rpc)

    plans = await _run_plan(
        pipeline, queries=["查询一"], config=_config(), exact_probe=_exact_probe()
    )

    # ONE bank-vector RPC for q0 (no dedicated exact-vector duplicate).
    assert rpc_calls.count("search_questions_bank_vector") == 1

    group_names = [plan["group_name"] for plan in plans]
    assert "question_exact_vector" in group_names
    # Plan position parity with the old dual-RPC path: right after questions_bank.
    assert group_names.index("question_exact_vector") == group_names.index("questions_bank") + 1

    exact_plan = next(plan for plan in plans if plan["group_name"] == "question_exact_vector")
    assert [item["id"] for item in exact_plan["results"]] == ["q-98"]
    assert exact_plan["query_weight"] == 1.0
    # questions_bank results keep their normalized shape (no raw-row leakage).
    bank_plan = next(plan for plan in plans if plan["group_name"] == "questions_bank")
    assert all("_raw_row" not in item for item in bank_plan["results"])


@pytest.mark.asyncio
async def test_q0_empty_bank_rows_still_emit_empty_exact_plan(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    monkeypatch.setattr(supabase_module, "get_embedding_client", lambda: _CountingEmbeddingClient())

    async def _fake_rpc(client, function_name, payload, **kwargs):
        _ = (client, function_name, payload, kwargs)
        return []

    monkeypatch.setattr(pipeline, "_rpc", _fake_rpc)

    plans = await _run_plan(
        pipeline, queries=["查询一"], config=_config(), exact_probe=_exact_probe()
    )

    exact_plans = [plan for plan in plans if plan["group_name"] == "question_exact_vector"]
    assert len(exact_plans) == 1 and exact_plans[0]["results"] == []


@pytest.mark.asyncio
async def test_small_fetch_count_keeps_the_dedicated_exact_rpc(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    monkeypatch.setattr(supabase_module, "get_embedding_client", lambda: _CountingEmbeddingClient())

    rpc_calls: list[str] = []

    async def _fake_rpc(client, function_name, payload, **kwargs):
        _ = (client, payload, kwargs)
        rpc_calls.append(function_name)
        return []

    monkeypatch.setattr(pipeline, "_rpc", _fake_rpc)

    await _run_plan(
        pipeline,
        queries=["查询一"],
        config=_config(fetch_count=4, top_k=2),  # below the >=5 superset gate
        exact_probe=_exact_probe(),
    )

    # Old dual-RPC behavior preserved when the superset precondition fails.
    assert rpc_calls.count("search_questions_bank_vector") == 2
