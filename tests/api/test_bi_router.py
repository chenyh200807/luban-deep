from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
bi_router = importlib.import_module("deeptutor.api.routers.bi").router

from deeptutor.services.bi_service import BIService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class _FakeMemberService:
    def get_dashboard(self, days: int = 30) -> dict[str, int | list[str]]:
        return {
            "total_count": 2,
            "active_count": 1,
            "expiring_soon_count": 1,
            "new_today_count": 0,
            "churn_risk_count": 1,
            "health_score": 50,
            "auto_renew_coverage": 50,
            "recommendations": [f"{days} 天窗口建议续费触达"],
        }

    def list_members(self, page: int = 1, page_size: int = 200, **_: object) -> dict[str, object]:
        items = [
            {
                "user_id": "u1",
                "display_name": "陈同学",
                "phone": "13800000001",
                "tier": "vip",
                "status": "active",
                "segment": "power_user",
                "risk_level": "low",
                "auto_renew": True,
                "expire_at": "2026-05-01T00:00:00+08:00",
                "created_at": "2026-04-01T00:00:00+08:00",
                "last_active_at": "2026-04-14T08:00:00+08:00",
                "points_balance": 500,
                "review_due": 2,
            },
            {
                "user_id": "u2",
                "display_name": "李同学",
                "phone": "13800000002",
                "tier": "trial",
                "status": "expiring_soon",
                "segment": "at_risk",
                "risk_level": "high",
                "auto_renew": False,
                "expire_at": "2026-04-16T00:00:00+08:00",
                "created_at": "2026-04-10T00:00:00+08:00",
                "last_active_at": "2026-04-12T00:00:00+08:00",
                "points_balance": 40,
                "review_due": 6,
            },
        ]
        return {"items": items, "page": page, "page_size": page_size, "pages": 1, "total": len(items)}


def _build_app(service: BIService) -> FastAPI:
    app = FastAPI()
    app.include_router(bi_router, prefix="/api/v1/bi")
    app.dependency_overrides = {}
    return app


@pytest.fixture
def bi_service(tmp_path: Path, monkeypatch) -> BIService:
    store = SQLiteSessionStore(db_path=tmp_path / "bi-router.db")
    service = BIService(session_store=store, member_service=_FakeMemberService())
    monkeypatch.setattr("deeptutor.api.routers.bi.get_bi_service", lambda: service)

    session = asyncio.run(store.create_session(title="BI Session"))
    asyncio.run(
        store.update_session_preferences(
            session["id"],
            {
                "capability": "deep_solve",
                "tools": ["rag", "reason"],
                "knowledge_bases": ["supabase-main"],
                "language": "zh",
                "source": "wx_miniprogram",
                "user_id": "u1",
            },
        )
    )
    turn = asyncio.run(store.create_turn(session["id"], capability="deep_solve"))
    asyncio.run(
        store.append_turn_event(
            turn["id"],
            {
                "type": "tool_call",
                "content": "rag",
                "metadata": {"args": {"query": "foundation"}},
            },
        )
    )
    asyncio.run(
        store.append_turn_event(
            turn["id"],
            {
                "type": "tool_result",
                "content": "ok",
                "metadata": {"tool": "rag"},
            },
        )
    )
    asyncio.run(
        store.append_turn_event(
            turn["id"],
            {
                "type": "result",
                "content": "done",
                "metadata": {
                    "metadata": {
                        "cost_summary": {
                            "total_tokens": 1200,
                            "total_cost_usd": 0.0123,
                        }
                    }
                },
            },
        )
    )
    asyncio.run(store.update_turn_status(turn["id"], "completed"))
    asyncio.run(
        store.upsert_notebook_entries(
            session["id"],
            [
                {
                    "question_id": "q1",
                    "question": "What is DeepTutor BI?",
                    "question_type": "qa",
                    "difficulty": "medium",
                    "is_correct": True,
                    "bookmarked": True,
                }
            ],
        )
    )
    class _FakeTutorBotManager:
        def list_bots(self):
            return [
                {
                    "bot_id": "bot_demo",
                    "name": "Demo Bot",
                    "channels": ["web"],
                    "model": "gpt-4o-mini",
                    "running": True,
                    "started_at": "2026-04-14T08:00:00",
                }
            ]

        def get_recent_active_bots(self, limit: int = 10):
            return [
                {
                    "bot_id": "bot_demo",
                    "name": "Demo Bot",
                    "running": True,
                    "last_message": "最近一次讲解了基础知识。",
                    "updated_at": "2026-04-14T09:00:00",
                }
            ][:limit]

        def get_bot_history(self, bot_id: str, limit: int = 50):
            return [{"role": "assistant", "content": "hello"} for _ in range(min(limit, 3))]

    monkeypatch.setattr("deeptutor.services.tutorbot.get_tutorbot_manager", lambda: _FakeTutorBotManager())
    return service


def test_bi_router_endpoints_return_expected_shapes(bi_service: BIService) -> None:
    with TestClient(_build_app(bi_service)) as client:
        overview = client.get("/api/v1/bi/overview?days=30")
        assert overview.status_code == 200
        overview_body = overview.json()
        assert overview_body["summary"]["total_sessions"] >= 1
        assert overview_body["summary"]["total_cost_usd"] > 0

        trend = client.get("/api/v1/bi/active-trend?days=30")
        assert trend.status_code == 200
        assert len(trend.json()["points"]) >= 1

        retention = client.get("/api/v1/bi/retention?days=30")
        assert retention.status_code == 200
        assert retention.json()["labels"] == ["D0", "D1", "D7", "D30"]

        capabilities = client.get("/api/v1/bi/capabilities?days=30")
        assert capabilities.status_code == 200
        assert capabilities.json()["items"][0]["capability"] == "deep_solve"

        tools = client.get("/api/v1/bi/tools?days=30")
        assert tools.status_code == 200
        assert tools.json()["items"][0]["tool_name"] == "rag"

        knowledge = client.get("/api/v1/bi/knowledge?days=30")
        assert knowledge.status_code == 200
        assert knowledge.json()["items"][0]["kb_name"] == "supabase-main"

        members = client.get("/api/v1/bi/members?days=30")
        assert members.status_code == 200
        assert members.json()["dashboard"]["active_count"] == 1

        filtered_members = client.get("/api/v1/bi/members?days=30&tier=vip")
        assert filtered_members.status_code == 200
        assert filtered_members.json()["tiers"][0]["tier"] == "vip"

        tutorbots = client.get("/api/v1/bi/tutorbots?days=30&entrypoint=web")
        assert tutorbots.status_code == 200
        tutorbot_body = tutorbots.json()
        assert tutorbot_body["items"][0]["bot_id"] == "bot_demo"
        assert tutorbot_body["ranking"][0]["label"] == "Demo Bot"
        assert tutorbot_body["status_breakdown"][0]["label"] in {"running", "idle"}
        assert isinstance(tutorbot_body["recent_messages"], list)

        learner = client.get("/api/v1/bi/learner/u1?days=30")
        assert learner.status_code == 200
        learner_body = learner.json()
        assert learner_body["profile"]["user_id"] == "u1"
        assert isinstance(learner_body["recent_sessions"], list)

        cost = client.get("/api/v1/bi/cost?days=30")
        assert cost.status_code == 200
        assert len(cost.json()["cards"]) >= 1

        anomalies = client.get("/api/v1/bi/anomalies?days=30&limit=10")
        assert anomalies.status_code == 200
        assert isinstance(anomalies.json()["items"], list)
