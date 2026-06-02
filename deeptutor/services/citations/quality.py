from __future__ import annotations

import re

from deeptutor.services.citations.redaction import HIDDEN_AUTHORITY_FIELDS
from deeptutor.services.citations.schema import CitedAnswer


class CitationQualityError(ValueError):
    pass


_MARKER_RE = re.compile(r"〔(\d+)〕")
_INLINE_MARKER_RE = re.compile(r"〔(\d{1,3})〕(?=$|[\s，。；;、,.!?！？）\])])")
_HIDDEN_FIELD_PATTERN = "|".join(
    re.escape(field) for field in sorted(HIDDEN_AUTHORITY_FIELDS, key=len, reverse=True)
)
_HIDDEN_LABEL_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?:{_HIDDEN_FIELD_PATTERN})(?![A-Za-z0-9_])\s*[:=：]",
    re.I,
)
_HIDDEN_EXACT_RE = re.compile(
    rf"^(?:{_HIDDEN_FIELD_PATTERN})$",
    re.I,
)
def _contains_hidden_authority(value: object, *, exact_field_name: bool = False) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_hidden_authority(key, exact_field_name=True)
            or _contains_hidden_authority(item, exact_field_name=exact_field_name)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(
            _contains_hidden_authority(item, exact_field_name=exact_field_name)
            for item in value
        )
    text = str(value or "")
    if _HIDDEN_LABEL_RE.search(text):
        return True
    return bool(exact_field_name and _HIDDEN_EXACT_RE.fullmatch(text.strip()))


def validate_cited_answer(answer: CitedAnswer) -> None:
    response = str(answer.response or "")
    if _contains_hidden_authority(response):
        raise CitationQualityError("hidden authority found in public response")
    inline_markers = {int(match.group(1)) for match in _INLINE_MARKER_RE.finditer(response)}
    expected = set(range(1, len(answer.bundle.refs) + 1))
    if answer.bundle.citation_state == "no_public_source":
        if inline_markers:
            raise CitationQualityError("no-public-source answer cannot contain citation markers")
        return
    if inline_markers:
        raise CitationQualityError("public response cannot contain citation markers")
    for ref in answer.bundle.refs:
        if any(
            _contains_hidden_authority(value, exact_field_name=True)
            for value in ref.to_public_dict().values()
        ):
            raise CitationQualityError("hidden authority found in public citation")
    footer_markers = {int(match.group(1)) for match in _MARKER_RE.finditer(answer.bundle.footer_text)}
    if expected - footer_markers:
        raise CitationQualityError("public marker without footer row")
