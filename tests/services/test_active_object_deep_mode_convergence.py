"""Differential / convergence net for the two ``_active_object_requires_deep``
implementations (control-plane S3a).

Two authorities historically decided "does the active question object require
deep mode?" and fed mode-selection (fast/deep → student-facing latency/density):

- COARSE ``turn_runtime._active_object_requires_deep_mode(active_object: dict)``
  used by ``start_turn`` mode-selection. It returns True whenever the active
  object carries any question context.
- FINE ``TutorBotCapability._active_object_requires_deep(context)`` used by
  ``_mode_policy`` smart fallback. It demotes practice-generation / answer
  submission / grading-followup turns on an active question to FAST.

This test:

1. First captures both legacy implementations over a corpus and ASSERTS the
   divergence is exactly the expected set (active question + answer/practice
   followup: coarse=deep, fine=fast). (RED before convergence.)
2. After convergence, asserts the canonical equals the FINE semantics for the
   whole corpus, and that the canonical differs from the coarse semantics only
   on those expected divergence rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from deeptutor.services.active_object_builder import normalize_active_object
from deeptutor.services.question_followup import normalize_question_followup_context


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

_SINGLE_QUESTION_CONTEXT = {
    "question": {
        "stem": "下列关于施工组织设计的说法，正确的是？",
        "options": [
            {"label": "A", "text": "选项A"},
            {"label": "B", "text": "选项B"},
            {"label": "C", "text": "选项C"},
            {"label": "D", "text": "选项D"},
        ],
        "answer": "A",
        "question_type": "single_choice",
    },
}


def _active_object(object_type: str, context: dict | None) -> dict:
    raw: dict = {
        "object_type": object_type,
        "object_id": "obj-1",
    }
    if context is not None:
        raw["state_snapshot"] = context
    normalized = normalize_active_object(raw)
    assert normalized is not None, f"corpus active_object failed to normalize: {object_type}"
    return normalized


@dataclass(frozen=True)
class Case:
    name: str
    active_object: dict | None
    user_message: str
    # Whether this row is one of the EXPECTED coarse-vs-fine divergences
    # (active question + answer-submission / practice-generation followup).
    expected_divergence: bool


def _build_corpus() -> list[Case]:
    sq = _active_object("single_question", _SINGLE_QUESTION_CONTEXT)
    qs = _active_object("question_set", _SINGLE_QUESTION_CONTEXT)
    open_topic = _active_object("open_chat_topic", None)

    return [
        # --- No active object: both fast ---
        Case("no_active_object", None, "什么是进度网络图？", expected_divergence=False),
        # --- Active question + pure explanation request: both deep ---
        Case(
            "active_question_explain",
            sq,
            "这道题为什么选A，详细讲一下解题思路",
            expected_divergence=False,
        ),
        # --- Active question + answer submission: coarse=deep, fine=fast ---
        Case(
            "active_question_submission_short",
            sq,
            "我选A",
            expected_divergence=True,
        ),
        Case(
            "active_question_submission_explicit",
            sq,
            "我的答案是D",
            expected_divergence=True,
        ),
        # --- Active question + practice-generation request: coarse=deep, fine=fast ---
        Case(
            "active_question_practice_generation",
            qs,
            "再来一道类似的题考我",
            expected_divergence=True,
        ),
        Case(
            "active_question_next_question",
            qs,
            "下一题",
            expected_divergence=True,
        ),
        # --- Active question + structured grading followup ("第N题"): coarse=deep, fine=fast ---
        Case(
            "active_question_structured_grading",
            qs,
            "第1题我选B，帮我批改",
            expected_divergence=True,
        ),
        # --- Open chat topic active object: both fast ---
        Case(
            "open_chat_topic",
            open_topic,
            "随便聊聊",
            expected_divergence=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Legacy implementations captured verbatim (frozen reference behavior)
# ---------------------------------------------------------------------------


def _legacy_coarse(active_object: dict | None) -> bool:
    """Mirror of turn_runtime._active_object_requires_deep_mode."""
    from deeptutor.services.active_object_builder import (
        extract_question_context_from_active_object,
    )

    normalized = normalize_active_object(active_object)
    if not isinstance(normalized, dict):
        return False
    if extract_question_context_from_active_object(normalized) is not None:
        return True
    object_type = str(normalized.get("object_type") or "").strip()
    return object_type not in {"", "open_chat_topic"}


def _legacy_fine(active_object: dict | None, user_message: str) -> bool:
    """Mirror of TutorBotCapability._active_object_requires_deep (fine semantics)."""
    import re

    from deeptutor.services.active_object_builder import (
        extract_question_context_from_active_object,
    )
    from deeptutor.services.question_followup import resolve_submission_attempt
    from deeptutor.tutorbot.teaching_modes import (
        looks_like_practice_generation_request,
    )

    active = normalize_active_object(active_object)
    if not isinstance(active, dict):
        return False
    object_type = str(active.get("object_type") or "").strip()
    if object_type == "open_chat_topic":
        return False

    followup_context = extract_question_context_from_active_object(active)
    if object_type in {"question_set", "single_question"} and followup_context:
        if looks_like_practice_generation_request(user_message):
            return False
        _, submission = resolve_submission_attempt(user_message, followup_context)
        if submission:
            return False
        text = str(user_message or "").strip()
        if any(marker in text for marker in ("我答", "我选", "批改", "判分", "打分")) and re.search(
            r"第\s*[0-9一二两三四五六七八九十]+\s*[题问]", text
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _build_corpus(), ids=lambda c: c.name)
def test_legacy_divergence_is_exactly_the_expected_set(case: Case) -> None:
    """RED net: the two legacy authorities diverge iff the row is an
    active-question + answer/practice followup (coarse=deep, fine=fast)."""
    coarse = _legacy_coarse(case.active_object)
    fine = _legacy_fine(case.active_object, case.user_message)
    diverges = coarse != fine
    assert diverges == case.expected_divergence, (
        f"{case.name}: coarse={coarse} fine={fine} "
        f"(expected_divergence={case.expected_divergence})"
    )
    if case.expected_divergence:
        # Expected direction: coarse deep -> fine fast.
        assert coarse is True and fine is False


@pytest.mark.parametrize("case", _build_corpus(), ids=lambda c: c.name)
def test_canonical_matches_fine_semantics(case: Case) -> None:
    """After convergence the canonical must equal the FINE (more correct)
    semantics for the entire corpus."""
    from deeptutor.tutorbot.response_mode import active_object_requires_deep_mode

    followup_context = None
    # start_turn provides followup① explicitly; emulate by deriving from the
    # active object's embedded context (both callers can supply it).
    from deeptutor.services.active_object_builder import (
        extract_question_context_from_active_object,
    )

    normalized = normalize_active_object(case.active_object)
    if normalized is not None:
        followup_context = extract_question_context_from_active_object(normalized)
    followup_context = normalize_question_followup_context(followup_context)

    canonical = active_object_requires_deep_mode(
        active_object=case.active_object,
        followup_context=followup_context,
        user_message=case.user_message,
    )
    fine = _legacy_fine(case.active_object, case.user_message)
    assert canonical == fine, f"{case.name}: canonical={canonical} fine={fine}"


@pytest.mark.parametrize("case", _build_corpus(), ids=lambda c: c.name)
def test_canonical_differs_from_coarse_only_on_expected_rows(case: Case) -> None:
    """The behaviour change vs the old coarse authority is bounded to the
    expected active-question + answer/practice divergence rows."""
    from deeptutor.services.active_object_builder import (
        extract_question_context_from_active_object,
    )
    from deeptutor.tutorbot.response_mode import active_object_requires_deep_mode

    normalized = normalize_active_object(case.active_object)
    followup_context = (
        extract_question_context_from_active_object(normalized)
        if normalized is not None
        else None
    )
    canonical = active_object_requires_deep_mode(
        active_object=case.active_object,
        followup_context=normalize_question_followup_context(followup_context),
        user_message=case.user_message,
    )
    coarse = _legacy_coarse(case.active_object)
    differs = canonical != coarse
    assert differs == case.expected_divergence, (
        f"{case.name}: canonical={canonical} coarse={coarse} "
        f"(expected_divergence={case.expected_divergence})"
    )
