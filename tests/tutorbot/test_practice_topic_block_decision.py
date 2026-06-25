from __future__ import annotations

from deeptutor.tutorbot.teaching_modes import (
    practice_generation_topic_block_decision,
    practice_generation_topic_domain_status,
)


def test_out_of_scope_blocks() -> None:
    assert (
        practice_generation_topic_block_decision("out_of_scope_topic")
        == "block_out_of_scope"
    )


def test_needs_context_anchor_asks_for_anchor() -> None:
    assert (
        practice_generation_topic_block_decision("needs_context_anchor")
        == "needs_anchor"
    )


def test_unknown_topic_is_allowed() -> None:
    # 一建他科(市政/机电/公路) + 建筑工程白名单漏词(沟槽开挖) 都落 unknown_topic，
    # 入口放行——科目真正守门由出口校验门承担（生成题⊆建筑否则 subject_unavailable）。
    assert practice_generation_topic_block_decision("unknown_topic") == "allow"


def test_construction_topic_is_allowed() -> None:
    assert practice_generation_topic_block_decision("construction_topic") == "allow"


def test_intra_jianzao_subjects_not_blocked_at_entry() -> None:
    # 入口不拦一建他科/建筑漏词（出口门兜底）；只拦明确非考试。
    for message in (
        "给我出一道市政公用工程实务的单选题练练，我想试试手感。",
        "那就考点给我出一道关于沟槽开挖与支护的单选题吧。",
        "给我出一道机电工程的题",
        "给我出一道公路工程的题",
    ):
        status = practice_generation_topic_domain_status(message)
        assert (
            practice_generation_topic_block_decision(status) == "allow"
        ), f"intra-jianzao topic wrongly blocked at entry: {message} -> {status}"


def test_construction_topic_still_generates() -> None:
    for message in ("基坑支护", "土方开挖", "深基坑开挖与支护", "屋面防水"):
        status = practice_generation_topic_domain_status(message)
        assert practice_generation_topic_block_decision(status) == "allow", message


def test_non_exam_topic_still_blocked() -> None:
    status = practice_generation_topic_domain_status("法国首都是哪")
    assert (
        practice_generation_topic_block_decision(status) == "block_out_of_scope"
    )
