from __future__ import annotations

from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
    build_review_horizon_projection,
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


def test_needs_revalidation_emits_up_to_daily_capacity() -> None:
    """日容量 owner 2026-07-11 拍板 1→5: 到期≤容量时全部发射, 超出才压制。"""
    queue = build_revalidation_queue_projection(
        user_id="student_demo",
        candidates=[_state_item(), _state_item(node_id="1A413020", label="地基处理")],
        now_iso="2026-05-22T09:00:00+08:00",
    )

    active = [item for item in queue["items"] if item["status"] == "active"]

    assert len(queue["items"]) == 2
    assert len(active) == 2
    assert all(i["kind"] == "revalidation_probe" for i in active)
    assert active[0]["intent"]["intent_version"] == 2
    assert active[0]["intent"]["prescription_steps"][-1]["phase"] == "verification_probe"
    assert queue["source_status"]["daily_capacity"] == 5
    assert queue["source_status"]["due_count"] == 2
    assert queue["source_status"]["suppressed_due_count"] == 0
    # 超容量压制仍生效: 7 个到期只发 5
    many = [
        _state_item(node_id=f"1A41300{i}", label=f"站{i}") for i in range(7)
    ]
    queue7 = build_revalidation_queue_projection(
        user_id="student_demo", candidates=many,
        now_iso="2026-05-22T09:00:00+08:00",
    )
    assert len([i for i in queue7["items"] if i["status"] == "active"]) == 5
    assert queue7["source_status"]["suppressed_due_count"] == 2


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


def test_cycle_anchor_changes_probe_identity_without_breaking_same_cycle_replay() -> None:
    base = {
        "node_id": "F16",
        "label": "屋面防水",
        "state": "stable",
        "ability_dimension": "code_application",
        "last_observed_at": "2026-07-01T09:00:00+08:00",
        "successful_review_streak": 1,
        "cycle_anchor": "terminal_r1",
    }
    first = build_revalidation_queue_projection(
        user_id="u1", candidates=[base], now_iso="2026-07-04T09:01:00+08:00"
    )["items"][0]["probe_id"]
    replay = build_revalidation_queue_projection(
        user_id="u1", candidates=[dict(base)], now_iso="2026-07-04T10:00:00+08:00"
    )["items"][0]["probe_id"]
    next_cycle = build_revalidation_queue_projection(
        user_id="u1",
        candidates=[{
            **base,
            "last_observed_at": "2026-07-04T10:00:00+08:00",
            "successful_review_streak": 2,
            "cycle_anchor": "terminal_r2",
        }],
        now_iso="2026-07-11T10:01:00+08:00",
    )["items"][0]["probe_id"]
    assert first == replay
    assert next_cycle != first


def test_stable_review_uses_existing_decay_profile_schedule() -> None:
    def _due(streak: int, observed: str, now: str) -> int:
        return build_revalidation_queue_projection(
            user_id="u1",
            candidates=[{
                "node_id": "F16",
                "label": "屋面防水",
                "state": "stable",
                "ability_dimension": "code_application",
                "last_observed_at": observed,
                "successful_review_streak": streak,
                "cycle_anchor": f"r{streak}",
            }],
            now_iso=now,
        )["source_status"]["due_count"]

    assert _due(1, "2026-07-01T09:00:00+08:00", "2026-07-04T09:00:00+08:00") == 1
    assert _due(2, "2026-07-01T09:00:00+08:00", "2026-07-08T09:00:00+08:00") == 1
    assert _due(3, "2026-07-01T09:00:00+08:00", "2026-07-15T09:00:00+08:00") == 1


# ── 7 天到期预报读面（计划体系 §3.1 权威点 2：horizon 只准住本模块）──────────


def _horizon_candidate(label: str, state: str, observed: str, **overrides) -> dict:
    row = {
        "node_id": label,
        "label": label,
        "state": state,
        "ability_dimension": "code_application",
        "error_code": "E02",
        "evidence_refs": [f"evt_{label}"],
        "last_observed_at": observed,
    }
    row.update(overrides)
    return row


def _horizon_candidates() -> list[dict]:
    return [
        # A: weak, 观测 4 天前 → 间隔 3 → 已逾期 → day 0
        _horizon_candidate("A_overdue", "weak", "2026-08-01T08:00:00+08:00"),
        # B: weak, 观测昨天 → due 8-07 → day 2
        _horizon_candidate("B_day2", "weak", "2026-08-04T10:00:00+08:00"),
        # C: fresh, 今晨学 → 日历日次日零点 → day 1
        _horizon_candidate("C_fresh", "fresh", "2026-08-05T01:00:00+08:00"),
        # D: stable streak=3 → 14 天档 → 8-15 → 窗外
        _horizon_candidate(
            "D_beyond", "stable", "2026-08-01T09:00:00+08:00",
            successful_review_streak=3,
        ),
    ]


def test_review_horizon_buckets_by_calendar_due_day() -> None:
    horizon = build_review_horizon_projection(
        user_id="u1",
        candidates=_horizon_candidates(),
        now_iso="2026-08-05T09:00:00+08:00",
        days=7,
    )
    assert horizon["horizon_days"] == 7
    assert len(horizon["days"]) == 7
    assert [d["date"] for d in horizon["days"]][:3] == ["2026-08-05", "2026-08-06", "2026-08-07"]
    by_day = {
        d["day_offset"]: [i["intent"]["concept_id"] for i in d["items"]]
        for d in horizon["days"]
    }
    assert by_day[0] == ["A_overdue"]
    assert by_day[1] == ["C_fresh"]
    assert by_day[2] == ["B_day2"]
    assert all(not by_day[i] for i in range(3, 7))
    assert "beyond_horizon" in horizon["source_status"]["blocked_reasons"]
    assert horizon["source_status"]["due_count"] == 3
    # day0 桶与当日队列的到期集合一致（同输入同 now）
    daily = build_revalidation_queue_projection(
        user_id="u1", candidates=_horizon_candidates(), now_iso="2026-08-05T09:00:00+08:00",
    )
    assert [i["intent"]["concept_id"] for i in daily["items"]] == by_day[0]
    # 预报项 due_at = 派生到期时刻（非 now）
    day2_item = horizon["days"][2]["items"][0]
    assert day2_item["due_at"] == "2026-08-07T10:00:00+08:00"


def test_review_horizon_is_deterministic_replay() -> None:
    kwargs = dict(
        user_id="u1", candidates=_horizon_candidates(),
        now_iso="2026-08-05T09:00:00+08:00", exam_date_iso="2026-11-01", days=7,
    )
    assert build_review_horizon_projection(**kwargs) == build_review_horizon_projection(**kwargs)


def test_review_horizon_keeps_daily_capacity_semantics() -> None:
    many = [
        _horizon_candidate(f"N{i}", "weak", "2026-08-03T10:00:00+08:00")  # due 8-06 → day 1
        for i in range(7)
    ]
    horizon = build_review_horizon_projection(
        user_id="u1", candidates=many, now_iso="2026-08-05T09:00:00+08:00", days=7,
    )
    day1 = horizon["days"][1]
    assert day1["due_count"] == 7
    assert len(day1["items"]) == 5
    assert day1["suppressed_due_count"] == 2


def test_review_horizon_verified_excluded_and_declined_deferred() -> None:
    horizon = build_review_horizon_projection(
        user_id="student_demo",
        candidates=[_state_item()],
        prescription_outcomes=[{
            "training_intent_id": "rvp_student_demo_1A412010_code_application_E02",
            "status": "verified",
        }],
        now_iso="2026-05-22T09:00:00+08:00",
    )
    assert all(not d["items"] for d in horizon["days"])
    assert "already_verified" in horizon["source_status"]["blocked_reasons"]

    declined = build_review_horizon_projection(
        user_id="student_demo",
        candidates=[_state_item()],
        declined_probe_ids=["rvp_student_demo_1A412010_code_application_E02"],
        now_iso="2026-05-22T09:00:00+08:00",
    )
    item = declined["days"][0]["items"][0]
    assert item["status"] == "deferred"
    assert item["next_available_at"] == "2026-05-23T09:00:00+08:00"


def test_derive_review_due_at_accepts_streak_and_defaults_unchanged() -> None:
    from deeptutor.services.learner_state.revalidation_queue import derive_review_due_at

    # stable streak=3 → 14 天档（DECAY_PROFILES schedule，真值仍归本模块）
    assert derive_review_due_at(
        last_observed_at="2026-07-01T09:00:00+08:00",
        state="stable",
        ability_dimension="code_application",
        successful_review_streak=3,
        now_iso="2026-07-02T09:00:00+08:00",
    ) == "2026-07-15T09:00:00+08:00"
    # 不带 streak（旧签名）行为不变：weak 观测+3 天
    assert derive_review_due_at(
        last_observed_at="2026-07-01T10:00:00+08:00",
        state="weak",
        now_iso="2026-07-02T09:00:00+08:00",
    ) == "2026-07-04T10:00:00+08:00"
