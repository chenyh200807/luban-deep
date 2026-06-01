from deeptutor.services.citations.assembler import assemble_cited_answer
from deeptutor.services.citations.quality import validate_cited_answer
from deeptutor.services.citations.schema import CitationPolicy


def test_assembles_markers_on_multiple_knowledge_lines() -> None:
    cited = assemble_cited_answer(
        "屋面防水等级应根据工程重要性确定。\n\n设防要求要结合渗漏后果判断。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_roof_level",
                    "source_span": {"chapter": "1", "section": "1.4"},
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            },
            {
                "source_type": "standard",
                "title": "屋面工程技术规范",
                "standard_code": "GB 50345-2012",
                "article_code": "3.0.1",
                "rag_content": "设防要求应结合渗漏后果判断。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "屋面防水等级应根据工程重要性确定。〔1〕" in cited.response
    assert "设防要求要结合渗漏后果判断。〔2〕" in cited.response
    assert "\n\n依据\n〔1〕2026 建筑实务教材" in cited.response
    assert "〔2〕屋面工程技术规范，GB 50345-2012 第 3.0.1 条" in cited.response
    assert cited.bundle.citation_state == "supported"
    assert len(cited.bundle.claims) == 2
    validate_cited_answer(cited)


def test_partial_answer_footer_only_includes_visible_markers() -> None:
    cited = assemble_cited_answer(
        "屋面防水等级应根据工程重要性确定。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_roof_level"},
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            },
            {
                "source_type": "standard",
                "title": "施工现场临时用电安全技术规范",
                "standard_code": "JGJ 46-2005",
                "article_code": "3.1.1",
                "rag_content": "临时用电组织设计应包含用电负荷计算。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "〔1〕" in cited.response
    assert "〔2〕" not in cited.response
    assert len(cited.bundle.refs) == 1
    validate_cited_answer(cited)


def test_visible_subset_refs_are_renumbered_contiguously() -> None:
    cited = assemble_cited_answer(
        "临时用电组织设计应包含用电负荷计算。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_roof_level"},
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            },
            {
                "source_type": "standard",
                "title": "施工现场临时用电安全技术规范",
                "standard_code": "JGJ 46-2005",
                "article_code": "3.1.1",
                "rag_content": "临时用电组织设计应包含用电负荷计算。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "临时用电组织设计应包含用电负荷计算。〔1〕" in cited.response
    assert "〔2〕" not in cited.response
    assert cited.bundle.refs[0].marker == "〔1〕"
    validate_cited_answer(cited)


def test_student_surface_prefers_textbook_reference_over_standard_when_available() -> None:
    cited = assemble_cited_answer(
        "防火门等级要与使用部位匹配，甲级常用于防火分区隔墙，乙级常用于疏散楼梯间。",
        sources=[
            {
                "source_type": "standard",
                "title": "GB 50016-2019 建筑防火",
                "standard_code": "GB 50016-2019",
                "article_code": "6.13.1",
                "rag_content": "防火门等级要与使用部位匹配，甲级防火门常用于防火分区隔墙，乙级防火门常用于疏散楼梯间。",
                "authority_rank": 80,
            },
            {
                "source_type": "textbook",
                "title": "防火门等级与使用部位",
                "source": "2026教材 v3_production_core9-166",
                "chapter": "1",
                "section": "1.2.4",
                "page": 47,
                "rag_content": "教材归纳：防火门等级应与使用部位匹配，甲级用于防火分区隔墙，乙级用于疏散楼梯间。",
                "authority_rank": 45,
            },
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert "防火门等级要与使用部位匹配" in cited.response
    assert cited.bundle.refs[0].source_type == "textbook"
    assert cited.bundle.refs[0].title.startswith("2026 建筑实务教材")
    assert "GB 50016-2019 建筑防火" not in cited.bundle.footer_text
    validate_cited_answer(cited)


def test_student_surface_keeps_standard_reference_for_explicit_standard_claim() -> None:
    cited = assemble_cited_answer(
        "GB 50016-2019 第 6.13.1 条要求防火门等级与使用部位匹配。",
        sources=[
            {
                "source_type": "textbook",
                "title": "防火门等级与使用部位",
                "source": "2026教材 v3_production_core9-166",
                "chapter": "1",
                "section": "1.2.4",
                "page": 47,
                "rag_content": "教材归纳：GB 50016-2019 第 6.13.1 条要求防火门等级与使用部位匹配。",
                "authority_rank": 45,
            },
            {
                "source_type": "standard",
                "title": "GB 50016-2019 建筑防火",
                "standard_code": "GB 50016-2019",
                "article_code": "6.13.1",
                "rag_content": "GB 50016-2019 第 6.13.1 条要求防火门等级与使用部位匹配。",
                "authority_rank": 80,
            },
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert cited.bundle.refs[0].source_type == "standard"
    assert "GB 50016-2019 建筑防火" in cited.bundle.footer_text
    validate_cited_answer(cited)


def test_assembles_no_public_source_footer_without_fake_marker() -> None:
    cited = assemble_cited_answer("你好，我可以帮你复习。", sources=[], policy=CitationPolicy())

    assert cited.response.startswith("你好，我可以帮你复习。")
    assert "本轮未使用可公开引用" in cited.response
    assert "〔1〕" not in cited.response
    assert cited.bundle.citation_state == "no_public_source"
    validate_cited_answer(cited)
