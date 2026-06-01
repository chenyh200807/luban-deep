from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from deeptutor.services.citations.formatter import format_citation_footer
from deeptutor.services.citations.normalizer import normalize_citation_sources
from deeptutor.services.citations.schema import (
    CitationBundle,
    CitationPolicy,
    CitationSourceRef,
    CitedAnswer,
    CitedClaim,
)


_FOOTER_RE = re.compile(r"\n{1,2}依据\n", re.MULTILINE)
_MARKER_RE = re.compile(r"〔\d+〕$")
_STANDARD_CLAIM_RE = re.compile(
    r"(?:\b(?:GB|GB/T|JGJ|CECS|DB)\s*[- ]?\d+|第\s*\d+(?:\.\d+){1,4}\s*条|条文|规范规定|标准规定)",
    re.IGNORECASE,
)


def _strip_existing_footer(answer: str) -> str:
    text = str(answer or "").strip()
    match = _FOOTER_RE.search(text)
    return text[: match.start()].strip() if match else text


def _segments(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"(\n{2,}|(?<=。)\n)", answer) if part.strip()]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text))


def _score(segment: str, ref: CitationSourceRef) -> float:
    source_text = " ".join([ref.public_quote, ref.title, ref.locator])
    a = _tokens(segment)
    b = _tokens(source_text)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), 1)


def _source_type_priority(ref: CitationSourceRef, *, policy: CitationPolicy) -> int:
    if policy.surface != "student":
        return 0
    source_type = str(ref.source_type or "").strip().lower()
    return {
        "textbook": 40,
        "textbook_assessment": 35,
        "questions_bank": 30,
        "exam": 25,
        "compiled_learning_truth": 20,
        "standard": 10,
        "spec": 10,
    }.get(source_type, 0)


def _is_standard_ref(ref: CitationSourceRef) -> bool:
    source_type = str(ref.source_type or "").strip().lower()
    return source_type in {"standard", "spec", "standard_precision", "standard_code_exact"}


def _looks_like_standard_claim(segment: str) -> bool:
    return bool(_STANDARD_CLAIM_RE.search(str(segment or "")))


def _best_ref(
    segment: str,
    refs: list[CitationSourceRef],
    *,
    policy: CitationPolicy,
) -> tuple[CitationSourceRef | None, float]:
    scored = [(ref, _score(segment, ref)) for ref in refs]
    if not scored:
        return None, 0.0
    if policy.surface == "student" and _looks_like_standard_claim(segment):
        standard_candidates = [
            (ref, score)
            for ref, score in scored
            if _is_standard_ref(ref) and score >= policy.min_claim_ref_score
        ]
        if standard_candidates:
            return max(standard_candidates, key=lambda item: (item[1], item[0].authority_rank))
    if policy.surface == "student":
        best_score = max(score for _, score in scored)
        preferred_score_floor = max(policy.min_claim_ref_score, best_score - 0.12)
        preferred = [
            (ref, score)
            for ref, score in scored
            if score >= preferred_score_floor and _source_type_priority(ref, policy=policy) > 0
        ]
        if preferred:
            return max(
                preferred,
                key=lambda item: (
                    _source_type_priority(item[0], policy=policy),
                    item[1],
                    item[0].authority_rank,
                ),
            )
    return max(scored, key=lambda item: (item[1], item[0].authority_rank))


def assemble_cited_answer(
    answer: str,
    *,
    sources: list[dict[str, Any]],
    policy: CitationPolicy | None = None,
) -> CitedAnswer:
    active_policy = policy or CitationPolicy()
    clean_answer = _strip_existing_footer(answer)
    refs = normalize_citation_sources(sources, policy=active_policy)
    if not refs:
        bundle = CitationBundle.no_public_source()
        return CitedAnswer(response=f"{clean_answer}\n\n{bundle.footer_text}".strip(), bundle=bundle)

    rendered_segments: list[str] = []
    claims: list[CitedClaim] = []
    used_ref_ids: set[str] = set()
    matched_count = 0
    segments = _segments(clean_answer)
    for index, segment in enumerate(segments, start=1):
        ref, score = _best_ref(segment, refs, policy=active_policy)
        if ref and score >= active_policy.min_claim_ref_score and not _MARKER_RE.search(segment):
            rendered_segments.append(f"{segment}{ref.marker}")
            claims.append(CitedClaim(f"claim_{index}", segment, [ref.citation_id], round(score, 4)))
            used_ref_ids.add(ref.citation_id)
            matched_count += 1
        else:
            rendered_segments.append(segment)

    if matched_count == 0 and refs and rendered_segments:
        ref = refs[0]
        original_segment = rendered_segments[-1]
        rendered_segments[-1] = f"{original_segment}{ref.marker}"
        claims.append(CitedClaim("claim_fallback_1", original_segment, [ref.citation_id], 0.0))
        used_ref_ids.add(ref.citation_id)

    citation_state = "supported" if matched_count == len(segments) else "partial"
    visible_refs: list[CitationSourceRef] = []
    marker_map: dict[str, str] = {}
    for ref in refs:
        if ref.citation_id not in used_ref_ids:
            continue
        new_marker = f"〔{len(visible_refs) + 1}〕"
        marker_map[ref.marker] = new_marker
        visible_refs.append(replace(ref, marker=new_marker))
    if marker_map:
        renumbered_segments: list[str] = []
        for segment in rendered_segments:
            updated = segment
            for old_marker, new_marker in marker_map.items():
                updated = updated.replace(old_marker, new_marker)
            renumbered_segments.append(updated)
        rendered_segments = renumbered_segments
    footer = format_citation_footer(visible_refs)
    bundle = CitationBundle(citation_state=citation_state, refs=visible_refs, claims=claims, footer_text=footer)
    body = "\n\n".join(rendered_segments)
    return CitedAnswer(response=f"{body}\n\n{footer}".strip(), bundle=bundle)
