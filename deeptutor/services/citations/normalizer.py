from __future__ import annotations

import hashlib
import re
from typing import Any

from deeptutor.services.citations.redaction import HIDDEN_AUTHORITY_FIELDS
from deeptutor.services.citations.schema import CitationPolicy, CitationSourceRef
from deeptutor.services.taxonomy.textbook_directory import textbook_topic_meta


_HIDDEN_FIELDS = HIDDEN_AUTHORITY_FIELDS
_TEXTBOOK_CODE_RE = re.compile(r"1A\d{3,6}", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _metadata(source: dict[str, Any]) -> dict[str, Any]:
    metadata = source.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _public_quote(source: dict[str, Any], *, max_chars: int) -> str:
    for key in ("public_quote", "rag_content", "content", "text", "value", "snippet"):
        value = _text(source.get(key))
        if value:
            return value[:max_chars]
    return ""


def _hidden_value_present(source: dict[str, Any]) -> bool:
    metadata = _metadata(source)
    for key in _HIDDEN_FIELDS:
        if key in source or key in metadata:
            return True
    field = _text(source.get("field") or source.get("source_field") or source.get("source_key") or source.get("name"))
    if not field:
        field = _text(metadata.get("field") or metadata.get("source_field") or metadata.get("source_key") or metadata.get("name"))
    return field in _HIDDEN_FIELDS


def _is_hidden_source(source: dict[str, Any], *, policy: CitationPolicy) -> bool:
    return policy.surface == "student" and _hidden_value_present(source)


def _source_type(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    return _text(source.get("source_type") or source.get("_source_group") or metadata.get("source_type") or "source")


def _source_id(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    return _text(
        source.get("source_id")
        or source.get("stable_source_id")
        or metadata.get("source_id")
        or metadata.get("stable_source_id")
        or source.get("chunk_id")
        or source.get("id")
    )


def _source_table(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    return _text(source.get("source_table") or metadata.get("source_table"))


def _stable_id(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    return _text(source.get("stable_id") or metadata.get("stable_id") or source.get("stable_source_id") or metadata.get("stable_source_id"))


def _source_span(source: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(source)
    span = source.get("source_span") or metadata.get("source_span")
    return dict(span) if isinstance(span, dict) else {}


def _raw_title(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    return _text(source.get("title") or metadata.get("title") or source.get("source_title"))


def _title(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    title = _raw_title(source)
    source_type = _source_type(source)
    source_label = _text(
        source.get("source")
        or source.get("source_doc")
        or source.get("doc_id")
        or metadata.get("source")
        or metadata.get("source_doc")
        or metadata.get("doc_id")
    )
    is_2026_textbook = (
        source_type.lower() == "textbook" and "2026" in source_label and "教材" in source_label
    )
    if is_2026_textbook:
        if title and not title.startswith("2026"):
            return f"2026 建筑实务教材：{title}"
        return title or "2026 建筑实务教材"
    return title or source_type


def _taxonomy_code(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    for value in (
        source.get("node_code"),
        metadata.get("node_code"),
        source.get("taxonomy_code"),
        metadata.get("taxonomy_code"),
        source.get("chunk_id"),
        metadata.get("chunk_id"),
        _source_id(source),
        _stable_id(source),
    ):
        match = _TEXTBOOK_CODE_RE.search(_text(value))
        if match:
            return match.group(0).upper()
    return ""


def _taxonomy_path_names(source: dict[str, Any]) -> list[str]:
    metadata = _metadata(source)
    value = source.get("taxonomy_path") or metadata.get("taxonomy_path")
    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    if not text:
        return []
    return [item.strip() for item in re.split(r"\s*(?:>|/|／|,|，|;|；)\s*", text) if item.strip()]


def _textbook_location_meta(source: dict[str, Any]) -> dict[str, Any]:
    if _source_type(source).lower() != "textbook":
        return {}
    code = _taxonomy_code(source)
    path_names = _taxonomy_path_names(source)
    meta = textbook_topic_meta(raw_value=code, label=_raw_title(source), path_names=path_names)
    if path_names and not meta.get("textbook_section_name"):
        for candidate in reversed(path_names):
            path_meta = textbook_topic_meta(raw_value="", label=candidate, path_names=path_names)
            if path_meta.get("textbook_section_name"):
                meta = {**meta, **path_meta}
                break
    return meta


def _format_chapter_locator(chapter: str) -> str:
    clean = _text(chapter)
    if not clean:
        return ""
    if clean.startswith("第") or "章" in clean:
        return clean
    return f"第 {clean} 章"


def _format_section_locator(section: str) -> str:
    clean = _text(section)
    if not clean:
        return ""
    if clean.startswith("第") or "节" in clean:
        return clean
    return f"第 {clean} 节"


def _locator(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    standard_code = _text(source.get("standard_code") or metadata.get("standard_code"))
    article_code = _text(source.get("article_code") or metadata.get("article_code"))
    if standard_code and article_code:
        return f"{standard_code} 第 {article_code} 条"

    span = _source_span(source)
    chapter = _text(span.get("chapter") or metadata.get("chapter") or source.get("chapter"))
    section = _text(span.get("section") or span.get("ref") or metadata.get("section") or source.get("section"))
    page = _text(span.get("page") or metadata.get("page") or source.get("page"))
    textbook_meta = _textbook_location_meta(source)
    parts: list[str] = []
    if chapter:
        parts.append(_format_chapter_locator(chapter))
    elif textbook_meta.get("textbook_chapter_name"):
        parts.append(_text(textbook_meta.get("textbook_chapter_name")))
    if section:
        parts.append(_format_section_locator(section))
    elif textbook_meta.get("textbook_section_name"):
        parts.append(_text(textbook_meta.get("textbook_section_name")))
    if page:
        parts.append(f"p.{page}")
    if parts:
        return " ".join(parts)

    question_no = _text(source.get("question_no") or metadata.get("question_no") or span.get("question"))
    sub_question = _text(source.get("sub_question") or metadata.get("sub_question") or span.get("sub_question"))
    exam_year = _text(source.get("exam_year") or metadata.get("exam_year"))
    if question_no:
        suffix = f"-{sub_question}" if sub_question else ""
        return f"{exam_year} 真题 {question_no}{suffix}".strip()
    return ""


def _stable_ref_id(source: dict[str, Any], locator: str, quote: str) -> str:
    seed = "|".join([_source_id(source), _stable_id(source), _source_type(source), locator, quote])
    return "cite_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def normalize_citation_sources(
    sources: list[dict[str, Any]],
    *,
    policy: CitationPolicy,
) -> list[CitationSourceRef]:
    refs: list[CitationSourceRef] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict) or _is_hidden_source(source, policy=policy):
            continue
        locator = _locator(source)
        sid = _source_id(source)
        stable_id = _stable_id(source)
        metadata = _metadata(source)
        quote = _public_quote(source, max_chars=policy.max_public_quote_chars)
        title = _title(source)
        identity = sid or stable_id or _text(source.get("chunk_id")) or _text(source.get("id"))
        if not identity:
            identity = "|".join([title, quote]).strip("|")
        key = (identity, locator)
        if key in seen:
            continue
        seen.add(key)
        index = len(refs) + 1
        refs.append(
            CitationSourceRef(
                citation_id=_stable_ref_id(source, locator, quote),
                marker=f"〔{index}〕",
                source_type=_source_type(source),
                title=title,
                locator=locator,
                source_id=sid,
                source_table=_source_table(source),
                stable_id=stable_id,
                source_span=_source_span(source),
                content_hash=_text(source.get("content_hash") or metadata.get("content_hash")),
                quote_hash=_text(source.get("quote_hash") or metadata.get("quote_hash")),
                public_quote=quote,
                authority_rank=_int(source.get("authority_rank") or metadata.get("authority_rank")),
                evidence_level=_text(source.get("evidence_level") or metadata.get("evidence_level")),
            )
        )
        if len(refs) >= policy.max_public_refs:
            break
    return refs
