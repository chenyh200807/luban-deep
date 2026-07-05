"""review_due 投影域测试：到期语义收权 revalidation_queue（假'有池=到期'的治本）。"""
from __future__ import annotations

from types import SimpleNamespace

from deeptutor.services.luban_lesson.review_due import build_review_due_projection


def _ev(created, pack, sig="station_completed"):
    return SimpleNamespace(created_at=created,
                           payload_json={"learning_signal_type": sig, "concept_id": pack})


def _lesson_viewed_ev(created, pack, stage="lesson"):
    """学-evidence（lesson_viewed）事件——经真实唯一 writer 产出，
    保证 payload/source_feature 形状与生产一致（禁手搓假形状）。"""
    from deeptutor.services.learner_state.lesson_evidence import record_lesson_view_evidence

    class _Capture:
        def append_memory_event(self, user_id, *, source_feature, source_id,
                                memory_kind, payload_json, dedupe_key=None, **_kw):
            self.event = SimpleNamespace(
                event_id="evt_lv",
                created_at=created,
                source_feature=source_feature,
                memory_kind=memory_kind,
                payload_json=payload_json,
            )
            return self.event

    svc = _Capture()
    record_lesson_view_evidence(
        svc, user_id="u1", pack_id=pack, watched_stage=stage)
    return svc.event


def test_learned_yesterday_due_today_learned_today_not_due():
    out = build_review_due_projection(
        user_id="u1",
        events=[_ev("2026-07-03T22:00:00+08:00", "F16"),
                _ev("2026-07-04T08:00:00+08:00", "S05")],
        now_iso="2026-07-04T09:00:00+08:00")
    assert [d["pack_id"] for d in out["due"]] == ["F16"], "昨晚学的到期, 今早学的不到期"
    assert out["due"][0]["retest_available"] is True, "F16 有变体池"
    assert out["learned_count"] == 2
    assert out["authority"] == "revalidation_queue"


def test_lesson_viewed_counts_as_learned_but_not_due():
    """真机验收回归（问题1）：讲懂幕看完 → lesson_viewed 已落账，
    learned_count 必须把它算进「已学」（融合计划 §1「已学·待验证 exposed」）；
    但绝不产生到期（复测调度触发事实仍只有 station_completed，禁第二调度器）。"""
    out = build_review_due_projection(
        user_id="u1",
        events=[_lesson_viewed_ev("2026-07-04T21:00:00+08:00", "F16")],
        now_iso="2026-07-05T09:00:00+08:00")
    assert out["learned_count"] == 1, "lesson_viewed 落账后 learned_count 必须可见"
    assert out["due"] == [], "只看讲懂不触发复测到期(调度权威=station_completed)"


def test_lesson_viewed_ungreen_pack_not_counted():
    """非绿灯 pack 的 lesson_viewed 不进 learned_count（与 station_completed 同口径）。"""
    out = build_review_due_projection(
        user_id="u1",
        events=[_lesson_viewed_ev("2026-07-04T21:00:00+08:00", "X99")],
        now_iso="2026-07-05T09:00:00+08:00")
    assert out["learned_count"] == 0


def test_lesson_viewed_and_completion_same_pack_counted_once():
    """同一 pack 既看过讲懂又完成过站 → learned_count 只算一次（pack 粒度去重）。"""
    out = build_review_due_projection(
        user_id="u1",
        events=[_lesson_viewed_ev("2026-07-03T21:00:00+08:00", "F16"),
                _ev("2026-07-04T09:00:00+08:00", "F16")],
        now_iso="2026-07-04T10:00:00+08:00")
    assert out["learned_count"] == 1


def test_no_completions_means_empty_not_all_green():
    """没学过任何站=空清单——旧假语义(六站天天全到期)的回归防线。"""
    out = build_review_due_projection(user_id="u1", events=[], now_iso="2026-07-04T09:00:00+08:00")
    assert out["due"] == [] and out["learned_count"] == 0


def test_ungreen_pack_completion_filtered_by_projection_gate():
    out = build_review_due_projection(
        user_id="u1",
        events=[_ev("2026-07-01T10:00:00+08:00", "X99")],
        now_iso="2026-07-04T09:00:00+08:00")
    assert out["due"] == [], "非绿灯站完成事件不产生到期(投影门 fail-closed)"


def test_retest_completion_resets_next_day():
    """复测完成再发 station_completed → 当日不再到期, 次日再到期(v0 单跳节律)。"""
    out = build_review_due_projection(
        user_id="u1",
        events=[_ev("2026-07-03T09:00:00+08:00", "F16"),
                _ev("2026-07-04T09:30:00+08:00", "F16")],
        now_iso="2026-07-04T10:00:00+08:00")
    assert out["due"] == [], "今晨复测完成→今天静默"


def test_variantless_green_pack_marks_retest_unavailable():
    """无变体池的绿灯站照常到期, 但 retest_available=False——客户端据此
    fail-closed 隐藏'换皮'承诺句(F05 为 wave1 如实跳过建池的绿灯站:
    其 pack 自检把机械扣分判断收归 R7 🔴, 结构性无池, 是本断言的稳定 fixture)。"""
    out = build_review_due_projection(
        user_id="u1",
        events=[_ev("2026-07-03T09:00:00+08:00", "F05")],
        now_iso="2026-07-04T09:00:00+08:00")
    assert [d["pack_id"] for d in out["due"]] == ["F05"]
    assert out["due"][0]["retest_available"] is False


def test_review_due_endpoint_flag_off_returns_empty(monkeypatch):
    """路由旗标关(默认) = fail-closed 空投影(enabled=false), 形状稳定不 404。"""
    import asyncio

    from deeptutor.api.routers import luban_lesson as router_module

    monkeypatch.delenv("LUBAN_REVIEW_MODULE_ENABLED", raising=False)
    out = asyncio.run(router_module.review_due(current_user=SimpleNamespace(user_id="u1")))
    assert out == {"due": [], "learned_count": 0, "authority": "revalidation_queue", "enabled": False}


def test_review_due_endpoint_flag_on_threads_exam_date(monkeypatch):
    """旗标开: 事件读自 learner_state service, exam_date 读自 member profile 并
    透传进投影(§6.1 地平线参数)。"""
    import asyncio

    from deeptutor.api.routers import luban_lesson as router_module
    import deeptutor.services.learner_state.service as ls_service

    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "true")

    class _FakeService:
        def list_memory_events(self, user_id, limit=200):
            return [_ev("2026-07-03T09:00:00+08:00", "F16")]

    monkeypatch.setattr(ls_service, "get_learner_state_service", lambda: _FakeService())
    monkeypatch.setattr(router_module, "_exam_date_for", lambda user_id: "2026-09-19")

    out = asyncio.run(router_module.review_due(current_user=SimpleNamespace(user_id="u1")))
    assert out["enabled"] is True
    assert out["authority"] == "revalidation_queue"
    assert [d["pack_id"] for d in out["due"]] == ["F16"]
