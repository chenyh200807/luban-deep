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


@pytest.mark.unit
def test_station_completed_signal_gated_by_review_module_flag(monkeypatch):
    """station_completed(站完成=复测调度触发事实, concept_id=pack_id)只在
    LUBAN_REVIEW_MODULE_ENABLED 后入白名单；仍走非 promoting 路径
    (source_feature=learner_signal, 证据编译器排除)。旗标关=与收权前行为一致(拒)。"""
    calls = {}

    class _Svc:
        def append_memory_event(self, user_id, **kw):
            calls.update(kw, user_id=user_id)
            return type("E", (), {"event_id": "e1"})()

    monkeypatch.delenv("LUBAN_REVIEW_MODULE_ENABLED", raising=False)
    with pytest.raises(ValueError):
        record_learner_signal(_Svc(), user_id="u1", signal_type="station_completed", concept_id="F16", completion_id="c1")

    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "true")
    record_learner_signal(_Svc(), user_id="u1", signal_type="station_completed",
                          concept_id="F16", concept_label="屋面防水", completion_id="c1")
    assert calls["source_feature"] == "learner_signal"
    assert calls["memory_kind"] == "learning_evidence"
    assert calls["payload_json"]["learning_signal_type"] == "station_completed"
    assert calls["payload_json"]["concept_id"] == "F16"
    assert calls["payload_json"]["completion_id"] == "c1"

    with pytest.raises(ValueError):
        record_learner_signal(_Svc(), user_id="u1", signal_type="station_done", concept_id="F16")


# ── plan_preference 意志族(pin/defer/time_budget, 计划体系 §3.1/§3.3) ────────


@pytest.mark.unit
def test_plan_preference_signals_gated_by_exam_prep_plan_flag(monkeypatch):
    """旗标关 = 与收权前逐字节同行为(三类被拒); 旗标开 = 同一写器同一通道。"""
    svc = _FakeLearnerStateService()
    monkeypatch.delenv("LUBAN_EXAM_PREP_PLAN_ENABLED", raising=False)
    for signal in ("pin", "defer", "time_budget"):
        with pytest.raises(ValueError):
            record_learner_signal(svc, user_id="u1", signal_type=signal,
                                  concept_id="F16", time_budget_minutes=60)
    assert svc.events == []

    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    pin = record_learner_signal(svc, user_id="u1", signal_type="pin", concept_id="F16")
    defer = record_learner_signal(
        svc, user_id="u1", signal_type="defer", concept_id="F16",
        probe_id="rvp_u1_F16_code_application_",
    )
    budget = record_learner_signal(
        svc, user_id="u1", signal_type="time_budget", time_budget_minutes=45,
    )
    assert pin.payload_json["learning_signal_type"] == "pin"
    assert defer.payload_json["probe_id"] == "rvp_u1_F16_code_application_"
    assert budget.payload_json["time_budget_minutes"] == 45
    assert budget.source_id == "time_budget:global"
    assert all(ev.source_feature == "learner_signal" for ev in svc.events)
    # time_budget 校验: 越界拒绝
    with pytest.raises(ValueError):
        record_learner_signal(svc, user_id="u1", signal_type="time_budget", time_budget_minutes=0)
    with pytest.raises(ValueError):
        record_learner_signal(svc, user_id="u1", signal_type="time_budget", time_budget_minutes=601)
    # pin/defer 仍要求 concept_id
    with pytest.raises(ValueError):
        record_learner_signal(svc, user_id="u1", signal_type="pin", concept_id="")


@pytest.mark.unit
def test_plan_preference_signals_never_enter_learning_evidence(monkeypatch):
    """机器验收(计划 §3.1): plan_preference 事件被
    evidence_lifecycle.is_learning_evidence_record 排除——绝不进学习证据/掌握度。"""
    from deeptutor.services.learner_state.evidence_lifecycle import (
        is_learning_evidence_event,
        is_learning_evidence_record,
    )

    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    svc = _FakeLearnerStateService()
    record_learner_signal(svc, user_id="u1", signal_type="pin", concept_id="k_pin")
    record_learner_signal(svc, user_id="u1", signal_type="defer", concept_id="k_defer")
    record_learner_signal(svc, user_id="u1", signal_type="time_budget", time_budget_minutes=30)

    assert svc.events, "写器必须真的写入"
    for ev in svc.events:
        assert is_learning_evidence_record(ev) is False
        assert is_learning_evidence_event(ev) is False

    truth = synthesize_learning_truth(svc.events)
    weak = {w.get("concept_id") for w in (truth.get("weak_points") or [])}
    obs = {c.get("concept_id") for c in (truth.get("observed_candidates") or [])}
    assert weak.isdisjoint({"k_pin", "k_defer"}) and obs.isdisjoint({"k_pin", "k_defer"})


@pytest.mark.unit
def test_defer_signal_wires_existing_declined_mechanism(monkeypatch):
    """复习任务 defer → revalidation_queue 既有 declined 机制(接通休眠 writer,
    不另记状态): 当日 defer 生效为 deferred, 隔日自然失效。"""
    from deeptutor.services.learner_state.revalidation_queue import (
        declined_probe_ids_from_events,
    )

    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    svc = _FakeLearnerStateService()
    probe = "rvp_u1_1A412010_code_application_E02"
    record_learner_signal(svc, user_id="u1", signal_type="defer",
                          concept_id="1A412010", probe_id=probe)
    # _FakeLearnerStateService 固定 created_at=2026-05-30T10:00:00+08:00
    same_day = declined_probe_ids_from_events(svc.events, now_iso="2026-05-30T20:00:00+08:00")
    next_day = declined_probe_ids_from_events(svc.events, now_iso="2026-05-31T09:00:00+08:00")
    assert same_day == [probe]
    assert next_day == []

    queue = build_revalidation_queue_projection(
        user_id="u1",
        candidates=[{
            "node_id": "1A412010", "label": "防火门构造", "state": "weak",
            "ability_dimension": "code_application", "error_code": "E02",
            "last_observed_at": "2026-05-26T08:00:00+08:00",
        }],
        declined_probe_ids=same_day,
        now_iso="2026-05-30T20:00:00+08:00",
    )
    assert queue["items"][0]["status"] == "deferred"
    assert queue["items"][0]["next_available_at"] == "2026-05-31T20:00:00+08:00"
