"""L1 瘦身检索：`retrieval_profile="case_grading_identity"` 的管线级不变量。

契约：contracts/rag.md 44。三条断言面——

1. **分母铁证**：同一批候选行下，lean 与 full 的 `exact_question`（含
   `covered_subquestions` / `covered_indexes`）**逐字段相同**。判分分母不变。
2. **可砍清单确实被砍**：questions_bank 以外的 source 检索、`_hydrate_sources`、
   `_rerank_results` 在 lean 下调用数为 0；`content` / `sources` 为空。
3. **必留清单还在**：exact 文本探针批、questions_bank 向量检索、以及 `case_like`
   强制 second pass（`covered_subquestions` 的主要来源）逐轮照跑。

外加陷阱②的回归：lean 的空 `content`/`sources` 是**正常终态**，
`retrieval_degraded` / `retrieval_status` 必须与 full 相同（`False` / `"ok"`）——
误判成降级会点亮降级闸，把正常判分回答降成「证据不足」。
"""

from __future__ import annotations

import pytest

CASE_QUERY = (
    "【背景资料】某新建办公楼工程，建筑面积 32000m2，地下 2 层，地上 12 层，"
    "现浇钢筋混凝土框架结构。施工单位与建设单位签订了施工总承包合同，"
    "基坑开挖深度为 6m，施工单位编制了基坑专项施工方案。\n"
    "【问题】\n1. 指出基坑施工中的不妥之处，并说明理由。\n"
    "2. 写出深基坑专项施工方案的论证要求。\n"
    "3. 列出模板拆除的条件。\n"
)

_BANK_ROW = {
    "id": 9348,
    "original_id": "E1",
    "stem": CASE_QUERY,
    "question_stem": "",
    "node_code": "1A420000",
    "source_type": "exam",
    "options": None,
    "correct_answer": "1. 不妥之处……\n2. 论证要求……\n3. 拆模条件……",
    "analysis": "解析全文",
    "question_type": "case_study",
    "similarity": 0.93,
    "source_chunk_id": "EXAM_1A420000_P0014_06",
    "exam_year": 2024,
    "background_context": None,
    "parent_id": None,
    "grading_rubric": None,
    "structured_rules": None,
    "logic_rule": None,
}


def _config(supabase_module):
    weights = {
        "textbook": 1.0,
        "standard": 1.2,
        "exam": 1.0,
        "questions_bank": 1.5,
        "question_exact_text": 4.2,
        "question_exact_vector": 3.4,
        "compiled_learning_truth": 0.6,
    }
    return supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",  # pragma: allowlist secret
        timeout_s=5.0,
        sources=["textbook", "standard", "exam"],
        include_questions=True,
        top_k=5,
        fetch_count=8,
        match_threshold=0.2,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights=dict(weights),
        question_weights=dict(weights),
        max_per_document=3,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=True,
        second_pass_max_queries=3,
        second_pass_min_hits=1,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=True,
        rerank_window=5,
        rerank_timeout_s=2.0,
        exact_question_enabled=True,
        exact_question_text_first=True,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
        query_plan_trace_enabled=True,
        compiled_truth_shadow_enabled=False,
        compiled_truth_enabled=False,
        provenance_boost_enabled=False,
    )


async def _run_search(monkeypatch: pytest.MonkeyPatch, *, retrieval_profile: str | None):
    """同一批候选行跑一次管线，返回 (payload, 各跳调用计数)。"""
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    pipeline = supabase_module.SupabasePipeline()
    config = _config(supabase_module)
    counters: dict[str, list | int] = {"source_groups": []}

    monkeypatch.setattr(pipeline, "_load_search_config", lambda **_kwargs: config)

    async def _available(**_kwargs):
        return None

    async def _client(*_args, **_kwargs):
        return object()

    async def _embed(_query):
        return [0.01] * 8

    async def _embed_batch(queries):
        return {query: [0.01] * 8 for query in queries}

    monkeypatch.setattr(pipeline, "_assert_data_api_available", _available)
    monkeypatch.setattr(pipeline, "_get_client", _client)
    monkeypatch.setattr(pipeline, "_embed_query", _embed)
    monkeypatch.setattr(pipeline, "_embed_queries_batch", _embed_batch)

    async def _search_source(*, client, query, vector_literal, source_type, config):
        counters["source_groups"].append(source_type)
        return [
            {
                "chunk_id": f"kb-{source_type}",
                "rag_content": f"{source_type} 教材正文",
                "score": 0.4,
                "source_type": source_type,
                "_source_table": "kb_chunks",
                "_source_group": source_type,
                "metadata": {},
            }
        ]

    async def _search_questions(*, client, vector_literal, config, raw_sink=None):
        counters["bank"] = int(counters.get("bank", 0)) + 1
        if raw_sink is not None:
            raw_sink.append(dict(_BANK_ROW))
        return [
            pipeline._normalize_question_result(
                dict(_BANK_ROW), source_group="questions_bank", score=0.93
            )
        ]

    async def _exact_text_batch(*, probe_queries, **_kwargs):
        counters["exact_text"] = int(counters.get("exact_text", 0)) + 1
        row = pipeline._normalize_question_result(
            dict(_BANK_ROW), source_group="question_exact_text", score=0.97
        )
        return [{"query": probe_queries[0], "results": [row]}]

    async def _rerank(*, query, results, config):
        counters["rerank"] = int(counters.get("rerank", 0)) + 1
        return list(results)

    async def _hydrate(results, *, config):
        counters["hydrate"] = int(counters.get("hydrate", 0)) + 1
        return results

    monkeypatch.setattr(pipeline, "_search_source", _search_source)
    monkeypatch.setattr(pipeline, "_search_questions", _search_questions)
    monkeypatch.setattr(pipeline, "_search_exact_question_text_batch", _exact_text_batch)
    monkeypatch.setattr(pipeline, "_rerank_results", _rerank)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _hydrate)

    kwargs: dict[str, str] = {}
    if retrieval_profile:
        kwargs["retrieval_profile"] = retrieval_profile
    payload = await pipeline.search(CASE_QUERY, "construction-exam", **kwargs)
    return payload, counters


@pytest.mark.asyncio
async def test_identity_profile_keeps_exact_question_and_denominator_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分母铁证：lean 与 full 的 exact payload 逐字段相同。

    砍掉的是产物加工，不是身份来源——`exact_question` 由 `all_plans` 的原始行算出，
    在 hydrate/rerank/正文拼装**之前**，因果方向与被砍的那些跳相反。
    """
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )

    full_payload, _ = await _run_search(monkeypatch, retrieval_profile=None)
    lean_payload, _ = await _run_search(
        monkeypatch, retrieval_profile=RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    )

    full_exact = full_payload.get("exact_question")
    lean_exact = lean_payload.get("exact_question")
    assert isinstance(full_exact, dict) and full_exact, "前提失效：full 轮必须命中 exact"
    # 逐字段相同（不是"都非空"）——这是分母不变的铁证。
    assert lean_exact == full_exact
    assert lean_exact["covered_indexes"] == full_exact["covered_indexes"]
    assert lean_exact["covered_subquestions"] == full_exact["covered_subquestions"]
    assert lean_exact["coverage_state"] == full_exact["coverage_state"]


@pytest.mark.asyncio
async def test_identity_profile_drops_only_the_零消费者_hops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """可砍清单被砍、必留清单还在。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )

    full_payload, full_counters = await _run_search(monkeypatch, retrieval_profile=None)
    lean_payload, lean_counters = await _run_search(
        monkeypatch, retrieval_profile=RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    )

    # ── 可砍：questions_bank 以外的 source 检索 / 全文水合 / rerank ──────────
    assert full_counters["source_groups"], "前提失效：full 轮必须检索 textbook/standard/exam"
    assert lean_counters["source_groups"] == []
    assert full_counters.get("hydrate") == 1
    assert lean_counters.get("hydrate", 0) == 0
    assert full_counters.get("rerank") == 1
    assert lean_counters.get("rerank", 0) == 0

    # ── 可砍：正文与 sources（直通轮零消费者）────────────────────────────────
    assert full_payload["content"] and full_payload["sources"]
    assert lean_payload["content"] == ""
    assert lean_payload["sources"] == []

    # ── 必留：exact 文本探针批 + bank 向量检索 + case_like 强制 second pass ──
    # bank 调用数 = 1 次 primary + N 次 second pass；lean 必须与 full 相同，
    # 少一次就意味着 covered_subquestions 的供给被削了（P0 兜底满分病复发）。
    assert lean_counters.get("exact_text") == full_counters.get("exact_text") == 1
    assert lean_counters.get("bank") == full_counters.get("bank")
    assert int(lean_counters.get("bank") or 0) > 1, "前提失效：case_like 必须触发 second pass"

    # ── 观测：profile 逐轮发声 ───────────────────────────────────────────────
    assert full_payload["retrieval_profile"] == "full"
    assert lean_payload["retrieval_profile"] == RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    lean_policy = lean_payload["evidence_bundle"]["trace"]["performance_policy"]
    assert lean_policy["retrieval_profile"] == RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    assert lean_policy["rerank_enabled"] is False


@pytest.mark.asyncio
async def test_identity_profile_empty_sources_is_not_a_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """陷阱②回归：空 content/sources 是正常终态，不得被标成 retrieval_degraded。

    降级标记会点亮三个降级闸，把正常判分回答降成「证据不足」。降级判据的单一
    权威仍是 `retrieval_warnings`，与 profile 无关。
    """
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY,
    )

    full_payload, _ = await _run_search(monkeypatch, retrieval_profile=None)
    lean_payload, _ = await _run_search(
        monkeypatch, retrieval_profile=RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY
    )

    assert lean_payload["retrieval_degraded"] == full_payload["retrieval_degraded"] is False
    assert lean_payload["retrieval_status"] == full_payload["retrieval_status"] == "ok"
    assert "warnings" not in lean_payload


@pytest.mark.asyncio
async def test_unknown_profile_falls_back_to_full_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """profile 是声明不是开关：未知/缺省值一律走全量管线（逐字节旧行为）。

    模型自发的 in-loop `rag` 调用永远不带这个键，必须落在这条分支上。
    """
    baseline_payload, baseline_counters = await _run_search(monkeypatch, retrieval_profile=None)
    unknown_payload, unknown_counters = await _run_search(
        monkeypatch, retrieval_profile="not_a_registered_profile"
    )

    assert unknown_counters["source_groups"] == baseline_counters["source_groups"]
    assert unknown_counters.get("rerank") == baseline_counters.get("rerank") == 1
    assert unknown_payload["content"] == baseline_payload["content"]
    assert unknown_payload["sources"] == baseline_payload["sources"]
