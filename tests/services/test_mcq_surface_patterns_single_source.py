"""Behavior-preservation tests for the MCQ-surface single-source convergence (task #12 step 1).

Asserts the canonical primitives in deeptutor.services.mcq_surface_patterns reproduce the
exact pre-convergence behavior of question_lifecycle_skills' former local regexes, and that
the lifecycle module now aliases the canonical objects (one definition, no drift).
"""

from __future__ import annotations

import re

from deeptutor.services import mcq_surface_patterns as canon
from deeptutor.services import question_lifecycle_skills as ql

# The pre-convergence regexes copied verbatim from question_lifecycle_skills (the form
# that lived there before single-sourcing) — the behavior baseline we must preserve.
_PREV_SELECTION = re.compile(
    r"(?:我选|我选择|选|答案是|我的答案是)\s*[A-DＡ-Ｄ]",
    re.IGNORECASE,
)
_PREV_OPTION_LIST = re.compile(
    r"(?:^|[\s，。；;：:？！!?）)])A(?:[\.．、:：\s]+|(?=[一-鿿])).{0,240}?"
    r"(?:[\s，。；;：:])B(?:[\.．、:：\s]+|(?=[一-鿿]))",
    re.IGNORECASE | re.DOTALL,
)

_MATRIX = [
    "我选A",
    "我选择 B",
    "答案是C",
    "我的答案是 D",
    "选D对吗",
    "这题 A.1% B.2% C.3% D.5%，我选A，判对错",
    "某工程屋面为压型金属板。A.5% B.2% C.3% D.1%。我选A",
    "A.红 B.绿 C.蓝 D.黄",
    "刚才那道屋面坡度题讲讲考点",
    "压型金属板屋面坡度最小值",
    "随便聊聊今天天气",
    "第1题A 第2题B",
    "为什么选B不对",
    "",
]


def test_lifecycle_aliases_are_the_canonical_objects() -> None:
    assert ql._FREE_TEXT_MCQ_OPTION_SELECTION_RE is canon.OPTION_ANSWER_ASSERTION_RE
    assert ql._FREE_TEXT_MCQ_OPTION_LIST_RE is canon.OPTION_LIST_RE


def test_option_answer_assertion_behavior_preserved() -> None:
    for text in _MATRIX:
        assert (
            (canon.OPTION_ANSWER_ASSERTION_RE.search(text) is not None)
            == (_PREV_SELECTION.search(text) is not None)
        ), f"selection mismatch on {text!r}"
        assert canon.message_asserts_option_answer(text) == (
            _PREV_SELECTION.search(text) is not None
        )


def test_option_list_behavior_preserved() -> None:
    for text in _MATRIX:
        assert (
            (canon.OPTION_LIST_RE.search(text) is not None)
            == (_PREV_OPTION_LIST.search(text) is not None)
        ), f"option-list mismatch on {text!r}"
        assert canon.message_carries_option_list(text) == (
            _PREV_OPTION_LIST.search(text) is not None
        )
