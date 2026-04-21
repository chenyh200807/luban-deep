from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

fastapi_module = pytest.importorskip("fastapi")
FastAPI = fastapi_module.FastAPI
HTTPException = fastapi_module.HTTPException
TestClient = pytest.importorskip("fastapi.testclient").TestClient
bi_router_module = importlib.import_module("deeptutor.api.routers.bi")
bi_router = bi_router_module.router

from deeptutor.services.bi_service import BIService
from deeptutor.services.feedback_service import build_mobile_feedback_row
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


def _assert_non_empty_list(value: object, field_name: str) -> list[object]:
    assert isinstance(value, list), f"{field_name} should be a list"
    assert value, f"{field_name} should not be empty"
    return value


@pytest.fixture
def bi_service(tmp_path: Path, monkeypatch) -> BIService:
    store = SQLiteSessionStore(db_path=tmp_path / "bi-router.db")
    feedback_rows = [
        build_mobile_feedback_row(
            user_id="u1",
            session_id="session_feedback_1",
            message_id="42",
            rating=-1,
            reason_tags=["事实错误", "逻辑不通"],
            comment="这里不对",
            answer_mode="fast",
        ),
        build_mobile_feedback_row(
            user_id="u1",
            session_id="session_feedback_1",
            message_id="43",
            rating=1,
            reason_tags=["有帮助"],
            comment="",
            answer_mode="deep",
        ),
        {
            "id": "ignore-other-source",
            "created_at": "2026-04-15T10:00:00+08:00",
            "user_id": None,
            "conversation_id": None,
            "message_id": None,
            "rating": -1,
            "reason_tags": ["noise"],
            "comment": "ignore",
            "metadata": {"source": "other_app"},
        },
    ]

    class _FakeFeedbackStore:
        def __init__(self, rows) -> None:
            self._rows = list(rows)
            self.is_configured = True

        async def list_feedback(self, *, created_after: str, limit: int = 500, offset: int = 0):
            assert created_after
            return self._rows[offset : offset + limit]

    class _FakeBailianTelemetryClient:
        def is_configured(self) -> bool:
            return True

        async def get_usage_totals(self, **kwargs):
            assert kwargs["start_ts"] > 0
            assert kwargs["end_ts"] >= kwargs["start_ts"]
            return type(
                "Totals",
                (),
                {
                    "to_dict": lambda self: {
                        "input_tokens": 1000,
                        "output_tokens": 180,
                        "total_tokens": 1180,
                        "models": {"deepseek-v3.2": 1170, "text-embedding-v3": 10},
                        "model_details": {
                            "deepseek-v3.2": {
                                "input_tokens": 1000,
                                "output_tokens": 170,
                                "total_tokens": 1170,
                                "estimated_cost_usd": 0.00251,
                            },
                            "text-embedding-v3": {
                                "input_tokens": 10,
                                "output_tokens": 0,
                                "total_tokens": 10,
                                "estimated_cost_usd": 0.00001,
                            },
                        },
                        "estimated_total_cost_usd": 0.00252,
                    },
                },
            )()

    class _FakeBailianBillingClient:
        def is_configured(self) -> bool:
            return True

        async def get_totals(self, **kwargs):
            assert kwargs["billing_cycles"]
            return type(
                "BillingTotals",
                (),
                {
                    "to_dict": lambda self: {
                        "billing_cycles": [
                            {
                                "billing_cycle": "2026-04",
                                "pretax_amount": 0.0124,
                                "after_discount_amount": 0.0124,
                                "items_count": 3,
                                "currency": "CNY",
                                "model_amounts": {"deepseek-v3.2": 0.0124},
                                "usage_kind_amounts": {
                                    "input_token": 0.0041,
                                    "output_token": 0.0083,
                                },
                            }
                        ],
                        "pretax_amount": 0.0124,
                        "after_discount_amount": 0.0124,
                        "items_count": 3,
                        "currency": "CNY",
                        "model_amounts": {"deepseek-v3.2": 0.0124},
                        "usage_kind_amounts": {
                            "input_token": 0.0041,
                            "output_token": 0.0083,
                        },
                    },
                },
            )()

    class _FakeUsageLedger:
        def get_totals(self, **kwargs):
            assert kwargs["provider_name"] == "dashscope"
            return type(
                "LedgerTotals",
                (),
                {
                    "to_dict": lambda self: {
                        "input_tokens": 1600,
                        "output_tokens": 120,
                        "total_tokens": 1720,
                        "total_cost_usd": 0.0181,
                        "measured_input_tokens": 1200,
                        "measured_output_tokens": 100,
                        "measured_total_tokens": 1300,
                        "measured_total_cost_usd": 0.0123,
                        "estimated_input_tokens": 400,
                        "estimated_output_tokens": 20,
                        "estimated_total_tokens": 420,
                        "estimated_total_cost_usd": 0.0058,
                        "events": 4,
                        "coverage_start_ts": kwargs["start_ts"] + 10,
                        "coverage_end_ts": kwargs["end_ts"] - 10,
                    },
                },
            )()

    service = BIService(
        session_store=store,
        member_service=_FakeMemberService(),
        feedback_store=_FakeFeedbackStore(feedback_rows),
        bailian_telemetry_client=_FakeBailianTelemetryClient(),
        bailian_billing_client=_FakeBailianBillingClient(),
        usage_ledger=_FakeUsageLedger(),
    )
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
                            "estimated_total_tokens": 300,
                            "estimated_total_cost_usd": 0.003,
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


def test_bi_router_requires_admin_for_sensitive_endpoints(bi_service: BIService) -> None:
    protected_paths = [
        "/api/v1/bi/overview?days=30",
        "/api/v1/bi/learner/u1?days=30",
        "/api/v1/bi/cost/reconciliation?days=30&workspace_id=ws-1&apikey_id=42&billing_cycle=2026-04",
        "/api/v1/bi/feedback?days=30&limit=10",
    ]

    with TestClient(_build_app(bi_service)) as client:
        for path in protected_paths:
            response = client.get(path)
            assert response.status_code == 401
            assert response.json()["detail"] == "Authentication required"


def test_bi_router_rejects_non_admin_even_with_authenticated_context(bi_service: BIService) -> None:
    app = _build_app(bi_service)

    def _deny_non_admin():
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[bi_router_module.require_bi_access] = _deny_non_admin

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/overview?days=30")
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"


def test_bi_router_allows_public_access_when_flag_enabled(
    bi_service: BIService,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/overview?days=30")
        assert response.status_code == 200
        assert response.json()["summary"]["total_sessions"] >= 1


def test_bi_router_endpoints_return_expected_shapes(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: None

    with TestClient(app) as client:
        overview = client.get("/api/v1/bi/overview?days=30")
        assert overview.status_code == 200
        overview_body = overview.json()
        assert overview_body["summary"]["total_sessions"] >= 1
        assert overview_body["summary"]["total_cost_usd"] > 0

        trend = client.get("/api/v1/bi/active-trend?days=30")
        assert trend.status_code == 200
        _assert_non_empty_list(trend.json()["points"], "active_trend.points")

        retention = client.get("/api/v1/bi/retention?days=30")
        assert retention.status_code == 200
        retention_labels = _assert_non_empty_list(retention.json()["labels"], "retention.labels")
        assert all(isinstance(label, str) and label for label in retention_labels)

        capabilities = client.get("/api/v1/bi/capabilities?days=30")
        assert capabilities.status_code == 200
        capability_items = _assert_non_empty_list(capabilities.json()["items"], "capabilities.items")
        assert capability_items[0]["capability"] == "deep_solve"

        tools = client.get("/api/v1/bi/tools?days=30")
        assert tools.status_code == 200
        tool_items = _assert_non_empty_list(tools.json()["items"], "tools.items")
        assert tool_items[0]["tool_name"] == "rag"

        knowledge = client.get("/api/v1/bi/knowledge?days=30")
        assert knowledge.status_code == 200
        knowledge_items = _assert_non_empty_list(knowledge.json()["items"], "knowledge.items")
        assert knowledge_items[0]["kb_name"] == "supabase-main"

        members = client.get("/api/v1/bi/members?days=30")
        assert members.status_code == 200
        assert members.json()["dashboard"]["active_count"] == 1

        filtered_members = client.get("/api/v1/bi/members?days=30&tier=vip")
        assert filtered_members.status_code == 200
        filtered_tiers = _assert_non_empty_list(filtered_members.json()["tiers"], "members.tiers")
        assert filtered_tiers[0]["tier"] == "vip"

        tutorbots = client.get("/api/v1/bi/tutorbots?days=30&entrypoint=web")
        assert tutorbots.status_code == 200
        tutorbot_body = tutorbots.json()
        tutorbot_items = _assert_non_empty_list(tutorbot_body["items"], "tutorbots.items")
        tutorbot_ranking = _assert_non_empty_list(tutorbot_body["ranking"], "tutorbots.ranking")
        tutorbot_statuses = _assert_non_empty_list(tutorbot_body["status_breakdown"], "tutorbots.status_breakdown")
        assert tutorbot_items[0]["bot_id"] == "bot_demo"
        assert tutorbot_ranking[0]["label"] == "Demo Bot"
        assert tutorbot_statuses[0]["label"] in {"running", "idle"}
        assert isinstance(tutorbot_body["recent_messages"], list)

        learner = client.get("/api/v1/bi/learner/u1?days=30")
        assert learner.status_code == 200
        learner_body = learner.json()
        assert learner_body["profile"]["user_id"] == "u1"
        assert isinstance(learner_body["recent_sessions"], list)

        cost = client.get("/api/v1/bi/cost?days=30")
        assert cost.status_code == 200
        assert len(cost.json()["cards"]) >= 1

        reconciliation = client.get(
            "/api/v1/bi/cost/reconciliation?days=30&workspace_id=ws-1&apikey_id=42&billing_cycle=2026-04"
        )
        assert reconciliation.status_code == 200
        reconciliation_body = reconciliation.json()
        assert reconciliation_body["system"]["total_tokens"] == 1500
        assert reconciliation_body["system"]["measured_total_tokens"] == 1200
        assert reconciliation_body["system"]["estimated_total_tokens"] == 300
        assert reconciliation_body["system"]["total_cost_usd"] == 0.0153
        assert reconciliation_body["system"]["measured_total_cost_usd"] == 0.0123
        assert reconciliation_body["system"]["estimated_total_cost_usd"] == 0.003
        assert reconciliation_body["bailian"]["total_tokens"] == 1180
        assert reconciliation_body["bailian"]["estimated_total_cost_usd"] == 0.00252
        assert reconciliation_body["bailian_billing"]["pretax_amount"] == 0.0124
        assert reconciliation_body["system_global_bailian"]["total_tokens"] == 1720
        assert reconciliation_body["system_global_bailian"]["estimated_total_cost_usd"] == 0.0058
        assert reconciliation_body["reconciliation"]["billing_cycle"] == "2026-04"
        assert reconciliation_body["reconciliation"]["billing_scope_system_cost_usd"] == 0.0153
        assert reconciliation_body["reconciliation"]["token_delta"] == 320
        assert reconciliation_body["reconciliation"]["cost_delta_usd"] == 0.01278
        assert reconciliation_body["reconciliation"]["status"] == "ok"
        assert any("usage ledger" in warning for warning in reconciliation_body["warnings"])

        anomalies = client.get("/api/v1/bi/anomalies?days=30&limit=10")
        assert anomalies.status_code == 200
        assert isinstance(anomalies.json()["items"], list)

        feedback = client.get("/api/v1/bi/feedback?days=30&limit=10")
        assert feedback.status_code == 200
        feedback_body = feedback.json()
        assert feedback_body["storage_status"] == "ok"
        assert feedback_body["summary"]["total_feedback"] == 2
        assert feedback_body["summary"]["thumbs_down"] == 1
        assert feedback_body["summary"]["thumbs_up"] == 1
        top_reason_tags = _assert_non_empty_list(feedback_body["top_reason_tags"], "feedback.top_reason_tags")
        recent_feedback = _assert_non_empty_list(feedback_body["recent"], "feedback.recent")
        assert top_reason_tags[0]["tag"] in {"事实错误", "逻辑不通", "有帮助"}
        assert recent_feedback[0]["session_id"] == "session_feedback_1"


def test_bi_router_boss_homepage_contract_shapes(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: None

    with TestClient(app) as client:
        overview = client.get("/api/v1/bi/overview?days=30")
        assert overview.status_code == 200
        overview_body = overview.json()
        assert {"cards", "entrypoints"}.issubset(overview_body)
        overview_cards = _assert_non_empty_list(overview_body["cards"], "overview.cards")
        overview_entrypoints = _assert_non_empty_list(overview_body["entrypoints"], "overview.entrypoints")
        assert {"label", "value"}.issubset(overview_cards[0])
        assert overview_cards[0]["label"]
        assert overview_cards[0]["value"] is not None
        assert {"entrypoint", "label", "value"}.issubset(overview_entrypoints[0])

        trend = client.get("/api/v1/bi/active-trend?days=30")
        assert trend.status_code == 200
        trend_body = trend.json()
        assert "points" in trend_body
        trend_points = _assert_non_empty_list(trend_body["points"], "active_trend.points")
        assert {"date", "active"}.issubset(trend_points[0])

        members = client.get("/api/v1/bi/members?days=30")
        assert members.status_code == 200
        members_body = members.json()
        assert {"samples", "tiers", "risks"}.issubset(members_body)
        member_samples = _assert_non_empty_list(members_body["samples"], "members.samples")
        member_tiers = _assert_non_empty_list(members_body["tiers"], "members.tiers")
        member_risks = _assert_non_empty_list(members_body["risks"], "members.risks")
        assert {"user_id", "tier", "risk_level"}.issubset(member_samples[0])
        assert {"tier", "label", "value"}.issubset(member_tiers[0])
        assert {"risk_level", "label", "value"}.issubset(member_risks[0])

        retention = client.get("/api/v1/bi/retention?days=30")
        assert retention.status_code == 200
        retention_body = retention.json()
        retention_labels = _assert_non_empty_list(retention_body["labels"], "retention.labels")
        retention_cohorts = _assert_non_empty_list(retention_body["cohorts"], "retention.cohorts")
        assert all(isinstance(label, str) and label for label in retention_labels)
        assert {"label", "values"}.issubset(retention_cohorts[0])

        anomalies = client.get("/api/v1/bi/anomalies?days=30&limit=10")
        assert anomalies.status_code == 200
        anomalies_body = anomalies.json()
        assert "items" in anomalies_body
        anomaly_items = _assert_non_empty_list(anomalies_body["items"], "anomalies.items")
        assert {"kind", "level", "title", "detail"}.issubset(anomaly_items[0])
