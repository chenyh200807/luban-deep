from __future__ import annotations

import pytest

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
        supply_kind="compiled_html",
        supply_digest="a" * 64,
    )

    assert verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
        supply_kind="compiled_html",
        supply_digest="a" * 64,
    )
    assert not verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026193,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
        supply_kind="compiled_html",
        supply_digest="a" * 64,
    )
    assert not verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
        supply_kind="compiled_html",
        supply_digest="b" * 64,
    )


def test_selection_refuses_unsigned_supply_identity() -> None:
    with pytest.raises(ValueError, match="retest_selection_supply_invalid"):
        issue_retest_selection(
            user_id="qa_eval_selection",
            pack_id="F16",
            day_index=2026192,
            mode="forward",
            variant_ids=["F16-v1"],
            supply_kind="compiled_html",
            supply_digest="not-a-sha",
        )


def test_review_selection_binds_probe_and_cycle_anchor() -> None:
    token = issue_retest_selection(
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="review",
        variant_ids=["F16-v1"],
        supply_kind="signed_variant",
        supply_digest="a" * 64,
        probe_id="rvp-f16",
        cycle_anchor="terminal-forward-1",
    )

    assert verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="review",
        variant_ids=["F16-v1"],
        supply_kind="signed_variant",
        supply_digest="a" * 64,
        probe_id="rvp-f16",
        cycle_anchor="terminal-forward-1",
    )
    assert not verify_retest_selection(
        token,
        user_id="qa_eval_selection",
        pack_id="F16",
        day_index=2026192,
        mode="review",
        variant_ids=["F16-v1"],
        supply_kind="signed_variant",
        supply_digest="a" * 64,
        probe_id="rvp-f16",
        cycle_anchor="terminal-forward-2",
    )


def test_review_selection_requires_probe_and_cycle_anchor() -> None:
    with pytest.raises(ValueError, match="retest_selection_probe_cycle_required"):
        issue_retest_selection(
            user_id="qa_eval_selection",
            pack_id="F16",
            day_index=2026192,
            mode="review",
            variant_ids=["F16-v1"],
            supply_kind="signed_variant",
            supply_digest="a" * 64,
        )
