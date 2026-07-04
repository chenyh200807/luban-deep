from __future__ import annotations

from typing import Any

LIFECYCLE_STAGE_EVIDENCE_LEDGER = "evidence_ledger"
LIFECYCLE_STAGE_SHORT_TERM = "short_term_learning_memory"
LIFECYCLE_STAGE_STABLE_CLAIM = "stable_learner_claim"
LIFECYCLE_STAGE_CANONICAL_TRUTH = "canonical_learner_truth"

# evidence_level 语义的单一权威（§6-1 收权）：排序、稳定集合、置信度、
# 展示 label、claim_status 反查全部只在本模块定义。消费方（synthesis /
# canonical policy / RAG compiled truth / provenance / brain read model /
# deep_question personalization）只允许 import，不得再各自维护字面 map。
#
# 排序不变量：L3_mastery_signal > L2_real_retest > L2_confirmed >
# L1_repeated > L0_observed > 未知/空。ladder 外 level（如 "exposed"，
# 看动画只算接触）故意不进 rank map——M0 红线：接触绝不参与掌握排序。
EVIDENCE_LEVEL_RANK = {
    "L0_observed": 0,
    "L1_repeated": 1,
    "L2_confirmed": 2,
    "L2_real_retest": 3,
    "L3_mastery_signal": 4,
}

STABLE_EVIDENCE_LEVELS = frozenset({"L1_repeated", "L2_confirmed", "L2_real_retest", "L3_mastery_signal"})

EVIDENCE_LEVEL_CONFIDENCE = {
    "L0_observed": 0.45,
    "L1_repeated": 0.72,
    "L2_confirmed": 0.9,
    "L2_real_retest": 0.93,
    "L3_mastery_signal": 0.95,
}

EVIDENCE_LEVEL_LABELS = {
    "L0_observed": "单次观察",
    "L1_repeated": "重复出现",
    "L2_confirmed": "已确认",
    "L2_real_retest": "复测确认",
    "L3_mastery_signal": "改善信号",
    "unclassified": "待确认",
}

_CLAIM_STATUS_TO_EVIDENCE_LEVEL = {
    "observed": "L0_observed",
    "repeated": "L1_repeated",
    "confirmed": "L2_confirmed",
}

def _text(level: Any) -> str:
    return str(level or "").strip()


def evidence_level_rank(level: Any) -> int:
    return EVIDENCE_LEVEL_RANK.get(_text(level), -1)


def max_evidence_level(previous: Any, current: Any) -> str:
    previous_text = _text(previous)
    current_text = _text(current)
    return previous_text if evidence_level_rank(previous_text) >= evidence_level_rank(current_text) else current_text


def confidence_for_evidence_level(level: Any) -> float:
    return EVIDENCE_LEVEL_CONFIDENCE.get(_text(level), 0.3)


def is_stable_evidence_level(level: Any) -> bool:
    return _text(level) in STABLE_EVIDENCE_LEVELS


def evidence_level_from_claim_status(status: Any) -> str:
    return _CLAIM_STATUS_TO_EVIDENCE_LEVEL.get(_text(status), "")


def lifecycle_stage_for_evidence_level(level: Any) -> str:
    text = _text(level)
    if text == "L0_observed":
        return LIFECYCLE_STAGE_SHORT_TERM
    if text in STABLE_EVIDENCE_LEVELS:
        return LIFECYCLE_STAGE_STABLE_CLAIM
    return LIFECYCLE_STAGE_EVIDENCE_LEDGER
