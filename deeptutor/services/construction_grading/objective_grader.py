"""Objective deterministic grader (M25-B, fat skill).

100% deterministic objective grading. ``answer_key`` is the ONLY scoring authority; no LLM is
called and no LLM may change the key. Covers single-choice, multiple-choice (order-independent,
missed/extra), and true_false with alias tolerance (T/F, True/False, 对/错, A/B, yes/no, √/×...).
Invalid / empty / malformed input is graded wrong (is_correct=False) — never raises.
"""
from __future__ import annotations

import hashlib
from typing import Any

from deeptutor.services.construction_grading.normalization import normalize_choice_letters

AUTHORITY_KIND = "objective_answer_key_candidate"
STATUS_CANDIDATE = "candidate_unverified"

_TRUE_TOKENS = {"对", "正确", "true", "t", "yes", "y", "√", "1", "a"}
_FALSE_TOKENS = {"错", "错误", "false", "f", "no", "n", "×", "x", "0", "b"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_true_false_key(answer_key: str) -> bool:
    return answer_key.strip().upper() in ("T", "F")


def normalize_true_false(value: Any) -> str:
    """Map T/F, True/False, 对/错, A/B, yes/no, √/× ... to canonical 'T'/'F' (or '' if invalid)."""
    token = str(value or "").strip().lower()
    if not token:
        return ""
    if token in _TRUE_TOKENS:
        return "T"
    if token in _FALSE_TOKENS:
        return "F"
    return ""


def normalize_choice_set(value: Any) -> str:
    """Order-independent canonical letters, e.g. 'CAB' -> 'ABC'."""
    letters = normalize_choice_letters(value)
    return "".join(sorted(set(letters)))


def grade_objective_submission(
    *,
    answer_key: str,
    selected: Any,
    question_type: str | None = None,
    option_metadata: dict[str, Any] | None = None,
    max_score: float = 1.0,
) -> dict[str, Any]:
    """Grade an objective submission against ``answer_key`` (the sole authority).

    Returns the M25-B result shape. Deterministic; never raises on bad input.
    """
    key_raw = str(answer_key or "").strip()
    qt = str(question_type or "").strip().lower()
    is_tf = _is_true_false_key(key_raw) or qt in ("true_false", "judge", "judgement", "judgment", "tf")

    if is_tf:
        correct_norm = normalize_true_false(key_raw) or key_raw.upper()
        selected_norm = normalize_true_false(selected)
        correct_set = {correct_norm} if correct_norm in ("T", "F") else set()
        selected_set = {selected_norm} if selected_norm in ("T", "F") else set()
    else:
        correct_norm = normalize_choice_set(key_raw)
        selected_norm = normalize_choice_set(selected)
        correct_set = set(correct_norm)
        selected_set = set(selected_norm)

    missed = sorted(correct_set - selected_set)
    extra = sorted(selected_set - correct_set)
    is_correct = bool(correct_set) and not missed and not extra
    score = float(max_score) if is_correct else 0.0

    return {
        "is_correct": is_correct,
        "score": score,
        "max_score": float(max_score),
        "selected_option_normalized": selected_norm,
        "correct_option_set_hash": _sha(correct_norm),
        "missed": missed,
        "extra": extra,
        "grading_authority": "answer_key",
        "llm_may_decide_correctness": False,
        "authority_kind": AUTHORITY_KIND,
        "status": STATUS_CANDIDATE,
        "not_production_grade": True,
    }
