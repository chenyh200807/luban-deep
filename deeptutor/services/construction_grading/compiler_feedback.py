"""Compiler feedback loop (M26, §0.26.2 compiler-feedback mode).

Open-world diagnostics, repeated misses, review-queue items, and new RAG evidence become CANDIDATE
ledger entries for the LLM-assisted compiler + deterministic release gate. Candidates live in a
namespace fully separate from any signed release artifact and can NEVER enter runtime as release
truth.

Hard guards:
  * ``namespace = luban_compiler_candidate`` (never a release namespace),
  * every entry has ``promote_to_release=False``,
  * source-laundering guard: a retrieval chunk, model vote, or council vote may seed a
    ``source_candidate`` (needs human/governed review) but is REJECTED if it tries to become an
    ``answer_key_candidate`` directly — only a governed source can seed an answer key.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

NAMESPACE = "luban_compiler_candidate"  # strictly separate from release namespaces

KIND_QUESTION = "question_candidate"
KIND_ANSWER_KEY = "answer_key_candidate"
KIND_RUBRIC = "rubric_candidate"
KIND_SOURCE = "source_candidate"
KIND_MACHINE_SPEC = "machine_spec_candidate"
KIND_REJECTED = "rejected"
KIND_WORK_ORDER = "work_order"
KIND_RELEASE_DELTA = "release_candidate_delta"

_VALID_KINDS = {
    KIND_QUESTION, KIND_ANSWER_KEY, KIND_RUBRIC, KIND_SOURCE,
    KIND_MACHINE_SPEC, KIND_REJECTED, KIND_WORK_ORDER, KIND_RELEASE_DELTA,
}

# Origins that are NOT a governed source and therefore must never seed an answer key directly.
_NON_GOVERNED_ORIGINS = {"rag_chunk", "model_vote", "council_vote", "llm_guess", "retrieval"}
_GOVERNED_ORIGINS = {"questions_bank", "public_exam_paper", "governed_registry", "teacher_review"}


def _sha16(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _entry(kind: str, origin: str, payload: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "namespace": NAMESPACE,
        "kind": kind,
        "origin": origin,
        "status": "candidate_unverified",
        "promote_to_release": False,
        "is_release_truth": False,
        "reason": reason,
        "payload": payload,
        "candidate_id": _sha16({"kind": kind, "origin": origin, "payload": payload}),
        "next_action": "route_to_llm_assisted_compiler_then_deterministic_release_gate",
    }


def make_candidate(
    *,
    kind: str,
    origin: str,
    payload: dict[str, Any],
    reason: str = "",
) -> dict[str, Any]:
    """Create one candidate-ledger entry. Enforces the source-laundering guard for answer keys."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown candidate kind: {kind}")

    if kind == KIND_ANSWER_KEY and origin in _NON_GOVERNED_ORIGINS:
        # Source laundering attempt: a non-governed origin tries to mint an answer key. Reject it,
        # but keep the audit trail as a rejected entry (never silently drop).
        return _entry(
            KIND_REJECTED,
            origin,
            {"attempted_kind": KIND_ANSWER_KEY, "blocked_payload_hash": _sha16(payload)},
            reason=f"source_laundering_blocked:{origin}_cannot_seed_answer_key",
        )

    if kind == KIND_ANSWER_KEY and origin not in _GOVERNED_ORIGINS:
        return _entry(
            KIND_REJECTED,
            origin,
            {"attempted_kind": KIND_ANSWER_KEY, "blocked_payload_hash": _sha16(payload)},
            reason=f"answer_key_requires_governed_origin:got_{origin or 'unknown'}",
        )

    return _entry(kind, origin, payload, reason or f"{kind}_from_{origin}")


def work_order_from_open_world(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Convert an open-world diagnostic dict into a question candidate + work-order pair."""
    wo = diagnostic.get("candidate_work_order") or {}
    excerpt = str(wo.get("prompt_excerpt") or "").strip()
    question_candidate = make_candidate(
        kind=KIND_QUESTION,
        origin="open_world_diagnostic",
        payload={
            "prompt_excerpt": excerpt,
            "evidence_ref_count": wo.get("evidence_ref_count", 0),
            "uncertainty_label": diagnostic.get("uncertainty_label"),
        },
        reason="high_value_not_in_bank_prompt",
    )
    work_order = make_candidate(
        kind=KIND_WORK_ORDER,
        origin="open_world_diagnostic",
        payload={
            "task": "compile_canonical_question_and_answer_key",
            "prompt_excerpt": excerpt,
            "needs_governed_source": True,
        },
        reason="route_open_world_miss_to_compiler",
    )
    return {"question_candidate": question_candidate, "work_order": work_order}


_SOURCE_CONFLICT_WORK_ORDER_TYPES = {
    "query_path_source_mismatch": "scoring_artifact_reanchor",
    "source_supports_sibling_node_only": "scoring_artifact_detach",
    "low_confidence_but_plausible": "scoring_artifact_needs_review",
}


def work_order_from_source_path_conflict(
    *,
    question_id: str,
    failed_path: str,
    reason: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Route M35 source/path conflicts into the existing compiler candidate ledger."""

    normalized_reason = str(reason or "").strip() or "source_path_conflict"
    return make_candidate(
        kind=KIND_WORK_ORDER,
        origin="m35_scoring_artifact_gate",
        payload={
            "work_order_type": _SOURCE_CONFLICT_WORK_ORDER_TYPES.get(
                normalized_reason,
                "scoring_artifact_needs_review",
            ),
            "question_id": str(question_id or "").strip(),
            "failed_path": str(failed_path or "").strip(),
            "evidence": dict(evidence or {}),
            "runtime_usable_as_truth": False,
        },
        reason=normalized_reason,
    )


def work_order_from_teacher_override(event: dict[str, Any]) -> dict[str, Any]:
    """Route M35 teacher overrides back into the compiler candidate flywheel."""

    return make_candidate(
        kind=KIND_WORK_ORDER,
        origin="m35_teacher_review",
        payload={
            "work_order_type": "teacher_override_review",
            "promote_to_release": False,
            "runtime_usable_as_truth": False,
            "question_id": str(event["question_id"]).strip(),
            "artifact_version": str(event["artifact_version"]).strip(),
            "point_id": str(event["point_id"]).strip(),
            "override_type": str(event["override_type"]).strip(),
            "teacher_evidence": str(event["teacher_evidence"]).strip(),
            "source_ref_ids": list(event.get("source_ref_ids") or []),
        },
        reason="route_teacher_override_to_compiler_review",
    )


def build_ledger(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a candidate ledger; computes laundering invariants for the M26 safety report."""
    by_kind: dict[str, int] = {}
    laundering_blocked = 0
    promoted = 0
    for e in entries:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        if str(e.get("reason", "")).startswith("source_laundering_blocked"):
            laundering_blocked += 1
        if e.get("promote_to_release") is True:
            promoted += 1
    return {
        "namespace": NAMESPACE,
        "count": len(entries),
        "by_kind": by_kind,
        "source_laundering_blocked": laundering_blocked,
        "candidate_used_as_release_truth": promoted,  # must be 0
        "all_separate_from_release": all(e.get("namespace") == NAMESPACE for e in entries),
        "ledger_hash": _sha16(entries),
    }


__all__ = [
    "NAMESPACE",
    "make_candidate",
    "work_order_from_open_world",
    "work_order_from_source_path_conflict",
    "work_order_from_teacher_override",
    "build_ledger",
    "KIND_QUESTION",
    "KIND_ANSWER_KEY",
    "KIND_RUBRIC",
    "KIND_SOURCE",
    "KIND_MACHINE_SPEC",
    "KIND_REJECTED",
    "KIND_WORK_ORDER",
    "KIND_RELEASE_DELTA",
]
