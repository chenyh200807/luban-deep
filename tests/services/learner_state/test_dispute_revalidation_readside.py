"""Stage 1 (Task 5 读侧) — user_dispute → revalidation probe。

dispute 候选与 scoring_point_map 候选【可叠加】(不替换)；needs_revalidation +
last_observed_at="" 使其立即到期 → 队列吐一个 probe intent。
写入侧(API 造 user_dispute 事件 + supabase_writer 白名单)=🟡，本轮不做。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
    dispute_candidates_from_events,
)


def _dispute_event(concept_id="k_zrzt", error_code="E02", ability="expression", event_id="evt_disp_1"):
    return SimpleNamespace(
        event_id=event_id,
        created_at="2026-05-30T10:00:00+08:00",
        payload_json={
            "learning_signal_type": "user_dispute",
            "concept_id": concept_id,
            "concept_label": "责任主体",
            "error_code": error_code,
            "ability_dimension": ability,
            "user_says": "mastered",
        },
    )


@pytest.mark.unit
def test_dispute_event_becomes_needs_revalidation_candidate():
    rows = dispute_candidates_from_events([_dispute_event()])
    assert len(rows) == 1
    assert rows[0]["node_id"] == "k_zrzt"
    assert rows[0]["state"] == "needs_revalidation"
    assert rows[0]["last_observed_at"] == ""             # 立即到期


@pytest.mark.unit
def test_non_dispute_events_ignored():
    ev = SimpleNamespace(
        event_id="e", created_at="2026-05-30T10:00:00+08:00",
        payload_json={"learning_signal_type": "grading", "concept_id": "k"},
    )
    assert dispute_candidates_from_events([ev]) == []


@pytest.mark.unit
def test_dispute_candidate_emits_probe():
    disp = dispute_candidates_from_events([_dispute_event()])
    proj = build_revalidation_queue_projection(user_id="u1", dispute_candidates=disp)
    assert proj["items"], "needs_revalidation 立即到期应吐一个 probe"
    assert proj["items"][0]["kind"] == "revalidation_probe"
    assert proj["items"][0]["intent"]["concept_id"] == "k_zrzt"


@pytest.mark.unit
def test_dispute_is_additive_not_replacing_scoring_map():
    scoring_map = {"items": [{
        "knowledge_node_id": "k_scoring", "label": "复查验收", "ability_dimension": "expression",
        "error_codes": ["E04"], "miss_count": 2, "evidence_refs": ["evt_miss"],
    }]}
    events = [SimpleNamespace(event_id="evt_miss", created_at="2026-05-18T08:00:00+08:00", payload_json={})]
    disp = dispute_candidates_from_events([_dispute_event(concept_id="k_disp")])
    proj = build_revalidation_queue_projection(
        user_id="u1", events=events, scoring_point_map=scoring_map, dispute_candidates=disp,
    )
    assert proj["source_status"]["candidate_count"] == 2   # 两源叠加，不替换
