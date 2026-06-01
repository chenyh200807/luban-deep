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
        "〔1〕2026 建筑实务教材，第 1 章 第 1.4 节，source_id=book_2026_001。"
        "摘录：屋面防水等级应根据工程重要性确定。"
    )
