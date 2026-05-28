"""Deterministic answer-correctness scoring + cross-model differential report.

This is the *quality + verified-transmit* core (9+ roadmap H2/H6, north-star B):
- ``score_answer_correctness`` scores a model's answer against the question
  bank's authoritative answer — **deterministically, no LLM judge, no human
  labels** (roadmap C2: prefer ground truth where it exists). It reuses the
  single exact authority (``exact_authority``).
- ``cross_model_correctness_report`` compares correctness across models so a
  model upgrade can be *proven* better-and-not-regressed before the system
  "auto-upgrades with the model" — the operational mechanism of the north star.

Pluggable by design: feed it ``(question_with_authoritative_answer, model_response)``
pairs. Producing those pairs at scale needs a real question bank + keyed runs
(provided separately); this module is the scoring/comparison logic, validated
here with synthetic Q+A so it is correct the moment real data plugs in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Reuse the single MCQ-answer parsing authority from exact_authority — do NOT
# duplicate normalization/extraction here (single-authority gate, AGENTS §5.7).
from deeptutor.services.rag.exact_authority import (
    _extract_marked_mcq_answers,
    _normalize_mcq_answer_letters,
    extract_exact_question_authority_from_metadata,
)


@dataclass(frozen=True)
class CorrectnessScore:
    question_id: str
    answer_kind: str
    correct: bool
    detail: str = ""


def _compact(text: Any) -> str:
    return "".join(str(text or "").split())


def score_answer_correctness(
    *,
    question_id: str,
    exact_question: dict[str, Any],
    response: str,
) -> CorrectnessScore:
    """Score one model answer against the bank's authoritative answer.

    - mcq: closed-book correctness — the model's marked answer letter(s) must
      equal the authoritative letter(s). This is deliberately *not* the
      rendering-faithfulness oracle (``exact_authority_response_matches``),
      whose length / option-restatement / anti-echo guards reject legitimate
      closed-book answers like "答案：B".
    - free_text: the authoritative answer text must be present in the response.
    - case_study: every covered subquestion's authoritative answer must appear.
    """
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    response_compact = _compact(response)

    if answer_kind == "mcq":
        expected = _normalize_mcq_answer_letters(exact_question.get("correct_answer"))
        marked = _extract_marked_mcq_answers(str(response or ""))
        correct = bool(expected) and bool(marked) and all(ans == expected for ans in marked)
        return CorrectnessScore(question_id, "mcq", correct, "marked letter(s) vs authoritative letter(s)")

    if answer_kind == "free_text":
        answer = _compact(exact_question.get("correct_answer"))
        correct = bool(answer) and answer in response_compact
        return CorrectnessScore(question_id, "free_text", correct, "authoritative answer present")

    if answer_kind == "case_study":
        normalized = extract_exact_question_authority_from_metadata({"exact_question": exact_question})
        covered = (normalized or {}).get("covered_subquestions") or []
        authoritative = [
            _compact(item.get("authoritative_answer"))
            for item in covered
            if isinstance(item, dict) and _compact(item.get("authoritative_answer"))
        ]
        correct = bool(authoritative) and all(ans in response_compact for ans in authoritative)
        return CorrectnessScore(question_id, "case_study", correct, "all covered answers present")

    return CorrectnessScore(question_id, answer_kind or "unknown", False, "no scorable authority")


def cross_model_correctness_report(
    scores_by_model: dict[str, list[CorrectnessScore]],
    *,
    baseline_model: str | None = None,
) -> dict[str, Any]:
    """Compare correctness across models. Flags whether a candidate model
    regresses vs the baseline — the green-light/abort signal for a model upgrade.
    """
    per_model: dict[str, dict[str, Any]] = {}
    for model, scores in scores_by_model.items():
        total = len(scores)
        correct = sum(1 for s in scores if s.correct)
        per_model[model] = {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else None,
        }

    baseline = baseline_model or (next(iter(scores_by_model)) if scores_by_model else None)
    deltas: dict[str, Any] = {}
    regressions: list[dict[str, Any]] = []
    if baseline and per_model.get(baseline, {}).get("accuracy") is not None:
        base_acc = per_model[baseline]["accuracy"]
        for model, stats in per_model.items():
            if model == baseline or stats["accuracy"] is None:
                continue
            delta = round(stats["accuracy"] - base_acc, 4)
            deltas[model] = delta
            if delta < 0:
                regressions.append({"model": model, "accuracy_delta": delta, "vs": baseline})
            # per-question regressions: baseline correct -> candidate wrong
            base_by_q = {s.question_id: s.correct for s in scores_by_model[baseline]}
            for s in scores_by_model[model]:
                if base_by_q.get(s.question_id) and not s.correct:
                    regressions.append(
                        {"model": model, "question_id": s.question_id, "regressed": True}
                    )

    return {
        "baseline_model": baseline,
        "per_model": per_model,
        "accuracy_delta_vs_baseline": deltas,
        "regressions": regressions,
        "upgrade_safe": not regressions,
    }
