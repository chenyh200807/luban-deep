"""病C（窗口粒度错配）：首页/雷达/章节盘的 learner 事件读窗必须容得下
「满天 lesson_viewed + 判分证据」的混合流——20 窗曾被 80 条/天的
lesson_viewed 灌满，把判分证据挤出窗外，掌握度回退、pack 从 practiced
退 exposed。窗容量 = _HOME_LEARNER_EVENT_LIMIT（单一命名常量，两处引用）。
"""
from __future__ import annotations

from types import SimpleNamespace

from deeptutor.services.member_console.service import (
    _HOME_LEARNER_EVENT_LIMIT,
    MemberConsoleService,
)

_CHAPTER = "施工组织设计"


def _lesson_event(index: int) -> SimpleNamespace:
    pack_id = f"P{index:02d}"
    return SimpleNamespace(
        event_id=f"lesson_{index}",
        memory_kind="learning_evidence",
        source_feature="luban_lesson",
        source_id=f"lesson_viewed:{pack_id}:lesson",
        dedupe_key=f"lesson_viewed:u1:{pack_id}:lesson:2026-07-04",
        created_at="2026-07-04T09:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "learning_signal_type": "lesson_viewed",
            "pack_id": pack_id,
            "watched_stage": "lesson",
            "evidence_level": "exposed",
            "quality": {"progress_countable": False},
        },
    )


def _grading_event(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        event_id=f"grading_{index}",
        memory_kind="learning_evidence",
        source_feature="construction_grading",
        source_id=f"turn:q_{index}",
        dedupe_key=f"grading:u1:q_{index}",
        created_at="2026-07-04T10:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "question_id": f"q_{index}",
            "is_correct": True,
            "score_awarded": 1.0,
            "max_score": 1.0,
            "canonical_topic": {"label": _CHAPTER},
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )


def _mixed_events() -> list[SimpleNamespace]:
    # 80 条 lesson_viewed（40 pack × 2 幕的满天场景）+ 5 条判分证据。
    return [_lesson_event(i) for i in range(80)] + [_grading_event(i) for i in range(5)]


def test_window_constant_holds_the_mixed_day() -> None:
    assert _HOME_LEARNER_EVENT_LIMIT == 100
    assert len(_mixed_events()) <= _HOME_LEARNER_EVENT_LIMIT


def test_mastery_evidence_read_uses_shared_window_constant() -> None:
    captured: dict = {}
    events = _mixed_events()

    class _LearnerStub:
        def read_snapshot(self, user_id, *, event_limit):
            captured["event_limit"] = event_limit
            # 语义同真实 read_snapshot：窗只保最近 event_limit 条。
            return SimpleNamespace(memory_events=events[-event_limit:])

    service = object.__new__(MemberConsoleService)
    service._get_learner_state_service = lambda: _LearnerStub()  # type: ignore[method-assign]

    windowed = service._mastery_evidence_events({"user_id": "u1"}, "u1")
    assert captured["event_limit"] == _HOME_LEARNER_EVENT_LIMIT
    grading_in_window = [
        event for event in windowed if event.source_feature == "construction_grading"
    ]
    # 20 窗时这里是 0（判分证据被 80 条 lesson_viewed 挤出）；100 窗必须全在。
    assert len(grading_in_window) == 5


def test_blend_sees_all_grading_evidence_behind_lesson_flood() -> None:
    from deeptutor.services.learner_state.learning_report_read_model import (
        aggregate_attempts_by_label,
    )

    events = _mixed_events()
    attempts = aggregate_attempts_by_label(events)
    # 窗后语义过滤：lesson_viewed（progress_countable=false）不进 attempts，
    # 5 条判分证据一条不少。
    assert len(attempts.get(_CHAPTER) or []) == 5

    items = [{"name": _CHAPTER, "mastery": 10}]
    blended = MemberConsoleService._blend_mastery_with_evidence(
        items, evidence_events=events
    )
    assert blended[0]["name"] == _CHAPTER
    # 5 条全对判分证据必须驱动掌握分离开 legacy 值（证据没被挤出）。
    assert blended[0]["mastery"] != 10


class _EnvStoreStub:
    def __init__(self, values: dict):
        self._values = values

    def get(self, name, default=""):
        return self._values.get(name, default)


def _stub_flag(monkeypatch, enabled: bool) -> None:
    # 本仓地雷:env_store 读磁盘 .env,monkeypatch os.environ 清不掉——
    # flag 测试必须 stub get_env_store 汇点。
    import deeptutor.services.config.env_store as env_store_module

    monkeypatch.setattr(
        env_store_module,
        "get_env_store",
        lambda: _EnvStoreStub(
            {"DEEPTUTOR_HOME_NEXT_STEP_ENABLED": "true" if enabled else "false"}
        ),
    )


def test_mastery_blend_gated_by_home_next_step_flag(monkeypatch) -> None:
    # C-flag(owner 拍板):DEEPTUTOR_HOME_NEXT_STEP_ENABLED = home 生命周期
    # 融合面总开关。off = 旧静态分(blend 不生效);on = blend 生效。
    service = object.__new__(MemberConsoleService)
    member = {"chapter_mastery": {"ch_1": {"name": _CHAPTER, "mastery": 10}}}
    events = _mixed_events()

    _stub_flag(monkeypatch, enabled=False)
    off_items = service._report_mastery_items(member, evidence_events=events)
    assert [item["mastery"] for item in off_items if item["name"] == _CHAPTER] == [10]

    _stub_flag(monkeypatch, enabled=True)
    on_items = service._report_mastery_items(member, evidence_events=events)
    on_score = next(item["mastery"] for item in on_items if item["name"] == _CHAPTER)
    assert on_score != 10  # 5 条全对判分证据驱动 blend 离开 legacy 静态分
