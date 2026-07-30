from __future__ import annotations

import pytest

from deeptutor.services.rag.pipelines.supabase_strategy import (
    build_exact_question_keyword_terms,
    build_exact_question_text_candidates,
    build_second_pass_queries,
    classify_query_shape,
    dedupe_ranked_results,
    exact_question_identity_corresponds,
    expand_query_variants,
    extract_case_subquestion_items,
    extract_standard_codes,
    matches_allowed_question_type,
    normalize_retrieval_query,
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


def test_citation_wording_does_not_turn_textbook_query_into_standard_query() -> None:
    query = "防火门等级和使用部位怎么区分？请按2026年一级建造师建筑实务教材口径回答，并在最后附依据。"
    plan = select_sources(query, include_questions_default=True)
    weights = resolve_group_weights(
        query,
        base_source_weights={"standard": 1.4, "textbook": 1.0, "exam": 0.7, "questions_bank": 0.4, "standard_precision": 2.2},
        base_question_weights={"standard": 1.4, "textbook": 1.0, "exam": 1.2, "questions_bank": 1.5, "standard_precision": 2.2},
    )

    assert plan.query_shape == "concept_like"
    assert plan.search_textbook_chunks is True
    assert plan.search_questions_bank is False
    assert weights["textbook"] > weights["standard"]


def test_design_requirement_wording_is_not_calculation_query() -> None:
    plan = select_sources("建筑防水等级划分依据和设防要求分别是什么，请系统解释原因", include_questions_default=True)

    assert plan.query_shape == "concept_like"
    assert plan.search_questions_bank is False


@pytest.mark.parametrize(
    "query",
    [
        "求总工期",
        "求流水步距",
        "求最大弯矩",
        "求配筋率",
        "求混凝土用量",
    ],
)
def test_short_calculation_requests_still_route_to_calc_like(query: str) -> None:
    plan = select_sources(query, include_questions_default=True)

    assert plan.query_shape == "calc_like"


def test_normative_standard_phrasing_still_routes_to_standard_sources() -> None:
    plan = select_sources("建筑防火规范对防火门等级使用部位有哪些规定", include_questions_default=True)

    assert plan.query_shape == "standard_like"
    assert plan.search_questions_bank is False


def test_standard_answer_wording_is_not_normative_standard_query() -> None:
    plan = select_sources("这道题的标准答案和采分标准是什么", include_questions_default=True)

    assert plan.query_shape != "standard_like"


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


def test_resolve_group_weights_prefers_textbook_for_concept_teaching() -> None:
    weights = resolve_group_weights(
        "防火门等级和使用部位怎么区分",
        base_source_weights={"standard": 1.4, "textbook": 1.0, "exam": 0.7, "questions_bank": 0.4, "standard_precision": 2.2},
        base_question_weights={"standard": 1.4, "textbook": 1.0, "exam": 1.2, "questions_bank": 1.5, "standard_precision": 2.2},
    )

    assert weights["textbook"] > weights["standard"]


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


def test_prepare_exact_question_probe_strips_leading_punctuation_from_mcq_stem() -> None:
    probe = prepare_exact_question_probe(
        ".结构的可靠性包括（ ）\nA.稳定 B.安全性\nC.耐久性 D.经济性\nE.适用性"
    )

    assert probe is not None
    assert probe.query == "结构的可靠性包括"
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


@pytest.mark.parametrize("query", ["2025真题", "历年真题", "防水真题", "2025真题有哪些", "2025真题答案"])
def test_prepare_exact_question_probe_skips_low_information_exam_query(query: str) -> None:
    assert prepare_exact_question_probe(query) is None


def test_prepare_exact_question_probe_bounds_calculation_authority_types() -> None:
    query = (
        "背景：某工程到第6个月末：计划完成工程量8000m²，预算单价500元/m²；"
        "实际完成工程量7500m²，实际单价520元/m²。\n"
        "问题：计算BCWS、BCWP、ACWP，帮我算出答案"
    )

    probe = prepare_exact_question_probe(query)

    assert classify_query_shape(query) == "calc_like"
    assert probe is not None
    assert probe.allowed_question_types == ["calculation", "single", "multi", "free_text"]
    assert "calc_allowed_types" in probe.reason


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


def test_build_exact_question_text_candidates_strips_leading_punctuation() -> None:
    candidates = build_exact_question_text_candidates(".结构的可靠性包括")

    assert "结构的可靠性包括" in candidates


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


def test_validate_exact_question_options_accepts_short_chinese_option_overlap() -> None:
    assert validate_exact_question_options(
        original_query=".结构的可靠性包括（ ）\nA.稳定 B.安全性\nC.耐久性 D.经济性\nE.适用性",
        options=[
            {"key": "A", "value": "稳定"},
            {"key": "B", "value": "安全性"},
            {"key": "C", "value": "耐久性"},
            {"key": "D", "value": "经济性"},
            {"key": "E", "value": "适用性"},
        ],
        option_validation_required=True,
    )
    assert not validate_exact_question_options(
        original_query=".结构的可靠性包括（ ）\nA.稳定 B.安全性",
        options=[
            {"key": "A", "value": "防水"},
            {"key": "B", "value": "屋面"},
            {"key": "C", "value": "荷载"},
        ],
        option_validation_required=True,
    )


def test_matches_allowed_question_type_uses_alias_table_not_substring_match() -> None:
    assert matches_allowed_question_type("single_choice", ["single"])
    assert not matches_allowed_question_type("case_study_followup", ["case_study"])
    assert not matches_allowed_question_type("single_choice", [])


@pytest.mark.asyncio
async def test_supabase_search_raises_typed_error_on_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(supabase_module, "rewrite_query", lambda query, max_variants=1: SimpleNamespace(
        primary_query=query,
        normalized_query=query,
        query_shape="concept_like",
        standard_codes=[],
        keywords=[],
        reasons=[],
    ))
    monkeypatch.setattr(supabase_module, "is_question_like_query", lambda query: False)
    monkeypatch.setattr(supabase_module, "select_sources", lambda *args, **kwargs: SimpleNamespace(
        search_textbook_chunks=True,
        search_standard_chunks=False,
        search_exam_chunks=False,
        search_questions_bank=False,
        to_trace_dict=lambda: {},
        selection_reasons=[],
    ))
    monkeypatch.setattr(supabase_module, "classify_query_shape", lambda query: "concept_like")
    monkeypatch.setattr(supabase_module, "expand_query_variants", lambda query, max_variants=1: [query])

    with pytest.raises(RAGSearchError) as exc_info:
        await pipeline.search(query="防水等级", kb_name="construction-exam")

    err = exc_info.value
    assert err.provider == "supabase"
    assert err.kb_name == "construction-exam"
    assert err.query == "防水等级"
    assert err.stage == "pipeline.search"
    assert "primary plan exploded" in str(err)


# Bug#6: question_exact_text keyword false-positive. A keyword search on a shared
# common term ("混凝土") returned a totally unrelated bank MCQ and surfaced its
# answer as authoritative. Since the 2026-07-12 semantic-integrity campaign the
# rejector is the identity adjudicator (exact_question_identity_corresponds):
# incidental keyword overlap is relevance, never identity.
_FALSE_STEM = "地下工程的防水等级分为（  ），防水混凝土的适用环境温度不得高于（  ）。"


def test_stem_correspondence_rejects_incidental_keyword_match() -> None:
    from deeptutor.services.rag.pipelines.supabase_strategy import (
        exact_question_identity_corresponds,
    )

    # the production false positive: chitchat sharing only "混凝土" with the stem
    assert not exact_question_identity_corresponds(
        original_query="我是二建零基础小白，钢筋和混凝土哪个硬啊？",
        matched_stem=_FALSE_STEM,
        question_type="single_choice",
    )
    # a comparison that shares no discriminative content at all
    assert not exact_question_identity_corresponds(
        original_query="水泥和钢筋哪个贵？",
        matched_stem=_FALSE_STEM,
        question_type="single_choice",
    )


# NOTE(2026-07-12 semantic-integrity campaign): the old companion test
# test_stem_correspondence_accepts_real_paraphrase_or_paste was removed on
# purpose. Asking ABOUT one blank of a bank stem is relevance, not identity —
# under the identity adjudicator it falls open to normal RAG instead of
# minting an exact chapter. See test_identity_paraphrase_is_not_identity.


def test_calculation_stem_correspondence_rejects_different_numeric_identity() -> None:
    query = (
        "背景：某工程到第6个月末：计划完成工程量8000m²，预算单价500元/m²；"
        "实际完成工程量7500m²，实际单价520元/m²。"
        "问题：计算BCWS、BCWP、ACWP，帮我算出答案"
    )
    bank_stem = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。"

    assert not exact_question_identity_corresponds(
        original_query=query,
        matched_stem=bank_stem,
        question_type="single_choice",
    )


def test_calculation_stem_correspondence_rejects_same_numbers_different_target() -> None:
    query = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时费用偏差为多少万元？"
    bank_stem = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。"

    assert not exact_question_identity_corresponds(
        original_query=query,
        matched_stem=bank_stem,
        question_type="single_choice",
    )


def test_calculation_stem_correspondence_rejects_same_numbers_swapped_roles() -> None:
    query = "某工程计划完成工程量3000m3，预算成本单价150元/m3，现已完成5000m3，实际价是200元/m3，此时进度偏差为多少万元？"
    bank_stem = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。"

    assert not exact_question_identity_corresponds(
        original_query=query,
        matched_stem=bank_stem,
        question_type="single_choice",
    )


def test_calculation_stem_correspondence_accepts_target_alias() -> None:
    query = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时CV为多少万元？"
    bank_stem = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时费用偏差为（　　）万元。"

    assert exact_question_identity_corresponds(
        original_query=query,
        matched_stem=bank_stem,
        question_type="single_choice",
    )


def test_calculation_stem_correspondence_accepts_role_aliases() -> None:
    query = "某工程计划完成工程量5000m3，预算单价150元/m3，实际完成工程量3000m3，实际单价200元/m3，此时进度偏差为多少万元？"
    bank_stem = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。"

    assert exact_question_identity_corresponds(
        original_query=query,
        matched_stem=bank_stem,
        question_type="single_choice",
    )


def test_calculation_stem_correspondence_accepts_same_calculation_question() -> None:
    query = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为多少万元？"
    bank_stem = "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。"

    assert exact_question_identity_corresponds(
        original_query=query,
        matched_stem=bank_stem,
        question_type="single_choice",
    )


def test_stem_correspondence_skips_case_study_and_empty() -> None:
    # case_study matches use bundle coverage, not surface overlap — never gated here
    assert exact_question_identity_corresponds(
        original_query="背景资料：某项目……问题一：……",
        matched_stem=_FALSE_STEM,
        question_type="case_study",
    )
    # an empty matched stem cannot be an authoritative exact match
    assert not exact_question_identity_corresponds(
        original_query="防水混凝土温度",
        matched_stem="",
        question_type="single_choice",
    )


# ---------------------------------------------------------------------------
# Identity adjudication (semantic-integrity campaign, 2026-07-12)
#
# "学员本轮粘贴的题是否=题库某道原题" is an IDENTITY judgement, not a relevance
# judgement. The single falsifiable adjudicator is
# exact_question_identity_corresponds: normalized containment (bank stem ⊆
# learner text or learner text ⊆ bank stem) with a char-level coverage >= 0.90
# tolerance supplement for typos/line breaks. Bigram coverage has NO standalone
# authorization power any more (production live: cov 0.36 same-domain hijack).
# ---------------------------------------------------------------------------

def _identity(
    query: str,
    stem: str,
    question_type: str = "single_choice",
    options: list[str] | None = None,
) -> bool:
    from deeptutor.services.rag.pipelines.supabase_strategy import (
        exact_question_identity_corresponds,
    )

    return exact_question_identity_corresponds(
        original_query=query,
        matched_stem=stem,
        question_type=question_type,
        matched_options=options,
    )


_RED_STEM = "屋面防水等级为一级时,防水层合理使用年限不应少于(　)年。"


def test_identity_rejects_same_domain_relevance_hit() -> None:
    # RED anchor: bigram coverage 0.36 (>= old 0.30 floor) used to mint a false
    # exact chapter. Same domain (屋面防水等级一级), different question — the
    # learner asked a 做法-judgement MCQ, the bank row asks 合理使用年限.
    assert not _identity("下列关于屋面防水等级为一级的做法正确的是？", _RED_STEM)


def test_identity_regression_earned_value_bank_row_not_minted() -> None:
    # Production live hijack (question-14422 shape): free earned-value
    # calculation pasted by learner vs a bank row with different numbers.
    query = (
        "背景：某工程到第6个月末：计划完成工程量8000m²，预算单价500元/m²；"
        "实际完成工程量7500m²，实际单价520元/m²。"
        "问题：计算BCWS、BCWP、ACWP，帮我算出答案"
    )
    bank_stem = (
        "某工程计划完成工程量5000m3，预算成本单价150元/m3，"
        "现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。"
    )
    assert not _identity(query, bank_stem)


@pytest.mark.parametrize(
    ("query", "stem"),
    [
        (  # 防水
            "地下防水工程的防水混凝土配合比应符合下列哪项规定？",
            "屋面防水等级为一级时，防水层合理使用年限不应少于（　）年。",
        ),
        (  # 混凝土
            "关于大体积混凝土浇筑施工的说法，正确的是（　）。",
            "混凝土浇筑过程中，混凝土的自由倾落高度不应超过（　）m。",
        ),
        (  # 脚手架
            "关于扣件式钢管脚手架搭设的说法，正确的有（　）。",
            "扣件式钢管脚手架立杆基础验收合格后，纵距允许偏差为（　）mm。",
        ),
        (  # 网络计划
            "某双代号网络计划中，关键线路的确定依据是（　）。",
            "某工程双代号网络计划如下图，工作M的总时差为（　）天。",
        ),
        (  # 安全管理
            "施工现场安全管理中，专职安全生产管理人员的配备要求是（　）。",
            "建筑施工企业安全生产管理机构专职安全生产管理人员的职责不包括（　）。",
        ),
    ],
)
def test_identity_rejects_adversarial_same_domain_pairs(query: str, stem: str) -> None:
    # Same construction-exam domain vocabulary, different questions — none of
    # these may be adjudicated as the same bank question.
    assert not _identity(query, stem)


@pytest.mark.parametrize(
    ("query", "stem"),
    [
        # single load-bearing char differs (一级 vs 二级) — different question;
        # pre-hardening this cleared 0.90 ordered coverage (12/13) and minted.
        ("屋面防水等级为一级时怎么做？", "屋面防水等级为二级时怎么做？"),
        # numeric fact differs (7天 vs 14天) — the daowu-shaped confusion pair.
        ("混凝土浇水养护不得少于7天的是？", "混凝土浇水养护不得少于14天的是？"),
    ],
)
def test_identity_rejects_short_window_near_miss_pairs(query: str, stem: str) -> None:
    # 指挥官加固(2026-07-12): a 12-19 normalized-char surface is too thin for
    # the fuzzy-coverage path — one load-bearing char can differ and still
    # clear 0.90 coverage. Coverage may only decide identity on >=20-char
    # surfaces (_IDENTITY_MIN_FUZZY_SURFACE_LEN); these pairs must fall open.
    assert not _identity(query, stem)


def test_identity_short_verbatim_containment_still_hits() -> None:
    # The containment path keeps the 12-char floor: a short stem pasted
    # verbatim (with a colloquial prefix) is still identity — the fuzzy-path
    # hardening must not over-kill verbatim pastes of short stems.
    assert _identity("帮我看看这道题：屋面防水等级为一级时怎么做？", "屋面防水等级为一级时怎么做？")


@pytest.mark.parametrize(
    ("query", "stem"),
    [
        # >=20-char surface, only the load-bearing numeral differs (一级→二级):
        # 0.95+ char coverage but a CHANGED question — the numeric-fact
        # rejector must refuse to mint the wrong variant's standard answer.
        (
            "屋面防水等级为二级时,防水层合理使用年限不应少于(　)年。",
            _RED_STEM,
        ),
        # 7天 vs 14天 on a >=20-char stem (daowu-shaped confusion).
        (
            "混凝土浇水养护时间不得少于14天的部位是哪些？",
            "混凝土浇水养护时间不得少于7天的部位是哪些？",
        ),
    ],
)
def test_identity_rejects_numeral_variant_questions(query: str, stem: str) -> None:
    # 指挥官加固(2026-07-12): fuzzy coverage cannot tell a typo from a changed
    # numeral — every numeral+unit fact of the bank stem must appear verbatim
    # in the learner surface, else the fuzzy path falls open.
    assert not _identity(query, stem)


def test_identity_merged_options_requires_stem_presence() -> None:
    # 指挥官加固(2026-07-12): the merged (stem+options) surface may be
    # dominated by the options — an options-only paste must NOT decide
    # identity; the stem must be independently covered.
    options = [
        "单跨构件宜从跨端一侧向另一侧吊装",
        "单跨结构可从跨中间向两端吊装",
        "单跨结构不可从跨两端向中间吊装",
        "多跨结构宜先吊副跨后吊主跨",
        "多台起重设备共同作业时，可多跨同时吊装",
    ]
    options_only_paste = "\n".join(
        f"{letter}.{value}" for letter, value in zip("ABCDE", options)
    )
    assert not _identity(options_only_paste, "吊装顺序的正确说法", options=options)
    # Counter-check: stem present (with one typo) + near-verbatim options IS
    # identity via the merged surface (the WP1 option-match scenario).
    with_stem = "关于单层钢结构吊装顺序的说法，正确的有（ ）。\n" + options_only_paste
    assert _identity(with_stem, "关于单跨钢结构吊装顺序的说法，正确的有（　　）。", options=options)


@pytest.mark.parametrize(
    "query",
    [
        # verbatim stem only
        "屋面防水等级为一级时,防水层合理使用年限不应少于(　)年。",
        # verbatim stem + options
        "屋面防水等级为一级时,防水层合理使用年限不应少于(　)年。\nA. 10\nB. 15\nC. 20\nD. 25",
        # colloquial prefix/suffix around a verbatim paste
        "老师帮我看看这道题：屋面防水等级为一级时,防水层合理使用年限不应少于(　)年。这题选什么呀",
        # 1-2 typos (年现 for 年限) — similarity supplement must keep it
        "屋面防水等级为一级时,防水层合理使用年现不应少于()年。",
        # typos + colloquial prefix
        "老师帮我看看这道题：屋面防水等级为一级时,防水层合理使用年现不应少于()年？",
        # line-break / whitespace / full-width differences
        "屋面防水等级为一级时,\n防水层合理使用年限 不应少于(　)年。",
    ],
)
def test_identity_accepts_genuine_paste_variants(query: str) -> None:
    # SEV counterexample family: a learner pasting the real bank question must
    # still hit — the identity collapse must not over-kill true originals.
    assert _identity(query, _RED_STEM)


def test_identity_paraphrase_is_not_identity() -> None:
    # Semantic change vs the old bigram-relevance gate: asking ABOUT one blank
    # of a bank stem is relevance, not identity. It must fall open to normal
    # RAG (the row still reaches the LLM as ordinary retrieval context).
    assert not _identity(
        "防水混凝土的适用环境温度不得高于多少？",
        "地下工程的防水等级分为（  ），防水混凝土的适用环境温度不得高于（  ）。",
    )
    assert not _identity(
        "大体积混凝土里表温差控制多少？",
        "大体积混凝土施工里表温差不宜大于（  ）。",
    )


def test_identity_keeps_calculation_invariant_as_orthogonal_rejector() -> None:
    # #422 calc identity stays: same wording template, different numeric facts
    # can never be the same question even if surface coverage were high.
    assert not _identity(
        "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时费用偏差为多少万元？",
        "某工程计划完成工程量5000m3，预算成本单价150元/m3，现已完成3000m3，实际价是200元/m3，此时进度偏差为（　　）万元。",
    )


def test_identity_case_type_passthrough_is_preserved() -> None:
    # 指挥官裁决：case 家族推迟收权——case 型命中继续走 case_bundle 覆盖判定。
    assert _identity("背景资料：某项目……问题一：……", _RED_STEM, question_type="case_study")


def test_identity_short_fragments_never_authorize() -> None:
    # A tiny shared fragment (below the minimum discriminative surface) must
    # not authorize identity via the containment rule.
    assert not _identity("防水等级", "防水等级为（　）级。")


# ---------------------------------------------------------------------------
# tier1/2 可达性批1a（2026-07-30）：exact payload 顶层身份键
# ---------------------------------------------------------------------------
def test_exact_question_payload_carries_composite_qid_ingredients() -> None:
    """A1/A4：payload 顶层必须显式携带 question_id/source_chunk_id/exam_year——
    pgo 复合 qid = f"{exam_year}::{source_chunk_id}::E{n}" 的原料。此前顶层只有
    "id"，ctx 组装按 question_id 取键恒空 → tier1/2 在聊天通道结构性不可达。"""
    from deeptutor.services.rag.pipelines.supabase import SupabasePipeline

    pipeline = SupabasePipeline.__new__(SupabasePipeline)
    row = {
        "id": 9663,
        "chunk_id": "EXAM_1A432000_P0015_01",
        "source_chunk_id": "EXAM_1A432000_P0015_01",
        "exam_year": 2024,
        "stem": "某住宅工程案例题干……问题：1.指出不妥之处。",
        "question_type": "case_study",
        "correct_answer": "官方参考答案……",
        "analysis": "解析……",
        "options": "",
        "similarity": 0.97,
    }
    plans = [{
        "group_name": "question_exact_text",
        "results": [dict(row, _source_group="question_exact_text")],
    }]
    payload = pipeline._extract_exact_question_payload(
        plans, original_query=row["stem"]
    )

    assert payload is not None
    assert payload.get("question_id") == 9663
    assert payload.get("source_chunk_id") == "EXAM_1A432000_P0015_01"
    assert payload.get("exam_year") == 2024
