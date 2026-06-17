"""Rule-based paragraph / numbered-point rebuild from L0 line boxes.

Single-question pages are layout-simple (plan §5): numbering regex +
vertical-gap merge is enough; no paid layout engine. Numbering styles seen
in 一建案例题 answers: 1） 1. 1、 （一） ① 等。
"""

from __future__ import annotations

import re
from typing import Any

_NUMBERING_RE = re.compile(
    r"^\s*("
    r"\d+[）)\.、]"
    r"|（[一二三四五六七八九十\d]+）"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]"
    r")"
)

_GAP_FACTOR = 1.6  # 行距超过典型行高的 1.6 倍视为段落分隔


def rebuild_paragraphs(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    prev_bottom: float | None = None
    heights = [float((line.get("box") or [0, 0, 0, 0])[3]) for line in lines]
    typical_height = (sorted(h for h in heights if h > 0) or [30.0])[len([h for h in heights if h > 0]) // 2] if any(h > 0 for h in heights) else 30.0

    for line in lines:
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        box = list(line.get("box") or [0, 0, 0, 0])
        top = float(box[1])
        numbering_match = _NUMBERING_RE.match(text)
        big_gap = prev_bottom is not None and (top - prev_bottom) > _GAP_FACTOR * typical_height
        starts_new = current is None or numbering_match is not None or big_gap
        if starts_new:
            current = {
                "text": text,
                "numbering": numbering_match.group(1) if numbering_match else "",
                "line_indexes": [line.get("line_index")],
            }
            paragraphs.append(current)
        else:
            assert current is not None
            current["text"] += text
            current["line_indexes"].append(line.get("line_index"))
        prev_bottom = top + float(box[3])

    return paragraphs
