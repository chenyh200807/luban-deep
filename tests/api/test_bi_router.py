from __future__ import annotations

import asyncio
from datetime import datetime
import importlib
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

fastapi_module = pytest.importorskip("fastapi")
FastAPI = fastapi_module.FastAPI
HTTPException = fastapi_module.HTTPException
TestClient = pytest.importorskip("fastapi.testclient").TestClient
bi_router_module = importlib.import_module("deeptutor.api.routers.bi")
bi_router = bi_router_module.router

from deeptutor.services.bi_service import BIService
from deeptutor.services.config import env_store as env_store_module
from deeptutor.services.feedback_service import build_mobile_feedback_row
from deeptutor.services.member_console import rbac
from deeptutor.services.member_console.service import get_member_console_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class _FakeMemberService:
    def __init__(self) -> None:
        self.audit_log: list[dict[str, object]] = []
        self.audit_by_idempotency_key: dict[tuple[str, str, str], str] = {}

    def get_dashboard(self, days: int = 30) -> dict[str, int | list[str]]:
        return {
            "total_count": 2,
            "active_count": 1,
            "expiring_soon_count": 1,
            "new_today_count": 0,
            "new_7d_count": 0,
            "new_30d_count": 0,
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
                "created_at": "2026-06-22T00:00:00+08:00",
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
                "created_at": "2026-06-22T00:00:00+08:00",
                "last_active_at": "2026-04-12T00:00:00+08:00",
                "points_balance": 40,
                "review_due": 6,
            },
        ]
        return {"items": items, "page": page, "page_size": page_size, "pages": 1, "total": len(items)}

    def record_bi_audit(
        self,
        *,
        action: str,
        target_user: str,
        operator: str = "admin",
        reason: str = "",
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_key = str(idempotency_key or "").strip()
        dedup_key = (str(action), str(operator), normalized_key)
        if normalized_key and dedup_key in self.audit_by_idempotency_key:
            return {
                "audit_id": self.audit_by_idempotency_key[dedup_key],
                "deduped": True,
            }
        audit_id = f"audit_feedback_{len(self.audit_log) + 1}"
        self.audit_log.insert(
            0,
            {
                "id": audit_id,
                "action": action,
                "target_user": target_user,
                "operator": operator,
                "reason": reason,
                "before": before or {},
                "after": after or {},
            },
        )
        if normalized_key:
            self.audit_by_idempotency_key[dedup_key] = audit_id
        return {"audit_id": audit_id, "deduped": False}

    def record_ops_action_result(
        self,
        user_id: str,
        *,
        status: str,
        result: str,
        action_title: str = "",
        next_follow_up_at: str = "",
        operator: str = "admin",
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        audit = self.record_bi_audit(
            action="ops_action_result",
            target_user=user_id,
            operator=operator,
            reason=status,
            after={
                "status": status,
                "result": result,
                "action_title": action_title,
                "next_follow_up_at": next_follow_up_at,
            },
            idempotency_key=idempotency_key,
        )
        return {
            "status": status,
            "result": result,
            "action_title": action_title,
            "next_follow_up_at": next_follow_up_at,
            "note": {"id": "note_ops_1", "channel": "ops_action"},
            **audit,
        }

    def delete_member_account(
        self,
        user_id: str,
        *,
        operator: str = "admin",
        reason: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        audit = self.record_bi_audit(
            action="member_account_delete",
            target_user=user_id,
            operator=operator,
            reason=reason,
            after={"status": "deleted"},
            idempotency_key=idempotency_key,
        )
        return {
            "success": True,
            "user_id": user_id,
            "status": "deleted",
            "message": "会员账号已删除",
            "credentials_deleted": True,
            "sessions_invalidated": 1,
            **audit,
        }

    def get_wallet(self, user_id: str) -> dict[str, object]:
        return {
            "balance": 500 if user_id == "u1" else 40,
            "tier": "vip" if user_id == "u1" else "trial",
            "packages": [
                {
                    "id": "advance",
                    "label": "精学版",
                    "points": 4400,
                    "price": "99",
                    "per": "每周稳定学习额度",
                    "desc": "适合日常学习、错题讲解、章节复盘",
                }
            ],
        }


class _FakeWalletService:
    is_configured = True

    def list_recent_wallet_ledger(self, *, limit: int = 100, offset: int = 0):
        rows = [
            SimpleNamespace(
                id="ledger_real_1",
                user_id="u1",
                event_type="grant",
                delta_micros=1_200_000_000,
                balance_after_micros=1_700_000_000,
                frozen_after_micros=0,
                reference_type="order",
                reference_id="ord_real_1",
                idempotency_key="order:ord_real_1",
                metadata={"channel": "wechat", "amount_cny": 99},
                created_at="2026-06-22T10:00:00+08:00",
            ),
            SimpleNamespace(
                id="ledger_real_2",
                user_id="u1",
                event_type="usage",
                delta_micros=-20_000_000,
                balance_after_micros=1_680_000_000,
                frozen_after_micros=0,
                reference_type="usage",
                reference_id="session_1",
                idempotency_key="usage:session_1",
                metadata={"capability": "deep_solve"},
                created_at="2026-06-22T11:00:00+08:00",
            ),
        ]
        return rows[offset : offset + limit]


def _build_app(service: BIService) -> FastAPI:
    app = FastAPI()
    app.include_router(bi_router, prefix="/api/v1/bi")
    app.dependency_overrides = {}
    return app


def _set_metrics_env_store(monkeypatch, tmp_path: Path, token: str) -> None:
    env_file = tmp_path / "metrics.env"
    env_file.write_text(f"DEEPTUTOR_METRICS_TOKEN={token}\n", encoding="utf-8")
    monkeypatch.setattr(
        env_store_module,
        "_env_store",
        env_store_module.EnvStore(path=env_file, fallback_paths=()),
    )


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
            self.triage_updates: list[dict[str, object]] = []

        async def list_feedback(self, *, created_after: str, limit: int = 500, offset: int = 0):
            assert created_after
            return self._rows[offset : offset + limit]

        async def update_feedback_triage(
            self,
            feedback_id: str,
            *,
            status: str,
            operator: str,
            note: str = "",
        ):
            for index, row in enumerate(self._rows):
                if str(row.get("id") or "") != feedback_id:
                    continue
                before = dict(row)
                metadata = dict(before.get("metadata") or {})
                metadata["bi_triage"] = {
                    "status": status,
                    "operator": operator,
                    "note": note,
                    "updated_at": "2026-05-24T00:00:00+08:00",
                }
                after = dict(before)
                after["metadata"] = metadata
                self._rows[index] = after
                self.triage_updates.append(
                    {
                        "feedback_id": feedback_id,
                        "status": status,
                        "operator": operator,
                        "note": note,
                    }
                )
                return {"before": before, "after": after}
            raise KeyError(feedback_id)

    class _FakeInviteTestStore:
        def __init__(self) -> None:
            self._rows = [
                {
                    "id": "invite-app-1",
                    "created_at": "2026-05-17T11:29:29.524Z",
                    "source_page": "invite-test",
                    "name": "张同学",
                    "phone": "13800138000",
                    "email": "qa@example.com",
                    "wechat_id": "wx_old",
                    "exam_type": "二建建筑实务",
                    "exam_stage": "正在冲刺刷题",
                    "pain_point": "错题原因不清楚",
                    "weekly_time": "10-30 分钟",
                    "current_method": "自己刷题",
                    "latest_wrong_question": "案例题漏点",
                    "accept_interview": False,
                    "consent": True,
                    "status": "submitted",
                    "operator_note": "",
                    "submit_count": 1,
                    "raw_payload": {"studyDifficulties": "旧困难"},
                }
            ]

        async def list_applications(self, **_: object) -> dict[str, object]:
            return {
                "window_days": 365,
                "storage_status": "fake",
                "total": len(self._rows),
                "contact_revealed": True,
                "items": list(self._rows),
            }

        async def get_stats(self, **_: object) -> dict[str, object]:
            return {
                "window_days": 365,
                "storage_status": "fake",
                "summary": {
                    "total_applications": len(self._rows),
                    "unique_contacts": len(self._rows),
                    "accept_interview_count": 0,
                    "accept_interview_rate": 0,
                    "with_wrong_question_count": 1,
                    "with_wrong_question_rate": 1,
                    "consented_count": len(self._rows),
                },
                "status_breakdown": [{"status": "submitted", "count": len(self._rows)}],
                "source_breakdown": [{"source_page": "invite-test", "count": len(self._rows)}],
                "exam_type_breakdown": [{"exam_type": "二建建筑实务", "count": len(self._rows)}],
                "exam_stage_breakdown": [{"exam_stage": "正在冲刺刷题", "count": len(self._rows)}],
                "pain_point_breakdown": [{"pain_point": "错题原因不清楚", "count": len(self._rows)}],
                "weekly_time_breakdown": [{"weekly_time": "10-30 分钟", "count": len(self._rows)}],
            }

        async def update_application(self, application_id: str, patch: dict[str, object]) -> dict[str, object]:
            for index, row in enumerate(self._rows):
                if str(row.get("id")) != application_id:
                    continue
                before = dict(row)
                after = {**before, **patch}
                raw_payload = dict(before.get("raw_payload") or {})
                if "study_difficulties" in patch:
                    raw_payload["studyDifficulties"] = patch["study_difficulties"]
                after["raw_payload"] = raw_payload
                self._rows[index] = after
                return {"storage_status": "fake", "before": before, "after": after}
            raise KeyError(application_id)

    class _FakeLubanFeedbackStore:
        def __init__(self) -> None:
            self._rows = [
                {
                    "id": "luban-feedback-1",
                    "created_at": "2026-05-17T12:00:00.000Z",
                    "source_page": "luban-survey",
                    "survey_version": "v1",
                    "nps": 9,
                    "overall_satisfaction": 5,
                    "most_valuable": "错因定位",
                    "will_continue": "probably",
                    "pay_willingness": "maybe",
                    "would_recommend": "yes",
                    "revisit_willingness": "very_willing",
                    "attempt_count": "first",
                    "exam_timeframe": "within_1m",
                    "one_word": "清晰",
                    "top_suggestion": "希望增加回访提醒",
                    "unsolved_pain": "案例题不会组织答案",
                    "phone": "13800138000",
                    "wechat_id": "wx_luban",
                    "status": "submitted",
                    "operator_note": "",
                    "contact_revealed": True,
                }
            ]

        async def list_responses(self, **_: object) -> dict[str, object]:
            return {
                "window_days": 365,
                "storage_status": "fake",
                "total": len(self._rows),
                "contact_revealed": True,
                "items": list(self._rows),
            }

        async def get_stats(self, **_: object) -> dict[str, object]:
            return {
                "window_days": 365,
                "storage_status": "fake",
                "summary": {
                    "total_responses": len(self._rows),
                    "nps_score": 100,
                    "nps_base": len(self._rows),
                    "promoters": len(self._rows),
                    "passives": 0,
                    "detractors": 0,
                    "avg_satisfaction": 5,
                    "satisfaction_base": len(self._rows),
                    "revisit_willing_count": len(self._rows),
                    "revisit_willing_rate": 1,
                    "with_contact_count": len(self._rows),
                    "with_contact_rate": 1,
                },
            }

        async def update_response(self, response_id: str, patch: dict[str, object]) -> dict[str, object]:
            for index, row in enumerate(self._rows):
                if str(row.get("id")) != response_id:
                    continue
                after = {**row, **patch}
                self._rows[index] = after
                return {"storage_status": "fake", "after": after}
            raise KeyError(response_id)

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

    class _FakeDeepSeekBillingClient:
        async def get_balance(self):
            return type(
                "BalanceTotals",
                (),
                {
                    "to_dict": lambda self: {
                        "status": "unconfigured",
                        "provider_name": "deepseek",
                        "is_available": False,
                        "currency_balances": {},
                    },
                },
            )()

        async def get_usage_export_totals(self, **_kwargs):
            return type(
                "UsageTotals",
                (),
                {
                    "to_official_usage_dict": lambda self: {
                        "status": "unconfigured",
                        "provider_name": "deepseek",
                        "cost_basis": "net_charge_cost",
                        "currency_amounts": {},
                        "models": {},
                    },
                },
            )()

    class _FakeUsageLedger:
        def get_window_summary(self, *, start_ts, end_ts):
            return {
                "totals": {
                    "input_tokens": 90000,
                    "output_tokens": 24000,
                    "total_tokens": 114000,
                    "total_cost_usd": 5.46,
                    "measured_total_cost_usd": 2.44,
                    "estimated_total_cost_usd": 3.02,
                    "measured_total_tokens": 100000,
                    "estimated_total_tokens": 14000,
                },
                "by_model": [
                    {
                        "model": "deepseek-v4-flash",
                        "events": 100,
                        "total_tokens": 90000,
                        "measured_total_cost_usd": 2.0,
                        "estimated_total_cost_usd": 3.0,
                        "total_cost_usd": 5.0,
                    },
                    {
                        "model": "gte-rerank",
                        "events": 20,
                        "total_tokens": 24000,
                        "measured_total_cost_usd": 0.44,
                        "estimated_total_cost_usd": 0.02,
                        "total_cost_usd": 0.46,
                    },
                ],
                "by_usage_source": [
                    {
                        "usage_source": "provider",
                        "events": 100,
                        "total_tokens": 100000,
                        "measured_total_cost_usd": 2.44,
                        "estimated_total_cost_usd": 0.0,
                        "total_cost_usd": 2.44,
                    },
                    {
                        "usage_source": "tiktoken",
                        "events": 20,
                        "total_tokens": 14000,
                        "measured_total_cost_usd": 0.0,
                        "estimated_total_cost_usd": 3.02,
                        "total_cost_usd": 3.02,
                    },
                ],
                "by_day": [
                    {
                        "date": datetime.now().date().isoformat(),
                        "events": 120,
                        "total_tokens": 114000,
                        "measured_total_cost_usd": 2.44,
                        "estimated_total_cost_usd": 3.02,
                        "total_cost_usd": 5.46,
                    }
                ],
            }

        def get_totals(self, **kwargs):
            assert kwargs["provider_name"] in {"dashscope", "deepseek"}
            provider_name = kwargs["provider_name"]
            if provider_name == "deepseek":
                return type(
                    "LedgerTotals",
                    (),
                    {
                        "to_dict": lambda self: {
                            "input_tokens": 1000,
                            "output_tokens": 200,
                            "total_tokens": 1200,
                            "total_cost_usd": 0.0001,
                            "measured_input_tokens": 1000,
                            "measured_output_tokens": 200,
                            "measured_total_tokens": 1200,
                            "measured_total_cost_usd": 0.0001,
                            "estimated_input_tokens": 0,
                            "estimated_output_tokens": 0,
                            "estimated_total_tokens": 0,
                            "estimated_total_cost_usd": 0.0,
                            "events": 1,
                            "provider_calls": 1,
                            "billable_turns": 1,
                            "calls_per_billable_turn": 1.0,
                            "unattributed_provider_calls": 0,
                            "currency_amounts": {"USD": 0.0001},
                            "metadata_breakdown": {
                                "input_cache_hit_tokens": 700,
                                "input_cache_miss_tokens": 300,
                            },
                            "coverage_start_ts": kwargs["start_ts"] + 10,
                            "coverage_end_ts": kwargs["end_ts"] - 10,
                        },
                    },
                )()
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
        invite_test_store=_FakeInviteTestStore(),
        luban_feedback_store=_FakeLubanFeedbackStore(),
        bailian_telemetry_client=_FakeBailianTelemetryClient(),
        bailian_billing_client=_FakeBailianBillingClient(),
        deepseek_billing_client=_FakeDeepSeekBillingClient(),
        usage_ledger=_FakeUsageLedger(),
        wallet_service=_FakeWalletService(),
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
    billing_event_ts = datetime.now().timestamp()
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE turn_events SET created_at = ?, timestamp = ? WHERE turn_id = ? AND type = 'result'",
            (billing_event_ts, billing_event_ts, turn["id"]),
        )
        conn.commit()
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

    # 端点级 RBAC 接线后，require_bi_permission 用 can_access 裁决。这些功能/审计测试
    # 注入 is_admin=True 的假 auth，因此 member_console 在此 fixture 中给全权（等价
    # super_admin），让现有断言聚焦端点行为而非权限矩阵；RBAC enforcement 本身由
    # tests/api/test_bi_rbac_enforcement.py 用真实角色矩阵专门覆盖。
    class _FullAccessMemberService:
        def can_access(self, *_args, **_kwargs) -> bool:
            return True

        def get_admin_role(self, *_args, **_kwargs) -> str:
            return "super_admin"

        def can_manage_permissions(self, *_args, **_kwargs) -> bool:
            return True

        def record_ops_action_result(self, *args, **kwargs):
            return service._member_service.record_ops_action_result(*args, **kwargs)  # noqa: SLF001

        def delete_member_account(self, *args, **kwargs):
            return service._member_service.delete_member_account(*args, **kwargs)  # noqa: SLF001

    monkeypatch.setattr(
        "deeptutor.api.routers.bi.get_member_console_service",
        lambda: _FullAccessMemberService(),
    )
    return service


def test_bi_router_requires_admin_for_sensitive_endpoints(bi_service: BIService) -> None:
    protected_paths = [
        "/api/v1/bi/overview?days=30",
        "/api/v1/bi/learner/u1?days=30",
        "/api/v1/bi/cost/reconciliation?days=30&workspace_id=ws-1&apikey_id=42&billing_cycle=2026-04",
        "/api/v1/bi/commerce?limit=10",
        "/api/v1/bi/feedback?days=30&limit=10",
        "/api/v1/bi/invite-test/applications?days=365&limit=10",
        "/api/v1/bi/invite-test/stats?days=365",
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


def test_member_ops_overview_routes_server_side_filters(
    bi_service: BIService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _MemberOpsService:
        def can_access(self, *_args, **_kwargs) -> bool:
            return True

        def get_member_ops_overview(self, **kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {
                "dashboard": {"total_count": 2},
                "list": {"items": [], "total": 0, "page": 1, "page_size": 50, "pages": 1},
            }

    monkeypatch.setattr(bi_router_module, "get_member_console_service", lambda: _MemberOpsService())

    async def _internal_snapshot(*, limit: int = 1) -> dict[str, object]:
        assert limit == 1
        return {
            "available": True,
            "total_internal": 1,
            "states": {
                "internal-user": {"is_internal": True},
                "real-member": {"is_internal": False},
            },
        }

    monkeypatch.setattr(bi_service, "get_internal_accounts_snapshot", _internal_snapshot)
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(
        user_id="u-admin", is_admin=True
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bi/member/overview?"
            "page=1&page_size=50&registered_from=2026-07-01&registered_to=2026-07-13&"
            "risk_min=0.7&active_within_days=7&review_due_min=2&not_paid=true&"
            "auto_renew=false&channel=wechat_qr&behavior_cohort=chat_only"
        )

    assert response.status_code == 200
    assert response.json()["dashboard"]["total_count"] == 2
    assert captured["registered_from"] == datetime(2026, 7, 1).date()
    assert captured["registered_to"] == datetime(2026, 7, 13).date()
    assert captured["risk_min"] == 0.7
    assert captured["not_paid"] is True
    assert captured["auto_renew"] is False
    assert captured["channel"] == "wechat_qr"
    assert captured["behavior_cohort"] == "chat_only"
    assert captured["excluded_user_ids"] == frozenset({"internal-user"})
    assert response.json()["authority"]["internal_accounts"] == "bi_internal_accounts"
    assert response.json()["authority"]["internal_accounts_available"] is True
    assert response.json()["internal_accounts"]["total_internal"] == 1
    assert "states" not in response.json()["internal_accounts"]


def test_member_ops_overview_fails_closed_when_internal_account_authority_is_unavailable(
    bi_service: BIService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MemberOpsService:
        def can_access(self, *_args, **_kwargs) -> bool:
            return True

        def get_member_ops_overview(self, **kwargs: object) -> dict[str, object]:
            raise AssertionError("unconfirmed member scope must not be projected")

    async def _unavailable_snapshot(*, limit: int = 1) -> dict[str, object]:
        return {"available": False, "states": {}, "total_internal": None}

    monkeypatch.setattr(bi_router_module, "get_member_console_service", lambda: _MemberOpsService())
    monkeypatch.setattr(bi_service, "get_internal_accounts_snapshot", _unavailable_snapshot)
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(
        user_id="u-admin", is_admin=True
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/member/overview")

    assert response.status_code == 503
    assert "scope cannot be confirmed" in response.json()["detail"]


def test_member_list_pagination_reuses_internal_account_scope(
    bi_service: BIService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _MemberOpsService:
        def can_access(self, *_args, **_kwargs) -> bool:
            return True

        def list_members(self, **kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {"items": [], "total": 0, "page": 2, "page_size": 50, "pages": 2}

    async def _snapshot(*, limit: int = 1) -> dict[str, object]:
        return {
            "available": True,
            "states": {"internal-page-2": {"is_internal": True}},
            "total_internal": 1,
        }

    monkeypatch.setattr(bi_router_module, "get_member_console_service", lambda: _MemberOpsService())
    monkeypatch.setattr(bi_service, "get_internal_accounts_snapshot", _snapshot)
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(
        user_id="u-admin", is_admin=True
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/member/list?page=2&page_size=50")

    assert response.status_code == 200
    assert captured["page"] == 2
    assert captured["excluded_user_ids"] == frozenset({"internal-page-2"})


def test_bi_rbac_permission_management_endpoints_allow_admin(
    bi_service: BIService, tmp_path: Path, monkeypatch
) -> None:
    member_service = get_member_console_service()
    monkeypatch.setattr(member_service, "_bi_admins_path", lambda: tmp_path / "bi_admins.json")
    monkeypatch.setattr(member_service, "_env_admin_user_ids", lambda: {"env-super"})
    monkeypatch.setattr(member_service, "_safe_member_display_name", lambda uid: f"name-{uid}")
    monkeypatch.setattr(
        bi_router_module,
        "get_member_console_service",
        lambda: member_service,
    )
    member_service.set_admin_role(
        actor="env-super", user_id="u-admin", role=rbac.ROLE_ADMIN, at="t1"
    )
    member_service.set_admin_role(
        actor="env-super", user_id="u-op", role=rbac.ROLE_OPERATOR, at="t1"
    )

    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(
        user_id="u-admin", is_admin=True
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = lambda: SimpleNamespace(
        user_id="u-admin", is_admin=True
    )

    matrix = {tab: [] for tab in rbac.TABS}
    matrix["member_ops"] = list(rbac.ACTIONS)
    matrix["feedback"] = ["view"]
    matrix["commerce"] = ["view"]

    with TestClient(app) as client:
        me = client.get("/api/v1/bi/rbac/me")
        assert me.status_code == 200
        assert me.json()["can_manage_permissions"] is True

        roles = client.get("/api/v1/bi/rbac/roles")
        assert roles.status_code == 200
        operator = next(r for r in roles.json()["roles"] if r["key"] == "operator")
        assert operator["matrix"]["member_ops"] == list(rbac.ACTIONS)

        updated_roles = client.put(
            "/api/v1/bi/rbac/roles/operator/permissions",
            json={"matrix": matrix},
        )
        assert updated_roles.status_code == 200
        updated_operator = next(r for r in updated_roles.json()["roles"] if r["key"] == "operator")
        assert updated_operator["matrix"]["commerce"] == ["view"]

        admins = client.put(
            "/api/v1/bi/admins/u-op/permissions",
            json={"overrides": {"ops": ["view"]}},
        )
        assert admins.status_code == 200
        operator_row = next(a for a in admins.json()["admins"] if a["user_id"] == "u-op")
        assert operator_row["effective_matrix"]["ops"] == ["view"]

        effective = client.get("/api/v1/bi/admins/u-op/effective-permissions")
        assert effective.status_code == 200
        assert effective.json()["effective_matrix"]["member_ops"] == list(rbac.ACTIONS)


def test_bi_cost_reconciliation_supports_deepseek_provider(
    bi_service: BIService,
) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    app.dependency_overrides[bi_router_module.require_bi_admin] = lambda: SimpleNamespace(is_admin=True)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bi/cost/reconciliation"
            "?days=30&provider=deepseek&billing_cycle=2026-06"
            "&environment=production&cost_center=prod_user_chat&billable_only=true"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["provider"] == "deepseek"
    assert "providers" in payload
    assert "deepseek" in payload["providers"]
    deepseek = payload["providers"]["deepseek"]
    assert deepseek["internal"]["total_tokens"] == 1200
    assert deepseek["internal"]["currency_amounts"] == {"USD": 0.0001}
    assert deepseek["official_usage"]["status"] in {
        "unconfigured",
        "unsupported_export_schema",
    }
    assert deepseek["reconciliation"]["cost_basis"] == "list_price_cost"


def test_bi_cost_reconciliation_deepseek_does_not_query_bailian(
    bi_service: BIService,
) -> None:
    class FailingBailianClient:
        config = SimpleNamespace(workspace_id="", apikey_id="")

        def is_configured(self) -> bool:
            raise AssertionError("provider=deepseek must not query Bailian clients")

    bi_service._bailian_telemetry_client = FailingBailianClient()
    bi_service._bailian_billing_client = FailingBailianClient()

    class ProviderAwareLedger:
        def get_totals(self, **kwargs):
            if kwargs["provider_name"] != "deepseek":
                raise AssertionError("provider=deepseek must not query DashScope ledger totals")
            return type(
                "LedgerTotals",
                (),
                {
                    "to_dict": lambda self: {
                        "total_tokens": 1200,
                        "currency_amounts": {"USD": 0.0001},
                        "provider_calls": 1,
                        "billable_turns": 1,
                        "unattributed_provider_calls": 0,
                    }
                },
            )()

    bi_service._usage_ledger = ProviderAwareLedger()

    payload = asyncio.run(
        bi_service.get_cost_reconciliation(
            provider="deepseek",
            days=30,
            billing_cycle="2026-06",
            environment="production",
            cost_center="prod_user_chat",
            billable_only=True,
        )
    )

    assert payload["filters"]["provider"] == "deepseek"
    assert set(payload["providers"]) == {"deepseek"}
    assert payload["system_global_bailian"]["status"] != "error"
    assert not any("system_global_bailian" in warning for warning in payload["warnings"])


def test_bi_cost_reconciliation_all_returns_provider_neutral_official_usage(
    bi_service: BIService,
) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    app.dependency_overrides[bi_router_module.require_bi_admin] = lambda: SimpleNamespace(is_admin=True)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bi/cost/reconciliation?provider=all&billing_cycle=2026-06"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["provider"] == "all"
    assert set(payload["providers"]) == {"dashscope", "deepseek"}
    dashscope = payload["providers"]["dashscope"]
    assert dashscope["official_usage"]["provider_name"] == "dashscope"
    assert dashscope["official_usage"]["cost_basis"] == "list_price_cost"
    assert dashscope["official_usage"]["list_price_cost"] == {"CNY": 0.0124}
    assert dashscope["official_usage"]["net_charge_cost"] == {"CNY": 0.0124}


def test_bi_cost_reconciliation_rejects_metrics_token_only(
    bi_service: BIService,
    monkeypatch,
) -> None:
    app = _build_app(bi_service)
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "true")
    monkeypatch.setenv("DEEPTUTOR_METRICS_TOKEN", "metrics-secret")

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bi/cost/reconciliation?provider=all&billing_cycle=2026-06",
            headers={"X-Metrics-Token": "metrics-secret"},
        )

    assert response.status_code == 403


def test_bi_router_allows_public_access_when_flag_enabled(
    bi_service: BIService,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/overview?days=30")
        assert response.status_code == 200
        assert response.json()["summary"]["total_sessions"] >= 1


def test_bi_router_public_flag_does_not_expose_invite_test_applications(
    bi_service: BIService,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/invite-test/applications?days=365&limit=10")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_router_public_flag_does_not_expose_commerce(
    bi_service: BIService,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/commerce?limit=10")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_router_public_flag_does_not_expose_invite_test_stats(
    bi_service: BIService,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/invite-test/stats?days=365")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_router_public_flag_does_not_expose_feedback(
    bi_service: BIService,
    monkeypatch,
) -> None:
    # /feedback recent records carry user_id / session_id / message_id /
    # trace_id / triage_operator / free-text comment — same identifier class
    # the existing commerce + invite-test admin gates protect. The public read
    # flag is for aggregate business metrics, not for member-level PII.
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/feedback?days=30&limit=10")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_router_honors_explicit_public_flag_in_production(
    bi_service: BIService,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_BI_PUBLIC_ENABLED", "1")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get("/api/v1/bi/overview?days=30")

    assert response.status_code == 200
    assert response.json()["summary"]["total_sessions"] >= 1


def test_bi_router_allows_metrics_token_in_production(
    bi_service: BIService,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_metrics_env_store(monkeypatch, tmp_path, "bi-read-token")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get(
            "/api/v1/bi/overview?days=30",
            headers={"X-Metrics-Token": "bi-read-token"},
        )

    assert response.status_code == 200
    assert response.json()["summary"]["total_sessions"] >= 1


def test_bi_router_metrics_token_does_not_expose_invite_test_applications(
    bi_service: BIService,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_metrics_env_store(monkeypatch, tmp_path, "bi-read-token")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get(
            "/api/v1/bi/invite-test/applications?days=365&limit=10",
            headers={"X-Metrics-Token": "bi-read-token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_router_metrics_token_does_not_expose_commerce(
    bi_service: BIService,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_metrics_env_store(monkeypatch, tmp_path, "bi-read-token")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get(
            "/api/v1/bi/commerce?limit=10",
            headers={"X-Metrics-Token": "bi-read-token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_router_metrics_token_does_not_expose_invite_test_stats(
    bi_service: BIService,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_metrics_env_store(monkeypatch, tmp_path, "bi-read-token")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get(
            "/api/v1/bi/invite-test/stats?days=365",
            headers={"X-Metrics-Token": "bi-read-token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_bi_feedback_triage_requires_admin_idempotency_and_dedupes_audit(
    bi_service: BIService,
) -> None:
    """feedback_triage is a real audited write, not a local UI status flip."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    feedback_id = str(bi_service._feedback_store._rows[0]["id"])  # noqa: SLF001

    with TestClient(app) as client:
        missing_key = client.post(
            f"/api/v1/bi/feedback/{feedback_id}/triage",
            json={"status": "triaged", "note": "转 AI 质量排查"},
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.post(
            f"/api/v1/bi/feedback/{feedback_id}/triage",
            headers={"X-Idempotency-Key": "feedback-key-1"},
            json={"status": "triaged", "note": "转 AI 质量排查"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False
        assert first_body["feedback"]["triage_status"] == "triaged"
        assert first_body["feedback"]["triage_operator"] == "admin_test"
        assert first_body["feedback"]["triage_note"] == "转 AI 质量排查"

        retry = client.post(
            f"/api/v1/bi/feedback/{feedback_id}/triage",
            headers={"X-Idempotency-Key": "feedback-key-1"},
            json={"status": "triaged", "note": "转 AI 质量排查"},
        )
        assert retry.status_code == 200
        retry_body = retry.json()
        assert retry_body["audit_id"] == first_body["audit_id"]
        assert retry_body["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001

        refreshed = client.get("/api/v1/bi/feedback?days=30&limit=10")
        assert refreshed.status_code == 200
        refreshed_items = refreshed.json()["recent"]
        updated_feedback = next(item for item in refreshed_items if item["id"] == feedback_id)
        assert updated_feedback["triage_status"] == "triaged"


def test_bi_feedback_triage_rejects_invalid_status(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    feedback_id = str(bi_service._feedback_store._rows[0]["id"])  # noqa: SLF001

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/bi/feedback/{feedback_id}/triage",
            headers={"X-Idempotency-Key": "feedback-key-2"},
            json={"status": "resolved"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "status must be one of open, triaged, ignored"


def test_bi_invite_test_application_update_requires_idempotency_and_dedupes_audit(
    bi_service: BIService,
) -> None:
    """invite_test_application_update is a real audited write for growth ops."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        missing_key = client.patch(
            "/api/v1/bi/invite-test/applications/invite-app-1",
            json={"status": "contacted", "operator_note": "已电话联系"},
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.patch(
            "/api/v1/bi/invite-test/applications/invite-app-1",
            headers={"X-Idempotency-Key": "invite-key-1"},
            json={
                "status": "contacted",
                "operator_note": "已电话联系",
                "study_difficulties": "案例题不会组织语言",
                "accept_interview": True,
            },
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False
        assert first_body["application"]["status"] == "contacted"
        assert first_body["application"]["operator_note"] == "已电话联系"
        assert first_body["application"]["study_difficulties"] == "案例题不会组织语言"
        assert first_body["application"]["accept_interview"] is True

        retry = client.patch(
            "/api/v1/bi/invite-test/applications/invite-app-1",
            headers={"X-Idempotency-Key": "invite-key-1"},
            json={
                "status": "contacted",
                "operator_note": "已电话联系",
                "study_difficulties": "案例题不会组织语言",
                "accept_interview": True,
            },
        )
        assert retry.status_code == 200
        retry_body = retry.json()
        assert retry_body["audit_id"] == first_body["audit_id"]
        assert retry_body["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001

        refreshed = client.get("/api/v1/bi/invite-test/applications?days=365&limit=10")
        assert refreshed.status_code == 200
        updated = refreshed.json()["items"][0]
        assert updated["status"] == "contacted"


def test_bi_invite_test_application_delete_requires_idempotency_and_dedupes_audit(
    bi_service: BIService,
) -> None:
    """invite_test_application_delete archives an application through the audited write gate."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        missing_key = client.request(
            "DELETE",
            "/api/v1/bi/invite-test/applications/invite-app-1",
            json={"reason": "重复提交，运营删除"},
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.request(
            "DELETE",
            "/api/v1/bi/invite-test/applications/invite-app-1",
            headers={"X-Idempotency-Key": "invite-delete-key-1"},
            json={"reason": "重复提交，运营删除"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False
        assert first_body["deleted"] is True
        assert first_body["application"]["status"] == "archived"

        retry = client.request(
            "DELETE",
            "/api/v1/bi/invite-test/applications/invite-app-1",
            headers={"X-Idempotency-Key": "invite-delete-key-1"},
            json={"reason": "重复提交，运营删除"},
        )
        assert retry.status_code == 200
        retry_body = retry.json()
        assert retry_body["audit_id"] == first_body["audit_id"]
        assert retry_body["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001


def test_bi_luban_feedback_update_requires_idempotency_and_dedupes_audit(
    bi_service: BIService,
) -> None:
    """luban_feedback_response_update edits ops-owned fields and dedupes audit."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        missing_key = client.patch(
            "/api/v1/bi/luban-feedback/responses/luban-feedback-1",
            json={"status": "contacted", "operator_note": "已约回访"},
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.patch(
            "/api/v1/bi/luban-feedback/responses/luban-feedback-1",
            headers={"X-Idempotency-Key": "luban-feedback-key-1"},
            json={"status": "contacted", "operator_note": "已约回访"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False
        assert first_body["response"]["status"] == "contacted"
        assert first_body["response"]["operator_note"] == "已约回访"

        retry = client.patch(
            "/api/v1/bi/luban-feedback/responses/luban-feedback-1",
            headers={"X-Idempotency-Key": "luban-feedback-key-1"},
            json={"status": "contacted", "operator_note": "已约回访"},
        )
        assert retry.status_code == 200
        assert retry.json()["audit_id"] == first_body["audit_id"]
        assert retry.json()["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001
        audit_entry = bi_service._member_service.audit_log[0]  # noqa: SLF001
        assert audit_entry["action"] == "luban_feedback_response_update"
        assert audit_entry["target_user"] == "luban-feedback:luban-feedback-1"


def test_bi_member_ops_action_requires_idempotency_and_dedupes_audit(
    bi_service: BIService,
) -> None:
    """ops_action_result writes from BI must use the enforced audited boundary."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        missing_key = client.post(
            "/api/v1/bi/member/u1/ops-action",
            json={"status": "done", "result": "已电话联系", "action_title": "标记已联系"},
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.post(
            "/api/v1/bi/member/u1/ops-action",
            headers={"X-Idempotency-Key": "member-action-key-1"},
            json={"status": "done", "result": "已电话联系", "action_title": "标记已联系"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False
        assert first_body["note"]["channel"] == "ops_action"

        retry = client.post(
            "/api/v1/bi/member/u1/ops-action",
            headers={"X-Idempotency-Key": "member-action-key-1"},
            json={"status": "done", "result": "已电话联系", "action_title": "标记已联系"},
        )
        assert retry.status_code == 200
        assert retry.json()["audit_id"] == first_body["audit_id"]
        assert retry.json()["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001


def test_bi_member_account_delete_requires_high_risk_and_idempotency(
    bi_service: BIService,
) -> None:
    """BI 删除会员账号必须走 member_ops/high_risk + audit idempotency."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        missing_key = client.request(
            "DELETE",
            "/api/v1/bi/member/u1/account",
            json={"reason": "用户要求删除测试账号"},
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.request(
            "DELETE",
            "/api/v1/bi/member/u1/account",
            headers={"X-Idempotency-Key": "member-delete-key-1"},
            json={"reason": "用户要求删除测试账号"},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["status"] == "deleted"
        assert first_body["credentials_deleted"] is True
        assert first_body["sessions_invalidated"] == 1
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False

        retry = client.request(
            "DELETE",
            "/api/v1/bi/member/u1/account",
            headers={"X-Idempotency-Key": "member-delete-key-1"},
            json={"reason": "用户要求删除测试账号"},
        )
        assert retry.status_code == 200
        assert retry.json()["audit_id"] == first_body["audit_id"]
        assert retry.json()["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001


def test_bi_export_request_requires_idempotency_and_dedupes_audit(
    bi_service: BIService,
) -> None:
    """bi_export_request is a real audited write before any export job is visible."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        missing_key = client.post(
            "/api/v1/bi/export-jobs",
            json={
                "dataset": "member_audit_log",
                "format": "csv",
                "filters": {"operator": "admin_test", "category": "feedback"},
            },
        )
        assert missing_key.status_code == 400
        assert "X-Idempotency-Key" in missing_key.json()["detail"]

        first = client.post(
            "/api/v1/bi/export-jobs",
            headers={"X-Idempotency-Key": "export-key-1"},
            json={
                "dataset": "member_audit_log",
                "format": "csv",
                "filters": {"operator": "admin_test", "category": "feedback"},
            },
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["audit_id"] == "audit_feedback_1"
        assert first_body["deduped"] is False
        assert first_body["export_job"]["id"] == "export_audit_feedback_1"
        assert first_body["export_job"]["dataset"] == "member_audit_log"
        assert first_body["export_job"]["scrubbed"] is True

        retry = client.post(
            "/api/v1/bi/export-jobs",
            headers={"X-Idempotency-Key": "export-key-1"},
            json={
                "dataset": "member_audit_log",
                "format": "csv",
                "filters": {"operator": "admin_test", "category": "feedback"},
            },
        )
        assert retry.status_code == 200
        assert retry.json()["audit_id"] == first_body["audit_id"]
        assert retry.json()["deduped"] is True
        assert len(bi_service._member_service.audit_log) == 1  # noqa: SLF001
        audit_entry = bi_service._member_service.audit_log[0]  # noqa: SLF001
        assert audit_entry["action"] == "bi_export_request"
        assert audit_entry["after"]["filters"] == {"operator": "admin_test", "category": "feedback"}


def test_invite_test_applications_export_request_is_audited(bi_service: BIService) -> None:
    """Invite-test exports must go through the same audited export boundary."""
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )
    app.dependency_overrides[bi_router_module.require_bi_admin] = (
        lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/bi/export-jobs",
            headers={"X-Idempotency-Key": "invite-export-key-1"},
            json={
                "dataset": "invite_test_applications",
                "format": "csv",
                "filters": {"days": 365, "status": "submitted", "visible_rows": 23},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["export_job"]["dataset"] == "invite_test_applications"
        assert body["export_job"]["name"] == "内测申请导出"
        assert body["export_job"]["scrubbed"] is True
        audit_entry = bi_service._member_service.audit_log[0]  # noqa: SLF001
        assert audit_entry["action"] == "bi_export_request"
        assert audit_entry["target_user"] == "export:invite_test_applications"
        assert audit_entry["after"]["filters"] == {
            "days": 365,
            "status": "submitted",
            "visible_rows": 23,
        }


def test_behavior_export_job_is_raw_mode_and_audited(bi_service: BIService, tmp_path: Path) -> None:
    from deeptutor.services.observability import reset_product_behavior_store

    behavior_store = reset_product_behavior_store(tmp_path / "behavior-test.db")
    now_ms = int(datetime.now().timestamp() * 1000)
    behavior_store.record_event(
        {
            "event_id": "evt-export-u1-1",
            "event_name": "section_viewed",
            "event_version": 1,
            "occurred_at_ms": now_ms,
            "received_at_ms": now_ms + 100,
            "user_id": "u1",
            "visit_id": "visit-export-1",
            "session_id": "session-export-1",
            "turn_id": "turn-export-1",
            "surface": "web",
            "module": "learning_report",
            "section": "next_action",
            "action": "view",
            "properties_json": {"entry_source": "member_ops"},
        }
    )

    result = asyncio.run(
        bi_service.request_export_job(
            dataset="product_behavior_raw",
            export_format="csv",
            filters={"user_id": "u1", "module": "learning_report", "days": 7},
            operator="admin_demo",
            idempotency_key="behavior-export-1",
        )
    )

    job = result["export_job"]
    assert job["dataset"] == "product_behavior_raw"
    assert job["scrubbed"] is False
    assert job["raw_mode"] is True
    assert job["status"] == "ready"
    assert job["rows"] == 1
    assert result["export"]["content_type"] == "text/csv"
    assert "evt-export-u1-1" in result["export"]["content"]
    assert "next_action" in result["export"]["content"]
    assert result["audit_id"]
    audit_entry = bi_service._member_service.audit_log[0]  # noqa: SLF001
    assert audit_entry["after"]["scrubbed"] is False
    assert audit_entry["after"]["raw_mode"] is True


def test_bi_router_rejects_invalid_metrics_token_in_production(
    bi_service: BIService,
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_metrics_env_store(monkeypatch, tmp_path, "bi-read-token")

    with TestClient(_build_app(bi_service)) as client:
        response = client.get(
            "/api/v1/bi/overview?days=30",
            headers={"X-Metrics-Token": "wrong-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_bi_router_endpoints_return_expected_shapes(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: SimpleNamespace(user_id="admin_test", is_admin=True)
    app.dependency_overrides[bi_router_module.require_bi_admin] = lambda: SimpleNamespace(user_id="admin_test", is_admin=True)

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

        commerce = client.get("/api/v1/bi/commerce?limit=10")
        assert commerce.status_code == 200
        commerce_body = commerce.json()
        assert commerce_body["authority"]["wallet_ledger"] == "wallet_ledger"
        assert commerce_body["summary"]["member_count"] == 1
        assert commerce_body["summary"]["recharge_count"] == 1
        assert commerce_body["summary"]["ledger_count"] >= 2
        recharge_records = _assert_non_empty_list(commerce_body["recharge_records"], "commerce.recharge_records")
        wallet_ledger = _assert_non_empty_list(commerce_body["ledger"], "commerce.ledger")
        packages = _assert_non_empty_list(commerce_body["packages"], "commerce.packages")
        assert recharge_records[0]["ledger_event_id"] == "ledger_real_1"
        assert wallet_ledger[0]["authority"] == "wallet_ledger"
        assert packages[0]["authority"] == "member_console.packages"

        billing_cycle = datetime.now().strftime("%Y-%m")
        reconciliation = client.get(
            f"/api/v1/bi/cost/reconciliation?days=30&workspace_id=ws-1&apikey_id=42&billing_cycle={billing_cycle}"
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
        assert reconciliation_body["reconciliation"]["billing_cycle"] == billing_cycle
        assert reconciliation_body["reconciliation"]["billing_scope_system_cost_usd"] == 0.0181
        assert reconciliation_body["reconciliation"]["token_delta"] == 540
        assert reconciliation_body["reconciliation"]["cost_delta_usd"] == 0.01558
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


def test_bi_overview_exposes_risk_queue_and_member_handoff(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: None

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/overview?days=30")

    assert response.status_code == 200
    body = response.json()
    workbench = body["boss_workbench"]
    assert workbench["risk_queue"][0]["bucket"] == "expiring_soon"
    assert workbench["risk_queue"][0]["handoff_filters"]["expire_within_days"] == 7
    assert workbench["watchlist"][0]["user_id"] == "u2"


def test_bi_overview_keeps_member_snapshot_consistent_under_tier_filter(bi_service: BIService) -> None:
    app = _build_app(bi_service)
    app.dependency_overrides[bi_router_module.require_bi_access] = lambda: None

    with TestClient(app) as client:
        response = client.get("/api/v1/bi/overview?days=30&tier=vip")

    assert response.status_code == 200
    body = response.json()
    assert body["member_snapshot"]["churn_risk_count"] == 0
    assert body["member_snapshot"]["health_score"] == 100
    assert body["boss_workbench"]["risk_queue"][0]["count"] == 0
    assert body["boss_workbench"]["risk_queue"][1]["count"] == 0
    assert [item["tier"] for item in body["boss_workbench"]["watchlist"]] == ["vip"]


def test_bi_cost_stats_reads_usage_ledger_authority(bi_service: BIService) -> None:
    """P2-F1: 成本唯一 authority = UsageLedger，cards 带血统分量与 metric_id。"""
    payload = asyncio.run(bi_service.get_cost_stats(days=7))
    assert payload["provenance"] == "usage_ledger"
    cards = {card["label"]: card for card in payload["cards"]}
    total = cards["总成本"]
    assert total["value"] == 5.46
    assert total["measured_value"] == 2.44
    assert total["estimated_value"] == 3.02
    assert total["metric_id"] == "total_cost_usd"
    assert cards["总 Token"]["value"] == 114000
    assert cards["总 Token"]["metric_id"] == "total_tokens"
    models = {row["label"]: row["value"] for row in payload["models"]}
    assert models["deepseek-v4-flash"] == 5.0
    providers = {row["label"]: row["value"] for row in payload["providers"]}
    assert providers["provider"] == 2.44


def test_bi_overview_cost_matches_cost_endpoint_single_authority(bi_service: BIService) -> None:
    """P2-F1: overview 与 cost 同源——自相矛盾消除。"""
    overview = asyncio.run(bi_service.get_overview(days=7))
    cost = asyncio.run(bi_service.get_cost_stats(days=7))
    cost_total = next(c for c in cost["cards"] if c["label"] == "总成本")["value"]
    assert overview["summary"]["total_cost_usd"] == cost_total == 5.46
    assert overview["summary"]["measured_total_cost_usd"] == 2.44
    assert overview["summary"]["estimated_total_cost_usd"] == 3.02
    assert overview["summary"]["cost_provenance"] == "usage_ledger"
    assert overview["summary"]["total_tokens"] == 114000
    # boss_workbench 今日成本与 ledger by_day 同源
    kpis = {k["label"]: k for k in overview["boss_workbench"]["kpis"]}
    assert kpis["今日成本"]["value"] == 5.46


def test_bi_overview_wires_unit_economics_and_ai_quality_values(bi_service: BIService) -> None:
    """P2-F3/F4: 已注册指标必须有 value 承载（可为 null 但键必须在）。"""
    overview = asyncio.run(bi_service.get_overview(days=7))
    ue = overview["unit_economics"]
    assert "value" in ue
    assert ue["value"] == ue["cost_per_effective_learning_usd"]
    assert ue["value"] is not None and ue["value"] > 0
    aiq = overview["ai_quality"]
    assert aiq["value"] == aiq["engineering_success_rate"]
    dt = overview["data_trust"]
    assert "value" in dt  # v1 显式 null + 状态，禁止缺键
    behavior_modules = [m for m in dt["degraded_modules"] if m["id"] == "product_behavior"]
    assert behavior_modules and behavior_modules[0]["status"] == "pending"


def test_bi_all_emitted_card_labels_resolve_to_registry(bi_service: BIService) -> None:
    """P2-F5 contract: 任何 payload 卡片标签必须可经注册表 label/alias 解析。"""
    from deeptutor.services.bi_metrics import BI_METRICS

    known: set[str] = set()
    for metric in BI_METRICS:
        known.add(metric.label)
        known.update(metric.label_aliases)

    overview = asyncio.run(bi_service.get_overview(days=7))
    cost = asyncio.run(bi_service.get_cost_stats(days=7))
    members = asyncio.run(bi_service.get_member_stats(days=7))
    labels: list[str] = []
    for payload in (overview, cost, members):
        labels.extend(card.get("label") for card in payload.get("cards") or [])
    labels.extend(k.get("label") for k in overview["boss_workbench"]["kpis"])
    unregistered = sorted({label for label in labels if label and label not in known})
    assert unregistered == [], f"注册表外标签: {unregistered}"
    # 所有卡片必须携带可解析的 metric_id
    from deeptutor.services.bi_metrics import metric_by_id

    for payload in (overview, cost, members):
        for card in payload.get("cards") or []:
            assert card.get("metric_id"), card
            metric_by_id(card["metric_id"])
