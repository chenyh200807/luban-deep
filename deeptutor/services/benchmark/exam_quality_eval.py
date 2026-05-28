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
from datetime import date
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from deeptutor.services.benchmark.exam_quality_bank import (
    ExamQuestion,
    load_exam_quality_bank,
)
from deeptutor.services.benchmark.harness_hit_ledger import HarnessHit, append_hit
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
class ModelSpec:
    """One model to eval: an opaque model name plus optional explicit binding.

    With ``binding=None`` the call falls back to the configured default provider
    (current production deepseek). With ``binding`` set, the eval bypasses the
    default config and resolves the provider via ``provider_registry`` —
    required for cross-model runs (e.g. ``dashscope:qwen-max`` next to
    ``deepseek:deepseek-v4-flash``) so each call hits the right key + base_url.
    """

    model: str
    binding: str | None = None

    @property
    def label(self) -> str:
        return f"{self.binding}:{self.model}" if self.binding else self.model


def parse_model_spec(arg: str) -> ModelSpec:
    """Parse a CLI arg of form ``model`` or ``binding:model``.

    Fail fast on empty model name — a typo would otherwise silently use config.
    """
    arg = (arg or "").strip()
    if not arg:
        raise ValueError("empty model spec")
    if ":" in arg:
        binding, model = arg.split(":", 1)
        binding = binding.strip() or None
        model = model.strip()
    else:
        binding, model = None, arg
    if not model:
        raise ValueError(f"empty model name in spec {arg!r}")
    return ModelSpec(model=model, binding=binding)


def build_completer_for_spec(spec: ModelSpec) -> Completer:
    """Build the completer for a model spec.

    No binding → reuse the configured-default completer (zero env requirements).
    Explicit binding → resolve the provider via the single ``provider_registry``
    authority, read the env key it declares, and pass the full quad
    (model + api_key + base_url + binding) to ``factory.complete`` so the
    configured-default never bleeds in.
    """
    if spec.binding is None:
        return _default_completer

    from deeptutor.services.provider_registry import find_by_name

    provider = find_by_name(spec.binding)
    if provider is None:
        raise ValueError(f"unknown provider binding: {spec.binding!r}")
    env_key = getattr(provider, "env_key", "") or ""
    api_key = os.environ.get(env_key) if env_key else None
    base_url = getattr(provider, "default_api_base", None)
    # Fall back to the configured default ONLY when the configured binding
    # matches the requested one — otherwise we'd risk hitting one provider's
    # endpoint with another's key. This keeps "deepseek:deepseek-v4-flash"
    # usable on a deepseek-configured project without DEEPSEEK_API_KEY in
    # os.environ, while still failing fast on real cross-provider key gaps.
    if not api_key:
        from deeptutor.services.llm.config import get_llm_config

        try:
            cfg = get_llm_config()
        except Exception:
            cfg = None
        if cfg is not None and str(getattr(cfg, "binding", "") or "").lower() == spec.binding.lower():
            api_key = getattr(cfg, "api_key", None) or api_key
            base_url = base_url or getattr(cfg, "base_url", None)
    if env_key and not api_key:
        raise RuntimeError(
            f"binding {spec.binding!r} requires env var {env_key} (not set, "
            f"and configured provider does not match); set it before running "
            f"cross-model eval."
        )

    async def _completer(
        *, prompt: str, system_prompt: str, model: str | None, **kwargs: Any
    ) -> str:
        from deeptutor.services.llm.factory import complete

        return await complete(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
            base_url=base_url,
            binding=spec.binding,
            **kwargs,
        )

    return _completer


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


def record_cross_model_real_hits(
    report: dict[str, Any],
    *,
    bank_label: str = "一建《建筑实务》62 MCQ",
    ledger_path: Path | None = None,
) -> int:
    """Append one ``kind="real"`` hit per regressing candidate; return count.

    Each candidate with ``accuracy_delta < 0`` is a real regression the cross-model
    gate caught — a model swap that would degrade quality. This is exactly the
    catch that proves north-star B is operational (roadmap H4 / C3 'real' lane);
    without this hook, real-catches don't accrue and the ledger stays at 0.
    """
    if not isinstance(report, dict) or report.get("upgrade_safe") is not False:
        return 0
    deltas = report.get("accuracy_delta_vs_baseline") or {}
    baseline = str(report.get("baseline_model") or "")
    today = date.today().isoformat()
    appended = 0
    for model, delta in deltas.items():
        if not isinstance(delta, (int, float)) or delta >= 0:
            continue
        hit = HarnessHit(
            gate="exam_quality_eval.cross_model",
            regression=f"{model} {delta:+.4f} vs {baseline} on {bank_label}",
            caught=True,
            kind="real",
            date=today,
            note=f"cross-model auto-record: candidate would regress quality by {-float(delta) * 100:.2f}pp",
        )
        append_hit(hit, ledger_path)
        appended += 1
    return appended


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


async def _amain(args: list[str]) -> None:
    questions = load_exam_quality_bank()
    # Flag handling: opt-out of auto-recording real hits. Default ON so the
    # ledger actually accrues real-catches with normal use (the gap §0.8/§0.9
    # called out — wired only here, not in inner-loop code, so no surprise).
    record_hits = "--no-record-hits" not in args
    args = [a for a in args if not a.startswith("--")]
    print(f"loaded {len(questions)} ground-truth MCQs")
    if not args:
        result = await run_closed_book_eval(questions)
        print(_format_result(result))
        return

    specs = [parse_model_spec(a) for a in args]
    scores_by_model: dict[str, list[CorrectnessScore]] = {}
    for spec in specs:
        completer = build_completer_for_spec(spec)
        result = await run_closed_book_eval(
            questions, model=spec.model, completer=completer
        )
        # report uses the full label (binding:model) so cross-model output is unambiguous
        labeled = ClosedBookEvalResult(
            model=spec.label,
            scores=result.scores,
            accuracy=result.accuracy,
            by_year=result.by_year,
            errors=result.errors,
        )
        print(_format_result(labeled))
        scores_by_model[spec.label] = result.scores
    if len(specs) >= 2:
        report = cross_model_correctness_report(
            scores_by_model, baseline_model=specs[0].label
        )
        print("=== cross-model upgrade verdict ===")
        print(
            f"baseline={report['baseline_model']}  "
            f"upgrade_safe={report['upgrade_safe']}  "
            f"deltas={report['accuracy_delta_vs_baseline']}"
        )
        if report["regressions"]:
            print(f"regressions: {report['regressions']}")
        if record_hits:
            n = record_cross_model_real_hits(report)
            if n:
                print(f"recorded {n} real hit(s) in harness_hit_ledger.json")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    import sys

    asyncio.run(_amain(sys.argv[1:]))
