from __future__ import annotations

import pytest

from deeptutor.services.rag.pipelines.supabase_strategy import (
    build_exact_question_keyword_terms,
    build_exact_question_text_candidates,
    build_second_pass_queries,
    classify_query_shape,
    dedupe_ranked_results,
    expand_query_variants,
    extract_case_subquestion_items,
    extract_standard_codes,
    normalize_retrieval_query,
    matches_allowed_question_type,
    prepare_exact_question_probe,
    resolve_group_weights,
    rewrite_query,
    select_sources,
    should_run_second_pass,
    validate_exact_question_options,
)


def test_expand_query_variants_for_contrast_query() -> None:
    variants = expand_query_variants("防水等级和设防层数有什么区别？", max_variants=6)

    assert "防水等级和设防层数有什么区别？" in variants
    assert any("防水等级 定义 要求" == item for item in variants)
    assert any("设防层数 定义 要求" == item for item in variants)
    assert any("防水等级 设防层数 区别 关系" == item for item in variants)


def test_build_second_pass_queries_prefers_entity_specific_queries() -> None:
    queries = build_second_pass_queries("防水等级和设防层数有什么区别？", max_queries=2)

    assert len(queries) == 2
    assert queries[0] == "防水等级 定义 适用范围"
    assert queries[1] == "设防层数 定义 适用范围"


def test_should_run_second_pass_for_sparse_or_duplicate_results() -> None:
    assert should_run_second_pass(
        query="普通问题",
        results=[{"chunk_id": "a"}],
        top_k=5,
        min_hits=2,
    )
    assert should_run_second_pass(
        query="普通问题",
        results=[
            {"chunk_id": "a", "source": "doc-1"},
            {"chunk_id": "b", "source": "doc-1"},
            {"chunk_id": "c", "source": "doc-1"},
        ],
        top_k=5,
        min_hits=2,
        max_dup_ratio=0.5,
    )


def test_select_sources_prunes_question_noise_for_pure_concept_query() -> None:
    plan = select_sources("防水等级和设防层数有什么区别", include_questions_default=True)

    assert plan.search_questions_bank is True
    assert plan.search_exam_chunks is True
    assert plan.pruning_applied is False

    plan = select_sources("建筑防水等级划分依据和设防要求分别是什么，请系统解释原因", include_questions_default=True)
    assert plan.search_questions_bank is False
    assert plan.search_exam_chunks is False
    assert plan.pruning_applied is True


def test_select_sources_routes_standard_query_away_from_question_bank() -> None:
    plan = select_sources("GB 50345-2015 第3.0.1条对屋面防水等级怎么规定", include_questions_default=True)

    assert plan.query_shape == "standard_like"
    assert plan.search_questions_bank is False
    assert plan.search_exam_chunks is False


def test_select_sources_keeps_question_bank_for_mcq_like_query() -> None:
    plan = select_sources("单选题：确定屋面防水工程的防水等级应根据什么", include_questions_default=True)

    assert plan.query_shape == "mcq_like"
    assert plan.search_questions_bank is True


def test_select_sources_respects_upstream_question_type_for_ambiguous_query() -> None:
    plan = select_sources(
        "屋面防水等级",
        include_questions_default=True,
        question_type="single_choice",
    )

    assert plan.search_questions_bank is True
    assert "force_qbank_by_question_type" in plan.selection_reasons


def test_select_sources_respects_upstream_intent_for_answer_submission() -> None:
    plan = select_sources(
        "屋面防水等级",
        include_questions_default=True,
        intent="answer_questions",
    )

    assert plan.search_questions_bank is True
    assert "force_qbank_by_intent" in plan.selection_reasons


def test_select_sources_does_not_treat_preferred_question_type_as_current_question_type() -> None:
    plan = select_sources(
        "建筑防水等级划分依据和设防要求分别是什么，请系统解释原因",
        include_questions_default=True,
        routing_metadata={"preferred_question_type": "choice"},
    )

    assert plan.search_questions_bank is False
    assert plan.pruning_applied is True


def test_resolve_group_weights_matches_query_shape() -> None:
    mcq_weights = resolve_group_weights(
        "单选题：确定屋面防水工程的防水等级应根据什么",
        base_source_weights={"standard": 1.4, "textbook": 1.0, "exam": 0.7, "questions_bank": 0.4, "standard_precision": 2.2},
        base_question_weights={"standard": 1.4, "textbook": 1.0, "exam": 1.2, "questions_bank": 1.5, "standard_precision": 2.2},
    )
    standard_weights = resolve_group_weights(
        "GB 50345-2015 第3.0.1条对屋面防水等级怎么规定",
        base_source_weights={"standard": 1.4, "textbook": 1.0, "exam": 0.7, "questions_bank": 0.4, "standard_precision": 2.2},
        base_question_weights={"standard": 1.4, "textbook": 1.0, "exam": 1.2, "questions_bank": 1.5, "standard_precision": 2.2},
    )

    assert mcq_weights["questions_bank"] > mcq_weights["standard"]
    assert standard_weights["standard"] > standard_weights["questions_bank"]


def test_dedupe_ranked_results_removes_duplicate_stems() -> None:
    results = dedupe_ranked_results(
        [
            {"chunk_id": "q1", "card_title": "题目: 屋面防水等级", "rag_content": "【题目】屋面防水等级应根据什么\n【选项】A B C"},
            {"chunk_id": "q2", "card_title": "题目: 屋面防水等级", "rag_content": "【题目】屋面防水等级应根据什么\n【选项】A B C"},
            {"chunk_id": "q3", "card_title": "屋面工程", "rag_content": "【GB 50345】屋面工程应根据建筑物性质确定防水等级"},
        ]
    )

    assert [item["chunk_id"] for item in results] == ["q1", "q3"]


def test_classify_query_shape_for_mcq_stem_without_options() -> None:
    assert classify_query_shape("关于平屋面防水等级与做法，下列说法正确的是？") == "mcq_like"


def test_classify_query_shape_for_long_case_question() -> None:
    query = """
背景资料：
某旧城改造工程，建筑面积 20.50 万平方米，总投资 12.80 亿元，建设单位采用工程总承包模式发包。
问题：
1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？
2. 按照完全成本法计算的工程施工项目成本是多少亿元？
3. 分步骤列式计算钢结构装饰架的造价是多少万元？
"""

    assert classify_query_shape(query) == "case_like"


def test_select_sources_keeps_exam_paths_for_case_question() -> None:
    query = """
背景资料：
某旧城改造工程，建筑面积 20.50 万平方米，总投资 12.80 亿元，建设单位采用工程总承包模式发包。
问题：
1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？
2. 按照完全成本法计算的工程施工项目成本是多少亿元？
"""

    plan = select_sources(query, include_questions_default=True)

    assert plan.query_shape == "case_like"
    assert plan.search_exam_chunks is True
    assert plan.search_questions_bank is True
    assert plan.pruning_applied is False


def test_extract_standard_codes_normalizes_code_forms() -> None:
    assert extract_standard_codes("GB 50345-2015 第3.0.1条对屋面防水等级怎么规定") == ["GB50345-2015"]


def test_rewrite_query_enhances_mcq_stem() -> None:
    rewritten = rewrite_query(
        "单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积",
        max_variants=5,
    )

    assert rewritten.query_shape == "mcq_like"
    assert "屋面工程" in rewritten.primary_query
    assert rewritten.variants[0] == rewritten.primary_query


def test_normalize_retrieval_query_strips_exam_prefix_and_inline_options() -> None:
    normalized = normalize_retrieval_query(
        "2024年一级建造师《建筑实务》真题：关于屋面防水等级，下列说法正确的是（ ）A. 一级防水 B. 二级防水 C. 三级防水"
    )

    assert normalized.startswith("关于屋面防水等级")
    assert "真题" not in normalized
    assert "A." not in normalized


def test_expand_query_variants_includes_normalized_standard_codes() -> None:
    variants = expand_query_variants("GB 50345-2015 第3.0.1条对屋面防水等级怎么规定", max_variants=6)

    assert any(item == "GB50345-2015" for item in variants)


def test_prepare_exact_question_probe_extracts_stem_for_mcq_with_options() -> None:
    probe = prepare_exact_question_probe(
        "单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积"
    )

    assert probe is not None
    assert probe.query == "确定屋面防水工程的防水等级应根据什么"
    assert probe.allowed_question_types == ["single", "multi"]
    assert probe.option_validation_required is True


def test_prepare_exact_question_probe_skips_pure_concept_query() -> None:
    assert prepare_exact_question_probe("防水等级和设防层数有什么区别") is None


def test_prepare_exact_question_probe_skips_learning_strategy_prompt_with_exam_words() -> None:
    assert (
        prepare_exact_question_probe(
            "我现在最大问题不是听不懂，是记不住，做题时规范数字和条件全串了。给我一个今晚就能执行的冲刺学习法。"
        )
        is None
    )


def test_prepare_exact_question_probe_extracts_case_focus_query() -> None:
    query = """
背景资料：
某旧城改造工程，建筑面积 20.50 万平方米，总投资 12.80 亿元，建设单位采用工程总承包模式发包。
问题：
1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？
2. 按照完全成本法计算的工程施工项目成本是多少亿元？
"""

    probe = prepare_exact_question_probe(query)

    assert probe is not None
    assert probe.allowed_question_types == ["case", "case_study", "case_background", "calculation"]
    assert "资格预审" in probe.query
    assert probe.stripped_from_full_query is True


def test_build_exact_question_text_candidates_normalizes_mcq_surface() -> None:
    candidates = build_exact_question_text_candidates("确定屋面防水工程的防水等级应根据什么")

    assert "确定屋面防水工程的防水等级应根据什么" in candidates
    assert "确定屋面防水工程的防水等级应根据" in candidates
    assert "确定屋面防水工程的防水等级应根据（ ）" in candidates


def test_build_exact_question_keyword_terms_prefers_core_tokens() -> None:
    terms = build_exact_question_keyword_terms("确定屋面防水工程的防水等级应根据什么", max_terms=3)

    assert "防水等级" in terms or "屋面防水工程" in terms


def test_expand_query_variants_extracts_case_subquestions() -> None:
    query = """
背景资料：
某旧城改造工程，建筑面积 20.50 万平方米，总投资 12.80 亿元，建设单位采用工程总承包模式发包。
问题：
1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？
2. 按照完全成本法计算的工程施工项目成本是多少亿元？
3. 分步骤列式计算钢结构装饰架的造价是多少万元？
"""

    variants = expand_query_variants(query, max_variants=6)

    assert any("资格预审" in item for item in variants)
    assert any("完全成本法" in item for item in variants)


def test_extract_case_subquestion_items_preserves_indices() -> None:
    query = """
背景资料：
某旧城改造工程，建筑面积 20.50 万平方米，总投资 12.80 亿元。
问题：
1. 通常进行资格预审的工程有哪些特点？资格预审的方法有哪些？
2. 按照完全成本法计算的工程施工项目成本是多少亿元？
3. 分步骤列式计算钢结构装饰架的造价是多少万元？
"""

    items = extract_case_subquestion_items(query, max_items=5)

    assert [item["display_index"] for item in items] == ["1", "2", "3"]
    assert "资格预审" in items[0]["prompt"]
    assert "完全成本法" in items[1]["prompt"]


def test_validate_exact_question_options_requires_overlap() -> None:
    assert validate_exact_question_options(
        original_query="单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积",
        options={"A": "建筑物类别", "B": "建筑物用途"},
        option_validation_required=True,
    )
    assert not validate_exact_question_options(
        original_query="单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积",
        options={"A": "地下工程埋置深度", "B": "防水混凝土强度"},
        option_validation_required=True,
    )


def test_validate_exact_question_options_supports_list_payloads() -> None:
    assert validate_exact_question_options(
        original_query="单选题：确定屋面防水工程的防水等级应根据什么\nA. 建筑物类别\nB. 建筑物面积",
        options=["A. 建筑物类别", "B. 建筑物用途"],
        option_validation_required=True,
    )


def test_matches_allowed_question_type_uses_alias_table_not_substring_match() -> None:
    assert matches_allowed_question_type("single_choice", ["single"])
    assert not matches_allowed_question_type("case_study_followup", ["case_study"])


@pytest.mark.asyncio
async def test_supabase_search_raises_typed_error_on_primary_failure() -> None:
    from types import SimpleNamespace

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

    async def _fake_get_client(*args, **kwargs):
        _ = (args, kwargs)
        return object()

    async def _raise_runtime_error(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("primary plan exploded")

    pipeline._load_search_config = lambda **kwargs: config
    pipeline._get_client = _fake_get_client
    pipeline._run_query_plan = _raise_runtime_error
    supabase_module.rewrite_query = lambda query, max_variants=1: SimpleNamespace(
        primary_query=query,
        query_shape="concept_like",
        standard_codes=[],
        keywords=[],
        reasons=[],
    )
    supabase_module.is_question_like_query = lambda query: False
    supabase_module.select_sources = lambda *args, **kwargs: SimpleNamespace(
        search_textbook_chunks=True,
        search_standard_chunks=False,
        search_exam_chunks=False,
        search_questions_bank=False,
        to_trace_dict=lambda: {},
        selection_reasons=[],
    )
    supabase_module.classify_query_shape = lambda query: "concept_like"
    supabase_module.expand_query_variants = lambda query, max_variants=1: [query]

    with pytest.raises(RAGSearchError) as exc_info:
        await pipeline.search(query="防水等级", kb_name="construction-exam")

    err = exc_info.value
    assert err.provider == "supabase"
    assert err.kb_name == "construction-exam"
    assert err.query == "防水等级"
    assert err.stage == "pipeline.search"
    assert "primary plan exploded" in str(err)
