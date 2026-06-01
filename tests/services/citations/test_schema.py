from deeptutor.services.citations.schema import (
    CitationBundle,
    CitationPolicy,
    CitationSourceRef,
    CitedClaim,
)


def test_public_ref_dict_is_compact_and_stable() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="textbook",
        title="2026 建筑实务教材",
        locator="防水工程 > 屋面防水等级",
        source_id="book_2026_001",
        source_table="kb_chunks",
        stable_id="book_2026_001:1.4",
        source_span={"chapter": "1", "section": "1.4", "page": 32},
        content_hash="abc123",
        quote_hash="def456",
        public_quote="防水等级应根据工程重要性确定。",
        visibility="public",
        authority_rank=45,
        evidence_level="direct",
    )

    assert ref.to_public_dict() == {
        "citation_id": "c1",
        "marker": "〔1〕",
        "source_type": "textbook",
        "title": "2026 建筑实务教材",
        "locator": "防水工程 > 屋面防水等级",
        "source_id": "book_2026_001",
        "source_table": "kb_chunks",
        "stable_id": "book_2026_001:1.4",
        "source_span": {"chapter": "1", "section": "1.4", "page": 32},
        "content_hash": "abc123",
        "quote_hash": "def456",
        "public_quote": "防水等级应根据工程重要性确定。",
        "authority_rank": 45,
        "evidence_level": "direct",
    }


def test_private_ref_is_not_public() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="hidden",
        locator="grading_key",
        visibility="private",
        public_quote="correct_answer: A",
    )

    assert ref.is_public is False
    assert ref.to_public_dict() == {}


def test_bundle_carries_claims_and_no_public_source_state() -> None:
    claim = CitedClaim(
        claim_id="claim_1",
        text="屋面防水等级应根据工程重要性确定。",
        citation_ids=["c1"],
        confidence=0.93,
    )
    bundle = CitationBundle(
        citation_state="supported",
        refs=[],
        claims=[claim],
        footer_text="依据",
    )

    assert bundle.claims[0].citation_ids == ["c1"]
    no_source = CitationBundle.no_public_source()
    assert no_source.citation_state == "no_public_source"
    assert no_source.refs == []
    assert "未使用可公开引用" in no_source.footer_text


def test_policy_defaults_to_student_surface() -> None:
    policy = CitationPolicy()

    assert policy.surface == "student"
    assert policy.require_footer is True
    assert policy.max_public_refs == 8
    assert policy.min_claim_ref_score == 0.18
