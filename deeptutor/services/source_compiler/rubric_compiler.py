from __future__ import annotations

from .metadata import with_compiler_metadata


def compile_option_reasoning_backfill(
    capsule: dict,
    *,
    existing_option_reasoning: dict | None,
    run_id: str,
    source_path: str,
    compiled_at: str,
    writeback_policy: str | None = None,
) -> dict:
    if capsule.get("candidate_questions_bank_id") is None:
        raise ValueError("candidate_questions_bank_id is required for option reasoning backfill")
    existing_non_empty = bool(existing_option_reasoning)
    policy = writeback_policy or ("skip_if_non_empty" if existing_non_empty else "overwrite_only_if_empty")
    payload = {
        "stable_question_source_id": capsule.get("stable_question_source_id"),
        "candidate_questions_bank_id": capsule.get("candidate_questions_bank_id"),
        "question_type": capsule.get("question_type"),
        "option_reasoning": capsule.get("option_reasoning") or {},
        "writeback_policy": policy,
    }
    return with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at)


def compile_rubric_candidate(capsule: dict, *, run_id: str, source_path: str, compiled_at: str) -> dict | None:
    if capsule.get("candidate_questions_bank_id") is None:
        return None
    if capsule.get("question_type") != "case_study":
        return None
    payload = {
        "stable_question_source_id": capsule.get("stable_question_source_id"),
        "candidate_questions_bank_id": capsule.get("candidate_questions_bank_id"),
        "rubric_points": capsule.get("grading_keywords") or capsule.get("testing_focus") or [],
        "writeback_policy": "overwrite_only_if_empty",
    }
    return with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at)

