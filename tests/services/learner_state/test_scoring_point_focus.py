"""Stage 3 (G3/Task4 surgical 落点) — 关注线驱动采分点地图/复测排序。

`_apply_training_intent_priority` 是全仓唯一消费 `prioritize_training_intents`
的地方，且 scoring_point_map 又是 revalidation queue 的源。在 prioritize 前给
intent 打 `subjective_focus_weight`，Task3 的 α=0.5 上限随即生效：关注重排采分点，
但盖不过证据关键弱点。subjective_focus 写入侧=🟡（无事件时 focus_weights 空→inert）。
home today_focus hero 选择器(next_training_signal)是分布式多处，留 deferred。
"""
from __future__ import annotations

import pytest

from deeptutor.services.learner_state.scoring_point_map_read_model import (
    _apply_training_intent_priority,
)


def _item(tid: str, concept_id: str, forgetting_risk: float, evidence_refs: list[str]) -> dict:
    return {"next_action": {"intent": {
        "training_intent_id": tid, "concept_id": concept_id,
        "forgetting_risk": forgetting_risk, "evidence_refs": evidence_refs,
    }}}


@pytest.mark.unit
def test_subjective_focus_boosts_scoring_point_priority():
    items = [_item("a", "k_a", 0.5, ["e1"]), _item("b", "k_b", 0.5, ["e2"])]
    _apply_training_intent_priority(items, focus_weights={"k_b": 1.0})
    a = items[0]["next_action"]["intent"]
    b = items[1]["next_action"]["intent"]
    assert b["priority"] > a["priority"]            # 关注的采分点排前


@pytest.mark.unit
def test_focus_cannot_bury_critical_recurrence():
    items = [_item("crit", "k_crit", 0.9, ["e1", "e2", "e3"]), _item("foc", "k_foc", 0.4, ["e9"])]
    _apply_training_intent_priority(items, focus_weights={"k_foc": 1.0})
    crit = items[0]["next_action"]["intent"]
    foc = items[1]["next_action"]["intent"]
    assert crit["priority"] > foc["priority"]       # α=0.5 上限：关注盖不过证据关键弱点


@pytest.mark.unit
def test_no_focus_weights_is_inert():
    items = [_item("a", "k_a", 0.5, ["e1"])]
    _apply_training_intent_priority(items)          # 无 focus_weights → 向后兼容、行为不变
    assert "priority" in items[0]["next_action"]["intent"]
