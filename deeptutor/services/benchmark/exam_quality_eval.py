"""Closed-book quality eval over the historical-exam ground-truth bank.

This is the operational mechanism of north-star B (verified transmit, 9+
roadmap H2/H6): run a model *closed-book* against real past-exam MCQs whose
authoritative answers we hold, score correctness deterministically
(``quality_scoring``), and report accuracy. Run two models and the
cross-model report proves whether a model upgrade is better-and-not-regressed
before the system auto-upgrades with it.

Design: the LLM call is injected (``completer``) so the scoring/reporting
pipeline is fully testable offline; the default completer wraps the single
LLM entry (``factory.complete``) and uses the configured model.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from deeptutor.services.benchmark.exam_quality_bank import (
    ExamQuestion,
    load_exam_quality_bank,
)
from deeptutor.services.benchmark.quality_scoring import (
    CorrectnessScore,
    cross_model_correctness_report,
    score_answer_correctness,
)

_SYSTEM_PROMPT = "你是参加一级建造师《建筑实务》考试的考生，闭卷作答，只依据自己的知识判断。"

# A completer takes the prompt/system/model and returns the model's text answer.
Completer = Callable[..., Awaitable[str]]


def build_closed_book_prompt(exact_question: dict[str, Any], *, is_multiple: bool) -> str:
    """Build the closed-book prompt for one MCQ.

    Discloses only the question *type* (single vs multiple — which the real
    exam states), never the number of correct answers. Instructs the strict
    ``答案：X`` output format that the single MCQ-parsing authority extracts.
    """
    stem = str(exact_question.get("stem") or "").strip()
    options = exact_question.get("options") or {}
    option_lines = "\n".join(f"{key}. {value}" for key, value in sorted(options.items()))
    kind = "多选题（两个或以上正确选项）" if is_multiple else "单选题（只有一个正确选项）"
    return (
        f"以下是一道{kind}。\n\n"
        f"{stem}\n\n"
        f"选项：\n{option_lines}\n\n"
        "请只输出一行最终答案，格式为「答案：」后紧跟所选选项的大写字母；"
        "多选请将字母连续写在一起。不要输出任何解释或推理过程。"
    )


@dataclass(frozen=True)
class ClosedBookEvalResult:
    model: str
    scores: list[CorrectnessScore]
    accuracy: float | None
    by_year: dict[int, dict[str, int]]
    errors: int


async def _default_completer(
    *, prompt: str, system_prompt: str, model: str | None, **kwargs: Any
) -> str:
    # Single LLM entry point; deferred import keeps this module importable
    # (and testable) without the provider stack.
    from deeptutor.services.llm.factory import complete

    return await complete(
        prompt=prompt, system_prompt=system_prompt, model=model, **kwargs
    )


async def _answer_one(
    question: ExamQuestion,
    *,
    model: str | None,
    completer: Completer,
    semaphore: asyncio.Semaphore,
) -> tuple[ExamQuestion, str, str | None]:
    prompt = build_closed_book_prompt(
        question.exact_question, is_multiple=question.type == "multiple_choice"
    )
    async with semaphore:
        try:
            response = await completer(
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                model=model,
                temperature=0,
            )
            return question, str(response or ""), None
        except Exception as exc:  # network/provider failure: record, don't crash run
            return question, "", f"{type(exc).__name__}: {exc}"


async def run_closed_book_eval(
    questions: list[ExamQuestion],
    *,
    model: str | None = None,
    completer: Completer | None = None,
    concurrency: int = 4,
) -> ClosedBookEvalResult:
    """Answer every question closed-book, score against ground truth, aggregate."""
    completer = completer or _default_completer
    semaphore = asyncio.Semaphore(max(1, concurrency))
    answered = await asyncio.gather(
        *(
            _answer_one(q, model=model, completer=completer, semaphore=semaphore)
            for q in questions
        )
    )

    scores: list[CorrectnessScore] = []
    by_year: dict[int, dict[str, int]] = {}
    errors = 0
    for question, response, error in answered:
        if error:
            errors += 1
        score = score_answer_correctness(
            question_id=question.question_id,
            exact_question=question.exact_question,
            response=response,
        )
        scores.append(score)
        bucket = by_year.setdefault(question.year, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += 1 if score.correct else 0

    total = len(scores)
    correct = sum(1 for s in scores if s.correct)
    accuracy = round(correct / total, 4) if total else None
    return ClosedBookEvalResult(
        model=model or "configured-default",
        scores=scores,
        accuracy=accuracy,
        by_year=by_year,
        errors=errors,
    )


def _format_result(result: ClosedBookEvalResult) -> str:
    lines = [
        f"model={result.model}",
        f"accuracy={result.accuracy}  ({sum(1 for s in result.scores if s.correct)}/{len(result.scores)})",
        f"errors={result.errors}",
    ]
    for year in sorted(result.by_year):
        bucket = result.by_year[year]
        acc = round(bucket["correct"] / bucket["total"], 4) if bucket["total"] else None
        lines.append(f"  {year}: {bucket['correct']}/{bucket['total']} acc={acc}")
    return "\n".join(lines)


async def _amain(models: list[str]) -> None:
    questions = load_exam_quality_bank()
    print(f"loaded {len(questions)} ground-truth MCQs")
    if not models:
        result = await run_closed_book_eval(questions)
        print(_format_result(result))
        return

    scores_by_model: dict[str, list[CorrectnessScore]] = {}
    for model in models:
        result = await run_closed_book_eval(questions, model=model)
        print(_format_result(result))
        scores_by_model[model] = result.scores
    report = cross_model_correctness_report(scores_by_model, baseline_model=models[0])
    print("=== cross-model upgrade verdict ===")
    print(f"upgrade_safe={report['upgrade_safe']}  deltas={report['accuracy_delta_vs_baseline']}")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    import sys

    asyncio.run(_amain(sys.argv[1:]))
