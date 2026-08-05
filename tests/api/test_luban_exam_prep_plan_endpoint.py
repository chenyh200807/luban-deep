"""GET /api/v1/luban/exam-prep-plan 端点测试——薄包装透传 + flag off 语义。"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from deeptutor.api.routers import luban_lesson


def _call(payload: dict, captured: dict) -> dict:
    import deeptutor.services.member_console as member_console_pkg

    class _Service:
        def get_exam_prep_plan(self, user_id: str) -> dict:
            captured["user_id"] = user_id
            return payload

    original = member_console_pkg.get_member_console_service
    member_console_pkg.get_member_console_service = lambda: _Service()
    try:
        return asyncio.run(
            luban_lesson.exam_prep_plan(SimpleNamespace(user_id="user-1"))
        )
    finally:
        member_console_pkg.get_member_console_service = original


@pytest.mark.unit
def test_endpoint_passes_service_payload_through_unmodified() -> None:
    payload = {
        "enabled": True,
        "plan_policy_version": "exam_prep_plan_policy_v1",
        "horizon_days": 7,
        "days": [{"date": "2026-08-05", "day_offset": 0, "tasks": [], "planned_minutes": 0}],
        "supply_gaps": [],
        "next_step_arbitration": {"mode": "learn_next"},
        "source_status": {"authority": "exam_prep_plan_projection"},
        "pass_readiness": None,
        "exam_date": "",
        "exam_countdown_days": None,
    }
    captured: dict = {}
    result = _call(payload, captured)
    assert result == payload, "router 必须原样透传（零业务逻辑）"
    assert captured["user_id"] == "user-1", "owner-scope: user_id 只取鉴权上下文"


@pytest.mark.unit
def test_endpoint_flag_off_shape_is_enabled_false_not_404() -> None:
    result = _call({"enabled": False}, {})
    assert result == {"enabled": False}
