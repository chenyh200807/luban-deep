"""exam_prep_plan_projection 域测试（计划体系 §7 机器验收的纯函数层）。

- shadow parity：无 plan_preference 时，计划 day0 首任务与旧四臂输出逐字段相等；
- 确定性：同证据 fixture 同 now_iso 重放产生同一计划（deep equality）；
- 四臂语义保留：review 占位 > practice 承接 > learn 学序推进；
- 意志叠加：defer 后移一天且不动证据结论；time_budget 重排密度；
- 供给硬过滤：无 retest 供给的 intent 进 supply_gaps，不排假任务。
"""
from __future__ import annotations

from types import SimpleNamespace

from deeptutor.services.learner_state.exam_prep_plan import (
    PLAN_POLICY_VERSION,
    build_exam_prep_plan_projection,
    plan_preferences_from_events,
)
from deeptutor.services.learner_state.home_next_step_projection import (
    build_home_next_step_projection,
)

_NOW = "2026-08-05T09:00:00+08:00"


def _green(pack_id: str, title: str, retest: bool = True) -> dict:
    return {"pack_id": pack_id, "title": title, "retest_available": retest}


def _fixture(**overrides) -> dict:
    """固定证据 fixture：到期复 1 项 + 活跃练 1 项 + 未学站 2 个。"""
    inputs = {
        "now_iso": _NOW,
        "days": 7,
        "review_due_items": [
            {
                "pack_id": "F16",
                "title": "屋面防水",
                "probe_id": "rvp_u1_F16_code_application_",
                "due_at": "2026-08-05T00:00:00+08:00",
                "cycle_anchor": "cycle-1",
                "retest_available": True,
            }
        ],
        "review_horizon": {
            "horizon_days": 7,
            "days": [
                {"date": "2026-08-05", "day_offset": 0, "items": [
                    {
                        "probe_id": "rvp_u1_F16_code_application_",
                        "due_at": "2026-08-05T00:00:00+08:00",
                        "status": "queued",
                        "evidence_refs": ["evt_f16_miss"],
                        "intent": {"concept_id": "F16", "concept_label": "屋面防水"},
                    }
                ]},
                {"date": "2026-08-07", "day_offset": 2, "items": [
                    {
                        "probe_id": "rvp_u1_S05_code_application_",
                        "due_at": "2026-08-07T10:00:00+08:00",
                        "status": "queued",
                        "evidence_refs": ["evt_s05_miss"],
                        "intent": {"concept_id": "S05", "concept_label": "地基处理"},
                    }
                ]},
            ],
        },
        "active_training_intents": [
            {
                "training_intent_id": "ti_x03",
                "target_pack_id": "X03",
                "concept_label": "模板支架",
                "evidence_refs": ["evt_x03_miss"],
            }
        ],
        "pack_lifecycle": {"packs": {
            "F16": {"lifecycle_state": "practiced"},
            "X03": {"lifecycle_state": "practiced"},
        }},
        "green_lessons": [
            _green("F16", "屋面防水"),
            _green("X03", "模板支架"),
            _green("N01", "主体结构"),
            _green("N02", "施工测量"),
        ],
        "plan_preferences": None,
        "daily_target_minutes": 30,
    }
    inputs.update(overrides)
    return inputs


def test_shadow_parity_head_task_equals_four_arm_output_field_by_field() -> None:
    """机器验收：无 plan_preference 时计划首任务 ⊇ 旧四臂输出（逐字段相等）。"""
    inputs = _fixture()
    old = build_home_next_step_projection(
        review_due_items=inputs["review_due_items"],
        active_training_intents=inputs["active_training_intents"],
        pack_lifecycle=inputs["pack_lifecycle"],
        green_lessons=inputs["green_lessons"],
    )
    plan = build_exam_prep_plan_projection(**inputs)
    head = plan["days"][0]["tasks"][0]
    for key, value in old.items():
        assert head[key] == value, f"shadow parity broken on field {key!r}"
    # 计划信封字段齐备（§3.1 输出契约）
    for key in ("task", "source_authority", "evidence_refs", "expected_time",
                "completion_condition", "retest_condition", "why"):
        assert key in head


def test_parity_holds_for_practice_and_learn_heads() -> None:
    # 无到期复 → practice 承接
    inputs = _fixture(review_due_items=[], review_horizon=None)
    old = build_home_next_step_projection(
        review_due_items=[],
        active_training_intents=inputs["active_training_intents"],
        pack_lifecycle=inputs["pack_lifecycle"],
        green_lessons=inputs["green_lessons"],
    )
    assert old["mode"] == "practice_active"
    head = build_exam_prep_plan_projection(**inputs)["days"][0]["tasks"][0]
    for key, value in old.items():
        assert head[key] == value
    # 无到期复无活跃练 → learn_next 学序推进
    inputs2 = _fixture(review_due_items=[], review_horizon=None, active_training_intents=[])
    old2 = build_home_next_step_projection(
        review_due_items=[],
        active_training_intents=[],
        pack_lifecycle=inputs2["pack_lifecycle"],
        green_lessons=inputs2["green_lessons"],
    )
    assert old2["mode"] == "learn_next"
    head2 = build_exam_prep_plan_projection(**inputs2)["days"][0]["tasks"][0]
    for key, value in old2.items():
        assert head2[key] == value


def test_same_evidence_replays_same_plan_deterministically() -> None:
    """机器验收：同证据集固定 now_iso 重放产生同一计划。"""
    assert build_exam_prep_plan_projection(**_fixture()) == build_exam_prep_plan_projection(**_fixture())


def test_seven_day_rollout_review_priority_and_horizon_consumption() -> None:
    plan = build_exam_prep_plan_projection(**_fixture())
    assert plan["plan_policy_version"] == PLAN_POLICY_VERSION
    assert len(plan["days"]) == 7
    assert plan["days"][0]["date"] == "2026-08-05"
    day0_modes = [t["mode"] for t in plan["days"][0]["tasks"]]
    # review 占位 > practice 承接 > learn（预算 30 分钟内: 5+8+12=25）
    assert day0_modes[:3] == ["review_due", "practice_active", "learn_next"]
    # day2 复习任务来自 horizon 读面（不自算到期）
    day2 = plan["days"][2]["tasks"]
    assert day2 and day2[0]["mode"] == "review_due"
    assert day2[0]["source_ref"] == "rvp_u1_S05_code_application_"
    assert day2[0]["evidence_refs"] == ["evt_s05_miss"]
    # day0 review 证据链从 horizon 同 probe 富化
    assert plan["days"][0]["tasks"][0]["evidence_refs"] == ["evt_f16_miss"]


def test_supply_unavailable_intent_goes_to_gap_not_fake_task() -> None:
    inputs = _fixture(
        active_training_intents=[
            {"training_intent_id": "ti_dead", "target_pack_id": "Z99", "concept_label": "停发站"}
        ],
    )
    plan = build_exam_prep_plan_projection(**inputs)
    all_refs = [t["source_ref"] for d in plan["days"] for t in d["tasks"]]
    assert "ti_dead" not in all_refs
    assert plan["supply_gaps"] == [{
        "kind": "practice_retest",
        "source_ref": "ti_dead",
        "target_pack_id": "Z99",
        "gap_reason": "practice_supply_unavailable",
    }]


def test_defer_preference_pushes_task_to_next_day() -> None:
    prefs = {"pins": [], "deferred_targets": ["X03"], "time_budget_minutes": 0}
    plan = build_exam_prep_plan_projection(**_fixture(plan_preferences=prefs))
    day0_targets = [t["target_pack_id"] for t in plan["days"][0]["tasks"]]
    day1_targets = [t["target_pack_id"] for t in plan["days"][1]["tasks"]]
    assert "X03" not in day0_targets, "defer 的任务不得占 day0"
    assert "X03" in day1_targets, "defer 后移一天（给替补，不惩罚）"
    assert plan["source_status"]["preference_applied"]["defer"] == 1
    # 意志不动证据结论：review 占位仍在
    assert plan["days"][0]["tasks"][0]["mode"] == "review_due"


def test_pin_preference_promotes_task_with_visible_consequence() -> None:
    prefs = {"pins": ["N01"], "deferred_targets": [], "time_budget_minutes": 0}
    plan = build_exam_prep_plan_projection(**_fixture(plan_preferences=prefs))
    head = plan["days"][0]["tasks"][0]
    assert head["target_pack_id"] == "N01"
    assert head.get("pinned") is True
    assert "顺延" in head.get("consequence", ""), "红线：不静默覆盖，后果可见"


def test_time_budget_preference_reshapes_daily_density() -> None:
    prefs = {"pins": [], "deferred_targets": [], "time_budget_minutes": 5}
    plan = build_exam_prep_plan_projection(**_fixture(plan_preferences=prefs))
    # 预算 5 分钟：review 占位后即满（复习优先占位约束 > 预算）
    day0 = plan["days"][0]["tasks"]
    assert [t["mode"] for t in day0] == ["review_due"]
    assert plan["source_status"]["daily_budget_minutes"] == 5
    # 未排任务顺延到后续天，不消失
    later = [t["mode"] for d in plan["days"][1:] for t in d["tasks"]]
    assert "practice_active" in later


def test_plan_preferences_from_events_extraction() -> None:
    def _ev(signal, created="2026-08-05T08:00:00+08:00", **payload):
        return SimpleNamespace(
            created_at=created,
            payload_json={"learning_signal_type": signal, **payload},
        )

    events = [
        _ev("pin", concept_id="n01"),
        _ev("defer", concept_id="x03"),                          # 当日非复习 defer
        _ev("defer", concept_id="f16", probe_id="rvp_x"),        # 复习 defer → declined 机制，不在此
        _ev("defer", concept_id="s05", created="2026-08-04T08:00:00+08:00"),  # 隔日失效
        _ev("time_budget", time_budget_minutes=45),
        _ev("time_budget", time_budget_minutes=60),               # 最后一条生效
        _ev("subjective_focus", concept_id="k1"),                 # 非意志族，无视
    ]
    prefs = plan_preferences_from_events(events, now_iso=_NOW)
    assert prefs == {
        "pins": ["N01"],
        "deferred_targets": ["X03"],
        "time_budget_minutes": 60,
    }


def test_policy_v2_interleaves_practice_and_learn_within_days() -> None:
    """policy_v2(owner 2026-08-08「别太线性」):practice/learn 轮转交错,
    不再整天同臂连排;族内保各自权威序。"""

    inputs = _fixture(
        review_due_items=[],
        review_horizon=None,
        active_training_intents=[
            {"training_intent_id": "ti_a01", "target_pack_id": "F16", "concept_label": "体检失分点·屋面防水"},
            {"training_intent_id": "ti_x03", "target_pack_id": "X03", "concept_label": "体检失分点·模板支架"},
        ],
        pack_lifecycle={"packs": {}},
    )
    plan = build_exam_prep_plan_projection(**inputs)
    assert plan["plan_policy_version"] == "exam_prep_plan_policy_v2"
    flat = [t["task"] for d in plan["days"] for t in d["tasks"]]
    # 前四个任务 practice/learn 交错(首任务=四臂 practice 承接,第二个即学习站)
    assert flat[0] == "practice_retest"
    assert flat[1] == "learn_station"
    assert flat[2] == "practice_retest"
    assert flat[3] == "learn_station"
    # 体检来源在 reason 里可解释
    first = plan["days"][0]["tasks"][0]
    assert "体检失分点" in first["reason"] or "体检失分点" in first["why"]
