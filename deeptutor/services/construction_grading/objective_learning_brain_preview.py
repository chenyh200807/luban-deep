"""Objective -> Learning Brain PREVIEW (M25-EF, fat skill).

Turns an M25-B objective candidate runtime payload into a Learning-Brain-shaped PREVIEW:
objective evidence event -> claim proposal -> PersonalizationContextPack preview -> next action +
retest plan. PREVIEW ONLY: nothing is written to DB / canonical truth / mastery / published
registry. Every claim is candidate_unverified, carries supporting_event_ids, and never promotes
mastery. Isolated by (user_id, subject_id). Reuses the existing learner_state authority
(``build_learning_evidence_payload``) for the base evidence shape — no second learner memory.

Claim lifecycle:
  correct                         -> observed_strength (candidate) + ready_retest
  wrong/blank/invalid/multi_*     -> concept_gap + needs_retest
  open_world_unknown (not-in-bank)-> diagnostic_draft + compiler_work_order (NO official score)
"""
from __future__ import annotations

import hashlib
from typing import Any

from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)

CANDIDATE_STATUS = "candidate_unverified"


def _eid(*parts: str) -> str:
    return "obj-evt:" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def _classify(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Return (outcome, claim_kind, retest_kind) from an objective candidate payload."""
    if payload.get("mode") == "open_world_fail_open":
        return ("open_world_unknown", "diagnostic_draft", "needs_review")
    if payload.get("fail_closed"):
        return ("supply_unavailable", "diagnostic_draft", "needs_review")
    res = payload.get("result") or {}
    if res.get("is_correct"):
        return ("correct", "observed_strength", "ready_retest")
    if res.get("missed"):
        return ("multi_missing", "concept_gap", "needs_retest")
    if res.get("extra"):
        return ("multi_extra", "concept_gap", "needs_retest")
    if not str(res.get("selected_option_normalized") or "").strip():
        return ("blank_or_invalid", "concept_gap", "needs_retest")
    return ("wrong", "concept_gap", "needs_retest")


def build_objective_evidence_event(
    payload: dict[str, Any],
    *,
    user_id: str,
    subject_id: str,
    question_id: str,
    variant: str = "",
    turn_id: str = "",
) -> dict[str, Any]:
    """Objective evidence event PREVIEW (no write). Specific (not generic), candidate-only."""
    outcome, claim_kind, retest_kind = _classify(payload)
    res = payload.get("result") or {}
    event_id = _eid(user_id, subject_id, question_id, variant)
    answer_key_hash = payload.get("answer_key_hash") or res.get("correct_option_set_hash") or ""
    source_refs = list(payload.get("source_refs") or [])
    # base evidence shape via the existing learner_state authority (objective grading result)
    base = {}
    try:
        base = build_learning_evidence_payload(
            grading_result={
                "question_id": question_id,
                "type": "mcq",
                "is_correct": bool(res.get("is_correct")),
                "score_awarded": res.get("score", 0.0),
                "max_score": res.get("max_score", 1.0),
                "error_events": [] if res.get("is_correct") else [{"option": res.get("selected_option_normalized", ""),
                                                                    "diagnosis": outcome}],
                "evidence_refs": [{"source": "objective_answer_key", "ref": question_id}],
            },
            turn_id=turn_id,
        )
    except Exception:  # noqa: BLE001 — preview must never break on base-shape extraction
        base = {}
    return {
        "event_id": event_id,
        "kind": "objective_evidence",
        "user_id": user_id,
        "subject_id": subject_id,
        "question_id": question_id,
        "variant": variant,
        "outcome": outcome,
        "claim_kind": claim_kind,
        "retest_kind": retest_kind,
        "answer_key_hash": answer_key_hash,
        "authority_kind": payload.get("authority_kind") or "objective_answer_key_candidate",
        "source_refs": source_refs,
        "evidence_refs": [f"objective_answer_key:{question_id}"],
        "status": CANDIDATE_STATUS,
        "promoted_to_mastery": False,
        "canonical_truth_written": False,
        "official_score": payload.get("mode") not in ("open_world_fail_open",) and outcome != "open_world_unknown",
        "base_quality": (base.get("quality") if isinstance(base, dict) else None),
        "is_specific": bool(question_id) and bool(answer_key_hash),  # tied to a concrete question + key
    }


def build_claim_proposal(event: dict[str, Any]) -> dict[str, Any]:
    """Claim proposal with mandatory supporting_event_ids. Never mastery, never canonical."""
    return {
        "claim_id": "obj-claim:" + event["event_id"].split(":", 1)[1],
        "user_id": event["user_id"],
        "subject_id": event["subject_id"],
        "claim_kind": event["claim_kind"],
        "question_id": event["question_id"],
        "supporting_event_ids": [event["event_id"]],  # always >=1
        "evidence_refs": event["evidence_refs"],
        "status": CANDIDATE_STATUS,
        "promoted_to_mastery": False,
        "unsupported": False,
        "generic_fallback": not event["is_specific"],
    }


def build_retest_plan(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "retest_id": "obj-retest:" + event["event_id"].split(":", 1)[1],
        "user_id": event["user_id"],
        "subject_id": event["subject_id"],
        "question_id": event["question_id"],
        "retest_kind": event["retest_kind"],
        "supporting_event_ids": [event["event_id"]],
        "evidence_refs": event["evidence_refs"],
        "simulated": True,
        "simulated_retest_as_real": False,
        "status": CANDIDATE_STATUS,
    }


def build_open_world_work_order(payload: dict[str, Any], *, user_id: str, subject_id: str,
                                question_id: str) -> dict[str, Any]:
    return {
        "work_order_id": "obj-wo:" + _eid(user_id, subject_id, question_id).split(":", 1)[1],
        "kind": "objective_answer_key_candidate",
        "user_id": user_id,
        "subject_id": subject_id,
        "question_id": question_id,
        "label": "unverified_diagnostic",
        "official_answer_claimed": False,
        "auto_score": False,
        "promote_to_release": False,
    }


def build_pcp_preview(events: list[dict[str, Any]], *, user_id: str, subject_id: str) -> dict[str, Any]:
    """PersonalizationContextPack PREVIEW, isolated to (user_id, subject_id). No teacher-only fields."""
    mine = [e for e in events if e["user_id"] == user_id and e["subject_id"] == subject_id]
    strengths = [e["question_id"] for e in mine if e["claim_kind"] == "observed_strength"]
    gaps = [e["question_id"] for e in mine if e["claim_kind"] == "concept_gap"]
    drafts = [e["question_id"] for e in mine if e["claim_kind"] == "diagnostic_draft"]
    next_action = {
        "action": "retest_concept_gaps" if gaps else ("confirm_strengths" if strengths else "diagnose"),
        "supporting_event_ids": [e["event_id"] for e in mine][:20],
        "evidence_refs": [r for e in mine for r in e["evidence_refs"]][:20],
    }
    return {
        "user_id": user_id,
        "subject_id": subject_id,
        "observed_strength_candidates": strengths,
        "concept_gap_candidates": gaps,
        "diagnostic_drafts": drafts,
        "next_action": next_action,
        "status": CANDIDATE_STATUS,
        "promoted_to_mastery": False,
        "teacher_only_fields_present": False,
        "isolation_key": f"{user_id}|{subject_id}",
    }
