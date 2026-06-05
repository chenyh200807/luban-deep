"""Objective runtime adapter (M25-B, fat skill).

Bridges the compiled objective answer-key CANDIDATE bundle to the runtime: looks a question up
by ``question_id``, builds a scoped GradingPacket, grades deterministically, and returns an
append-only ``candidate_unverified`` payload. Never claims official truth, never auto-promotes
to release, never writes production / canonical truth. Fail-closed on a missing / malformed /
tampered bundle; fail-OPEN (open-world diagnostic) when the question is not in the bank.

ALL policy lives here / in the compiler / grader (fat skills). The deep_question wrapper only
does flag + cohort + append.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from deeptutor.services.construction_grading import objective_answer_key_compiler as _C
from deeptutor.services.construction_grading.grading_packet_builder import build_grading_packet
from deeptutor.services.construction_grading.objective_grader import grade_objective_submission

AUTHORITY = "luban_grading_engine_objective_candidate"


@lru_cache(maxsize=1)
def _candidate_index() -> tuple[bool, dict[str, dict[str, Any]]]:
    """Load + verify the tracked candidate bundle once. Returns (verified, {question_id: record})."""
    bundle = _C.build_candidate_bundle_from_seed()
    if not _C.verify_objective_bundle(bundle):
        return (False, {})
    index = {r["question_id"]: r for r in bundle.get("records", []) if r.get("question_id")}
    return (True, index)


def _fail_closed(reason: str) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "mode": "objective_candidate",
        "status": "candidate_bundle_unavailable",
        "fail_closed": True,
        "unavailable_reason": reason[:200],
        "not_production_grade": True,
        "writeback_performed": False,
    }


def _open_world(question_id: str, selected_option: Any) -> dict[str, Any]:
    """Not-in-bank: fail-open teaching/diagnostic. Never an official score."""
    ctx = {"status": "unresolved", "question_id": question_id}
    packet = build_grading_packet(ctx, selected_option=selected_option)
    return {
        "authority": AUTHORITY,
        "mode": "open_world_fail_open",
        "status": "needs_review",
        "label": "unverified_diagnostic",
        "official_answer_claimed": False,
        "auto_score": False,
        "packet": packet,
        "compiler_work_order": {
            "kind": "objective_answer_key_candidate",
            "question_id": question_id,
            "reason": "question_id not in candidate bundle; route to compiler candidate, not release",
            "promote_to_release": False,
        },
        "not_production_grade": True,
        "writeback_performed": False,
    }


def build_objective_candidate_payload(
    *,
    question_id: str,
    selected_option: Any,
    learner_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append-only objective candidate payload. Fail-closed on tamper; fail-open on not-in-bank."""
    qid = str(question_id or "").strip()
    try:
        verified, index = _candidate_index()
    except Exception as exc:  # noqa: BLE001 — must never break legacy
        return _fail_closed(f"index_error:{exc}")
    if not verified:
        return _fail_closed("candidate_bundle_failed_verification")  # tamper / malformed -> fail-closed
    if not qid or qid not in index:
        return _open_world(qid, selected_option)

    record = index[qid]
    answer_key = str(record.get("answer_key") or "")
    ctx = {
        "status": "resolved",
        "question_id": qid,
        "question_type": record.get("question_type"),
        "answer_key": answer_key,
        "source_refs": record.get("source_refs") or [],
    }
    packet = build_grading_packet(
        ctx,
        learner_context=learner_context or {},
        selected_option=selected_option,
        answer_key=answer_key,
    )
    grade = grade_objective_submission(
        answer_key=answer_key,
        selected=selected_option,
        question_type=str(record.get("question_type") or ""),
        option_metadata=record.get("option_metadata"),
    )
    return {
        "authority": AUTHORITY,
        "mode": "objective_candidate",
        "lane": packet["lane"],
        "answer_key_hash": record.get("answer_key_hash"),
        "selected_option": selected_option,
        "option_metadata": record.get("option_metadata"),
        "source_refs": record.get("source_refs") or [],
        "result": grade,
        "llm_may_decide_correctness": False,
        "authority_kind": "objective_answer_key_candidate",
        "status": "candidate_unverified",
        "not_production_grade": True,
        "writeback_performed": False,
    }
