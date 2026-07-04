"""写入侧点亮 — record_learner_signal 让 subjective_focus / user_dispute 事件能被创建，
并端到端点亮已合读侧(Stage1/Stage3)；同时守住"不进证据编译器"不变量。

事件写 memory_kind="learning_evidence"(白名单已含) + source_feature="learner_signal"
(_is_learning_evidence 要求 source_feature ∈ {construction_grading, assessment_testset}，
故被排除，零污染)。读侧按 payload.learning_signal_type 照常消费。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.learner_state.learner_signal import record_learner_signal
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
    dispute_candidates_from_events,
)
from deeptutor.services.learner_state.subjective_focus import subjective_focus_projection


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    def append_memory_event(self, user_id, *, source_feature, source_id, memory_kind,
                            payload_json, source_bot_id=None, dedupe_key=None):
        ev = SimpleNamespace(
            event_id=f"evt_{len(self.events)}",
            user_id=user_id,
            source_feature=source_feature,
            source_id=source_id,
            memory_kind=memory_kind,
            payload_json=payload_json,
            created_at="2026-05-30T10:00:00+08:00",
        )
        self.events.append(ev)
        return ev


@pytest.mark.unit
def test_subjective_focus_signal_lights_up_projection():
    svc = _FakeLearnerStateService()
    record_learner_signal(svc, user_id="u1", signal_type="subjective_focus",
                          concept_id="k_fang", concept_label="防水工程")
    weights = subjective_focus_projection(svc.events, now_iso="2026-05-30T10:00:00+08:00")
    assert weights.get("k_fang", 0) > 0          # 写→读：关注线投影点亮


@pytest.mark.unit
def test_user_dispute_signal_lights_up_probe():
    svc = _FakeLearnerStateService()
    record_learner_signal(svc, user_id="u1", signal_type="user_dispute",
                          concept_id="k_zrzt", error_code="E02", user_says="mastered")
    disp = dispute_candidates_from_events(svc.events)
    proj = build_revalidation_queue_projection(user_id="u1", dispute_candidates=disp)
    assert proj["items"], "写一条 user_dispute → 读侧 queue 应吐 probe"
    assert proj["items"][0]["intent"]["concept_id"] == "k_zrzt"


@pytest.mark.unit
def test_learner_signal_does_not_pollute_truth_compiler():
    svc = _FakeLearnerStateService()
    record_learner_signal(svc, user_id="u1", signal_type="subjective_focus", concept_id="k_x", concept_label="x")
    record_learner_signal(svc, user_id="u1", signal_type="user_dispute", concept_id="k_y", error_code="E02")
    truth = synthesize_learning_truth(svc.events)
    weak = {w.get("concept_id") for w in (truth.get("weak_points") or [])}
    obs = {c.get("concept_id") for c in (truth.get("observed_candidates") or [])}
    assert "k_x" not in weak and "k_y" not in weak      # 不进弱点
    assert "k_x" not in obs and "k_y" not in obs        # 不进证据候选（编译器纯净）


@pytest.mark.unit
def test_invalid_signal_type_rejected():
    svc = _FakeLearnerStateService()
    with pytest.raises(ValueError):
        record_learner_signal(svc, user_id="u1", signal_type="mastery_hack", concept_id="k")


def test_station_completed_signal_type_accepted():
    """station_completed(站完成=复测调度触发事实, concept_id=pack_id)入白名单；
    仍走非 promoting 路径(source_feature=learner_signal, 证据编译器排除)。"""
    from deeptutor.services.learner_state.learner_signal import record_learner_signal

    calls = {}

    class _Svc:
        def append_memory_event(self, user_id, **kw):
            calls.update(kw, user_id=user_id)
            return type("E", (), {"event_id": "e1"})()

    record_learner_signal(_Svc(), user_id="u1", signal_type="station_completed",
                          concept_id="F16", concept_label="屋面防水")
    assert calls["source_feature"] == "learner_signal"
    assert calls["memory_kind"] == "learning_evidence"
    assert calls["payload_json"]["learning_signal_type"] == "station_completed"
    assert calls["payload_json"]["concept_id"] == "F16"

    import pytest as _pytest
    with _pytest.raises(ValueError):
        record_learner_signal(_Svc(), user_id="u1", signal_type="station_done", concept_id="F16")
