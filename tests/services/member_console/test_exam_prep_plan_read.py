"""计划页读面 get_exam_prep_plan 域测试（AI 学习计划体系 §7 P0 / 跑道计划 §2）。

聚焦验收：
- flag off → ``{"enabled": False}``（不组装、不 404）；
- flag on → 投影字段逐键透传（薄包装零改写）+ 收敛条附加字段；
- 无体检报告 → ``pass_readiness=None``（前端走「先做一次过线体检」引导，禁造数）；
- 有体检报告 → 四字段提取（带子只显示报告值，禁重估）；
- exam_countdown_days：exam_date 未设置 = None；已设置 = 确定性天数。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.services.member_console.service import (
    MemberConsoleService,
    _exam_countdown_days,
)

_GREEN = [
    {"pack_id": "N01", "title": "主体结构", "retest_available": True},
    {"pack_id": "N02", "title": "施工测量", "retest_available": True},
]

_READINESS_REPORT = {
    "schema_version": "p0a-v1",
    "generated_at": "2026-08-01T09:00:00Z",
    "estimated_score_band": "75-95",
    "pass_line": 96,
    "risk_band": "medium",
}

_TOPIC_REPORT = {
    "schema_version": "p0a-v1",
    "generated_at": "2026-08-02T09:00:00Z",
    "score_summary": {"score": 60},
}


class _LearnerStub:
    def read_compiled_learning_truth(self, user_id):
        return {}

    def list_learning_evidence_events(self, user_id, *, limit=None, since=None):
        return []


class _RepoStub:
    def __init__(self, rows):
        self._stub_rows = list(rows)

    def list_report_sessions(self, user_id, *, limit=20):
        return [dict(row) for row in self._stub_rows[:limit]]


def _service(monkeypatch, *, report_rows=(), member=None) -> MemberConsoleService:
    import deeptutor.services.luban_lesson as luban_lesson_pkg

    monkeypatch.setattr(luban_lesson_pkg, "list_green_lessons", lambda: [dict(g) for g in _GREEN])
    service = object.__new__(MemberConsoleService)
    service._get_learner_state_service = lambda: _LearnerStub()  # type: ignore[method-assign]
    service._assessment_session_repository = _RepoStub(report_rows)
    member_row = dict(member or {"user_id": "u1", "exam_date": "", "daily_target": 30})
    service._load_member_snapshot = lambda user_id: {"member": member_row}  # type: ignore[method-assign]
    service._read_learner_snapshot = (  # type: ignore[method-assign]
        lambda user_id, event_limit=100: SimpleNamespace(memory_events=[])
    )
    return service


@pytest.mark.unit
def test_flag_off_returns_disabled_without_assembly(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.delenv("LUBAN_EXAM_PREP_PLAN_ENABLED", raising=False)

    def _boom(**kwargs):  # pragma: no cover - 断言用
        raise AssertionError("flag off 不得组装")

    service._assemble_home_plan_inputs = _boom  # type: ignore[method-assign]
    assert service.get_exam_prep_plan("u1") == {"enabled": False}


@pytest.mark.unit
def test_flag_on_passes_projection_fields_through(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    monkeypatch.delenv("LUBAN_REVIEW_MODULE_ENABLED", raising=False)
    payload = service.get_exam_prep_plan("u1")
    assert payload["enabled"] is True
    # 投影字段逐键透传（薄包装：投影输出 + 收敛条附加字段，别无其他）。
    projection_keys = {
        "plan_policy_version",
        "horizon_days",
        "days",
        "supply_gaps",
        "next_step_arbitration",
        "source_status",
    }
    extra_keys = {"enabled", "pass_readiness", "exam_date", "exam_countdown_days"}
    assert set(payload.keys()) == projection_keys | extra_keys
    assert payload["horizon_days"] == 7
    assert len(payload["days"]) == 7
    day0 = payload["days"][0]
    assert set(day0.keys()) == {"date", "day_offset", "tasks", "planned_minutes"}
    head = day0["tasks"][0]
    for field in (
        "task",
        "mode",
        "why",
        "evidence_refs",
        "expected_time",
        "completion_condition",
        "retest_condition",
        "source_authority",
        "source_ref",
        "target_pack_id",
    ):
        assert field in head, f"任务字段 {field!r} 未透传"


@pytest.mark.unit
def test_no_report_yields_null_pass_readiness(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    payload = service.get_exam_prep_plan("u1")
    assert payload["pass_readiness"] is None
    assert payload["exam_countdown_days"] is None
    assert payload["exam_date"] == ""


@pytest.mark.unit
def test_latest_pass_readiness_report_wins_and_topic_reports_are_skipped(monkeypatch):
    # 新→旧排序：最新是普通专题报告（无带子）→ 跳过；取其后最近的体检报告。
    rows = [
        {"result_report_json": dict(_TOPIC_REPORT)},
        {"result_report_json": dict(_READINESS_REPORT)},
    ]
    service = _service(monkeypatch, report_rows=rows)
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    payload = service.get_exam_prep_plan("u1")
    assert payload["pass_readiness"] == {
        "estimated_score_band": "75-95",
        "pass_line": 96,
        "risk_band": "medium",
        "generated_at": "2026-08-01T09:00:00Z",
    }


@pytest.mark.unit
def test_exam_countdown_days_is_deterministic(monkeypatch):
    member = {"user_id": "u1", "exam_date": "2026-12-11", "daily_target": 30}
    service = _service(monkeypatch, member=member)
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    payload = service.get_exam_prep_plan("u1")
    assert isinstance(payload["exam_countdown_days"], int)
    assert payload["exam_date"] == "2026-12-11"
    # 纯函数确定性：固定 now → 固定天数；未设置/坏值 → None。
    assert _exam_countdown_days("2026-12-11", now_iso="2026-08-05T10:00:00+08:00") == 128
    assert _exam_countdown_days("", now_iso="2026-08-05T10:00:00+08:00") is None
    assert _exam_countdown_days("not-a-date", now_iso="2026-08-05T10:00:00+08:00") is None


@pytest.mark.unit
def test_repository_failure_degrades_readiness_to_null(monkeypatch):
    service = _service(monkeypatch)

    class _BrokenRepo:
        def list_report_sessions(self, user_id, *, limit=20):
            raise RuntimeError("assessment_sessions_unavailable")

    service._assessment_session_repository = _BrokenRepo()
    monkeypatch.setenv("LUBAN_EXAM_PREP_PLAN_ENABLED", "true")
    payload = service.get_exam_prep_plan("u1")
    assert payload["enabled"] is True
    assert payload["pass_readiness"] is None
