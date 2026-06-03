import pytest

from deeptutor.services.citations.quality import CitationQualityError, validate_cited_answer
from deeptutor.services.citations.redaction import HIDDEN_AUTHORITY_FIELDS
from deeptutor.services.citations.runtime import assemble_public_cited_answer
from deeptutor.services.citations.schema import CitationBundle, CitationSourceRef, CitedAnswer, CitedClaim


def _answer(
    response: str,
    refs: list[CitationSourceRef],
    claims: list[CitedClaim] | None = None,
) -> CitedAnswer:
    return CitedAnswer(
        response=response,
        bundle=CitationBundle(
            citation_state="supported",
            refs=refs,
            claims=claims or [],
            footer_text="依据\n" + "\n".join(f"{ref.marker}{ref.title}" for ref in refs),
        ),
    )


def test_rejects_inline_response_marker() -> None:
    ref = CitationSourceRef("c1", "〔1〕", "textbook", "教材", "第 1 章")
    with pytest.raises(CitationQualityError, match="orphan citation marker"):
        validate_cited_answer(_answer("正文〔1〕", [ref]))


def test_allows_legal_document_number_brackets_in_response() -> None:
    ref = CitationSourceRef("c1", "〔1〕", "textbook", "教材", "第 1 章")
    validate_cited_answer(_answer("复工要求可参考建办质〔2020〕8号。", [ref]))


def test_rejects_orphan_inline_response_marker() -> None:
    with pytest.raises(CitationQualityError, match="orphan citation marker"):
        validate_cited_answer(_answer("正文〔2〕\n\n依据\n〔1〕来源", []))


def test_allows_structured_footer_rows_without_visible_body_marker() -> None:
    ref = CitationSourceRef("c1", "〔1〕", "textbook", "教材", "第 1 章")
    validate_cited_answer(_answer("正文", [ref]))


def test_rejects_missing_claim_marker_in_response() -> None:
    ref = CitationSourceRef("c1", "〔1〕", "textbook", "教材", "第 1 章")
    claim = CitedClaim("claim_1", "正文", ["c1"], 0.9)
    with pytest.raises(CitationQualityError, match="missing claim citation marker"):
        validate_cited_answer(_answer("正文", [ref], [claim]))


def test_accepts_inline_marker_when_backed_by_claim() -> None:
    ref = CitationSourceRef("c1", "〔1〕", "textbook", "教材", "第 1 章")
    claim = CitedClaim("claim_1", "正文", ["c1"], 0.9)
    validate_cited_answer(_answer("正文〔1〕", [ref], [claim]))


def test_rejects_hidden_public_quote() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="题库",
        locator="Q1",
        public_quote="correct_answer: A",
    )
    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer("正文", [ref]))


def test_rejects_hidden_text_in_response() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="题库",
        locator="Q1",
        public_quote="屋面防水",
    )

    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer("正文 correct_answer: A", [ref]))


def test_allows_plain_answer_word_without_hidden_field_label() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="textbook",
        title="教材",
        locator="Q1",
        public_quote="屋面防水",
    )

    validate_cited_answer(_answer("The answer depends on the waterproofing grade.", [ref]))


def test_safe_runtime_fallback_redacts_hidden_authority_response_body() -> None:
    cited = assemble_public_cited_answer(
        "correct_answer: A",
        sources=[
            {
                "source_type": "questions_bank",
                "field": "knowledge_point",
                "value": "屋面防水",
            }
        ],
    )

    assert "correct_answer" not in cited.response
    assert "不可公开展示" in cited.response
    assert cited.bundle.citation_state == "no_public_source"
    validate_cited_answer(cited)


def test_rejects_hidden_text_in_any_public_ref_field() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="grading_key",
        title="题库",
        locator="Q1",
        public_quote="屋面防水",
        evidence_level="correct_answer",
    )

    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer("正文", [ref]))


def test_rejects_hidden_nested_public_ref_field() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="题库",
        locator="Q1",
        source_span={"correct_answer": "A"},
        public_quote="屋面防水",
    )

    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer("正文", [ref]))


@pytest.mark.parametrize("hidden_field", sorted(HIDDEN_AUTHORITY_FIELDS))
def test_rejects_every_hidden_authority_field_in_response_and_public_ref(hidden_field: str) -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="textbook",
        title="教材",
        locator="Q1",
        public_quote="屋面防水",
        evidence_level=hidden_field,
    )

    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer(f"正文 {hidden_field}: value", [ref]))

    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer("正文", [ref]))


def test_accepts_no_public_source_footer() -> None:
    answer = CitedAnswer(
        response="你好",
        bundle=CitationBundle.no_public_source(),
    )

    validate_cited_answer(answer)
