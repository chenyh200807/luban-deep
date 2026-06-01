from __future__ import annotations

from typing import Any

from deeptutor.services.citations.assembler import assemble_cited_answer
from deeptutor.services.citations.quality import CitationQualityError, validate_cited_answer
from deeptutor.services.citations.schema import CitationBundle, CitationPolicy, CitedAnswer


SAFE_CITATION_FAILURE_RESPONSE = (
    "本轮回答包含不可公开展示的内部评分或答案字段，已按安全策略隐藏。"
    "请重新提问，或在提交后查看公开解析。"
)


def assemble_public_cited_answer(
    answer: str,
    *,
    sources: list[dict[str, Any]],
    policy: CitationPolicy | None = None,
) -> CitedAnswer:
    active_policy = policy or CitationPolicy(surface="student")
    try:
        cited = assemble_cited_answer(answer, sources=sources, policy=active_policy)
        validate_cited_answer(cited)
        return cited
    except CitationQualityError:
        cited = assemble_cited_answer(answer, sources=[], policy=active_policy)
        try:
            validate_cited_answer(cited)
            return cited
        except CitationQualityError:
            safe = assemble_cited_answer(
                SAFE_CITATION_FAILURE_RESPONSE,
                sources=[],
                policy=active_policy,
            )
            validate_cited_answer(safe)
            return safe


def citation_metrics(bundle: CitationBundle) -> dict[str, Any]:
    public_markers = {ref.marker for ref in bundle.refs if ref.marker}
    source_types = sorted({str(ref.source_type or "source") for ref in bundle.refs})
    cited_claims = [
        claim for claim in bundle.claims if any(citation_id for citation_id in claim.citation_ids)
    ]
    return {
        "citation_state": bundle.citation_state,
        "citation_ref_count": len(bundle.refs),
        "citation_claim_count": len(bundle.claims),
        "citation_source_types": source_types,
        "citation_quality": {
            "hidden_leak_detected": False,
            "orphan_marker_count": 0,
            "footer_marker_mismatch": False,
            "orphan_marker_detected": False,
            "footer_mismatch_detected": False,
        },
        "public_ref_count": len(bundle.refs),
        "claim_count": len(bundle.claims),
        "cited_claim_count": len(cited_claims),
        "public_marker_count": len(public_markers),
    }


def apply_answer_citation_metadata(
    result_payload: dict[str, Any],
    *,
    response: str,
    sources: list[dict[str, Any]],
    enabled: bool,
    policy: CitationPolicy | None = None,
) -> str:
    cited = assemble_public_cited_answer(response, sources=sources, policy=policy)
    metrics = citation_metrics(cited.bundle)
    if enabled:
        result_payload["citation_bundle"] = cited.bundle.to_public_dict()
        result_payload["citation_metrics"] = metrics
        return cited.response
    result_payload["citation_bundle_candidate"] = cited.bundle.to_public_dict()
    result_payload["citation_metrics"] = metrics
    return response
