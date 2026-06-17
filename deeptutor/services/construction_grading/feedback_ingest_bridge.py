"""Feedback ingest bridge (Living LLM Artifact Compiler, S0 + S7 producer).

Design: docs/plan/2026-06-06-luban-living-llm-artifact-compiler-design.md.

Today ``compiler_feedback.py`` has ZERO callers and M20 deltas stage but never execute — the SAME
missing wire: feedback never re-enters as candidates. This bridge is that wire. It turns the six raw
evidence sources (and the S7 re-ingest of work-orders / rejects / runtime misses / council disputes)
into immutable ``EvidenceItem`` rows for the pipeline, and wraps the existing M20 delta absorber and
the open-world work-order producer.

Authority discipline: this module ONLY produces candidates/evidence. It NEVER signs, never promotes,
never writes a release artifact. ``origin`` is stamped immutably here and is the signing boundary the
deterministic gates later enforce. An ``official_answer`` is a case-rubric SEED (``non_governed``),
never a textbook source.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from deeptutor.services.construction_grading import compiler_feedback as _CF
from deeptutor.services.construction_grading import full_knowledge_compiler as _FKC

# Evidence kinds (S0 contract). Each maps to a deterministic S2 dispatch in the pipeline.
EVIDENCE_KINDS = (
    "textbook_block",
    "objective_row",
    "case_official_answer",
    "machine_spec_point",
    "runtime_miss",
    "review_item",
    "retrieval_chunk",
    "council_dispute",
)

# Signing boundary: only these source_kinds may ever back signed truth (governed); others are seeds.
_GOVERNED_SOURCE_KINDS = {"governed_textbook", "governed_questions_bank"}

# evidence_kind -> (default origin, default source_kind). official_answer is a SEED, not a source.
_KIND_DEFAULTS: dict[str, tuple[str, str]] = {
    "textbook_block": ("questions_bank", "governed_textbook"),
    "objective_row": ("questions_bank", "governed_questions_bank"),
    "case_official_answer": ("questions_bank", "non_governed"),  # official_answer = SEED only
    "machine_spec_point": ("questions_bank", "non_governed"),    # machine-checkable; verified by attack gate
    "runtime_miss": ("open_world_diagnostic", "non_governed"),
    "review_item": ("teacher_review", "governed_questions_bank"),
    "retrieval_chunk": ("rag_chunk", "non_governed"),
    "council_dispute": ("council_vote", "non_governed"),
}


def _sha16(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_evidence_item(
    *,
    evidence_kind: str,
    payload: dict[str, Any],
    origin: str | None = None,
    source_kind: str | None = None,
    provenance: dict[str, Any] | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Build one immutable ``EvidenceItem``. ``evidence_id`` is content-addressed (loop dedup key)."""
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError(f"unknown evidence_kind: {evidence_kind}")
    d_origin, d_source = _KIND_DEFAULTS[evidence_kind]
    item_origin = str(origin or d_origin)
    item_source = str(source_kind or d_source)
    return {
        "evidence_id": _sha16({"k": evidence_kind, "o": item_origin, "p": payload}),
        "evidence_kind": evidence_kind,
        "origin": item_origin,            # IMMUTABLE for life; the signing boundary
        "source_kind": item_source,
        "is_governed_source": item_source in _GOVERNED_SOURCE_KINDS,
        "payload": dict(payload),
        "provenance": dict(provenance or {}),
        "discovered_in_run": run_id,
    }


def ingest_sources(
    *,
    textbook_blocks: list[dict[str, Any]] | None = None,
    objective_rows: list[dict[str, Any]] | None = None,
    case_official_answers: list[dict[str, Any]] | None = None,
    machine_spec_points: list[dict[str, Any]] | None = None,
    runtime_misses: list[dict[str, Any]] | None = None,
    review_items: list[dict[str, Any]] | None = None,
    retrieval_chunks: list[dict[str, Any]] | None = None,
    council_disputes: list[dict[str, Any]] | None = None,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """S0: pull the six (here: eight typed) raw sources into a deduped EvidenceItem list."""
    buckets: list[tuple[str, list[dict[str, Any]]]] = [
        ("textbook_block", textbook_blocks or []),
        ("objective_row", objective_rows or []),
        ("case_official_answer", case_official_answers or []),
        ("machine_spec_point", machine_spec_points or []),
        ("runtime_miss", runtime_misses or []),
        ("review_item", review_items or []),
        ("retrieval_chunk", retrieval_chunks or []),
        ("council_dispute", council_disputes or []),
    ]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind, rows in buckets:
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = make_evidence_item(
                evidence_kind=kind,
                payload=row.get("payload") if isinstance(row.get("payload"), dict) else row,
                origin=row.get("origin"),
                source_kind=row.get("source_kind"),
                provenance=row.get("provenance"),
                run_id=run_id,
            )
            if item["evidence_id"] in seen:
                continue
            seen.add(item["evidence_id"])
            items.append(item)
    return items


def open_world_to_candidates(diagnostic: dict[str, Any]) -> list[dict[str, Any]]:
    """S7: convert an open-world diagnostic into question + work-order candidates (existing producer)."""
    pair = _CF.work_order_from_open_world(diagnostic)
    return [pair["question_candidate"], pair["work_order"]]


def absorb_m20_deltas(deltas: list[dict[str, Any]]) -> dict[str, Any]:
    """S0/S7: route accepted M20 deltas through the existing deterministic absorber (the dead executor).

    The absorber classifies into release_candidate / staged_delta / work_order; a non-governed origin
    that is not source-backed stays a work_order (never silently promoted). This bridge is the caller
    M20 never had.
    """
    return _FKC.absorb_m20_deltas(deltas)


def reingest_terminal(entries: list[dict[str, Any]], *, seen: set[str], run_id: str = "") -> list[dict[str, Any]]:
    """S7 -> S0: turn this run's work_orders / rejects / disputes into NEW evidence for the next run.

    Content-addressed dedup against ``seen`` guarantees the loop is bounded (a fully resolved or
    twice-rejected item is terminal and never re-emitted)."""
    out: list[dict[str, Any]] = []
    for e in entries:
        kind = str(e.get("kind") or "")
        if kind not in {_CF.KIND_WORK_ORDER, _CF.KIND_REJECTED}:
            continue
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {"ref": e.get("candidate_id")}
        item = make_evidence_item(
            evidence_kind="runtime_miss",
            payload={"reingested_from": kind, "reason": e.get("reason"), **payload},
            origin="open_world_diagnostic",
            run_id=run_id,
        )
        if item["evidence_id"] in seen:
            continue
        seen.add(item["evidence_id"])
        out.append(item)
    return out


__all__ = [
    "EVIDENCE_KINDS",
    "make_evidence_item",
    "ingest_sources",
    "open_world_to_candidates",
    "absorb_m20_deltas",
    "reingest_terminal",
]
