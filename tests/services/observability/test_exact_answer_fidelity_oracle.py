"""Deterministic exact-answer-fidelity oracle (harness 9+ roadmap, C8 step-0).

This is the harness's first *quality* signal that is deterministic, LLM-free, and
runs every commit: the exact-authority renderer must keep the authoritative answer
faithful. The second test is the harness's first **hit-rate data point** — it
injects a renderer regression and proves the oracle catches it pre-merge.
"""

from __future__ import annotations

from deeptutor.services.observability import arr_runner


def _status(results: list[dict], case_id: str) -> str:
    return next(r["status"] for r in results if r["case_id"] == case_id)


def test_fidelity_oracle_passes_on_faithful_render() -> None:
    _, results = arr_runner.run_rag_grounding_suite()
    assert _status(results, "exact_answer_fidelity_mcq") == "PASS"
    assert _status(results, "exact_answer_fidelity_free_text") == "PASS"


def test_fidelity_oracle_catches_dropped_answer_regression(monkeypatch) -> None:
    """Inject a renderer regression: the exact response no longer carries the
    authoritative MCQ answer. The oracle MUST flip the case PASS -> FAIL.

    This is the deliberate "答案被改错/丢失" injection: it proves the net has
    teeth, and is the first recorded harness hit (a real regression that would
    be caught before merge / before reaching production)."""
    real = arr_runner.build_exact_authority_response

    def regressed(exact_question: dict) -> str:
        if str(exact_question.get("answer_kind") or "").strip().lower() == "mcq":
            return "## 📊 阅卷结论\n本题暂无法给出标准答案。"  # authoritative answer dropped
        return real(exact_question)

    monkeypatch.setattr(arr_runner, "build_exact_authority_response", regressed)
    _, results = arr_runner.run_rag_grounding_suite()

    assert _status(results, "exact_answer_fidelity_mcq") == "FAIL"
    # The grounding-decision cases (no exact rendering) must stay green — the
    # oracle is specific, not a blunt instrument.
    assert _status(results, "grounded_followup_forces_retrieval_first") == "PASS"
