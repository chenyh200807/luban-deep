from __future__ import annotations

from deeptutor.services.learner_state.memory_lifecycle import (
    EVIDENCE_LEVEL_LABELS,
    LIFECYCLE_STAGE_CANONICAL_TRUTH,
    LIFECYCLE_STAGE_EVIDENCE_LEDGER,
    LIFECYCLE_STAGE_SHORT_TERM,
    LIFECYCLE_STAGE_STABLE_CLAIM,
    STABLE_EVIDENCE_LEVELS,
    confidence_for_evidence_level,
    evidence_level_from_claim_status,
    evidence_level_rank,
    lifecycle_stage_for_evidence_level,
    max_evidence_level,
)


def test_lifecycle_stage_for_evidence_levels() -> None:
    assert lifecycle_stage_for_evidence_level("L0_observed") == LIFECYCLE_STAGE_SHORT_TERM
    assert lifecycle_stage_for_evidence_level("L1_repeated") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L2_confirmed") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L2_real_retest") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L3_mastery_signal") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("") == LIFECYCLE_STAGE_EVIDENCE_LEDGER


def test_canonical_truth_stage_is_reserved_for_write_gate() -> None:
    assert LIFECYCLE_STAGE_CANONICAL_TRUTH == "canonical_learner_truth"


def test_evidence_level_rank_is_a_total_order_over_the_ladder() -> None:
    # 单一权威排序：真懂/复测信号必须高于 L0——这是 §6-1 的排序地雷修复点。
    assert (
        evidence_level_rank("L3_mastery_signal")
        > evidence_level_rank("L2_real_retest")
        > evidence_level_rank("L2_confirmed")
        > evidence_level_rank("L1_repeated")
        > evidence_level_rank("L0_observed")
        > evidence_level_rank("")
    )
    # ladder 外 level（如 exposed）不参与掌握排序：M0 红线。
    assert evidence_level_rank("exposed") == evidence_level_rank("")
    assert evidence_level_rank("unknown_future_level") == evidence_level_rank("")


def test_max_evidence_level_never_downgrades_stable_levels() -> None:
    # 地雷复现：旧 _max_level 会让 L0 覆盖 L3_mastery_signal / L2_real_retest。
    assert max_evidence_level("L3_mastery_signal", "L0_observed") == "L3_mastery_signal"
    assert max_evidence_level("L2_real_retest", "L0_observed") == "L2_real_retest"
    assert max_evidence_level("L2_real_retest", "L2_confirmed") == "L2_real_retest"
    assert max_evidence_level("", "L0_observed") == "L0_observed"
    assert max_evidence_level("L1_repeated", "L2_confirmed") == "L2_confirmed"


def test_confidence_is_monotonic_with_rank() -> None:
    # 地雷复现：旧 _confidence_for_level 对 L3/L2_real_retest 兜底 0.3（比 L0 还低）。
    assert (
        confidence_for_evidence_level("L3_mastery_signal")
        > confidence_for_evidence_level("L2_real_retest")
        > confidence_for_evidence_level("L2_confirmed")
        > confidence_for_evidence_level("L1_repeated")
        > confidence_for_evidence_level("L0_observed")
        > confidence_for_evidence_level("")
    )


def test_stable_levels_and_labels_cover_the_full_ladder() -> None:
    assert STABLE_EVIDENCE_LEVELS == frozenset(
        {"L1_repeated", "L2_confirmed", "L2_real_retest", "L3_mastery_signal"}
    )
    for level in ("L0_observed", *sorted(STABLE_EVIDENCE_LEVELS)):
        assert EVIDENCE_LEVEL_LABELS.get(level)


def test_evidence_level_from_claim_status_roundtrip() -> None:
    assert evidence_level_from_claim_status("observed") == "L0_observed"
    assert evidence_level_from_claim_status("repeated") == "L1_repeated"
    assert evidence_level_from_claim_status("confirmed") == "L2_confirmed"
    assert evidence_level_from_claim_status("stale") == ""
