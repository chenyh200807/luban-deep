from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import deeptutor.services.bi_service as bi_service_module
from deeptutor.services.bi_service import BIService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class _QuietMemberService:
    def get_dashboard(self, days: int = 30) -> dict[str, object]:
        return {
            "total_count": 0,
            "active_count": 0,
            "expiring_soon_count": 0,
            "new_today_count": 0,
            "churn_risk_count": 0,
            "health_score": 100,
            "auto_renew_coverage": 100,
            "recommendations": [],
        }

    def list_members(self, page: int = 1, page_size: int = 200, **_: object) -> dict[str, object]:
        return {"items": [], "page": page, "page_size": page_size, "pages": 1, "total": 0}


class _RegisteredMemberService(_QuietMemberService):
    def list_members(self, page: int = 1, page_size: int = 200, **_: object) -> dict[str, object]:
        return {
            "items": [
                {
                    "user_id": "member_1",
                    "canonical_user_id": "member_1",
                    "alias_user_ids": ["member_1", "wx_member_1"],
                    "phone": "15558866508",
                    "tier": "trial",
                    "status": "active",
                    "risk_level": "low",
                    "auto_renew": False,
                    "created_at": "2026-04-20T10:00:00+08:00",
                    "expire_at": "2026-05-20T10:00:00+08:00",
                    "last_active_at": "2026-04-22T10:00:00+08:00",
                    "chapter_mastery": {
                        "地基基础": {"name": "地基基础", "mastery": 58},
                        "主体结构": {"name": "主体结构", "mastery": 76},
                    },
                },
                {
                    "user_id": "internal_probe",
                    "canonical_user_id": "internal_probe",
                    "alias_user_ids": ["internal_probe"],
                    "phone": "",
                    "tier": "trial",
                    "status": "active",
                    "risk_level": "high",
                    "auto_renew": False,
                    "created_at": "2026-04-20T10:00:00+08:00",
                    "expire_at": "2026-05-20T10:00:00+08:00",
                    "last_active_at": "2026-04-22T10:00:00+08:00",
                    "chapter_mastery": {
                        "内部压测": {"name": "内部压测", "mastery": 99},
                    },
                }
            ],
            "page": page,
            "page_size": page_size,
            "pages": 1,
            "total": 2,
        }


@pytest.fixture
def store(tmp_path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(db_path=tmp_path / "bi-limits.db")


def test_bi_context_loader_caps_each_collection(
    monkeypatch: pytest.MonkeyPatch,
    store: SQLiteSessionStore,
) -> None:
    monkeypatch.setattr(bi_service_module, "_BI_CONTEXT_ROW_LIMIT", 2)
    service = BIService(session_store=store, member_service=_QuietMemberService())

    async def _seed() -> None:
        for index in range(3):
            session = await store.create_session(title=f"Session {index}", session_id=f"session_{index}")
            await store.update_session_preferences(
                session["id"],
                {
                    "source": "wx_miniprogram",
                    "user_id": f"user_{index}",
                },
            )
            turn = await store.create_turn(session["id"], capability="chat")
            await store.append_turn_event(
                turn["id"],
                {
                    "type": "tool_call",
                    "content": "rag",
                    "metadata": {"args": {"query": f"q_{index}"}},
                },
            )
            await store.append_turn_event(
                turn["id"],
                {
                    "type": "result",
                    "content": "done",
                    "metadata": {"cost_summary": {"total_tokens": index + 1, "total_cost_usd": 0.001}},
                },
            )
            await store.update_turn_status(turn["id"], "completed")
            await store.upsert_notebook_entries(
                session["id"],
                [
                    {
                        "question_id": f"q_{index}",
                        "question": f"Question {index}",
                        "question_type": "choice",
                        "is_correct": False,
                    }
                ],
            )

    asyncio.run(_seed())
    context = asyncio.run(service._load_context_since(0.0))

    assert len(context.sessions) == 2
    assert len(context.turns) == 2
    assert len(context.result_events) == 2
    assert len(context.tool_events) == 2
    assert len(context.notebook_entries) == 2
    assert set(context.truncated_collections) == {
        "sessions",
        "turns",
        "result_events",
        "tool_events",
        "notebook_entries",
    }


def test_boss_workbench_exposes_daily_cost_from_result_cost_summary(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _seed() -> None:
        session = await store.create_session(title="Cost Session", session_id="cost_session")
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": "member_1",
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.append_turn_event(
            turn["id"],
            {
                "type": "result",
                "content": "done",
                "metadata": {
                    "cost_summary": {
                        "total_input_tokens": 100,
                        "total_output_tokens": 50,
                        "total_tokens": 150,
                        "total_cost_usd": 0.125,
                        "usage_sources": {"langfuse": 1},
                    }
                },
            },
        )
        await store.update_turn_status(turn["id"], "completed")

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7))
    boss = overview["boss_workbench"]

    assert boss["daily_cost"]["today_usd"] == 0.125
    assert boss["daily_cost"]["window_total_usd"] == 0.125
    assert boss["daily_cost"]["series"][-1]["cost_usd"] == 0.125
    assert boss["daily_cost"]["source"] == "turn_result_cost_summary"
    assert any(item["label"] == "今日成本" for item in boss["kpis"])


def test_boss_workbench_counts_only_registered_member_activity(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _create_session(session_id: str, user_id: str, *, status: str, cost: float) -> None:
        session = await store.create_session(title=session_id, session_id=session_id)
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": user_id,
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.append_turn_event(
            turn["id"],
            {
                "type": "result",
                "content": "done",
                "metadata": {
                    "cost_summary": {
                        "total_tokens": 100,
                        "total_cost_usd": cost,
                    }
                },
            },
        )
        await store.update_turn_status(turn["id"], status)

    async def _seed() -> None:
        await _create_session("real_canonical", "member_1", status="completed", cost=0.1)
        await _create_session("real_alias", "wx_member_1", status="completed", cost=0.2)
        await _create_session("internal_casefix", "casefix_internal", status="failed", cost=9.9)
        await _create_session("anonymous_probe", "", status="failed", cost=8.8)

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7))
    trend = asyncio.run(service.get_active_trend(days=7))

    assert overview["summary"]["total_sessions"] == 2
    assert overview["summary"]["active_learners"] == 1
    assert overview["summary"]["total_turns"] == 2
    assert overview["summary"]["success_turn_rate"] == 100
    assert overview["boss_workbench"]["daily_cost"]["window_total_usd"] == 0.3
    assert not any("失败回合" in item for item in overview["risk_alerts"])
    assert sum(point["sessions"] for point in trend["points"]) == 2
    assert max(point["active"] for point in trend["points"]) == 1


def test_overview_exposes_top_tier_bi_payloads_without_counting_unregistered_activity(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _create_session(session_id: str, user_id: str, *, status: str, cost: float) -> None:
        session = await store.create_session(title=session_id, session_id=session_id)
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": user_id,
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.append_turn_event(
            turn["id"],
            {
                "type": "result",
                "content": "done",
                "metadata": {
                    "cost_summary": {
                        "total_tokens": 100,
                        "total_cost_usd": cost,
                    }
                },
            },
        )
        await store.update_turn_status(turn["id"], status)

    async def _seed() -> None:
        await _create_session("real_member", "member_1", status="completed", cost=0.25)
        await _create_session("anonymous_probe", "", status="failed", cost=7.7)

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7))

    assert overview["north_star"]["metric_id"] == "effective_learning_members"
    assert overview["north_star"]["label"] == "有效学习成功会员数"
    assert overview["north_star"]["value"] == 1
    assert overview["north_star"]["trust_level"] == "B"
    assert overview["growth_funnel"]["steps"][0]["id"] == "registered_members"
    assert overview["growth_funnel"]["steps"][0]["value"] == 1
    assert overview["growth_funnel"]["steps"][1]["id"] == "activated_members"
    assert overview["growth_funnel"]["steps"][1]["value"] == 1
    assert overview["member_health"]["score"]["trust_level"] == "C"
    assert overview["operating_rhythm"]["top_actions"][0]["target"] in {
        "member_ops",
        "data_trust",
        "ai_quality",
    }
    assert overview["ai_quality"]["engineering_success_rate"] == 100
    assert overview["unit_economics"]["revenue_status"] == "pending"
    assert overview["unit_economics"]["cost_per_effective_learning_usd"] == 0.25
    assert overview["teaching_effect"]["chapter_progress"][0]["name"] == "地基基础"
    assert overview["teaching_effect"]["chapter_progress"][0]["mastery"] == 58
    assert overview["teaching_effect"]["chapter_progress"][0]["member_count"] == 1
    assert all(item["name"] != "内部压测" for item in overview["teaching_effect"]["chapter_progress"])
    assert overview["data_trust"]["status"] == "ready"
    assert all(
        {"metric_id", "label", "definition", "authority", "trust_level", "owner", "drilldown"}
        <= set(metric)
        for metric in overview["data_trust"]["metric_definitions"]
    )


def test_north_star_does_not_count_empty_registered_member_sessions(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _seed() -> None:
        session = await store.create_session(title="Empty Session", session_id="empty_session")
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": "member_1",
            },
        )

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7))

    assert overview["summary"]["total_sessions"] == 1
    assert overview["summary"]["total_turns"] == 0
    assert overview["summary"]["active_learners"] == 0
    assert overview["north_star"]["value"] == 0


def test_growth_funnel_does_not_use_renewal_risk_as_paid_proxy(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _seed() -> None:
        session = await store.create_session(title="Effective Session", session_id="effective_session")
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": "member_1",
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.update_turn_status(turn["id"], "completed")

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7))
    step_ids = [step["id"] for step in overview["growth_funnel"]["steps"]]

    assert "renewal_risk_members" not in step_ids
    assert all(step["conversion_rate"] <= 100 for step in overview["growth_funnel"]["steps"])


def test_tier_filter_uses_canonical_identity_values_not_only_user_id(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _seed() -> None:
        session = await store.create_session(title="Phone Session", session_id="phone_session")
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "phone": "15558866508",
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.update_turn_status(turn["id"], "completed")

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7, tier="trial"))

    assert overview["summary"]["total_sessions"] == 1
    assert overview["north_star"]["value"] == 1
