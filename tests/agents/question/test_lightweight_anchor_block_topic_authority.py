"""p11 / S3 real root cause: the lightweight no-grounding anchor block must decide on the
RAW user_topic via the single subject authority, NOT a lossy re-derived concentration label.

Live-confirmed root cause (deployed main, S3DIAG trace): both domain gates returned
``construction_topic`` for "出一道流水施工的单选题考考我", yet it was canned. The canned came
from ``_should_block_unresolved_lightweight_anchor``: when RAG returned no grounding it
re-derived a label via ``_derive_lightweight_anchor_label`` which over-stripped the noisy
topic to "考我" (losing "流水施工") → ``needs_context_anchor("考我")`` True → block → the
"请指定围绕哪个知识点" canned. A valid construction topic was false-blocked.

Fix = decide the block on the raw ``user_topic`` (single authority), so a noisy-but-valid
topic generates and only a bare action word (no topic at all) blocks.

Hermetic: pure static helper, no LLM / RAG / network.
"""
from __future__ import annotations

from deeptutor.agents.question.coordinator import AgentCoordinator

_NO_GROUNDING: dict = {}  # no anchor_source/grounding -> exercises the topic-authority path
_GROUNDED = {"anchor_source": "rag_knowledge", "knowledge_context": "流水施工…"}
# RAG returned a concentration topic but NOT full grounding (no anchor_source): a continuation
# ("继续出一道") whose own text is action-only is still topic-bearing via this concentration.
_CONCENTRATION_ONLY = {"concentration": "流水施工"}


def _block(user_topic: str, payload: dict) -> bool:
    return AgentCoordinator._should_block_unresolved_lightweight_anchor(
        user_topic=user_topic, anchor_payload=payload
    )


# ---- the fix: noisy-but-valid topic must NOT be blocked even without RAG grounding -------
def test_noisy_valid_topic_not_blocked_without_grounding():
    # "...单选题考考我" suffix used to derive to "考我" and false-block. The topic IS 流水施工.
    assert _block("出一道流水施工的单选题考考我", _NO_GROUNDING) is False
    assert _block("流水施工考考我", _NO_GROUNDING) is False
    assert _block("出一道流水施工的题", _NO_GROUNDING) is False


# ---- preserved: an action-only continuation grounded by a RAG concentration generates ----
def test_action_continuation_with_concentration_not_blocked():
    # "继续出一道" is action-only on its own, but the RAG concentration carries the topic;
    # the label path must keep it generating (regression guard for the over-aggressive
    # raw-topic-only fix, which canned continuations).
    assert _block("继续出一道", _CONCENTRATION_ONLY) is False
    assert _block("再来一道", _CONCENTRATION_ONLY) is False


# ---- boundary: a bare action word with NO topic anywhere (no grounding/concentration) blocks
def test_bare_action_word_still_blocks_without_topic():
    assert _block("继续出一道", _NO_GROUNDING) is True
    assert _block("出三道题", _NO_GROUNDING) is True


# ---- boundary: grounding always wins (never block) --------------------------------------
def test_grounded_anchor_never_blocks():
    assert _block("继续出一道", _GROUNDED) is False
    assert _block("出一道流水施工的单选题考考我", _GROUNDED) is False
