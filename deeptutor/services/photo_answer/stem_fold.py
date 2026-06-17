"""Stem folding: mark OCR paragraphs that are probably the printed question
stem the user photographed along with the answer (plan §5, Codex C5).

Rule semantics (v3.2 G3, pinned): a stem-suspect paragraph is EXCLUDED from
the confirmed_text draft by default but the text is never deleted — the
confirm page shows it as a folded card with one-tap restore. Threshold is
deliberately high (0.62): false "stem" labels on real answers cost an order
of magnitude more than leaving stem noise in (students quote stem
conditions in high-scoring answers).
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher
from typing import Any

_STEM_SIMILARITY_THRESHOLD = 0.62
_MIN_PARA_CHARS = 12  # 短段落（如编号行）不参与题干判定


def _norm(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text or "").split())


def _similarity(para: str, stem: str) -> float:
    if not para or not stem:
        return 0.0
    # 段落通常只是题干的一个片段：用"段落在题干中的最长匹配占段落长度比"而非全局 ratio
    matcher = SequenceMatcher(None, para, stem)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / max(len(para), 1)


def fold_stem_paragraphs(
    paragraphs: list[dict[str, Any]],
    *,
    question_stem: str,
    return_mismatch: bool = False,
    threshold: float = _STEM_SIMILARITY_THRESHOLD,
):
    stem_norm = _norm(question_stem)
    out: list[dict[str, Any]] = []
    for para in paragraphs:
        entry = dict(para)
        para_norm = _norm(str(para.get("text") or ""))
        is_suspect = bool(
            stem_norm
            and len(para_norm) >= _MIN_PARA_CHARS
            and _similarity(para_norm, stem_norm) >= threshold
        )
        entry["is_stem_suspect"] = is_suspect
        out.append(entry)

    if not return_mismatch:
        return out

    # 拍错题信号（plan §11 C18）：保守口径——只有当页面上出现"像题干的长段落"
    # 而它与绑定题干完全不相似时，才报 mismatch。答案与题干不相似是常态，不算。
    mismatch = False
    for entry in out:
        text_norm = _norm(str(entry.get("text") or ""))
        looks_like_stem = text_norm.startswith(_norm("背景资料")) or text_norm.startswith(_norm("背景："))
        if looks_like_stem and len(text_norm) >= 30 and not entry["is_stem_suspect"]:
            mismatch = True
            break
    return out, mismatch
