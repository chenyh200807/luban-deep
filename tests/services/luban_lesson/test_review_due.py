"""review_due 投影域测试：到期语义收权 revalidation_queue（假'有池=到期'的治本）。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.luban_lesson.review_due import (
    ReviewHorizonUnavailable,
    build_review_due_projection,
    resolve_due_review_probe,
    resolve_review_exam_date,
)


def _ev(created, pack, sig="station_completed"):
    completion_id = f"cmp_{pack}_{created}"
    return SimpleNamespace(
        event_id=f"station_{completion_id}",
        created_at=created,
        source_feature="learner_signal",
        payload_json={
            "learning_signal_type": sig,
            "concept_id": pack,
            "completion_id": completion_id,
        },
    )


def _terminal(
    created,
    pack,
    *,
    completion_id,
    mode="forward",
    score_ratio=1.0,
    status=None,
    authority="signed_variant_server_rescore",
):
    result_status = status or ("verified" if mode == "review" and score_ratio >= 1.0 else "not_verified")
    question_count = 1 if score_ratio in {0.0, 1.0} else 2
    score_awarded = score_ratio * question_count
    return SimpleNamespace(
        event_id=f"terminal_{completion_id}",
        created_at=created,
        source_feature="assessment_testset",
        source_id=f"{completion_id}:terminal",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "assessment_testset",
            "assessment_type": f"luban_{mode}_completion",
            "retest_completion_id": completion_id,
            "completion_terminal": True,
            "request_hash": f"request:{completion_id}",
            "practice_mode": mode,
            "pack_id": pack,
            "target_pack_id": pack,
            "score_ratio": score_ratio,
            "score_awarded": score_awarded,
            "max_score": float(question_count),
            "item_event_refs": [
                f"item_{completion_id}_{index}" for index in range(question_count)
            ],
            "claim_promotion_allowed": mode == "review",
            "prescription_result": {"status": result_status, "score_ratio": score_ratio},
            "quality": {
                "authority": authority,
                "writeback_eligible": True,
                "measurement_confidence": "high" if mode == "review" else "medium",
                "evidence_level": "L2_real_retest" if mode == "review" else "L0_observed",
            },
        },
    )


def _items_for_terminal(terminal):
    payload = terminal.payload_json
    completion_id = payload["retest_completion_id"]
    correct_count = int(payload["score_awarded"])
    return [
        SimpleNamespace(
            event_id=event_id,
            created_at=terminal.created_at,
            source_feature="assessment_testset",
            source_id=f"{completion_id}:q{index + 1}",
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "learning_evidence",
                "retest_completion_id": completion_id,
                "request_hash": payload["request_hash"],
                "practice_mode": payload["practice_mode"],
                "pack_id": payload["pack_id"],
                "target_pack_id": payload["target_pack_id"],
                "question_id": f"q{index + 1}",
                "probe_role": "anchor" if payload["practice_mode"] == "forward" else "",
                "is_correct": index < correct_count,
                "score_awarded": 1.0 if index < correct_count else 0.0,
                "max_score": 1.0,
            },
        )
        for index, event_id in enumerate(payload["item_event_refs"])
    ]


def _completion_pair(created, pack, *, completion_id, mode="forward", score_ratio=1.0):
    station = _ev(created, pack)
    station.payload_json["completion_id"] = completion_id
    station.event_id = f"station_{completion_id}"
    terminal = _terminal(
        created,
        pack,
        completion_id=completion_id,
        mode=mode,
        score_ratio=score_ratio,
    )
    return [*_items_for_terminal(terminal), terminal, station]


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


def test_exact_due_probe_resolution_requires_cycle_and_available_supply() -> None:
    projection = {
        "due": [
            {
                "pack_id": "F16",
                "probe_id": "without-cycle",
                "cycle_anchor": "",
                "retest_available": True,
            },
            {
                "pack_id": "F16",
                "probe_id": "without-supply",
                "cycle_anchor": "cycle-1",
                "retest_available": False,
            },
            {
                "pack_id": "F16",
                "probe_id": "canonical",
                "cycle_anchor": "cycle-1",
                "retest_available": True,
            },
        ]
    }

    assert resolve_due_review_probe(
        projection, pack_id="f16", probe_id="canonical"
    ) == projection["due"][2]
    assert resolve_due_review_probe(
        projection, pack_id="F16", probe_id="without-cycle"
    ) is None
    assert resolve_due_review_probe(
        projection, pack_id="F16", probe_id="without-supply"
    ) is None


def test_learned_yesterday_due_today_learned_today_not_due():
    out = build_review_due_projection(
        user_id="u1",
        events=[
            *_completion_pair("2026-07-03T22:00:00+08:00", "F16", completion_id="cmp_f16_1"),
            *_completion_pair("2026-07-04T08:00:00+08:00", "S05", completion_id="cmp_s05_1"),
        ],
        now_iso="2026-07-04T09:00:00+08:00")
    assert [d["pack_id"] for d in out["due"]] == ["F16"], "昨晚学的到期, 今早学的不到期"
    assert out["due"][0]["retest_available"] is False, "未完成 v3 人审签发时必须 fail-closed"
    assert out["learned_count"] == 2
    assert out["authority"] == "revalidation_queue"


def test_compiled_forward_completion_starts_next_calendar_day_review() -> None:
    terminal = _terminal(
        "2026-07-03T22:00:00+08:00",
        "F16",
        completion_id="cmp_f16_compiled",
        authority="compiled_html_server_rescore",
    )
    events = [*_items_for_terminal(terminal), terminal]

    before = build_review_due_projection(
        user_id="u1",
        events=events,
        now_iso="2026-07-03T23:59:00+08:00",
    )
    due = build_review_due_projection(
        user_id="u1",
        events=events,
        now_iso="2026-07-04T00:01:00+08:00",
    )

    assert before["due"] == []
    assert [item["pack_id"] for item in due["due"]] == ["F16"]


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
        events=[
            _lesson_viewed_ev("2026-07-03T21:00:00+08:00", "F16"),
            *_completion_pair("2026-07-04T09:00:00+08:00", "F16", completion_id="cmp_f16_1"),
        ],
        now_iso="2026-07-04T10:00:00+08:00")
    assert out["learned_count"] == 1


def test_no_completions_means_empty_not_all_green():
    """没学过任何站=空清单——旧假语义(六站天天全到期)的回归防线。"""
    out = build_review_due_projection(user_id="u1", events=[], now_iso="2026-07-04T09:00:00+08:00")
    assert out["due"] == [] and out["learned_count"] == 0


def test_ungreen_pack_completion_filtered_by_projection_gate():
    out = build_review_due_projection(
        user_id="u1",
        events=_completion_pair("2026-07-01T10:00:00+08:00", "X99", completion_id="cmp_x99_1"),
        now_iso="2026-07-04T09:00:00+08:00")
    assert out["due"] == [], "非绿灯站完成事件不产生到期(投影门 fail-closed)"


def test_verified_review_advances_to_existing_three_day_cadence():
    """第一次 canonical review 全对后按 DECAY_PROFILES 推进 3 天，不再天天到期。"""
    out = build_review_due_projection(
        user_id="u1",
        events=[
            *_completion_pair("2026-07-01T09:00:00+08:00", "F16", completion_id="cmp_f16_forward"),
            *_completion_pair(
                "2026-07-02T09:30:00+08:00",
                "F16",
                completion_id="cmp_f16_review_1",
                mode="review",
                score_ratio=1.0,
            ),
        ],
        now_iso="2026-07-04T10:00:00+08:00",
    )
    assert out["due"] == [], "成功复测后第 2 天不得再次到期"

    due = build_review_due_projection(
        user_id="u1",
        events=[
            *_completion_pair("2026-07-01T09:00:00+08:00", "F16", completion_id="cmp_f16_forward"),
            *_completion_pair(
                "2026-07-02T09:30:00+08:00",
                "F16",
                completion_id="cmp_f16_review_1",
                mode="review",
                score_ratio=1.0,
            ),
        ],
        now_iso="2026-07-05T10:00:00+08:00",
    )
    assert [item["pack_id"] for item in due["due"]] == ["F16"]
    assert due["due"][0]["review_status"] == "verified"


def test_review_success_ladder_uses_three_seven_fourteen_and_failure_resets():
    events = [
        *_completion_pair("2026-07-01T09:00:00+08:00", "F16", completion_id="fwd"),
        *_completion_pair("2026-07-02T09:00:00+08:00", "F16", completion_id="r1", mode="review"),
        *_completion_pair("2026-07-05T09:00:00+08:00", "F16", completion_id="r2", mode="review"),
    ]
    assert build_review_due_projection(
        user_id="u1", events=events, now_iso="2026-07-11T23:59:00+08:00"
    )["due"] == []
    assert build_review_due_projection(
        user_id="u1", events=events, now_iso="2026-07-12T09:01:00+08:00"
    )["due"][0]["successful_review_streak"] == 2

    failed = [
        *events,
        *_completion_pair(
            "2026-07-12T10:00:00+08:00",
            "F16",
            completion_id="r3_fail",
            mode="review",
            score_ratio=0.5,
        ),
    ]
    reset = build_review_due_projection(
        user_id="u1", events=failed, now_iso="2026-07-15T10:01:00+08:00"
    )
    assert reset["due"][0]["successful_review_streak"] == 0
    assert reset["due"][0]["review_status"] == "not_verified"


def test_station_without_matching_terminal_is_not_a_completion():
    out = build_review_due_projection(
        user_id="u1",
        events=[_ev("2026-07-03T09:00:00+08:00", "F16")],
        now_iso="2026-07-04T09:00:00+08:00",
    )
    assert out["due"] == []
    assert out["learned_count"] == 0


def test_variantless_green_pack_marks_retest_unavailable():
    """无变体池的绿灯站照常到期, 但 retest_available=False——客户端据此
    fail-closed 隐藏'换皮'承诺句(F05 为 wave1 如实跳过建池的绿灯站:
    其 pack 自检把机械扣分判断收归 R7 🔴, 结构性无池, 是本断言的稳定 fixture)。"""
    out = build_review_due_projection(
        user_id="u1",
        events=_completion_pair("2026-07-03T09:00:00+08:00", "F05", completion_id="cmp_f05_1"),
        now_iso="2026-07-04T09:00:00+08:00")
    assert [d["pack_id"] for d in out["due"]] == ["F05"]
    assert out["due"][0]["retest_available"] is False


def test_due_item_carries_state_for_probe_tier_selection():
    """due item 透传 state（fresh/weak/stable）——变体探针消费点2 据此在 D+3/D+7
    抽查（weak/stable）换 d1_probe 变体，D+1 首验（fresh）恒走 anchor MCQ。"""
    fresh = build_review_due_projection(
        user_id="u1",
        events=_completion_pair("2026-07-03T22:00:00+08:00", "F16", completion_id="cmp_f16_1"),
        now_iso="2026-07-04T09:00:00+08:00",
    )
    assert fresh["due"][0]["state"] == "fresh"

    verified = build_review_due_projection(
        user_id="u1",
        events=[
            *_completion_pair("2026-07-01T09:00:00+08:00", "F16", completion_id="fwd"),
            *_completion_pair(
                "2026-07-02T09:30:00+08:00",
                "F16",
                completion_id="r1",
                mode="review",
                score_ratio=1.0,
            ),
        ],
        now_iso="2026-07-05T10:00:00+08:00",
    )
    assert verified["due"][0]["state"] == "stable"

    weak = build_review_due_projection(
        user_id="u1",
        events=[
            *_completion_pair("2026-07-01T09:00:00+08:00", "F16", completion_id="fwd"),
            *_completion_pair(
                "2026-07-02T09:30:00+08:00",
                "F16",
                completion_id="r1f",
                mode="review",
                score_ratio=0.5,
            ),
        ],
        now_iso="2026-07-05T10:00:00+08:00",
    )
    assert weak["due"][0]["state"] == "weak"


def test_review_due_endpoint_flag_off_returns_empty(monkeypatch):
    """路由旗标关(默认) = fail-closed 空投影(enabled=false), 形状稳定不 404。"""
    import asyncio

    from deeptutor.api.routers import luban_lesson as router_module

    monkeypatch.delenv("LUBAN_REVIEW_MODULE_ENABLED", raising=False)
    out = asyncio.run(router_module.review_due(current_user=SimpleNamespace(user_id="u1")))
    assert out == {"due": [], "learned_count": 0, "authority": "revalidation_queue", "enabled": False}


def test_review_exam_date_distinguishes_known_empty_from_profile_failure() -> None:
    class _KnownEmpty:
        def get_profile(self, user_id: str) -> dict:
            return {"user_id": user_id, "exam_date": ""}

    class _Unavailable:
        def get_profile(self, user_id: str) -> dict:
            raise RuntimeError("profile backend offline")

    assert resolve_review_exam_date("u1", member_service=_KnownEmpty()) == ""
    with pytest.raises(ReviewHorizonUnavailable, match="member_profile_unavailable"):
        resolve_review_exam_date("u1", member_service=_Unavailable())


@pytest.mark.parametrize("profile", [None, [], "", 0])
def test_review_exam_date_rejects_non_object_profile(profile: object) -> None:
    class _InvalidProfile:
        def get_profile(self, user_id: str) -> object:
            return profile

    with pytest.raises(ReviewHorizonUnavailable, match="member_profile_unavailable"):
        resolve_review_exam_date("u1", member_service=_InvalidProfile())


def test_review_due_endpoint_flag_on_threads_exam_date(monkeypatch):
    """旗标开: 事件读自 learner_state service, exam_date 读自 member profile 并
    透传进投影(§6.1 地平线参数)。"""
    import asyncio

    from deeptutor.api.routers import luban_lesson as router_module
    import deeptutor.services.learner_state.service as ls_service

    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "true")

    class _FakeService:
        def list_learning_evidence_events(self, user_id, limit=None, since=None):
            assert limit is None
            assert since is None
            return _completion_pair("2026-07-03T09:00:00+08:00", "F16", completion_id="cmp_f16_1")

    monkeypatch.setattr(ls_service, "get_learner_state_service", lambda: _FakeService())
    monkeypatch.setattr(router_module, "_exam_date_for", lambda user_id: "2026-09-19")

    out = asyncio.run(router_module.review_due(current_user=SimpleNamespace(user_id="u1")))
    assert out["enabled"] is True
    assert out["authority"] == "revalidation_queue"
    assert [d["pack_id"] for d in out["due"]] == ["F16"]


def test_review_due_endpoint_maps_member_profile_failure_to_503(monkeypatch):
    import asyncio

    from fastapi import HTTPException

    from deeptutor.api.routers import luban_lesson as router_module
    import deeptutor.services.learner_state.service as ls_service

    class _FakeService:
        def list_learning_evidence_events(self, user_id, limit=None, since=None):
            return []

    def _unavailable(_user_id: str) -> str:
        raise ReviewHorizonUnavailable("member_profile_unavailable")

    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "true")
    monkeypatch.setattr(ls_service, "get_learner_state_service", lambda: _FakeService())
    monkeypatch.setattr(router_module, "_exam_date_for", _unavailable)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(router_module.review_due(current_user=SimpleNamespace(user_id="u1")))

    assert exc.value.status_code == 503
    assert exc.value.detail == "review horizon member profile unavailable"
