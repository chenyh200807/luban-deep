from __future__ import annotations

from deeptutor.services.luban_lesson.retest_selection import (
    issue_retest_selection,
    verify_retest_selection,
)


def test_selection_identity_binds_user_pack_day_mode_and_variant_set() -> None:
    token = issue_retest_selection(
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=["F16-v2", "F16-v1"],
    )

    assert verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
    )
    assert not verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026193,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
    )
