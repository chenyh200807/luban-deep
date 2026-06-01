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
