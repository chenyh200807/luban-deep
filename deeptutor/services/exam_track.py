"""Canonical exam-track normalization for construction exam runtime."""

from __future__ import annotations

from typing import Any

EXAM_TRACK_LABELS: dict[str, str] = {
    "first_construction": "一级建造师建筑实务",
    "second_construction": "二级建造师建筑实务",
    "first_cost": "一级造价工程师",
    "second_cost": "二级造价工程师",
}

_TRACK_ALIASES: dict[str, str] = {
    "first_construction": "first_construction",
    "yijian": "first_construction",
    "一级建造师": "first_construction",
    "一建": "first_construction",
    "second_construction": "second_construction",
    "erjian": "second_construction",
    "二级建造师": "second_construction",
    "二建": "second_construction",
    "first_cost": "first_cost",
    "yizao": "first_cost",
    "一级造价工程师": "first_cost",
    "一级造价": "first_cost",
    "一造": "first_cost",
    "second_cost": "second_cost",
    "erzao": "second_cost",
    "二级造价工程师": "second_cost",
    "二级造价": "second_cost",
    "二造": "second_cost",
}

_TRACK_MENTIONS: tuple[tuple[str, str], ...] = (
    ("一级造价工程师", "first_cost"),
    ("二级造价工程师", "second_cost"),
    ("一级建造师", "first_construction"),
    ("二级建造师", "second_construction"),
    ("一级造价", "first_cost"),
    ("二级造价", "second_cost"),
    ("一造", "first_cost"),
    ("二造", "second_cost"),
    ("一建", "first_construction"),
    ("二建", "second_construction"),
)

_NEGATION_MARKERS = (
    "不是",
    "并非",
    "非",
    "不要按",
    "别按",
    "不用按",
    "不要",
    "别",
)


def normalize_exam_track(value: Any) -> str:
    """Return the canonical exam track id, or empty string when unknown."""
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    return _TRACK_ALIASES.get(lowered) or _TRACK_ALIASES.get(normalized) or ""


def infer_exam_track_from_text(text: str) -> str:
    """Infer an explicit track mention from user text without guessing on generic construction terms."""
    content = str(text or "").strip()
    if not content:
        return ""

    matches = _positive_exam_track_mentions(content)

    if not matches:
        return ""
    if len({track for _, track in matches}) > 1:
        return ""
    return max(matches, key=lambda item: item[0])[1]


def infer_denied_exam_tracks_from_text(text: str) -> set[str]:
    """Return explicitly negated track ids from user text."""
    content = str(text or "").strip()
    if not content:
        return set()

    denied: set[str] = set()
    for needle, track in _TRACK_MENTIONS:
        start = 0
        while True:
            index = content.find(needle, start)
            if index < 0:
                break
            if _is_negated_exam_track_mention(content, index):
                denied.add(track)
            start = index + len(needle)
    return denied


def has_multiple_exam_track_mentions(text: str) -> bool:
    """Return whether user text explicitly mentions multiple non-negated exam tracks."""
    content = str(text or "").strip()
    if not content:
        return False
    matches = _positive_exam_track_mentions(content)
    return len({track for _, track in matches}) > 1


def _positive_exam_track_mentions(content: str) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for needle, track in _TRACK_MENTIONS:
        start = 0
        while True:
            index = content.find(needle, start)
            if index < 0:
                break
            if not _is_negated_exam_track_mention(content, index):
                matches.append((index, track))
            start = index + len(needle)
    return matches


def _is_negated_exam_track_mention(content: str, mention_index: int) -> bool:
    prefix = content[max(0, mention_index - 8) : mention_index]
    normalized_prefix = prefix.strip(" \t\r\n，,。.!！?；;：:")
    return any(normalized_prefix.endswith(marker) for marker in _NEGATION_MARKERS)


def exam_track_label(track: Any) -> str:
    return EXAM_TRACK_LABELS.get(normalize_exam_track(track), "")
