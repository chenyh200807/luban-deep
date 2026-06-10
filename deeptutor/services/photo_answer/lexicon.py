"""Shape-error lexicon suggestions (plan §8 lexicon row, Codex C8/C17).

HARD CONSTRAINT: suggestions require OCR candidate evidence. We only
propose replacing char X with candidate Y when (a) the engine itself listed
Y as a recognition candidate for that exact glyph, and (b) the substitution
makes the surrounding text match a domain lexicon term. This is OCR shape
correction. We never suggest rubric required_terms or any substitution the
engine didn't already consider — that would turn the confirm page into an
answer polisher and destroy grading fairness.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_TAXONOMY_FILENAME = "FINAL_CLEANED_TAXONOMY2026.json"


@lru_cache(maxsize=1)
def load_taxonomy_terms() -> frozenset[str]:
    """Best-effort load of canonical taxonomy keywords as the lexicon.

    Missing taxonomy → empty lexicon → zero suggestions (fail-open is safe:
    the feature degrades to nothing rather than to wrong suggestions).
    """
    candidates = [
        Path(__file__).resolve().parents[3] / _TAXONOMY_FILENAME,
        Path(__file__).resolve().parents[3] / "data" / _TAXONOMY_FILENAME,
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to load taxonomy lexicon from %s", path, exc_info=True)
            continue
        terms: set[str] = set()

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                for key in ("name", "keyword", "keywords", "title"):
                    value = node.get(key)
                    if isinstance(value, str) and len(value) >= 3:
                        terms.add(value)
                    elif isinstance(value, list):
                        terms.update(v for v in value if isinstance(v, str) and len(v) >= 3)
                for value in node.values():
                    _walk(value)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(payload)
        if terms:
            return frozenset(terms)
    return frozenset()


def suggest_shape_corrections(
    line_text: str,
    chars: list[dict[str, Any]],
    *,
    lexicon_terms: Iterable[str] | None = None,
    low_conf_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    terms = set(lexicon_terms) if lexicon_terms is not None else set(load_taxonomy_terms())
    if not terms or not line_text:
        return []

    suggestions: list[dict[str, Any]] = []
    for ch in chars:
        prob = float(ch.get("prob") or 0.0)
        char_text = str(ch.get("char") or "")
        candidates = [c for c in (ch.get("candidates") or []) if c and c != char_text]
        if not char_text or prob >= low_conf_threshold or not candidates:
            continue
        pos = line_text.find(char_text)
        if pos < 0:
            continue
        for candidate in candidates:
            replaced = line_text[:pos] + candidate + line_text[pos + len(char_text):]
            matched_term = next((t for t in terms if t in replaced and t not in line_text), None)
            if matched_term:
                suggestions.append(
                    {
                        "char": char_text,
                        "suggestion": candidate,
                        "term": matched_term,
                        "line_index": ch.get("line_index"),
                        "box": list(ch.get("box") or []),
                    }
                )
                break
    return suggestions
