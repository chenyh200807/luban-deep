"""Guard the p11 no-grounding block against lossy topic normalization.

The canonical topic normalizer must preserve a valid topic in noisy generation requests,
while an inherited RAG concentration must keep action-only continuations usable. Together
these assertions protect the current single-authority implementation without adding a
second raw-topic classifier to the block helper.

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


# ---- noisy-but-valid topic must NOT be blocked even without RAG grounding ----------------
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
