"""`retrieval_profile="unanchored_exam_query"` 的管线级不变量（contracts/rag.md 44）。

low_information_exam_query 锁权轮的题面供给收口:该 profile 下题目面两通道
（questions_bank 检索族 + exam 卷面 chunk）在**同一条管线内**不武装——bank 向量、
exact 文本探针、由 bank 行派生的 question_exact_vector、case second pass、
`exact_question` payload 全部连锁熄灭;教材/规范通道照常,正文与 sources 不含任何
题目面材料。缺省/其他 profile 逐字节旧行为。

TutorBot 侧的唯一声明点（RAGAdapterTool.execute）由
`tests/tutorbot/test_low_information_bank_disarm.py` 钉住。
"""

from __future__ import annotations

import pytest

QUERY = "2025年一建建筑实务真题第3题的答案是什么？"

_BANK_ROW = {
    "id": 9502,
    "original_id": "Q3",
    "stem": "混凝土结构工程施工中,同条件养护试件的留置组数应满足（ ）。",
    "question_stem": "",
    "node_code": "1A410000",
    "source_type": "exam",
    "options": [{"key": "A", "value": "15MPa"}, {"key": "B", "value": "10MPa"}],
    "correct_answer": "A",
    "analysis": "正确答案: A,依据教材……",
    "question_type": "single",
    "similarity": 0.91,
    "source_chunk_id": "EXAM_1A410000_P0003_01",
    "exam_year": 2015,
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
        rerank_enabled=False,
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
                "rag_content": f"{source_type} 正文段落",
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
                dict(_BANK_ROW), source_group="questions_bank", score=0.91
            )
        ]

    async def _exact_text_batch(*, probe_queries, **_kwargs):
        counters["exact_text"] = int(counters.get("exact_text", 0)) + 1
        return []

    async def _hydrate(results, *, config):
        counters["hydrate"] = int(counters.get("hydrate", 0)) + 1
        return results

    monkeypatch.setattr(pipeline, "_search_source", _search_source)
    monkeypatch.setattr(pipeline, "_search_questions", _search_questions)
    monkeypatch.setattr(pipeline, "_search_exact_question_text_batch", _exact_text_batch)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _hydrate)

    kwargs: dict[str, str] = {}
    if retrieval_profile:
        kwargs["retrieval_profile"] = retrieval_profile
    payload = await pipeline.search(QUERY, "construction-exam", **kwargs)
    return payload, counters


@pytest.mark.asyncio
async def test_disarmed_profile_supplies_no_question_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """题目面两通道整轮不武装:bank 检索族调用数 0、exam chunk 不检索、
    exact_question 不产出;教材/规范照常。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    full_payload, full_counters = await _run_search(monkeypatch, retrieval_profile=None)
    disarmed_payload, disarmed_counters = await _run_search(
        monkeypatch, retrieval_profile=RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )

    # 前提:full 轮确实检索 bank + exam(该 query exam_like → force_qbank)。
    assert int(full_counters.get("bank") or 0) >= 1, "前提失效:full 轮必须检索 bank"
    assert "exam" in full_counters["source_groups"], "前提失效:full 轮必须检索 exam chunk"

    # 题目面供给不武装。
    assert int(disarmed_counters.get("bank") or 0) == 0
    assert int(disarmed_counters.get("exact_text") or 0) == 0
    assert "exam" not in disarmed_counters["source_groups"]
    # 教材/规范照常武装。
    assert "textbook" in disarmed_counters["source_groups"]
    assert "standard" in disarmed_counters["source_groups"]

    # 产物面:无 exact 权威、无 bank/exam source、正文无答案钥匙。
    assert not disarmed_payload.get("exact_question")
    for item in disarmed_payload.get("sources") or []:
        assert str(item.get("source_table") or "") != "questions_bank"
        assert str(item.get("source_type") or "") != "exam"
    content = str(disarmed_payload.get("content") or "") + str(disarmed_payload.get("answer") or "")
    assert "【答案】" not in content and "【解析】" not in content

    # 观测:profile 逐轮发声。
    assert disarmed_payload["retrieval_profile"] == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    assert full_payload["retrieval_profile"] == "full"


@pytest.mark.asyncio
async def test_absent_profile_is_byte_for_byte_previous_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺省 = 全量管线(bank + exam 照常)——disarm 只在显式声明时生效。"""
    payload, counters = await _run_search(monkeypatch, retrieval_profile=None)
    assert int(counters.get("bank") or 0) >= 1
    assert "exam" in counters["source_groups"]
    assert any(
        str(item.get("source_table") or "") == "questions_bank"
        for item in payload.get("sources") or []
    )


@pytest.mark.asyncio
async def test_disarmed_round_retrieval_plan_trace_is_honest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F8 观测诚实:锁权轮导出的 retrieval_plan 不得声称查了题库/试卷——
    Langfuse trace 是本项目的定位权威,撒谎的 plan 会把健康轮误诊成回归
    (或未来事故时把人引到错误层)。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    payload, _ = await _run_search(
        monkeypatch, retrieval_profile=RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )
    plan = (payload.get("evidence_bundle") or {}).get("retrieval_plan") or {}
    groups = {
        str(group.get("name") or ""): group
        for group in plan.get("source_groups") or []
        if isinstance(group, dict)
    }
    assert groups, "前提失效:evidence_bundle.retrieval_plan.source_groups 缺失"
    assert groups["questions_bank"]["enabled"] is False
    assert groups["exam"]["enabled"] is False
    # 对照:full 轮 plan 照实声明查了题库。
    full_payload, _ = await _run_search(monkeypatch, retrieval_profile=None)
    full_plan = (full_payload.get("evidence_bundle") or {}).get("retrieval_plan") or {}
    full_groups = {
        str(group.get("name") or ""): group
        for group in full_plan.get("source_groups") or []
        if isinstance(group, dict)
    }
    assert full_groups["questions_bank"]["enabled"] is True


# --------------------------------------------------------------------------- #
# F2+F7:执法上移 RAGService(provider 无关)——历史真题回注跳过 + 不识 profile     #
# 的 provider fail-closed(禁供给而非静默 no-op)。                               #
# --------------------------------------------------------------------------- #

_HISTORICAL_EXACT = {
    "question_id": "2015-3",
    "question": "某历史真题题干……",
    "correct_answer": "C",
    "analysis": "标准答案:C……",
    "match_type": "exact",
    "answer_kind": "mcq",
}


def _service():
    from deeptutor.services.rag.service import RAGService

    return RAGService(provider="supabase")


def test_historical_question_fallback_is_skipped_on_disarmed_rounds(monkeypatch) -> None:
    """F2 错误路:pipeline 失败时的 historical-question 兜底会整段回注
    『【题库原题】…标准答案…解析…』——锁权轮必须跳过(供给收权在 service 层同样生效)。"""
    from deeptutor.services.rag import service as service_module
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    monkeypatch.setattr(
        service_module, "resolve_historical_question", lambda _q: dict(_HISTORICAL_EXACT)
    )
    svc = _service()

    armed = svc._build_historical_question_result(
        query=QUERY, kb_name="construction-exam", provider="supabase", search_kwargs={}
    )
    assert isinstance(armed, dict) and armed.get("exact_question"), "前提失效:常规轮兜底应命中"

    disarmed = svc._build_historical_question_result(
        query=QUERY,
        kb_name="construction-exam",
        provider="supabase",
        search_kwargs={"retrieval_profile": RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY},
    )
    assert disarmed is None, "锁权轮 historical 兜底仍回注题库原题(F2)"


def test_apply_historical_question_context_is_skipped_on_disarmed_rounds(monkeypatch) -> None:
    """F2 成功路:service 在 pipeline 结果之上的 historical 回注同样受锁权约束。"""
    from deeptutor.services.rag import service as service_module
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    monkeypatch.setattr(
        service_module, "resolve_historical_question", lambda _q: dict(_HISTORICAL_EXACT)
    )
    svc = _service()

    result = {"query": QUERY, "answer": "", "content": "", "sources": []}
    svc._apply_historical_question_context(
        result, retrieval_profile=RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )
    assert not result.get("exact_question")
    assert "标准答案" not in str(result.get("answer") or "")

    armed = {"query": QUERY, "answer": "", "content": "", "sources": []}
    svc._apply_historical_question_context(armed)
    assert armed.get("exact_question"), "前提失效:常规轮回注应生效"


@pytest.mark.asyncio
async def test_service_fails_closed_when_provider_does_not_echo_disarm(monkeypatch) -> None:
    """F7:不识 profile 的 provider(llamaindex/kbv5)静默吞掉声明 = 题面供给
    照旧的假收口。service 层以『结果必须回声 profile』为可证伪判据,不回声即
    fail-closed(本轮不供给,宁空不冒充)。"""
    from deeptutor.services.rag import service as service_module
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    class _IgnorantPipeline:
        async def search(self, *, query, kb_name, **kwargs):
            # 不识 retrieval_profile 的 provider:照常返回含真题+答案的材料。
            return {
                "answer": "【题库原题】某真题……标准答案:C 解析:……",
                "content": "【题库原题】某真题……标准答案:C 解析:……",
                "sources": [{"chunk_id": "doc-1", "source_type": "exam"}],
                "exact_question": {"question_id": "x", "correct_answer": "C"},
            }

    monkeypatch.setattr(service_module, "get_pipeline", lambda *a, **k: _IgnorantPipeline())
    monkeypatch.setattr(service_module, "resolve_historical_question", lambda _q: None)
    svc = _service()

    result = await svc.search(
        query=QUERY,
        kb_name="construction-exam",
        retrieval_profile=RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    assert str(result.get("answer") or "") == "" and str(result.get("content") or "") == ""
    assert result.get("sources") == []
    assert not result.get("exact_question")
    assert result.get("retrieval_status") == "question_surface_disarm_unsupported"


@pytest.mark.asyncio
async def test_service_passes_through_when_provider_echoes_disarm(monkeypatch) -> None:
    """回声即放行:supabase 管线已自证按 profile 收供给,service 不二次改写。"""
    from deeptutor.services.rag import service as service_module
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    class _HonoringPipeline:
        async def search(self, *, query, kb_name, **kwargs):
            return {
                "answer": "教材:混凝土强度……",
                "content": "教材:混凝土强度……",
                "sources": [{"chunk_id": "kb-textbook", "source_type": "textbook"}],
                "exact_question": {},
                "retrieval_profile": RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
            }

    monkeypatch.setattr(service_module, "get_pipeline", lambda *a, **k: _HonoringPipeline())
    monkeypatch.setattr(service_module, "resolve_historical_question", lambda _q: None)
    svc = _service()

    result = await svc.search(
        query=QUERY,
        kb_name="construction-exam",
        retrieval_profile=RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    assert "教材" in str(result.get("answer") or "")
    assert result.get("sources")
