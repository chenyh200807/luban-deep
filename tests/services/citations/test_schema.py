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


def test_ref_carries_no_dormant_visibility_gate() -> None:
    """来源可否公开的唯一权威在 normalizer(_is_hidden_source),不在 ref 自身。

    这里钉死的是 2026-08-03 的收权结论:`CitationSourceRef` 上**不得**再出现带默认值
    的 `visibility`/`is_public` 自述式开关。旧实现有这么一对,但唯一构造点
    (`normalizer.py`)从不写它、数据面也没有对应列,于是永远吃默认值 "public",
    脱敏分支在生产执行 0 次 —— 一道只在代码审查里"看起来存在"的门,已实际误导过
    一次静态审计。要恢复逐来源可见性,先在数据面定义权威并接上写入方,
    再改这条测试;不要靠一个默认值假装有门。
    """
    fields = set(CitationSourceRef.__dataclass_fields__)
    assert "visibility" not in fields
    assert not hasattr(CitationSourceRef, "is_public")

    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="题库",
        locator="第 1 题",
    )
    # to_public_dict() 恒返回非空:公开性裁剪已在上游完成,这里不再是判定点。
    assert ref.to_public_dict()


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
