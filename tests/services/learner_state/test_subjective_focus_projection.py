"""关注线 Task 2 — read-side 投影：衰减 + 掌握阻尼。

刻意不进 synthesize_learning_truth（保证据编译器纯净）。用纯 dict 事件测，
不依赖真实 LearnerStateEvent 工厂；投影对 dict 与真实事件(payload_json)都鲁棒。
"""
from __future__ import annotations

import pytest

from deeptutor.services.learner_state.subjective_focus import subjective_focus_projection


def _focus(concept_id: str, created_at: str) -> dict:
    return {
        "payload_json": {"learning_signal_type": "subjective_focus", "concept_id": concept_id},
        "created_at": created_at,
    }


@pytest.mark.unit
def test_recent_focus_weighted_old_focus_decayed():
    events = [
        _focus("k_fresh", "2026-05-29T10:00:00+08:00"),   # 1 天前
        _focus("k_old", "2026-04-15T10:00:00+08:00"),     # 45 天前
    ]
    w = subjective_focus_projection(events, now_iso="2026-05-30T10:00:00+08:00", half_life_days=14)
    assert w["k_fresh"] > w.get("k_old", 0)                # 新关注 > 旧关注
    assert w["k_old"] < 0.5                                 # 旧关注被显著衰减


@pytest.mark.unit
def test_mastery_damps_focus():
    events = [_focus("k_known", "2026-05-30T09:00:00+08:00")]
    w_lo = subjective_focus_projection(events, now_iso="2026-05-30T10:00:00+08:00", mastery_by_concept={"k_known": 0.1})
    w_hi = subjective_focus_projection(events, now_iso="2026-05-30T10:00:00+08:00", mastery_by_concept={"k_known": 0.9})
    assert w_hi["k_known"] < w_lo["k_known"]                # 已掌握的点，关注边际收益被阻尼


@pytest.mark.unit
def test_non_focus_events_ignored():
    events = [{"payload_json": {"learning_signal_type": "grading", "concept_id": "k"}, "created_at": "2026-05-30T09:00:00+08:00"}]
    w = subjective_focus_projection(events, now_iso="2026-05-30T10:00:00+08:00")
    assert w == {}                                          # 非关注信号不进投影
