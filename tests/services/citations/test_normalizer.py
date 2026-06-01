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
