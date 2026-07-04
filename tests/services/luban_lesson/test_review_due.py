"""review_due 投影域测试：到期语义收权 revalidation_queue（假'有池=到期'的治本）。"""
from __future__ import annotations

from types import SimpleNamespace

from deeptutor.services.luban_lesson.review_due import build_review_due_projection


def _ev(created, pack, sig="station_completed"):
    return SimpleNamespace(created_at=created,
                           payload_json={"learning_signal_type": sig, "concept_id": pack})


def test_learned_yesterday_due_today_learned_today_not_due():
    out = build_review_due_projection(
        user_id="u1",
        events=[_ev("2026-07-03T22:00:00+08:00", "F16"),
                _ev("2026-07-04T08:00:00+08:00", "S05")],
        now_iso="2026-07-04T09:00:00+08:00")
    assert [d["pack_id"] for d in out["due"]] == ["F16"], "昨晚学的到期, 今早学的不到期"
    assert out["due"][0]["retest_available"] is True, "F16 有 47 变体池"
    assert out["learned_count"] == 2
    assert out["authority"] == "revalidation_queue"


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
