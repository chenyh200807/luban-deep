"""§3 home_next_step_projection：确定性优先级、四字段可审计、冷启动
fallback 非空（day-0 不白屏）、铁律（零写入纯函数 + 规则单点）。"""

from __future__ import annotations

from pathlib import Path

from deeptutor.services.learner_state.home_next_step_projection import (
    MODE_FALLBACK,
    MODE_LEARN,
    MODE_PRACTICE,
    MODE_REVIEW,
    build_home_next_step_projection,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_GREEN = [
    {"pack_id": "A01", "title": "检验批验收程序"},
    {"pack_id": "N01", "title": "网络计划关键线路"},
    {"pack_id": "F16", "title": "屋面防水起鼓割补"},
]
_REVIEW_ITEM = {
    "probe_id": "rvp_x1",
    "intent": {"concept_id": "N01", "concept_label": "网络计划", "training_intent_id": "rvp_x1"},
}
_ACTIVE_INTENT = {
    "training_intent_id": "ti_1",
    "concept_label": "防水工程",
    "target_pack_id": "F16",
}
_FOUR_FIELDS = ("mode", "source_authority", "source_ref", "reason")


def _lifecycle(states: dict[str, str]) -> dict:
    return {"packs": {pack: {"lifecycle_state": state} for pack, state in states.items()}}


def test_priority_review_beats_practice_beats_learn() -> None:
    # 三权威同时非空 → 到期复赢。
    step = build_home_next_step_projection(
        revalidation_items=[_REVIEW_ITEM],
        active_training_intents=[_ACTIVE_INTENT],
        pack_lifecycle=_lifecycle({"A01": "unlearned"}),
        green_lessons=_GREEN,
    )
    assert step["mode"] == MODE_REVIEW
    assert step["source_authority"] == "revalidation_queue"
    assert step["source_ref"] == "rvp_x1"
    assert step["target_pack_id"] == "N01"

    # 无到期复 → 活跃练赢。
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[_ACTIVE_INTENT],
        pack_lifecycle=_lifecycle({"A01": "unlearned"}),
        green_lessons=_GREEN,
    )
    assert step["mode"] == MODE_PRACTICE
    assert step["source_authority"] == "training_intent"
    assert step["source_ref"] == "ti_1"
    assert step["target_pack_id"] == "F16"


def test_legacy_active_intent_is_not_silently_dropped_when_target_is_missing() -> None:
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[{"training_intent_id": "legacy-ti", "concept_label": "旧处方"}],
        pack_lifecycle={"packs": {}},
        green_lessons=_GREEN,
    )

    assert step["mode"] == MODE_PRACTICE
    assert step["source_ref"] == "legacy-ti"
    assert step["target_pack_id"] == ""

    # 只剩学 → 第一个 未学∧绿灯。
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[],
        pack_lifecycle=_lifecycle({"A01": "practiced", "N01": "unlearned"}),
        green_lessons=_GREEN,
    )
    assert step["mode"] == MODE_LEARN
    assert step["source_ref"] == "N01"


def test_cold_start_fallback_is_never_blank() -> None:
    # 冷启动零证据：前三臂全空 → fallback 必非空（day-0 不白屏），群体理由。
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[],
        pack_lifecycle={"packs": {}},
        green_lessons=_GREEN,
    )
    # 冷启动是全确定性的：零证据 → 绿灯包全「未学」→ 必然 learn 臂
    # （评审项 2：钉死，析取会遮蔽误入 fallback 的回归）。
    assert step["mode"] == MODE_LEARN
    assert step["source_authority"] == "pack_lifecycle_projection"
    assert step["source_ref"] == "A01"
    assert step["reason"]


def test_all_learned_falls_back_to_registry_first_green() -> None:
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[],
        pack_lifecycle=_lifecycle({"A01": "mastered", "N01": "practiced", "F16": "practiced"}),
        green_lessons=_GREEN,
    )
    assert step["mode"] == MODE_FALLBACK
    assert step["source_authority"] == "pack_manifest.registry_order"
    assert step["source_ref"] == "A01"
    assert "第一站" in step["reason"]


def test_every_arm_emits_all_four_audit_fields() -> None:
    cases = [
        dict(revalidation_items=[_REVIEW_ITEM], active_training_intents=[], pack_lifecycle={}, green_lessons=_GREEN),
        dict(revalidation_items=[], active_training_intents=[_ACTIVE_INTENT], pack_lifecycle={}, green_lessons=_GREEN),
        dict(revalidation_items=[], active_training_intents=[], pack_lifecycle=_lifecycle({"A01": "unlearned"}), green_lessons=_GREEN),
        dict(revalidation_items=[], active_training_intents=[], pack_lifecycle=_lifecycle({"A01": "mastered", "N01": "mastered"}), green_lessons=_GREEN),
    ]
    for kwargs in cases:
        step = build_home_next_step_projection(**kwargs)
        for field in _FOUR_FIELDS:
            assert field in step, f"missing audit field {field} in {step}"
        assert step["mode"] != "unavailable"


def test_no_green_supply_is_honest_unavailable() -> None:
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[],
        pack_lifecycle={},
        green_lessons=[],
    )
    assert step["mode"] == "unavailable"


def test_module_is_pure_no_ledger_write_no_intent_generation() -> None:
    # 铁律源码 pin（廉价 tripwire，保留）：禁写 ledger / 禁生成 training_intent /
    # 禁改 revalidation。
    source = (
        _REPO_ROOT / "deeptutor/services/learner_state/home_next_step_projection.py"
    ).read_text(encoding="utf-8")
    assert "append_memory_event" not in source
    assert "build_learning_training_intent" not in source
    assert "write_" not in source
    # 只读组合：不 import 任何 service 单例。
    assert "get_learner_state_service" not in source

    # 行为级不变异断言（评审项 3：grep 只是 tripwire，真权威是行为）：
    # sentinel 输入 deepcopy 前后逐字节相同 → 仲裁器不改 caller 的数据。
    import copy

    arm_inputs = [
        # 全供给（review 臂早退路径）与 learn 臂路径都要证明不变异。
        dict(
            revalidation_items=[copy.deepcopy(_REVIEW_ITEM)],
            active_training_intents=[copy.deepcopy(_ACTIVE_INTENT)],
            pack_lifecycle=_lifecycle({"A01": "unlearned"}),
            green_lessons=copy.deepcopy(_GREEN),
        ),
        dict(
            revalidation_items=[],
            active_training_intents=[],
            pack_lifecycle=_lifecycle({"A01": "practiced", "N01": "unlearned"}),
            green_lessons=copy.deepcopy(_GREEN),
        ),
    ]
    for kwargs in arm_inputs:
        snapshot = copy.deepcopy(kwargs)
        build_home_next_step_projection(**kwargs)
        assert kwargs == snapshot, "build_home_next_step_projection must not mutate its inputs"


class _FakeEnvStore:
    """env_flag 经 get_env_store 先读磁盘 .env（磁盘值遮蔽 os.environ），
    monkeypatch os.environ 清不掉——按仓内既有范式
    （tests/services/config/test_runtime_env.py）stub get_env_store 单一读点。"""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def _stub_env_store(monkeypatch, values: dict[str, str]) -> None:
    store = _FakeEnvStore({"DEEPTUTOR_ENV": "local", **values})
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: store,
    )


def test_home_dashboard_gates_next_step_behind_flag(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from deeptutor.services.member_console.service import MemberConsoleService

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    # 评审项 1：unset 用例 env store 里无 flag（get 返回 ""）——不再依赖开发机
    # 磁盘 .env 状态；os.environ 的 delenv/setenv 对 env_store 是无效操作。
    _stub_env_store(monkeypatch, {})
    service.get_profile("student_next_step")

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            return SimpleNamespace(profile={}, progress={}, summary="", memory_events=[])

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            return []

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("student_next_step")
    assert "next_step" not in dashboard  # flag 默认 off

    _stub_env_store(monkeypatch, {"DEEPTUTOR_HOME_NEXT_STEP_ENABLED": "1"})
    dashboard = service.get_home_dashboard("student_next_step")
    step = dashboard.get("next_step") or {}
    # 冷启动零证据 → 绿灯注册表全「未学」→ 必然 learn 臂（评审项 2 同款钉死）。
    assert step.get("mode") == MODE_LEARN
    assert step.get("source_authority") == "pack_lifecycle_projection"
    for field in _FOUR_FIELDS:
        assert step.get(field) is not None


def test_learn_arm_respects_prerequisite_order_k01_after_n01() -> None:
    # §4-2 章序陷阱：K01(432章)在字母/章节序上先于 N01(433章)，但 N01
    # (网络计划定量求解)是 K01(索赔工期臂)的前置——两者都未学时先推 N01。
    # 不设前置锁：只影响排序，可跳站不变。
    green = [
        {"pack_id": "K01", "title": "索赔成立与计算"},
        {"pack_id": "N01", "title": "网络计划关键线路"},
    ]
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[],
        pack_lifecycle=_lifecycle({"K01": "unlearned", "N01": "unlearned"}),
        green_lessons=green,
    )
    assert step["mode"] == MODE_LEARN
    assert step["source_ref"] == "N01", "prerequisite N01 must come before K01"

    # 前置已学（practiced）→ 不再挡 K01。
    step = build_home_next_step_projection(
        revalidation_items=[],
        active_training_intents=[],
        pack_lifecycle=_lifecycle({"K01": "unlearned", "N01": "practiced"}),
        green_lessons=green,
    )
    assert step["source_ref"] == "K01"


def test_home_next_step_wires_real_intents_claims_and_verified_suppression(
    tmp_path, monkeypatch
) -> None:
    # Codex SEV-1:practice 臂曾被硬编码 active_training_intents=[] 断供
    # (dormant authority),claims=[] 使 mastered 语义被改写;且首页 queue
    # 没传 prescription_outcomes(已验证 probe 会复活)。接线断言钉死三条输入。
    from types import SimpleNamespace

    from deeptutor.services.learner_state import home_next_step_projection as hns
    from deeptutor.services.learner_state import pack_lifecycle_projection as plp
    from deeptutor.services.learner_state import revalidation_queue as rq
    from deeptutor.services.member_console.service import MemberConsoleService

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("student_wired")

    practice_event = SimpleNamespace(
        event_id="rx_evt_1",
        memory_kind="learning_evidence",
        source_feature="construction_grading",
        source_id="turn:rx1",
        dedupe_key="rx_evt_1",
        created_at="2026-07-03T10:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "question_id": "q_rx_1",
            "training_intent_id": "ti_active_1",
            "prescription_phase": "discovery_probe",
            "score_awarded": 0.0,
            "max_score": 1.0,
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            return SimpleNamespace(
                profile={}, progress={}, summary="", memory_events=[practice_event]
            )

        def read_compiled_learning_truth(self, user_id: str):
            return {
                "weak_points": [
                    {
                        "concept_id": "1A433000-B041",
                        "evidence_level": "L2_real_retest",
                        "decay_state": "active",
                    }
                ]
            }

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            return []

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    captured: dict = {}

    def _capture_arbiter(**kwargs):
        captured["arbiter"] = kwargs
        return {"mode": "practice_active", "source_authority": "training_intent", "source_ref": "ti_active_1", "reason": "x"}

    def _capture_queue(**kwargs):
        captured["queue"] = kwargs
        return {"items": [], "source_status": {"candidate_count": 0}}

    def _capture_lifecycle(**kwargs):
        captured["lifecycle"] = kwargs
        return {"packs": {}}

    monkeypatch.setattr(hns, "build_home_next_step_projection", _capture_arbiter)
    monkeypatch.setattr(rq, "build_revalidation_queue_projection", _capture_queue)
    monkeypatch.setattr(plp, "project_pack_lifecycle", _capture_lifecycle)

    step = service._build_home_next_step(
        learner_user_id="student_wired",
        snapshot=_FakeLearnerStateService().read_snapshot("student_wired"),
    )
    assert step["mode"] == "practice_active"

    # ①practice 臂供给:未 verified 的处方 outcome 必须进 active_training_intents
    active = captured["arbiter"]["active_training_intents"]
    assert any(item.get("training_intent_id") == "ti_active_1" for item in active)
    # ②claims 供给:compiled truth 的 weak_points 必须喂 lifecycle(mastered 语义可达)
    assert captured["lifecycle"]["claims"], "claims must come from read_compiled_learning_truth"
    assert captured["lifecycle"]["claims"][0]["evidence_level"] == "L2_real_retest"
    # ③首页复验臂必须带已验证抑制(与 report 路径同口径)
    assert "prescription_outcomes" in captured["queue"]
    assert any(
        item.get("training_intent_id") == "ti_active_1"
        for item in captured["queue"]["prescription_outcomes"]
    )
