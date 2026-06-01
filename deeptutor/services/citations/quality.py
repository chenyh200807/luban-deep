from __future__ import annotations

import re

from deeptutor.services.citations.redaction import HIDDEN_AUTHORITY_FIELDS
from deeptutor.services.citations.schema import CitedAnswer


class CitationQualityError(ValueError):
    pass


_MARKER_RE = re.compile(r"〔(\d+)〕")
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
_FOOTER_SPLIT_RE = re.compile(r"\n{1,2}依据\n", re.MULTILINE)


def _split_body_footer(response: str) -> tuple[str, str]:
    match = _FOOTER_SPLIT_RE.search(response)
    if not match:
        return response, ""
    return response[: match.start()], response[match.start() :]


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
    body, footer = _split_body_footer(response)
    body_markers = {int(match.group(1)) for match in _MARKER_RE.finditer(body)}
    all_markers = {int(match.group(1)) for match in _MARKER_RE.finditer(response)}
    expected = set(range(1, len(answer.bundle.refs) + 1))
    if answer.bundle.citation_state == "no_public_source":
        if all_markers:
            raise CitationQualityError("no-public-source answer cannot contain citation markers")
        return
    if all_markers - expected:
        raise CitationQualityError("orphan citation marker")
    if expected - body_markers:
        raise CitationQualityError("footer row without visible marker")
    if footer and expected - {int(match.group(1)) for match in _MARKER_RE.finditer(footer)}:
        raise CitationQualityError("public marker without footer row")
    for ref in answer.bundle.refs:
        if any(
            _contains_hidden_authority(value, exact_field_name=True)
            for value in ref.to_public_dict().values()
        ):
            raise CitationQualityError("hidden authority found in public citation")
