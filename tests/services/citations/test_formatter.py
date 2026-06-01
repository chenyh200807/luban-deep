from deeptutor.services.citations.formatter import format_citation_footer
from deeptutor.services.citations.schema import CitationSourceRef


def test_formats_paper_style_footer() -> None:
    footer = format_citation_footer(
        [
            CitationSourceRef(
                citation_id="c1",
                marker="〔1〕",
                source_type="textbook",
                title="2026 建筑实务教材",
                locator="第 1 章 第 1.4 节",
                source_id="book_2026_001",
                public_quote="屋面防水等级应根据工程重要性确定。",
            )
        ]
    )

    assert footer == (
        "依据\n"
        "〔1〕2026 建筑实务教材，第 1 章 第 1.4 节。"
        "摘录：屋面防水等级应根据工程重要性确定。"
    )


def test_formats_footer_without_raw_source_type_or_internal_id() -> None:
    footer = format_citation_footer(
        [
            CitationSourceRef(
                citation_id="c1",
                marker="〔1〕",
                source_type="standard",
                title="GB 50016-2019 建筑防火",
                locator="",
                source_id="MSTDGB500162019613_01",
                public_quote="防火门等级应与使用部位匹配。",
            )
        ]
    )

    assert "standard" not in footer
    assert "source_id=" not in footer
    assert footer == "依据\n〔1〕GB 50016-2019 建筑防火。摘录：防火门等级应与使用部位匹配。"
