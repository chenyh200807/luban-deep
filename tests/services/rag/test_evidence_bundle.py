"""Unit tests for the single-authority evidence-bundle builder.

``build_evidence_bundle`` replaced 4 drifting inline assembly sites (kbv5 / supabase /
RAGService fallback / historical-question) with one canonical shape. These tests pin the
contract: the canonical top-level field set, the derived retrieval status, ``retrieval_empty``
derivation + override, deterministic provider-distinct ``bundle_id``, and the ``trace`` bucket
for lane-specific diagnostics.
"""

from __future__ import annotations

from deeptutor.services.rag.evidence_bundle import (
    SCHEMA_ID,
    EvidenceBundle,
    build_evidence_bundle,
    evidence_bundle_id,
)

_CANONICAL_KEYS = {
    "bundle_id",
    "query",
    "provider",
    "kb_name",
    "content_blocks",
    "sources",
    "exact_question",
    "retrieval_plan",
    "ranking_trace",
    "retrieval_empty",
    "query_shape",
    "retrieval_status",
    "retrieval_degraded",
    "warning_count",
    "trace",
}


def test_canonical_shape_is_the_dataclass_field_set() -> None:
    bundle = build_evidence_bundle(
        query="q", provider="kbv5", kb_name="kb", content_blocks=["c"], sources=[{"chunk_id": "1"}]
    )
    assert set(bundle.keys()) == _CANONICAL_KEYS
    assert set(EvidenceBundle.__dataclass_fields__.keys()) == _CANONICAL_KEYS
    assert SCHEMA_ID == "rag_evidence_bundle.v1"


def test_status_defaults_ok_and_not_degraded_without_warnings() -> None:
    bundle = build_evidence_bundle(
        query="q", provider="supabase", kb_name="kb", content_blocks=[], sources=[{"id": "1"}]
    )
    assert bundle["retrieval_status"] == "ok"
    assert bundle["retrieval_degraded"] is False
    assert bundle["warning_count"] == 0


def test_status_derives_partial_and_degraded_from_warnings() -> None:
    bundle = build_evidence_bundle(
        query="q",
        provider="supabase",
        kb_name="kb",
        content_blocks=[],
        sources=[{"id": "1"}],
        retrieval_warnings=[{"phase": "provider"}, {"phase": "rerank"}],
    )
    assert bundle["retrieval_status"] == "partial"
    assert bundle["retrieval_degraded"] is True
    assert bundle["warning_count"] == 2


def test_retrieval_status_override_is_honored() -> None:
    # the historical-question lane carries a specific status string
    bundle = build_evidence_bundle(
        query="q",
        provider="supabase",
        kb_name="kb",
        content_blocks=["x"],
        sources=[{"id": "1"}],
        retrieval_warnings=[{"phase": "provider"}],
        retrieval_status="provider_failed_exact_question_resolved",
    )
    assert bundle["retrieval_status"] == "provider_failed_exact_question_resolved"
    # degraded/count still derive from warnings even with an explicit status string
    assert bundle["retrieval_degraded"] is True
    assert bundle["warning_count"] == 1


def test_status_override_ok_with_warnings_is_reconciled_not_contradictory() -> None:
    # Self-defending contract: a bundle with warnings is degraded, so an explicit "ok" status
    # override is incoherent and must be reconciled to "partial" — never emit status="ok" while
    # retrieval_degraded=True (guards a future override caller from a self-contradictory bundle).
    bundle = build_evidence_bundle(
        query="q",
        provider="p",
        kb_name="k",
        content_blocks=[],
        sources=[],
        retrieval_status="ok",
        retrieval_warnings=[{"phase": "provider"}],
    )
    assert bundle["retrieval_degraded"] is True
    assert bundle["retrieval_status"] == "partial"  # reconciled, not the contradictory "ok"
    # a non-healthy override (e.g. the historical status) is preserved as-is alongside warnings
    historical = build_evidence_bundle(
        query="q",
        provider="p",
        kb_name="k",
        content_blocks=[],
        sources=[{"id": "1"}],
        retrieval_status="provider_failed_exact_question_resolved",
        retrieval_warnings=[{"phase": "provider"}],
    )
    assert historical["retrieval_status"] == "provider_failed_exact_question_resolved"
    assert historical["retrieval_degraded"] is True


def test_retrieval_empty_derives_from_sources_and_can_be_overridden() -> None:
    empty = build_evidence_bundle(query="q", provider="kbv5", kb_name="kb", content_blocks=[], sources=[])
    assert empty["retrieval_empty"] is True
    nonempty = build_evidence_bundle(
        query="q", provider="kbv5", kb_name="kb", content_blocks=[], sources=[{"id": "1"}]
    )
    assert nonempty["retrieval_empty"] is False
    forced = build_evidence_bundle(
        query="q", provider="kbv5", kb_name="kb", content_blocks=[], sources=[], retrieval_empty=False
    )
    assert forced["retrieval_empty"] is False


def test_lane_diagnostics_live_in_trace_not_top_level() -> None:
    bundle = build_evidence_bundle(
        query="q",
        provider="kbv5",
        kb_name="kb",
        content_blocks=["c"],
        sources=[{"id": "1"}],
        trace={"transport": "direct_postgres_readonly", "latency_ms": 12.3},
    )
    assert bundle["trace"]["transport"] == "direct_postgres_readonly"
    assert bundle["trace"]["latency_ms"] == 12.3
    # lane-specific keys must NOT leak to the top level (that was the pre-consolidation drift)
    assert "transport" not in bundle
    assert "latency_ms" not in bundle


def test_bundle_id_is_deterministic_and_provider_distinct() -> None:
    a = build_evidence_bundle(query="q", provider="kbv5", kb_name="kb", content_blocks=[], sources=[])
    b = build_evidence_bundle(query="q", provider="kbv5", kb_name="kb", content_blocks=[], sources=[])
    c = build_evidence_bundle(query="q", provider="supabase", kb_name="kb", content_blocks=[], sources=[])
    assert a["bundle_id"] == b["bundle_id"]  # deterministic
    assert a["bundle_id"] != c["bundle_id"]  # provider-distinct (was a drift before)
    assert a["bundle_id"] == evidence_bundle_id("kbv5", "kb", "q")
    assert len(a["bundle_id"]) == 16


def test_explicit_bundle_id_is_passed_through() -> None:
    bundle = build_evidence_bundle(
        query="q", provider="kbv5", kb_name="kb", content_blocks=[], sources=[], bundle_id="fixed-id"
    )
    assert bundle["bundle_id"] == "fixed-id"
