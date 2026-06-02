from deeptutor.services.citations.assembler import assemble_cited_answer
from deeptutor.services.citations.quality import validate_cited_answer
from deeptutor.services.citations.schema import CitationPolicy


def test_assembles_inline_markers_with_footer_references() -> None:
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

    assert cited.response == "屋面防水等级应根据工程重要性确定。〔1〕\n\n设防要求要结合渗漏后果判断。〔2〕"
    assert "〔1〕" in cited.response
    assert "〔2〕" in cited.response
    assert "依据" not in cited.response
    assert cited.bundle.footer_text.startswith("依据\n〔1〕2026 建筑实务教材")
    assert "〔2〕屋面工程技术规范，GB 50345-2012 第 3.0.1 条" in cited.bundle.footer_text
    assert cited.bundle.citation_state == "supported"
    assert len(cited.bundle.claims) == 2
    validate_cited_answer(cited)


def test_footer_keeps_all_public_refs_while_body_marks_used_ref() -> None:
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

    assert cited.response == "屋面防水等级应根据工程重要性确定。〔1〕"
    assert "〔2〕" not in cited.response
    assert len(cited.bundle.refs) == 2
    assert "〔1〕2026 建筑实务教材" in cited.bundle.footer_text
    assert "〔2〕施工现场临时用电安全技术规范" in cited.bundle.footer_text
    validate_cited_answer(cited)


def test_footer_refs_keep_contiguous_markers_without_body_renumbering() -> None:
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

    assert cited.response == "临时用电组织设计应包含用电负荷计算。〔2〕"
    assert [ref.marker for ref in cited.bundle.refs] == ["〔1〕", "〔2〕"]
    validate_cited_answer(cited)


def test_does_not_mark_markdown_headings_as_cited_claims() -> None:
    cited = assemble_cited_answer(
        "## 结论\n\n楼地面应满足隔声、保温、防水、防火要求。\n\n---\n\n## 采分点\n\n- 铺装面层应平整、防滑、耐磨、易清洁。",
        sources=[
            {
                "source_type": "textbook",
                "title": "楼地面构造",
                "source": "2026建筑实务教材",
                "chapter": "1",
                "section": "楼地面基本构造要求",
                "page": 15,
                "rag_content": "楼地面应满足隔声、保温、防水、防火要求。铺装面层应平整、防滑、耐磨、易清洁。",
            },
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert "## 结论〔1〕" not in cited.response
    assert "## 采分点〔1〕" not in cited.response
    assert "楼地面应满足隔声、保温、防水、防火要求。〔1〕" in cited.response
    assert "- 铺装面层应平整、防滑、耐磨、易清洁。〔1〕" in cited.response
    assert [claim.text for claim in cited.bundle.claims] == [
        "楼地面应满足隔声、保温、防水、防火要求。",
        "- 铺装面层应平整、防滑、耐磨、易清洁。",
    ]
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
    assert "〔1〕" in cited.response
    assert any(ref.source_type == "textbook" for ref in cited.bundle.refs)
    assert any(ref.title.startswith("2026 建筑实务教材") for ref in cited.bundle.refs)
    assert "GB 50016-2019 建筑防火" in cited.bundle.footer_text
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

    assert "〔2〕" in cited.response
    assert any(ref.source_type == "standard" for ref in cited.bundle.refs)
    assert "GB 50016-2019 建筑防火" in cited.bundle.footer_text
    validate_cited_answer(cited)


def test_assembles_no_public_source_footer_without_fake_marker() -> None:
    cited = assemble_cited_answer("你好，我可以帮你复习。", sources=[], policy=CitationPolicy())

    assert cited.response.startswith("你好，我可以帮你复习。")
    assert "本轮未使用可公开引用" not in cited.response
    assert "本轮未使用可公开引用" in cited.bundle.footer_text
    assert "〔1〕" not in cited.response
    assert cited.bundle.citation_state == "no_public_source"
    validate_cited_answer(cited)


def test_strips_model_generated_inline_reference_noise() -> None:
    cited = assemble_cited_answer(
        "屋面防水等级应根据工程重要性确定。〔1〕\n\n## 采分点\n- 按重要程度判断。〔1〕\n\n依据：2026 建筑实务教材第3章。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_roof_level", "source_span": {"chapter": "3"}},
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert cited.response == "屋面防水等级应根据工程重要性确定。〔1〕\n\n## 采分点\n- 按重要程度判断。〔1〕"
    assert "依据：" not in cited.response
    assert "〔1〕" in cited.response
    assert "〔1〕2026 建筑实务教材" in cited.bundle.footer_text
    validate_cited_answer(cited)


def test_preserves_legal_document_numbers_and_teaching_basis_lines() -> None:
    cited = assemble_cited_answer(
        "防疫复工可参考建办质〔2020〕8号。\n\n依据：关键线路决定总工期。\n\n采分点：先判断，再写依据。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_schedule_basis", "source_span": {"chapter": "2"}},
                "rag_content": "关键线路决定总工期，案例题要先判断再写依据。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "建办质〔2020〕8号" in cited.response
    assert "依据：关键线路决定总工期。" in cited.response
    assert "采分点：先判断，再写依据。" in cited.response
    assert "〔1〕" in cited.response
    validate_cited_answer(cited)


def test_preserves_plain_basis_section_without_reference_footer_shape() -> None:
    cited = assemble_cited_answer(
        "结论：应封闭管理。\n\n依据\n关键线路决定总工期。\n\n采分点：先判断，再写依据。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_schedule_basis", "source_span": {"chapter": "2"}},
                "rag_content": "关键线路决定总工期，案例题要先判断再写依据。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "依据\n关键线路决定总工期。" in cited.response
    assert "采分点：先判断，再写依据。" in cited.response
    validate_cited_answer(cited)


def test_strips_old_answer_footer_only_when_footer_has_reference_shape() -> None:
    cited = assemble_cited_answer(
        "屋面防水等级应根据工程重要性确定。\n\n依据\n〔1〕2026 建筑实务教材，第 3 章。摘录：屋面防水等级应根据工程重要性确定。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_roof_level", "source_span": {"chapter": "3"}},
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert cited.response == "屋面防水等级应根据工程重要性确定。〔1〕"
    validate_cited_answer(cited)


def test_strips_last_reference_footer_without_removing_teaching_basis_section() -> None:
    cited = assemble_cited_answer(
        "结论：应封闭管理。\n\n"
        "依据\n"
        "关键线路决定总工期。\n\n"
        "采分点：先判断，再写依据。\n\n"
        "依据\n"
        "〔1〕2026 建筑实务教材，第 2 章。摘录：关键线路决定总工期。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {"source_id": "book_2026_schedule_basis", "source_span": {"chapter": "2"}},
                "rag_content": "关键线路决定总工期，案例题要先判断再写依据。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "依据\n关键线路决定总工期。" in cited.response
    assert "采分点：先判断，再写依据。" in cited.response
    assert cited.response.endswith("采分点：先判断，再写依据。〔1〕")
    assert "〔1〕" in cited.response
    validate_cited_answer(cited)
