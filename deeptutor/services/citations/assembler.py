from __future__ import annotations

import re
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
_REFERENCE_LINE_RE = re.compile(
    r"^\s*(?:[-*>]\s*)?(?:#{1,6}\s*)?(?:依据|参考依据|参考来源|参考文献|references?)\s*[:：]\s*(?P<body>.*)$",
    re.IGNORECASE,
)
_REFERENCE_SOURCE_HINT_RE = re.compile(
    r"(?:source[_ -]?id|2026\s*建筑实务教材|教材|摘录|参考文献|§|"
    r"\b(?:GB|GB/T|JGJ|CECS|DB)\s*[- ]?\d+|第\s*\d+\s*章|第\s*\d+(?:\.\d+){1,4}\s*条)",
    re.IGNORECASE,
)
_STANDARD_CLAIM_RE = re.compile(
    r"(?:\b(?:GB|GB/T|JGJ|CECS|DB)\s*[- ]?\d+|第\s*\d+(?:\.\d+){1,4}\s*条|条文|规范规定|标准规定)",
    re.IGNORECASE,
)


def _strip_existing_footer(answer: str) -> str:
    text = str(answer or "").strip()
    footer_start: int | None = None
    for match in _FOOTER_RE.finditer(text):
        footer = text[match.end() :]
        if re.search(r"〔\d{1,3}〕", footer) and _REFERENCE_SOURCE_HINT_RE.search(footer):
            footer_start = match.start()
    return text[:footer_start].strip() if footer_start is not None else text


def _marker_pattern(markers: list[str]) -> re.Pattern[str] | None:
    escaped = [re.escape(marker) for marker in markers if marker]
    if not escaped:
        return None
    return re.compile(rf"(?:{'|'.join(escaped)})(?=$|[\s，。；;、,.!?！？）\])])")


def _strip_inline_reference_noise(answer: str, *, markers: list[str]) -> str:
    marker_pattern = _marker_pattern(markers)
    lines = []
    for line in str(answer or "").splitlines():
        reference_line = _REFERENCE_LINE_RE.match(line)
        if reference_line and _REFERENCE_SOURCE_HINT_RE.search(reference_line.group("body")):
            continue
        cleaned = marker_pattern.sub("", line) if marker_pattern else line
        lines.append(cleaned.rstrip())
    return "\n".join(lines).strip()


_ORPHAN_REFERENCE_MARKER_RE = re.compile(r"〔(\d{1,3})〕")
# 〔源:chunk_id〕 是 rich_leaf 检索 grounding 标记(supporting-citation-only),只该
# 出现在喂 LLM 判分/教学的上下文里,绝不是合法学生引用(合法引用是带 footer 的数字
# 〔N〕)。judge 模仿进输出时必须无条件剥——与 backing footer 无关。
_GROUNDING_SOURCE_MARKER_RE = re.compile(r"〔源[:：][^〕]*〕")


def _backing_reference_footer_markers(text: str) -> tuple[int | None, set[int]]:
    """Return the last legal citation footer start and its backed numeric markers."""
    footer_start: int | None = None
    backed_markers: set[int] = set()
    for match in _FOOTER_RE.finditer(text):
        footer = text[match.end() :]
        markers = {int(item.group(1)) for item in _ORPHAN_REFERENCE_MARKER_RE.finditer(footer)}
        if markers and _REFERENCE_SOURCE_HINT_RE.search(footer):
            footer_start = match.start()
            backed_markers = markers
    return footer_start, backed_markers


def _strip_unbacked_reference_markers(text: str, *, backed_markers: set[int]) -> str:
    def _replace(match: re.Match[str]) -> str:
        marker = int(match.group(1))
        return match.group(0) if marker in backed_markers else ""

    return _ORPHAN_REFERENCE_MARKER_RE.sub(_replace, text)


def strip_orphan_reference_markers(answer: str) -> str:
    """剥离学生可见文本里的孤儿数字脚注标注（〔N〕）+ 参考依据行。

    判据是 **这段文本里 〔N〕 有没有 backing footer**,与全局 citation flag 无关——
    实证(2026-06-23):test2 上 `answer_citations_enabled()=True` 但判分 LLM 吐的 〔N〕
    并没走引用装配、没有 footer = 孤儿,仍漏给学生。所以 flag≠footer,必须按 footer 判。
    有合法 footer(`依据`段+来源线索)→ 〔N〕 是合法引用,整段不动;无 footer → 〔N〕 是
    主 LLM 输出但解析不到来源的内部噪声,剥掉 + 去掉悬空参考依据行。
    """
    text = str(answer or "")
    if not text.strip():
        return text
    # 〔源:chunk_id〕 grounding 标记永远剥(与 footer 无关),它不是合法学生引用。
    text = _GROUNDING_SOURCE_MARKER_RE.sub("", text)
    footer_start, backed_markers = _backing_reference_footer_markers(text)
    if backed_markers:
        body = text[:footer_start] if footer_start is not None else text
        footer = text[footer_start:] if footer_start is not None else ""
        return _strip_unbacked_reference_markers(body, backed_markers=backed_markers) + footer
    lines = []
    for line in text.splitlines():
        reference_line = _REFERENCE_LINE_RE.match(line)
        if reference_line and _REFERENCE_SOURCE_HINT_RE.search(reference_line.group("body")):
            continue
        lines.append(_ORPHAN_REFERENCE_MARKER_RE.sub("", line).rstrip())
    return "\n".join(lines).strip()


def _segments(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"(\n{2,}|(?<=。)\n)", answer) if part.strip()]


def _is_citable_segment(segment: str) -> bool:
    text = str(segment or "").strip()
    if not text:
        return False
    if re.fullmatch(r"[-*_]{3,}", text):
        return False
    return not re.match(r"^#{1,6}\s+\S+", text)


def _claim_text_from_segment(segment: str) -> str:
    lines = []
    for line in str(segment or "").splitlines():
        text = line.strip()
        if not _is_citable_segment(text):
            continue
        lines.append(text)
    return "\n".join(lines).strip()


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


def _insert_inline_markers(
    answer: str,
    claims: list[CitedClaim],
    refs: list[CitationSourceRef],
) -> str:
    if not claims or not refs:
        return answer
    refs_by_id = {ref.citation_id: ref for ref in refs}
    marked = str(answer or "")
    cursor = 0
    for claim in claims:
        markers = "".join(
            ref.marker
            for citation_id in claim.citation_ids
            if (ref := refs_by_id.get(citation_id)) is not None and ref.marker
        )
        target = str(claim.text or "").strip()
        if not markers or not target:
            continue
        replacement = f"{target}{markers}"
        index = marked.find(target, cursor)
        if index < 0:
            index = marked.find(target)
        if index < 0:
            continue
        marked = f"{marked[:index]}{replacement}{marked[index + len(target):]}"
        cursor = index + len(replacement)
    return marked


def assemble_cited_answer(
    answer: str,
    *,
    sources: list[dict[str, Any]],
    policy: CitationPolicy | None = None,
) -> CitedAnswer:
    active_policy = policy or CitationPolicy()
    refs = normalize_citation_sources(sources, policy=active_policy)
    markers = [ref.marker for ref in refs] or [
        f"〔{index}〕" for index in range(1, active_policy.max_public_refs + 1)
    ]
    clean_answer = _strip_inline_reference_noise(_strip_existing_footer(answer), markers=markers)
    if not refs:
        bundle = CitationBundle.no_public_source()
        return CitedAnswer(response=clean_answer, bundle=bundle)

    claims: list[CitedClaim] = []
    matched_count = 0
    segments = [claim_text for segment in _segments(clean_answer) if (claim_text := _claim_text_from_segment(segment))]
    for index, segment in enumerate(segments, start=1):
        ref, score = _best_ref(segment, refs, policy=active_policy)
        if ref and score >= active_policy.min_claim_ref_score:
            claims.append(CitedClaim(f"claim_{index}", segment, [ref.citation_id], round(score, 4)))
            matched_count += 1

    citation_state = "supported" if matched_count == len(segments) else "partial"
    marked_answer = _insert_inline_markers(clean_answer, claims, refs)
    footer = format_citation_footer(refs)
    bundle = CitationBundle(citation_state=citation_state, refs=refs, claims=claims, footer_text=footer)
    return CitedAnswer(response=marked_answer, bundle=bundle)
