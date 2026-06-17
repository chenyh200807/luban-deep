from deeptutor.services.citations.normalizer import normalize_citation_sources
from deeptutor.services.citations.schema import CitationPolicy


def test_normalizes_textbook_source_span() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "book-1",
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_001",
                    "source_table": "kb_chunks",
                    "stable_id": "book_2026_001:1.4",
                    "source_span": {"chapter": "1", "section": "1.4", "page": 32},
                    "content_hash": "hash1",
                    "quote_hash": "quote1",
                    "chapter_name": "建筑工程防水",
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].marker == "〔1〕"
    assert refs[0].source_type == "textbook"
    assert refs[0].locator == "第 1 章 第 1.4 节 p.32"
    assert refs[0].source_id == "book_2026_001"
    assert refs[0].source_table == "kb_chunks"
    assert refs[0].stable_id == "book_2026_001:1.4"
    assert refs[0].public_quote == "屋面防水等级应根据工程重要性确定。"


def test_normalizes_rag_source_top_level_locator_fields() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "1A413030_122_0230",
                "source_type": "textbook",
                "title": "平屋面工程的防水做法",
                "source": "2026教材 v3_production_core9-166",
                "page": 122,
                "chapter": "3",
                "chapter_name": "屋面与防水工程施工",
                "section": "3.5.1",
                "content": "屋面防水工程应根据建筑物的类别、重要程度、使用功能要求确定防水等级。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第 3 章 第 3.5.1 节 p.122"
    assert refs[0].source_id == "1A413030_122_0230"
    assert refs[0].title == "2026 建筑实务教材：平屋面工程的防水做法"


def test_textbook_locator_uses_taxonomy_path_when_source_span_is_missing() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "1A413050_133_0255",
                "source_type": "textbook",
                "title": "防水工程",
                "source": "2026教材 v3_production_core9-166",
                "page": 133,
                "node_code": "1A413050",
                "taxonomy_path": ["建筑工程施工技术", "屋面与防水工程施工"],
                "content": "屋面防水等级应根据建筑物的类别、重要程度、使用功能要求确定防水等级。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第3章 建筑工程施工技术 屋面与防水工程施工 p.133"


def test_textbook_locator_ignores_unsupported_taxonomy_section() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "1A413030_133_0255",
                "source_type": "textbook",
                "title": "防水工程",
                "source": "2026教材 v3_production_core9-166",
                "page": 133,
                "node_code": "1A413030",
                "taxonomy_path": ["建筑工程施工技术", "地基与基础工程施工"],
                "content": "屋面防水等级应根据建筑物的类别、重要程度、使用功能要求确定防水等级。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第3章 建筑工程施工技术 p.133"
    assert "地基与基础工程施工" not in refs[0].locator


def test_textbook_locator_infers_chapter_from_chunk_code_without_guessing_section() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "1A412010_066_0130",
                "source_type": "textbook",
                "title": "防火材料技术要求",
                "source": "2026教材 v3_production_core9-166",
                "page": 66,
                "content": "钢结构防火涂料应能采用规定的分散介质进行调和、稀释。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第2章 主要建筑工程材料的性能与应用 p.66"
    assert "结构工程材料" not in refs[0].locator


def test_source_span_locator_fields_override_top_level_fallbacks() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "book-1",
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "chapter": "9",
                "section": "9.9",
                "page": 122,
                "metadata": {
                    "source_span": {"chapter": "1", "section": "1.4", "page": 32},
                },
                "content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第 1 章 第 1.4 节 p.32"


def test_source_span_allows_named_textbook_section_without_synthetic_section_prefix() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "1A411011_001_0001",
                "source_type": "textbook",
                "title": "建筑物分类",
                "source": "2026教材 v3_production_core9-166",
                "metadata": {
                    "source_span": {
                        "chapter": "第1章 建筑工程设计技术",
                        "section": "建筑物的构成与设计要求",
                        "page": 1,
                    },
                },
                "content": "建筑物分类与构成。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第1章 建筑工程设计技术 建筑物的构成与设计要求 p.1"
    assert "第 建筑物的构成与设计要求 节" not in refs[0].locator


def test_filters_hidden_grading_authority_for_student_surface() -> None:
    refs = normalize_citation_sources(
        [
            {"source_type": "questions_bank", "field": "correct_answer", "value": "A"},
            {"source_type": "questions_bank", "field": "knowledge_point", "value": "屋面防水"},
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert len(refs) == 1
    assert refs[0].public_quote == "屋面防水"


def test_filters_metadata_hidden_grading_authority_for_student_surface() -> None:
    refs = normalize_citation_sources(
        [
            {
                "source_type": "questions_bank",
                "metadata": {"field": "correct_answer"},
                "value": "A",
            },
            {
                "source_type": "questions_bank",
                "metadata": {"field": "knowledge_point"},
                "value": "屋面防水",
            },
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert len(refs) == 1
    assert refs[0].public_quote == "屋面防水"


def test_student_refs_prioritize_textbook_kb_chunk_over_question_bank_when_ref_slots_are_limited() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": f"question-{index}",
                "source_type": "TEXTBOOK",
                "source_table": "questions_bank",
                "title": f"题目 {index}",
                "rag_content": "题库解析。",
            }
            for index in range(1, 5)
        ]
        + [
            {
                "chunk_id": "1A411011_001_0001",
                "source_type": "textbook",
                "source_table": "kb_chunks",
                "title": "建筑物分类",
                "source": "2026教材 v3_production_core9-166",
                "metadata": {
                    "source_span": {
                        "chapter": "第1章 建筑工程设计技术",
                        "section": "建筑物的构成与设计要求",
                        "page": 1,
                    }
                },
                "rag_content": "建筑物分类与构成。",
            }
        ],
        policy=CitationPolicy(surface="student", max_public_refs=3),
    )

    assert refs[0].source_table == "kb_chunks"
    assert refs[0].source_id == "1A411011_001_0001"
    assert refs[0].locator == "第1章 建筑工程设计技术 建筑物的构成与设计要求 p.1"
    assert len(refs) == 3


def test_reviewer_refs_keep_input_order_without_student_prioritization() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "question-1",
                "source_type": "TEXTBOOK",
                "source_table": "questions_bank",
                "title": "题目",
                "rag_content": "题库解析。",
            },
            {
                "chunk_id": "1A411011_001_0001",
                "source_type": "textbook",
                "source_table": "kb_chunks",
                "title": "建筑物分类",
                "metadata": {
                    "source_span": {
                        "chapter": "第1章 建筑工程设计技术",
                        "section": "建筑物的构成与设计要求",
                        "page": 1,
                    }
                },
                "rag_content": "建筑物分类与构成。",
            },
        ],
        policy=CitationPolicy(surface="reviewer"),
    )

    assert [ref.source_table for ref in refs] == ["questions_bank", "kb_chunks"]


def test_deduplicates_same_source_and_span() -> None:
    refs = normalize_citation_sources(
        [
            {"chunk_id": "c1", "source_type": "standard", "standard_code": "GB 50345-2012", "article_code": "3.0.1"},
            {"chunk_id": "c1", "source_type": "standard", "standard_code": "GB 50345-2012", "article_code": "3.0.1"},
        ],
        policy=CitationPolicy(),
    )

    assert len(refs) == 1
    assert refs[0].locator == "GB 50345-2012 第 3.0.1 条"


def test_standard_locator_includes_related_textbook_mapping_when_available() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "std-1",
                "source_type": "standard",
                "title": "GB 50345-2012 屋面工程技术规范",
                "standard_code": "GB 50345-2012",
                "article_code": "3.0.1",
                "node_code": "1A413050",
                "taxonomy_path": ["建筑工程施工技术", "屋面与防水工程施工"],
                "rag_content": "屋面防水工程应根据建筑物的类别、重要程度、使用功能要求确定防水等级。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "GB 50345-2012 第 3.0.1 条；关联教材：第3章 建筑工程施工技术 屋面与防水工程施工"


def test_standard_locator_without_article_keeps_related_textbook_mapping() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "std-1",
                "source_type": "standard",
                "title": "建筑防火标准",
                "standard_code": "GB 50016-2014",
                "node_code": "1A411020",
                "rag_content": "防火门窗的耐火极限分为甲级、乙级、丙级。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "GB 50016-2014；关联教材：第1章 建筑工程设计技术"


def test_standard_without_textbook_mapping_keeps_original_locator_only() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "std-1",
                "source_type": "standard",
                "title": "GB 50016-2014 建筑防火",
                "standard_code": "GB 50016-2014",
                "article_code": "6.5.1",
                "rag_content": "防火门等级应与使用部位匹配。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "GB 50016-2014 第 6.5.1 条"


def test_standard_with_only_id_like_chunk_does_not_guess_textbook_mapping() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "standard_raw_1A413050_line_99",
                "source_id": "STD_GB50345_2012_1A413050_RAW",
                "stable_id": "std:1A413050:raw",
                "source_type": "standard",
                "title": "GB 50345-2012 屋面工程技术规范",
                "standard_code": "GB 50345-2012",
                "article_code": "3.0.1",
                "rag_content": "屋面工程应按不同屋面防水等级进行设防。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "GB 50345-2012 第 3.0.1 条"
    assert "关联教材" not in refs[0].locator


def test_standard_title_does_not_guess_textbook_mapping() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "std-title-only",
                "source_type": "standard",
                "title": "施工测量",
                "standard_code": "GB 50026-2020",
                "taxonomy_path": ["无法识别路径"],
                "rag_content": "施工测量应符合工程测量标准。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "GB 50026-2020"
    assert "关联教材" not in refs[0].locator


def test_standard_span_locator_appends_trusted_related_textbook_mapping() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "std-span-1",
                "source_type": "standard",
                "title": "基本规定",
                "metadata": {"source_span": {"chapter": "3", "page": 13}},
                "node_code": "1A413050",
                "taxonomy_path": ["建筑工程施工技术", "屋面与防水工程施工"],
                "rag_content": "屋面工程应根据建筑物的性质、重要程度、使用功能要求进行设防。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == "第 3 章 p.13；关联教材：第3章 建筑工程施工技术 屋面与防水工程施工"


def test_non_standard_source_with_textbook_mapping_does_not_get_related_locator() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "question-1",
                "source_type": "questions_bank",
                "title": "题库解析",
                "node_code": "1A413050",
                "taxonomy_path": ["建筑工程施工技术", "屋面与防水工程施工"],
                "rag_content": "屋面防水等级是本题考查点。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == ""


def test_missing_locator_does_not_fall_back_to_raw_source_type() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "std-1",
                "source_type": "standard",
                "title": "GB 50016-2019 建筑防火",
                "rag_content": "防火门等级应与使用部位匹配。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].locator == ""


def test_sources_without_identity_are_not_deduped_by_empty_locator() -> None:
    refs = normalize_citation_sources(
        [
            {
                "source_type": "standard",
                "title": "规范来源 A",
                "rag_content": "防火门等级应与使用部位匹配。",
            },
            {
                "source_type": "standard",
                "title": "规范来源 B",
                "rag_content": "防火门应具备自行关闭功能。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert [ref.title for ref in refs] == ["规范来源 A", "规范来源 B"]


def test_sources_without_identity_keep_same_title_different_quotes() -> None:
    refs = normalize_citation_sources(
        [
            {
                "source_type": "standard",
                "title": "规范来源",
                "rag_content": "防火门等级应与使用部位匹配。",
            },
            {
                "source_type": "standard",
                "title": "规范来源",
                "rag_content": "防火门应具备自行关闭功能。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert [ref.public_quote for ref in refs] == [
        "防火门等级应与使用部位匹配。",
        "防火门应具备自行关闭功能。",
    ]


def test_bad_authority_rank_degrades_to_zero() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "book-1",
                "source_type": "textbook",
                "authority_rank": "high",
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].authority_rank == 0
