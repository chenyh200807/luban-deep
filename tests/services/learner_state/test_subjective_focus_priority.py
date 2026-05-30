"""关注线 Task 3 — `_intent_priority` 有上限加权（α=0.5）。

关注只重排同档，盖不过高 forgetting_risk×recurrence 的证据关键弱点；
且绝不引入掌握/得分字段。
"""
from __future__ import annotations

import pytest

from deeptutor.services.learner_state.training_intent import prioritize_training_intents


@pytest.mark.unit
def test_focus_boosts_but_cannot_bury_critical_evidence():
    critical = {
        "training_intent_id": "crit", "forgetting_risk": 0.9, "exam_weight": 1.0,
        "evidence_refs": ["e1", "e2", "e3"],
    }
    focused = {
        "training_intent_id": "foc", "forgetting_risk": 0.4, "exam_weight": 1.0,
        "evidence_refs": ["e9"], "subjective_focus_weight": 1.0,
    }
    ranked = prioritize_training_intents([focused, critical], max_active=1)
    assert ranked[0]["training_intent_id"] == "crit"   # 关注 ×1.5 仍盖不过关键证据
    assert "mastery" not in ranked[0]


@pytest.mark.unit
def test_focus_breaks_ties_among_comparable():
    a = {"training_intent_id": "a", "forgetting_risk": 0.5, "evidence_refs": ["e1"]}
    b = {"training_intent_id": "b", "forgetting_risk": 0.5, "evidence_refs": ["e2"], "subjective_focus_weight": 1.0}
    ranked = prioritize_training_intents([a, b], max_active=1)
    assert ranked[0]["training_intent_id"] == "b"      # 同档关注排前
