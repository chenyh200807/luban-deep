from __future__ import annotations

import asyncio

from deeptutor.services.tutor_state.service import UserTutorStateService


class _PathServiceStub:
    def __init__(self, root):
        self._root = root

    def get_tutor_state_root(self):
        return self._root / "tutor_state"


class _FakeMemberService:
    def get_profile(self, user_id: str):
        return {
            "user_id": user_id,
            "display_name": "陈同学",
            "tier": "vip",
            "status": "active",
            "difficulty_preference": "medium",
            "explanation_style": "detailed",
            "daily_target": 30,
            "review_reminder": True,
            "level": 7,
            "points": 240,
            "exam_date": "2026-09-19",
            "focus_topic": "地基基础承载力",
        }


def _make_service(tmp_path):
    return UserTutorStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_FakeMemberService(),
    )


def test_user_tutor_state_build_context_seeds_profile_persona_and_memory(tmp_path) -> None:
    service = _make_service(tmp_path)

    context = service.build_context("student_demo", language="zh")
    profile_text = (tmp_path / "tutor_state" / "student_demo" / "PROFILE.md").read_text(encoding="utf-8")
    persona_text = (tmp_path / "tutor_state" / "student_demo" / "PERSONA.md").read_text(encoding="utf-8")

    assert "专属 Tutor 上下文" in context
    assert "地基基础承载力" in context
    assert "专属 TutorBot" in context
    assert "当前称呼：陈同学" in profile_text
    assert "备考紧迫度" in profile_text
    assert "优先让学员感觉自己被看见" in persona_text
    assert "心理支持策略" in persona_text
    assert "默认可自然使用称呼“陈同学”开场" in persona_text
    assert (tmp_path / "tutor_state" / "student_demo" / "PROFILE.md").exists()
    assert (tmp_path / "tutor_state" / "student_demo" / "PERSONA.md").exists()
    assert (tmp_path / "tutor_state" / "student_demo" / "MEMORY.md").exists()


async def _rewrite_stream(**_kwargs):
    yield (
        "## Current Focus\n"
        "- 地基基础承载力\n\n"
        "## Progress Signals\n"
        "- 已完成一轮概念梳理。\n\n"
        "## Misconceptions To Watch\n"
        "- 容易混淆承载力与沉降控制。\n\n"
        "## Next Follow-Up\n"
        "- 下一次继续做两道案例题。"
    )


def test_user_tutor_state_refresh_from_turn_updates_long_term_memory(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    monkeypatch.setattr("deeptutor.services.tutor_state.service.llm_stream", _rewrite_stream)

    result = asyncio.run(
        service.refresh_from_turn(
            user_id="student_demo",
            user_message="我总是把承载力和沉降控制混在一起。",
            assistant_message="先区分极限承载能力和正常使用阶段的沉降控制，再做两道案例题。",
            session_id="session_1",
            capability="chat",
            language="zh",
        )
    )

    memory_path = tmp_path / "tutor_state" / "student_demo" / "MEMORY.md"
    memory_text = memory_path.read_text(encoding="utf-8")

    assert result.changed is True
    assert "沉降控制" in result.content
    assert "下一次继续做两道案例题" in memory_text
