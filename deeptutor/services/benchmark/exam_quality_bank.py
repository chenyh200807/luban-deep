"""Loader for the historical-exam ground-truth bank (9+ roadmap H2/H6, north-star B).

The bank (``fixtures/exam_quality_bank.json``) holds real past-exam MCQs with
their authoritative answer letters — the ground truth that lets us score a
model's *closed-book correctness* deterministically, with no LLM judge and no
human labels. Each record's ``exact_question`` feeds
``quality_scoring.score_answer_correctness`` directly.

Pure ``json`` load (no eval): the fixture is the durable artifact; extraction
from the source papers was a one-shot prep step recorded in the fixture's
``provenance`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

_DEFAULT_BANK = Path(__file__).parent / "fixtures" / "exam_quality_bank.json"


@dataclass(frozen=True)
class ExamQuestion:
    """One ground-truth exam question. ``exact_question`` is the scorer input."""

    question_id: str
    year: int
    type: str
    exact_question: dict[str, Any]


def load_exam_quality_bank(path: Path | str | None = None) -> list[ExamQuestion]:
    """Load exam questions from the ground-truth bank fixture.

    Returns an empty list if the fixture has no questions. Raises
    ``FileNotFoundError`` if ``path`` does not exist (fail fast — a missing
    bank means the quality eval cannot run and should not silently pass).
    """
    bank_path = Path(path) if path else _DEFAULT_BANK
    data = json.loads(bank_path.read_text(encoding="utf-8"))
    questions: list[ExamQuestion] = []
    for raw in data.get("questions", []):
        exact = raw.get("exact_question")
        if not isinstance(exact, dict):
            continue
        questions.append(
            ExamQuestion(
                question_id=str(raw.get("question_id") or ""),
                year=int(raw.get("year") or 0),
                type=str(raw.get("type") or ""),
                exact_question=dict(exact),
            )
        )
    return questions
