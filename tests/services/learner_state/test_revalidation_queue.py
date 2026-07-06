from __future__ import annotations

from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
)


def _state_item(**overrides):
    item = {
        "node_id": "1A412010",
        "label": "防火门构造",
        "state": "weak",
        "ability_dimension": "code_application",
        "error_code": "E02",
        "evidence_refs": ["evt_miss_1", "evt_miss_2"],
        "last_observed_at": "2026-05-18T08:00:00+08:00",
        "forgetting_risk": 0.8,
    }
    item.update(overrides)
    return item


def test_needs_revalidation_creates_one_probe_intent_per_day() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(), _state_item(node_id="1A413020", label="地基处理")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    active = [item for item in queue["items"] if item["status"] == "active"]
    queued = [item for item in queue["items"] if item["status"] == "queued"]

    assert len(queue["items"]) == 1
    assert len(active) == 1
    assert queued == []
    assert active[0]["kind"] == "revalidation_probe"
    assert active[0]["intent"]["intent_version"] == 2
    assert active[0]["intent"]["prescription_steps"][-1]["phase"] == "verification_probe"
    assert active[0]["evidence_refs"] == ["evt_miss_1", "evt_miss_2"]
    assert queue["source_status"]["daily_capacity"] == 1
    assert queue["source_status"]["due_count"] == 2
    assert queue["source_status"]["suppressed_due_count"] == 1


def test_recent_observation_not_due_yet_is_not_enqueued() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(last_observed_at="2026-05-21T08:00:00+08:00")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"] == []
    assert "not_due" in queue["source_status"]["blocked_reasons"]


def test_declined_probe_is_pushed_back_one_day() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item()],
        declined_probe_ids=["rvp_student_demo_1A412010_code_application_E02"],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"][0]["status"] == "deferred"
    assert queue["items"][0]["next_available_at"] == "2026-05-23T09:00:00+08:00"


def test_verified_outcome_removes_probe_from_queue() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item()],
        prescription_outcomes=[
            {
                "training_intent_id": "rvp_student_demo_1A412010_code_application_E02",
                "status": "verified",
                "evidence_refs": ["evt_verified"],
            }
        ],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"] == []
    assert "already_verified" in queue["source_status"]["blocked_reasons"]


def test_unverified_weak_observation_uses_three_day_cadence() -> None:
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(state="weak", last_observed_at="2026-05-19T08:00:00+08:00")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    assert queue["items"][0]["status"] == "active"


def test_fresh_phase_due_next_calendar_day_not_24h():
    """新学相(fresh)按 UTC+8 日历日次日到期(双轮 §6.1 分相首跳/§9-D2 '天'=日历日)：
    昨晚学的今早即到期；同日不到期——'明天见'承诺的调度语义。"""

    def _q(observed, now):
        return build_revalidation_queue_projection(
            user_id="u1",
            candidates=[{"node_id": "F16", "label": "屋面防水", "state": "fresh",
                         "ability_dimension": "", "last_observed_at": observed}],
            now_iso=now,
        )["source_status"]["due_count"]

    assert _q("2026-07-03T22:00:00+08:00", "2026-07-04T09:00:00+08:00") == 1, "昨晚学→今早到期(仅 11h 但跨日)"
    assert _q("2026-07-04T01:00:00+08:00", "2026-07-04T23:59:00+08:00") == 0, "同日 23h 不到期"
    assert _q("2026-07-01T10:00:00+08:00", "2026-07-04T09:00:00+08:00") == 1, "跨多日仍到期"


def test_effective_interval_days_cap_and_exam_horizon():
    """§6.1 地平线折算：cap ≤14 恒生效；考前 40 天线性压缩；间隔永不超过距考天数
    (考前一周结构上不可能出现'21 天后复习')；考后/未设 exam_date 不压缩。"""
    from datetime import datetime, timedelta, timezone

    from deeptutor.services.learner_state.revalidation_queue import effective_interval_days

    tz = timezone(timedelta(hours=8))
    now = datetime(2026, 7, 4, 9, 0, tzinfo=tz)

    assert effective_interval_days(21, now=now) == 14, "无 exam_date: 只有 cap ≤14"
    assert effective_interval_days(3, now=now) == 3

    # 距考 120 天(>40): 不压缩, 只 cap
    assert effective_interval_days(21, now=now, exam_date_iso="2026-11-01") == 14
    # 距考 20 天: 线性压缩 14*20/40=7; 3*20/40=1.5→2
    assert effective_interval_days(21, now=now, exam_date_iso="2026-07-24") == 7
    assert effective_interval_days(3, now=now, exam_date_iso="2026-07-24") == 2
    # 考前一周(距考 5 天): 任何间隔都被钳到 ≤5
    assert effective_interval_days(21, now=now, exam_date_iso="2026-07-09") <= 5
    # 考后: 不压缩(队列语义切换归后续阶段)
    assert effective_interval_days(7, now=now, exam_date_iso="2026-06-01") == 7


def test_exam_horizon_compresses_due_decision():
    """weak 相 3 天节律在考前地平线内被压缩：距考 4 天时, 2 天前的观测已到期。"""
    candidates = [{"node_id": "n1", "label": "x", "state": "weak",
                   "ability_dimension": "code_application",
                   "last_observed_at": "2026-07-02T09:00:00+08:00"}]
    without_exam = build_revalidation_queue_projection(
        user_id="u1", candidates=candidates, now_iso="2026-07-04T09:00:00+08:00",
    )["source_status"]["due_count"]
    with_exam = build_revalidation_queue_projection(
        user_id="u1", candidates=candidates, now_iso="2026-07-04T09:00:00+08:00",
        exam_date_iso="2026-07-08",
    )["source_status"]["due_count"]
    assert without_exam == 0, "无地平线: 3 天节律未到"
    assert with_exam == 1, "考前 4 天: 间隔压缩→已到期"


def test_derive_review_due_at_read_side_projection():
    """mistake_book 等读模型的 review_due_at 派生口——间隔真值唯一归本模块。"""
    from deeptutor.services.learner_state.revalidation_queue import derive_review_due_at

    # weak 相: 观测 + 3 天
    due = derive_review_due_at(
        last_observed_at="2026-07-01T10:00:00+08:00",
        state="weak",
        now_iso="2026-07-02T09:00:00+08:00",
    )
    assert due == "2026-07-04T10:00:00+08:00"
    # fresh 相: 日历日次日零点
    due_fresh = derive_review_due_at(
        last_observed_at="2026-07-01T22:00:00+08:00",
        state="fresh",
        now_iso="2026-07-01T23:00:00+08:00",
    )
    assert due_fresh == "2026-07-02T00:00:00+08:00"
    # 空观测: fail-closed 空串(不造伪日期)
    assert derive_review_due_at(last_observed_at="", state="weak") == ""
    # 考期压缩传导: 距考 4 天 → weak 间隔 3 → max(1, round(3*4/40))=1 天
    due_exam = derive_review_due_at(
        last_observed_at="2026-07-01T10:00:00+08:00",
        state="weak",
        now_iso="2026-07-02T09:00:00+08:00",
        exam_date_iso="2026-07-06",
    )
    assert due_exam == "2026-07-02T10:00:00+08:00"
