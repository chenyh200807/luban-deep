"""Textbook verbatim lane — the S2 worker (Living LLM Artifact Compiler increment ①).

Turns one ``textbook_block`` EvidenceItem (a 2026 教材 content_block: content_markdown +
knowledge_cards + taxonomy) into per-card CANDIDATES through ``compiler_feedback.make_candidate``.
The worker only PROPOSES a verbatim quote per card; the deterministic signer
(``compile_textbook_knowledge_release_candidate``) is the sole authority that re-checks every field
against the block's own ``content_markdown`` and signs ONLY confirmed fields.

Two paths, identical output shape:
  * deterministic (no-LLM, hermetic): finds the longest verbatim clause of the card that is a
    substring of content_markdown.
  * DeepSeek live: the model proposes an exact verbatim span; the worker re-checks the substring
    before attaching it (defense in depth), and the signer re-checks again (final authority).

The worker NEVER signs, never promotes, never decides correctness.
"""
from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from deeptutor.services.construction_grading import compiler_feedback as _CF
from deeptutor.services.construction_grading.full_knowledge_compiler import (
    _MIN_SPAN,
    _norm_textbook,
)

_CLAUSE_SPLIT = re.compile(r"[。；;！!？?\n、，,：:]")
# Below this length a deterministic clause span is a weak fragment; ask the LLM for a fuller verbatim
# span (quality enrichment ① + rescue of clause-misaligned spans = human-gate expansion ②).
_ENRICH_THRESHOLD = 16


def _node_code(payload: dict[str, Any]) -> str:
    tax = payload.get("taxonomy") if isinstance(payload.get("taxonomy"), dict) else {}
    return str(payload.get("node_code") or tax.get("node_code") or "")


def _taxonomy_path(payload: dict[str, Any]) -> str:
    tax = payload.get("taxonomy") if isinstance(payload.get("taxonomy"), dict) else {}
    return str(payload.get("taxonomy_path") or tax.get("taxonomy_path") or "")


def find_verbatim_span(card: dict[str, Any], content_markdown: str) -> str | None:
    """Deterministic: the LONGEST clause of card_content/card_title that is a verbatim substring of
    content_markdown (>= _MIN_SPAN normalized chars). Returns None if no clause is verbatim."""
    norm_corpus = _norm_textbook(content_markdown)
    best = ""
    for field in (card.get("card_content"), card.get("card_title")):
        for clause in _CLAUSE_SPLIT.split(str(field or "")):
            cl = clause.strip()
            ncl = _norm_textbook(cl)
            if len(ncl) >= _MIN_SPAN and ncl in norm_corpus and len(cl) > len(best):
                best = cl
    return best or None


def _llm_propose_quote(
    card: dict[str, Any], content_markdown: str, complete_fn: Callable[..., Any], api_key: str
) -> str | None:
    """DeepSeek proposes a verbatim span; the worker re-checks it is a substring before trusting it."""
    import asyncio

    prompt = (
        "从下面的教材原文中，找出能逐字支撑该知识卡片论断的一段【连续子串】，"
        "原样复制，禁止改写/补字/删字；找不到就只回复 NONE。\n\n"
        f"教材原文:\n<<<{content_markdown[:1600]}>>>\n\n"
        f"卡片标题: {card.get('card_title')}\n卡片内容: {str(card.get('card_content'))[:300]}"
    )
    try:
        raw = asyncio.run(complete_fn(
            prompt=prompt,
            system_prompt="你只做教材原文逐字定位，绝不判定对错、绝不改写。只输出原文子串或 NONE。",
            model="deepseek-chat", api_key=api_key, max_retries=1,
        ))
    except Exception:  # noqa: BLE001 — LLM failure must never break the deterministic spine
        return None
    quote = str(raw or "").strip()
    if not quote or quote.upper() == "NONE":
        return None
    # defense in depth: only trust the model's quote if it is genuinely a verbatim substring.
    if _norm_textbook(quote) in _norm_textbook(content_markdown):
        return quote
    return None


def textbook_block_worker(
    item: dict[str, Any],
    *,
    complete_fn: Callable[..., Any] | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """S2: one textbook_block EvidenceItem -> per-card candidates (through make_candidate)."""
    payload = item.get("payload") or {}
    cid = str(payload.get("chunk_id") or item.get("evidence_id") or "")
    corpus = str(payload.get("content_markdown") or "")
    node = _node_code(payload)
    tax_path = _taxonomy_path(payload)
    cards = payload.get("knowledge_cards") or []

    out: list[dict[str, Any]] = []
    for idx, card in enumerate(cards):
        if not isinstance(card, dict):
            continue
        # deterministic-first; the LLM only enriches weak/missing spans, and only a LONGER verbatim
        # span is accepted (the signer re-verifies either way — the LLM never bypasses the corpus).
        quote = find_verbatim_span(card, corpus)
        if complete_fn is not None and api_key and (quote is None or len(quote) < _ENRICH_THRESHOLD):
            llm = _llm_propose_quote(card, corpus, complete_fn, api_key)
            if llm and (quote is None or len(llm) > len(quote)):
                quote = llm
        out.append(_CF.make_candidate(
            kind=_CF.KIND_RUBRIC,
            origin="llm_guess",
            payload={
                "point_id": f"{cid}::C{idx}",
                "chunk_id": cid,
                "node_code": node,
                # the block's OWN content_markdown (same-block corpus; must-fix #4) — the signer
                # re-derives provenance from this and binds content_hash to it.
                "content_markdown": corpus,
                "card_type": str(card.get("card_type") or ""),
                "card_content": str(card.get("card_content") or ""),
                "key_numbers": list(card.get("key_numbers") or []),
                "exact_quote": quote,
                "taxonomy_path": tax_path,
            },
            reason="textbook_card_candidate",
        ))
    return out


def default_textbook_block_worker(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Hermetic (no-LLM) S2 worker — deterministic verbatim-span search only."""
    return textbook_block_worker(item, complete_fn=None)


__all__ = ["textbook_block_worker", "default_textbook_block_worker", "find_verbatim_span"]
