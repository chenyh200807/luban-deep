"""Textbook paraphrase review channel (Living LLM Artifact Compiler, increment ① · backlog).

The textbook verbatim signer (``compile_textbook_knowledge_release_candidate``) signs ONLY cards whose
claim is a literal substring of their block's content_markdown. Cards that are a faithful *paraphrase*
or *synthesis* of the block (e.g. a table flattened into a sentence, a multi-step list summarized) have
no verbatim anchor and fall to the ``synthesis`` work-order backlog — valuable teaching content, but
NOT verbatim and therefore never signable as textbook authority.

This module OPENS a review channel for that backlog:
  * ``build_review_queue`` turns each synthesis work-order item into a review packet — the claim, the
    block's own source markdown, deterministic triage signals, and the fixed faithfulness question.
  * ``make_paraphrase_candidates`` stages those packets in the compiler_feedback candidate ledger
    (origin ``council_vote`` → ``source_candidate``; ``promote_to_release=False``; never an answer key).
  * ``sign_verified_paraphrase_release_candidate`` is a deterministic signer with a HARD review gate:
    it signs a packet into the SEPARATE namespace ``textbook_paraphrase_review`` ONLY when a governed
    reviewer (human / governed council) returned ``faithful`` AND every claim key_number is grounded
    in the source (numbers can never be laundered, even in a paraphrase). Everything else routes back
    to the work-order backlog. The signed class is ``verified_paraphrase`` — strictly weaker than
    verbatim: teaching/context only, ``official_answer_capable=False``, and this lane mints ZERO
    verbatim authority records by construction.

Single authority: verbatim → textbook authority lives in ``full_knowledge_compiler``; this lane never
touches that namespace and never produces an answer-key-grade record.
"""
from __future__ import annotations

import re
from typing import Any

from deeptutor.services.construction_grading import compiler_feedback as _CF
from deeptutor.services.construction_grading.full_knowledge_compiler import (
    _NODE_RE,
    SCHEMA_VERSION,
    STATUS_RELEASE_CANDIDATE,
    _norm_textbook,
    _num_core,
    _sha256_hex,
)

PARAPHRASE_NAMESPACE = "textbook_paraphrase_review"  # SEPARATE from textbook_knowledge_full
_SYNTHESIS_CLASS = "synthesis"
_VERIFIED_CLASS = "verified_paraphrase"

# The fixed question put to the reviewer. A "faithful" verdict means: the claim is fully entailed by
# the source block — it restates / summarizes content that IS in the block, adds NO new fact, and
# alters no number — but is not a literal substring (otherwise it would be verbatim-signed).
REVIEW_QUESTION = (
    "该知识卡片是否是源教材块的【忠实改写/归纳】？"
    "（卡片论断必须完全由源块内容支撑、不新增任何事实、不改动任何数字；"
    "仅因表述重组而非逐字，故走改写复核。是=faithful，否=not_faithful）"
)

# Only these reviewer roles can let a paraphrase exit the channel into the signed weaker-class lane.
# A bare model/council *vote* stages a candidate but can never sign — review must be governed.
_GOVERNED_REVIEWER_ROLES = frozenset({"human_reviewer", "governed_council"})

_CLAUSE_SPLIT = re.compile(r"[。；;！!？?\n、，,：:|]")


def _claim_clauses(text: str) -> list[str]:
    return [s.strip() for s in _CLAUSE_SPLIT.split(text) if s.strip()]


def _key_numbers_grounded(key_numbers: list[str], source_markdown: str) -> tuple[bool, list[str]]:
    """Every claim key_number's numeric core must appear in the source. A paraphrase may restructure
    prose freely, but it may NOT introduce or alter a number — that would be laundering, not paraphrase.
    Returns (all_grounded, grounded_list)."""
    norm = _norm_textbook(source_markdown)
    grounded: list[str] = []
    all_ok = True
    for kn in key_numbers or []:
        core = _num_core(kn)
        if core and core in norm:
            grounded.append(str(kn))
        else:
            all_ok = False
    return all_ok, grounded


def _triage_signals(card: dict[str, Any], source_markdown: str) -> dict[str, Any]:
    """Deterministic, NON-authority hints to focus the reviewer (never gate signing on their own)."""
    norm_src = _norm_textbook(source_markdown)
    claim = str(card.get("card_content") or "")
    clauses = [c for c in _claim_clauses(claim) if len(_norm_textbook(c)) >= 6]
    covered = sum(1 for c in clauses if _norm_textbook(c) in norm_src)
    all_grounded, grounded = _key_numbers_grounded(list(card.get("key_numbers") or []), source_markdown)
    return {
        "clause_count": len(clauses),
        "clauses_verbatim_in_source": covered,
        "clause_coverage": round(covered / len(clauses), 3) if clauses else 0.0,
        "key_numbers_all_grounded": all_grounded,
        "grounded_key_numbers": grounded,
    }


def build_review_packet(
    work_order_item: dict[str, Any], card: dict[str, Any], source_markdown: str
) -> dict[str, Any]:
    """One synthesis backlog item -> a self-contained review packet (claim + source + question)."""
    return {
        "namespace": PARAPHRASE_NAMESPACE,
        "point_id": str(work_order_item.get("point_id") or ""),
        "chunk_id": str(card.get("chunk_id") or work_order_item.get("chunk_id") or ""),
        "node_code": str(work_order_item.get("node_code") or card.get("node_code") or ""),
        "claim_title": str(card.get("card_title") or ""),
        "claim_content": str(card.get("card_content") or ""),
        "claim_key_numbers": list(card.get("key_numbers") or []),
        "source_markdown": str(source_markdown or ""),
        "source_content_hash": _sha256_hex(_norm_textbook(source_markdown)),
        "review_question": REVIEW_QUESTION,
        "triage": _triage_signals(card, source_markdown),
        # unfilled until a governed reviewer answers — the channel is OPEN, not yet decided.
        "review_verdict": None,        # "faithful" | "not_faithful"
        "reviewer_id": None,
        "reviewer_role": None,
    }


def build_review_queue(
    backlog: list[dict[str, Any]],
    cards_by_point: dict[str, dict[str, Any]],
    source_by_chunk: dict[str, str],
) -> dict[str, Any]:
    """Open the channel: every synthesis backlog item -> a review packet. Items whose card or source
    can't be joined are recorded (never silently dropped)."""
    packets: list[dict[str, Any]] = []
    unjoinable: list[dict[str, Any]] = []
    for wo in backlog:
        if str(wo.get("provenance_class") or "") != _SYNTHESIS_CLASS:
            continue  # only the paraphrase/synthesis backlog enters this channel
        pid = str(wo.get("point_id") or "")
        card = cards_by_point.get(pid)
        chunk = str((card or {}).get("chunk_id") or wo.get("chunk_id") or "")
        source = source_by_chunk.get(chunk)
        if not card or not source:
            unjoinable.append({"point_id": pid, "reason": "card_or_source_unavailable"})
            continue
        packets.append(build_review_packet(wo, card, source))
    return {"packets": packets, "unjoinable": unjoinable, "open_count": len(packets)}


def make_paraphrase_candidates(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stage review packets in the compiler_feedback candidate ledger (separate from any release).
    Origin ``council_vote`` -> a ``source_candidate`` (never an answer key); promote_to_release=False."""
    out: list[dict[str, Any]] = []
    for p in packets:
        out.append(_CF.make_candidate(
            kind=_CF.KIND_SOURCE,
            origin="council_vote",
            payload={
                "point_id": p["point_id"],
                "node_code": p["node_code"],
                "chunk_id": p["chunk_id"],
                "review_question": p["review_question"],
                "claim_title": p["claim_title"],
                "claim_content": p["claim_content"],
                "triage": p["triage"],
                "target_namespace": PARAPHRASE_NAMESPACE,
                "weaker_class_than_verbatim": True,
            },
            reason="open_verified_paraphrase_review_channel",
        ))
    return out


def sign_verified_paraphrase_release_candidate(
    reviewed_packets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Deterministic signer with a HARD review gate. A packet is signed into ``textbook_paraphrase_review``
    ONLY when ALL hold:
      * ``review_verdict == "faithful"`` from a governed reviewer (role in _GOVERNED_REVIEWER_ROLES
        with a reviewer_id) — a bare model/council vote can stage but never sign;
      * every claim key_number is grounded in the source (numbers never laundered, even in paraphrase);
      * node_code is a canonical taxonomy code.
    Everything else routes back to the work-order backlog. The signed class is ``verified_paraphrase``:
    teaching context only, ``official_answer_capable=False``, ZERO verbatim-authority records minted.
    """
    signed: list[dict[str, Any]] = []
    work_order: list[dict[str, Any]] = []
    seen: set[str] = set()

    for p in reviewed_packets:
        pid = str(p.get("point_id") or "")
        node = str(p.get("node_code") or "").strip()
        verdict = str(p.get("review_verdict") or "")
        role = str(p.get("reviewer_role") or "")
        reviewer = str(p.get("reviewer_id") or "").strip()

        if not _NODE_RE.match(node):
            work_order.append({"point_id": pid, "reason": "missing_or_bad_node_code"})
            continue
        if verdict != "faithful" or role not in _GOVERNED_REVIEWER_ROLES or not reviewer:
            work_order.append({"point_id": pid, "reason": "no_governed_faithful_verdict",
                               "verdict": verdict or None, "reviewer_role": role or None})
            continue
        all_grounded, grounded = _key_numbers_grounded(
            list(p.get("claim_key_numbers") or []), str(p.get("source_markdown") or ""))
        if not all_grounded:
            work_order.append({"point_id": pid, "reason": "key_number_not_grounded_in_source"})
            continue
        if pid in seen:
            work_order.append({"point_id": pid, "reason": "duplicate_point_id"})
            continue
        seen.add(pid)
        signed.append({
            "point_id": pid,
            "chunk_id": str(p.get("chunk_id") or ""),
            "node_code": node,
            "provenance_class": _VERIFIED_CLASS,
            "paraphrase_title": str(p.get("claim_title") or ""),
            "paraphrase_content": str(p.get("claim_content") or ""),
            "grounded_key_numbers": grounded,
            "source_content_hash": _sha256_hex(_norm_textbook(str(p.get("source_markdown") or ""))),
            "reviewer_id": reviewer,
            "reviewer_role": role,
            "answer_key_authority": "paraphrase_teaching_context_not_verbatim",
            "official_answer_capable": False,
        })

    signed.sort(key=lambda x: x["point_id"])
    content_hash = _sha256_hex(signed)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": PARAPHRASE_NAMESPACE,
        "lane": "textbook_paraphrase_review",
        "status": STATUS_RELEASE_CANDIDATE,
        "published": False,
        "signed_count": len(signed),
        "work_order_count": len(work_order),
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, PARAPHRASE_NAMESPACE, STATUS_RELEASE_CANDIDATE]),
        # invariants asserted by construction:
        "verbatim_authority_records": 0,       # this lane NEVER mints verbatim authority
        "official_answer_capable_records": 0,  # paraphrase is teaching context only
        "ungoverned_verdict_signed": 0,        # only governed faithful verdicts are signed
        "separate_namespace_from_verbatim": PARAPHRASE_NAMESPACE != "textbook_knowledge_full",
    }
    return {"manifest": manifest, "records": signed, "work_order": work_order}


__all__ = [
    "PARAPHRASE_NAMESPACE",
    "REVIEW_QUESTION",
    "build_review_packet",
    "build_review_queue",
    "make_paraphrase_candidates",
    "sign_verified_paraphrase_release_candidate",
]
