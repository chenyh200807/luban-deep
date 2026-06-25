"""Canonical single source for MCQ-surface text detection primitives.

Context-Continuity 真闭包 (task #12 step 1; contracts/turn.md §硬约束 24): the recurring
"切链路丢上下文/失忆" class is rooted in the same deterministic facts — "does this
message assert an option answer (我选A)?" and "does this message carry an option list
(A. … B. …)?" — being independently re-compiled in multiple modules
(`question_lifecycle_skills`, `question_followup`, `historical_questions`). Divergent
copies drift and re-decide submission/relation differently per layer.

This module is the ONE home for those primitives. It is intentionally dependency-free
(only ``re``) so any layer — including import-safety-constrained ones like
``question_lifecycle_skills`` (see contracts/capability.md §27) — can import it at module
level without pulling heavy deps or risking an import cycle. New consumers MUST import
from here rather than re-compiling an equivalent regex (the submission/relation gate
authority guard, ``scripts/check_submission_relation_gate_authority.py``, blocks new
ad-hoc gates).

Migration note: ``historical_questions._extract_query_options`` /
``_extract_query_answer_letters`` and ``question_followup``'s leading-answer detection
are candidates to converge onto these primitives in subsequent task #12 steps.
"""

from __future__ import annotations

import re

# "我选A" / "答案是A" style assertion that the message states an option answer. Moved
# verbatim from question_lifecycle_skills._FREE_TEXT_MCQ_OPTION_SELECTION_RE (behavior
# preserved — identical pattern + flags; a test asserts byte-equality).
OPTION_ANSWER_ASSERTION_RE = re.compile(
    r"(?:我选|我选择|选|答案(?:是|为)?|我的答案(?:是|为)?)\s*[:：]?\s*[A-DＡ-Ｄ]",
    re.IGNORECASE,
)

# "A. … B. …" style option list embedded in free text. Moved verbatim from
# question_lifecycle_skills._FREE_TEXT_MCQ_OPTION_LIST_RE (behavior preserved).
OPTION_LIST_RE = re.compile(
    r"(?:^|[\s，。；;：:？！!?）)])A(?:[\.．、:：\s]+|(?=[一-鿿])).{0,240}?"
    r"(?:[\s，。；;：:])B(?:[\.．、:：\s]+|(?=[一-鿿]))",
    re.IGNORECASE | re.DOTALL,
)


def message_asserts_option_answer(message: str) -> bool:
    """True when the message states an option answer (我选A / 答案是B)."""

    return OPTION_ANSWER_ASSERTION_RE.search(str(message or "")) is not None


def message_carries_option_list(message: str) -> bool:
    """True when the message embeds an A./B. option list."""

    return OPTION_LIST_RE.search(str(message or "")) is not None
