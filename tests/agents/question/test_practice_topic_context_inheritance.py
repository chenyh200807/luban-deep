"""goal2+3 Step 3 — p11 canned -> fall-through that inherits the established topic.

After Step 1 (generator subject lock) the generator structurally cannot emit off-domain
garbage, so a bare-action continuation ("继续出一道") whose own message carries no topic is
now SAFE to satisfy by inheriting the established construction topic from the conversation
context instead of falling to the needs-anchor canned. Only a true cold start (no topic in
the message AND none in the context) still cans.

`_resolve_practice_topic_with_context` is the single authority for that decision (reuses the
one normalizer); this pins it. Hermetic.
"""
from __future__ import annotations

from deeptutor.agents.question.coordinator import AgentCoordinator
from deeptutor.tutorbot.teaching_modes import practice_generation_topic_domain_status as _ds


def _resolve(user_topic: str, history_context: str) -> str:
    return AgentCoordinator._resolve_practice_topic_with_context(
        user_topic=user_topic, history_context=history_context
    )


# ---- bare-action continuation inherits the established construction topic ----------------
def test_continuation_inherits_topic_from_context():
    ctx = "用户正在练习流水施工，已经出了一道流水施工的单选题。"
    out = _resolve("继续出一道", ctx)
    assert _ds(out) == "construction_topic", f"continuation did not inherit a topic: {out!r}"


# ---- this turn's own topic wins when present (no need to inherit) ------------------------
def test_own_topic_used_when_present():
    out = _resolve("出一道流水施工的单选题考考我", "")
    assert _ds(out) == "construction_topic", f"own topic lost: {out!r}"


# ---- true cold start (no topic in message OR context) yields no topic (-> honest canned) -
def test_cold_start_yields_no_topic():
    assert _resolve("继续出一道", "") == ""
    assert _resolve("出三道题", "你好，今天天气不错") == ""
