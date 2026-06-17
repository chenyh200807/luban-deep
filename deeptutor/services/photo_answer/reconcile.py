"""Line-level cross-engine reconciliation (plan §5, Codex C6 design).

L0 (coordinate-bearing OCR) is the text and coordinate authority. L1
(generative VLM) text is only compared against L0 *lines* after
normalization; a poorly-matching line becomes a line-level "risk" suspicion
anchored to the L0 box. We deliberately do NOT char-align L0 against L1 —
generative output reflows/merges/repairs text, and char-level hard
alignment manufactures false divergences (满屏红 kills the confirm page).

Suspicion sources: engine_diff (L0×L1 divergence), low_conf (L0 char
probability). Numeric divergence is severity=critical (plan §7 C9: 数字/
金额/工期类疑点未确认 → fail-closed)。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from deeptutor.services.photo_answer.engines.base import EngineResult

_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

DEFAULT_LINE_SIMILARITY_FLOOR = 0.85
DEFAULT_LOW_CONF_THRESHOLD = 0.55


def normalize(text: str) -> str:
    """NFKC width-fold + strip all whitespace — alignment form only."""
    return _WS_RE.sub("", unicodedata.normalize("NFKC", text or ""))


@dataclass
class ReconcileOutput:
    suspicions: list[dict[str, Any]] = field(default_factory=list)
    line_scores: list[dict[str, Any]] = field(default_factory=list)


def _best_match_ratio(needle: str, haystack_lines: list[str]) -> float:
    if not needle:
        return 1.0
    best = 0.0
    for cand in haystack_lines:
        ratio = SequenceMatcher(None, needle, cand).ratio()
        if ratio > best:
            best = ratio
        if best >= 0.999:
            break
    return best


def _numbers_diverge(l0_line: str, l1_lines: list[str]) -> bool:
    nums = set(_NUM_RE.findall(normalize(l0_line)))
    if not nums:
        return False
    joined = normalize("\n".join(l1_lines))
    return any(n not in joined for n in nums)


def reconcile(
    l0: EngineResult,
    l1: EngineResult | None,
    *,
    line_similarity_floor: float = DEFAULT_LINE_SIMILARITY_FLOOR,
    low_conf_threshold: float = DEFAULT_LOW_CONF_THRESHOLD,
) -> ReconcileOutput:
    out = ReconcileOutput()

    l1_lines = [normalize(line) for line in (l1.raw_text if l1 else "").splitlines() if normalize(line)]

    for line in l0.line_boxes:
        text_norm = normalize(str(line.get("text") or ""))
        if not text_norm:
            continue
        score = _best_match_ratio(text_norm, l1_lines) if l1_lines else 1.0
        out.line_scores.append(
            {"line_index": line.get("line_index"), "score": score, "box": line.get("box")}
        )
        if not l1_lines:
            continue
        # 数字分歧独立于行相似度阈值：120 vs 180 的行 ratio 高达 0.857，
        # 会从任何合理阈值下溜走，但数字错一个就翻判（plan §9 ④）。
        numeric_div = _numbers_diverge(str(line.get("text") or ""), l1_lines)
        if numeric_div or score < line_similarity_floor:
            out.suspicions.append(
                {
                    "source": "engine_diff",
                    "severity": "critical" if numeric_div else "normal",
                    "page_index": int(line.get("page_index", 0)),
                    "span": {
                        "line_index": line.get("line_index"),
                        "box": list(line.get("box") or []),
                        "text": str(line.get("text") or ""),
                    },
                    "suggestion": "",
                }
            )

    for ch in l0.char_confidences:
        prob = float(ch.get("prob") or 0.0)
        if prob and prob < low_conf_threshold:
            char_text = str(ch.get("char") or "")
            severity = "critical" if char_text.isdigit() else "normal"
            out.suspicions.append(
                {
                    "source": "low_conf",
                    "severity": severity,
                    "page_index": int(ch.get("page_index", 0)),
                    "span": {
                        "line_index": ch.get("line_index"),
                        "box": list(ch.get("box") or []),
                        "char": char_text,
                    },
                    "suggestion": "/".join(
                        c for c in (ch.get("candidates") or []) if c and c != char_text
                    ),
                }
            )

    return out
