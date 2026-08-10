"""composition root 收权 + shadow parity 机器验收（计划体系 §3.1 权威点 1 / §7）。

- flag off = 逐字节旧四臂行为（不算不 serve 新计划）；
- flag on ∧ 无 plan_preference 事件 → serve 的首任务与旧四臂输出**逐字段相等**
  （shadow parity，同一次组装内双算）；
- 同证据 fixture 重放 → 同一 next_step（确定性，服务层）；
- 计划空 → fail-closed 回旧仲裁（不 serve 空卡）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.member_console.service import MemberConsoleService

_GREEN = [
    {"pack_id": "N01", "title": "主体结构", "retest_available": True},
    {"pack_id": "N02", "title": "施工测量", "retest_available": True},
]


class _LearnerStub:
    def read_compiled_learning_truth(self, user_id):
        return {}

    def list_learning_evidence_events(self, user_id, *, limit=None, since=None):
        return []


def _service(monkeypatch) -> MemberConsoleService:
    import deeptutor.services.luban_lesson as luban_lesson_pkg

    monkeypatch.setattr(luban_lesson_pkg, "list_green_lessons", lambda: [dict(g) for g in _GREEN])
    service = object.__new__(MemberConsoleService)
    service._get_learner_state_service = lambda: _LearnerStub()  # type: ignore[method-assign]
    return service


def _next_step(service, events=()):
    snapshot = SimpleNamespace(memory_events=list(events))
    return service._build_home_next_step(
        learner_user_id="u1",
        snapshot=snapshot,
        exam_date_iso="",
        daily_target_minutes=30,
    )


@pytest.mark.unit
def test_flag_on_without_preferences_serves_field_identical_head(monkeypatch):
    """机器验收：flag on ∧ 无 plan_preference → plan 首任务与旧四臂逐字段相等。"""
    service = _service(monkeypatch)
    monkeypatch.delenv("LUBAN_EXAM_PREP_PLAN_ENABLED", raising=False)
    monkeypatch.delenv("LUBAN_REVIEW_MODULE_ENABLED", raising=False)
    legacy = _next_step(service)
    assert legacy["mode"] == "learn_next", "fixture 预期: 零证据 → learn 臂"

    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    served = _next_step(service)
    for key, value in legacy.items():
        assert served[key] == value, f"shadow parity broken on field {key!r}"
    # serve 的是计划任务信封（多出计划字段，不少四臂字段）
    assert served["task"] == "learn_station"
    assert "completion_condition" in served and "why" in served


@pytest.mark.unit
def test_flag_off_is_byte_identical_legacy_arbitration(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.delenv("LUBAN_EXAM_PREP_PLAN_ENABLED", raising=False)
    step = _next_step(service)
    assert set(step.keys()) == {"mode", "source_authority", "source_ref", "target_pack_id", "reason"}


@pytest.mark.unit
def test_same_evidence_replays_same_next_step(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    assert _next_step(service) == _next_step(service)


@pytest.mark.unit
def test_empty_plan_fails_closed_to_legacy(monkeypatch):
    """供给面全空 → 计划无任务 → serve 旧仲裁空态（unavailable 哨兵由上层过滤）。"""
    import deeptutor.services.luban_lesson as luban_lesson_pkg

    service = _service(monkeypatch)
    monkeypatch.setattr(luban_lesson_pkg, "list_green_lessons", lambda: [])
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    step = _next_step(service)
    assert step["mode"] == "unavailable"
