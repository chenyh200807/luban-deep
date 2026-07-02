"""goal2+3 Step 2 — single-authority topic normalizer.

S3 live root cause: the noisy practice string is re-derived into a topic in several
lightweight sites via ``_derive_lightweight_anchor_label``; that function (through
``_extract_explicit_lightweight_topic_label``'s ``考(?!我|点|试)`` rule) mis-extracted
"考我" out of "出一道流水施工的单选题考考我", dropping the real "流水施工". The lossy
label then drove both the concentration the generator sees AND the anchor-block decision.

This pins the normalizer: a noisy-but-valid practice string must normalize to its core
construction topic (domain_status == construction_topic), never to the action-word
fragment "考我"; a bare action word normalizes to no usable topic.

Hermetic: pure string normalization, no LLM.
"""
from __future__ import annotations

from deeptutor.agents.question.coordinator import AgentCoordinator
from deeptutor.tutorbot.teaching_modes import practice_generation_topic_domain_status


def _norm(s: str) -> str:
    return AgentCoordinator._derive_lightweight_anchor_label(user_topic=s)


# ---- noisy-but-valid strings normalize to a construction topic, never to "考我" ---------
def test_noisy_string_normalizes_to_construction_core():
    for s in (
        "出一道流水施工的单选题考考我",
        "出一道流水施工的单选题",
        "来一道流水施工的题考考我",
    ):
        out = _norm(s)
        assert "考我" != out, f"{s!r} mis-extracted to the action fragment {out!r}"
        assert practice_generation_topic_domain_status(out) == "construction_topic", (
            f"{s!r} -> {out!r} did not normalize to a construction topic"
        )


# ---- explicit "围绕/关于 X" still extracts the topic --------------------------------------
def test_explicit_topic_marker_extracts_topic():
    assert practice_generation_topic_domain_status(_norm("围绕网络计划出一道单选题")) == "construction_topic"
    assert practice_generation_topic_domain_status(_norm("关于屋面防水考考我")) == "construction_topic"


# ---- a bare action word yields NO usable construction topic -----------------------------
def test_bare_action_word_has_no_topic():
    for s in ("继续出一道", "出三道题", "考考我"):
        out = _norm(s)
        assert practice_generation_topic_domain_status(out) != "construction_topic", (
            f"bare action {s!r} wrongly normalized to construction topic {out!r}"
        )
