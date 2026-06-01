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


def _best_ref(segment: str, refs: list[CitationSourceRef]) -> tuple[CitationSourceRef | None, float]:
    scored = [(ref, _score(segment, ref)) for ref in refs]
    if not scored:
        return None, 0.0
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
        ref, score = _best_ref(segment, refs)
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
