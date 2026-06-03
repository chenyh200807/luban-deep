from __future__ import annotations

import hashlib
import re
from typing import Any

from deeptutor.services.citations.redaction import HIDDEN_AUTHORITY_FIELDS
from deeptutor.services.citations.schema import CitationPolicy, CitationSourceRef
from deeptutor.services.taxonomy.textbook_directory import textbook_topic_meta


_HIDDEN_FIELDS = HIDDEN_AUTHORITY_FIELDS
_TEXTBOOK_CODE_RE = re.compile(r"1A\d{3,6}", re.IGNORECASE)
_SECTION_GENERIC_TERMS = ("工程", "施工", "技术", "相关", "规定", "管理", "应用")
_STANDARD_SOURCE_TYPES = {"standard", "spec", "standard_precision", "standard_code_exact", "standard_article"}
_QUESTION_SOURCE_TABLES = {"questions_bank", "question_bank"}


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


def _is_standard_source(source: dict[str, Any]) -> bool:
    return _source_type(source).lower() in _STANDARD_SOURCE_TYPES


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


def _trusted_taxonomy_code(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    for value in (
        source.get("node_code"),
        metadata.get("node_code"),
        source.get("taxonomy_code"),
        metadata.get("taxonomy_code"),
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


def _textbook_location_meta(source: dict[str, Any], *, allow_linked_source: bool = False) -> dict[str, Any]:
    source_type = _source_type(source).lower()
    if source_type != "textbook" and (not allow_linked_source or not _is_standard_source(source)):
        return {}
    code = _taxonomy_code(source) if source_type == "textbook" else _trusted_taxonomy_code(source)
    path_names = _taxonomy_path_names(source)
    if allow_linked_source and source_type != "textbook" and not code and not path_names:
        return {}
    label = _raw_title(source) if source_type == "textbook" else (path_names[-1] if path_names else code)
    meta = textbook_topic_meta(raw_value=code, label=label, path_names=path_names)
    if path_names and not meta.get("textbook_section_name"):
        for candidate in reversed(path_names):
            path_meta = textbook_topic_meta(raw_value="", label=candidate, path_names=path_names)
            if path_meta.get("textbook_section_name") and _section_supported_by_source(source, candidate):
                meta = {**meta, **path_meta}
                break
    return meta


def _related_textbook_locator(source: dict[str, Any]) -> str:
    if _source_type(source).lower() == "textbook" or not _is_standard_source(source):
        return ""
    textbook_meta = _textbook_location_meta(source, allow_linked_source=True)
    parts: list[str] = []
    if textbook_meta.get("textbook_chapter_name"):
        parts.append(_text(textbook_meta.get("textbook_chapter_name")))
    if textbook_meta.get("textbook_section_name"):
        parts.append(_text(textbook_meta.get("textbook_section_name")))
    return f"关联教材：{' '.join(parts)}" if parts else ""


def _append_related_textbook_locator(source: dict[str, Any], locator: str) -> str:
    related = _related_textbook_locator(source)
    if not related:
        return locator
    return f"{locator}；{related}"


def _section_supported_by_source(source: dict[str, Any], section: str) -> bool:
    candidate = _text(section)
    if not candidate:
        return False
    haystack = "".join(
        [
            _raw_title(source),
            _text(source.get("content") or source.get("rag_content") or source.get("public_quote")),
        ]
    )
    if not haystack:
        return False
    reduced = candidate
    for term in _SECTION_GENERIC_TERMS:
        reduced = reduced.replace(term, "")
    parts = [item for item in re.split(r"[与和及、/／\s]+", reduced) if len(item) >= 2]
    if len(reduced) >= 2:
        parts.extend(reduced[index : index + 2] for index in range(0, len(reduced) - 1))
    seen: set[str] = set()
    for token in parts:
        if token in seen:
            continue
        seen.add(token)
        if token and token in haystack:
            return True
    return False


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
    if re.search(r"[\u4e00-\u9fff]", clean) and not re.match(r"^\d+(?:\.\d+)*", clean):
        return clean
    return f"第 {clean} 节"


def _locator(source: dict[str, Any]) -> str:
    metadata = _metadata(source)
    standard_code = _text(source.get("standard_code") or metadata.get("standard_code"))
    article_code = _text(source.get("article_code") or metadata.get("article_code"))
    if standard_code and article_code:
        return _append_related_textbook_locator(source, f"{standard_code} 第 {article_code} 条")
    if standard_code:
        return _append_related_textbook_locator(source, standard_code)

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
        locator = " ".join(parts)
        return _append_related_textbook_locator(source, locator) if _is_standard_source(source) else locator

    question_no = _text(source.get("question_no") or metadata.get("question_no") or span.get("question"))
    sub_question = _text(source.get("sub_question") or metadata.get("sub_question") or span.get("sub_question"))
    exam_year = _text(source.get("exam_year") or metadata.get("exam_year"))
    if question_no:
        suffix = f"-{sub_question}" if sub_question else ""
        return f"{exam_year} 真题 {question_no}{suffix}".strip()
    if _is_standard_source(source):
        related = _related_textbook_locator(source)
        if related:
            return related
    return ""


def _stable_ref_id(source: dict[str, Any], locator: str, quote: str) -> str:
    seed = "|".join([_source_id(source), _stable_id(source), _source_type(source), locator, quote])
    return "cite_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _student_source_priority(source: dict[str, Any]) -> int:
    source_type = _source_type(source).lower()
    source_table = _source_table(source).lower()
    span = _source_span(source)
    standard_code = _text(source.get("standard_code") or _metadata(source).get("standard_code"))
    article_code = _text(source.get("article_code") or _metadata(source).get("article_code"))

    if source_table in _QUESTION_SOURCE_TABLES:
        return 45
    if source_table == "kb_chunks" and source_type == "textbook" and span:
        return 100
    if source_table == "kb_chunks" and source_type == "textbook":
        return 95
    if source_type == "textbook" and span:
        return 90
    if source_type == "textbook":
        return 88
    if standard_code and article_code:
        return 85
    if source_type in _STANDARD_SOURCE_TYPES:
        return 80
    return 50


def _public_source_candidates(
    sources: list[dict[str, Any]],
    *,
    policy: CitationPolicy,
) -> list[dict[str, Any]]:
    candidates = [
        source
        for source in sources
        if isinstance(source, dict) and not _is_hidden_source(source, policy=policy)
    ]
    if policy.surface != "student":
        return candidates
    ordered = sorted(
        enumerate(candidates),
        key=lambda item: (
            -_student_source_priority(item[1]),
            -_int(item[1].get("authority_rank") or _metadata(item[1]).get("authority_rank")),
            item[0],
        ),
    )
    return [source for _, source in ordered]


def normalize_citation_sources(
    sources: list[dict[str, Any]],
    *,
    policy: CitationPolicy,
) -> list[CitationSourceRef]:
    refs: list[CitationSourceRef] = []
    seen: set[tuple[str, str]] = set()
    for source in _public_source_candidates(sources, policy=policy):
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
