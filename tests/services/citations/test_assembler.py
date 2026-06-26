from deeptutor.services.citations.assembler import assemble_cited_answer
from deeptutor.services.citations.quality import validate_cited_answer
from deeptutor.services.citations.runtime import citation_metrics
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
    assert "〔2〕屋面工程技术规范｜GB 50345-2012 第 3.0.1 条" in cited.bundle.footer_text
    assert cited.bundle.citation_state == "supported"
    assert len(cited.bundle.claims) == 2
    validate_cited_answer(cited)


def test_citation_metrics_separate_provider_tokens_from_display_payload() -> None:
    cited = assemble_cited_answer(
        "屋面防水等级应根据工程重要性确定。",
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
        ],
        policy=CitationPolicy(),
    )

    metrics = citation_metrics(cited.bundle)

    assert metrics["citation_ref_count"] == 1
    assert metrics["citation_footer_chars"] == len(cited.bundle.footer_text)
    assert metrics["citation_public_quote_chars"] == len("屋面防水等级应根据工程重要性确定。")
    assert metrics["citation_public_payload_bytes"] > metrics["citation_footer_chars"]
    assert metrics["citation_display_cost_source"] == "post_llm_public_projection"


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


def test_strip_orphan_reference_markers_removes_unbacked_footnotes():
    """阶段1 去毒(meta_leak 〔N〕渲染层):引用关闭/无 sources 时,主 LLM 输出的孤儿
    〔N〕脚注标注解析不到来源=内部噪声,绝不能漏给学生;参考依据行一并剥离。"""
    from deeptutor.services.citations.assembler import strip_orphan_reference_markers

    raw = "这道题考点是危大工程〔1〕。\n核心是专家论证〔5〕。\n依据：2026建筑实务教材 §3.1"
    out = strip_orphan_reference_markers(raw)
    assert "〔1〕" not in out and "〔5〕" not in out
    assert "依据：2026建筑实务教材" not in out
    assert "危大工程" in out and "专家论证" in out  # 正文保留


def test_strip_orphan_reference_markers_removes_rich_grounding_source_markers():
    """task#27:〔源:chunk_id〕 是 supporting-citation-only 的检索 grounding 标记
    (rich_leaf_runtime),只该出现在喂 LLM 的上下文里;judge 模仿进判分/教学输出时
    绝不能漏给学生。无 backing footer 时必剥(正文保留)。"""
    from deeptutor.services.citations.assembler import strip_orphan_reference_markers

    raw = "正确答案是 A。专家论证是危大工程核心〔源:CK_1A_0001〕。"
    out = strip_orphan_reference_markers(raw)
    assert "〔源:CK_1A_0001〕" not in out
    assert "〔源" not in out
    assert "正确答案是 A" in out and "专家论证是危大工程核心" in out


def test_strip_orphan_reference_markers_strips_source_markers_even_with_footer():
    """〔源:〕 永远剥——即使文本带合法 backing footer。合法学生引用是带 footer 行的
    数字 〔N〕;〔源:chunk_id〕 是内部 grounding,任何情况下都不该露给学生。
    带 footer 的合法数字 〔N〕 保留。"""
    from deeptutor.services.citations.assembler import strip_orphan_reference_markers

    raw = (
        "屋面防水等级应根据工程重要性确定。〔1〕〔源:CK_1A_0001〕\n\n"
        "依据\n〔1〕2026 建筑实务教材，第 3 章。摘录：屋面防水等级应根据工程重要性确定。"
    )
    out = strip_orphan_reference_markers(raw)
    assert "〔源:CK_1A_0001〕" not in out and "〔源" not in out  # grounding 标记永远剥
    assert "〔1〕" in out  # 合法数字引用 + footer 保留
    assert "2026 建筑实务教材" in out


def test_apply_answer_citation_metadata_strips_markers_when_disabled():
    """引用关闭(生产默认)的 apply_answer_citation_metadata 必须返回剥离后的正文,
    不再原样把 〔N〕 漏给学生。"""
    from deeptutor.services.citations.runtime import apply_answer_citation_metadata

    payload = {}
    out = apply_answer_citation_metadata(
        payload, response="答案讲解〔1〕\n要点〔2〕", sources=[], enabled=False
    )
    assert "〔1〕" not in out and "〔2〕" not in out
    assert "答案讲解" in out and "要点" in out


def test_apply_answer_citation_metadata_drops_sources_for_internal_visible_leak():
    from deeptutor.services.citations.runtime import apply_answer_citation_metadata

    payload = {}
    out = apply_answer_citation_metadata(
        payload,
        response="根据我看到的内部记忆上下文，你的身份标签是 qa_persona_10。",
        sources=[
            {
                "source_type": "textbook",
                "title": "安全检查标准保证项目记忆口诀",
                "content": "安全检查标准保证项目包括基坑工程、高处作业、施工用电。",
            }
        ],
        enabled=True,
    )

    assert out == "暂时未生成适合直接展示的答案，请重试一次。"
    bundle = payload["citation_bundle"]
    assert bundle["refs"] == []
    assert bundle["claims"] == []
    assert bundle["citation_state"] == "no_public_source"
    assert "安全检查标准保证项目记忆口诀" not in str(payload)


def test_apply_answer_citation_metadata_drops_sources_for_security_refusal():
    from deeptutor.services.citations.runtime import apply_answer_citation_metadata

    payload = {}
    out = apply_answer_citation_metadata(
        payload,
        response="这类内容我不展开。你可以把要解决的建筑实务题目发给我。",
        sources=[
            {
                "source_type": "textbook",
                "title": "试样标识与见证送样",
                "content": "见证送样资料应按规定归档。",
            }
        ],
        enabled=True,
    )

    assert out == "这类内容我不展开。你可以把要解决的建筑实务题目发给我。"
    bundle = payload["citation_bundle"]
    assert bundle["refs"] == []
    assert bundle["claims"] == []
    assert bundle["citation_state"] == "no_public_source"
    assert "试样标识与见证送样" not in str(payload)
