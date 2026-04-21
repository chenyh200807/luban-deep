from __future__ import annotations

import re
from typing import Any


_BUILDING_ANCHOR_RE = re.compile(
    r"([0-9一二两三四五六七八九十百]+层(?:住宅楼|办公楼|教学楼|厂房|宿舍楼|综合楼|商住楼|楼))",
    flags=re.IGNORECASE,
)


def extract_anchor_terms(*texts: Any, limit: int = 3) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for raw in texts:
        text = str(raw or "").strip()
        if not text:
            continue
        for match in _BUILDING_ANCHOR_RE.findall(text):
            candidate = str(match or "").strip()
            lowered = candidate.lower()
            if not candidate or lowered in seen:
                continue
            seen.add(lowered)
            anchors.append(candidate)
            if len(anchors) >= limit:
                return anchors
    return anchors


def render_anchor_contract(language: str, anchor_terms: list[str]) -> str:
    if not anchor_terms:
        return ""
    if str(language or "").lower().startswith("zh"):
        return (
            "如果继续沿用当前题目的具体案例或对象，必须显式保留这些锚点原词："
            f"{'、'.join(anchor_terms)}。不要自行缩写、泛化或换称呼。"
        )
    return (
        "If you continue using the current question's concrete case or object, "
        f"preserve these anchor terms verbatim: {', '.join(anchor_terms)}. "
        "Do not shorten, generalize, or rename them."
    )
