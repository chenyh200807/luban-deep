from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

import pytest

import deeptutor.services.bi_service as bi_service_module
from deeptutor.services.bi_service import BIService
from deeptutor.services.observability.usage_ledger import UsageLedger
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def _seeded_ledger(tmp_path: Path, *costs: float) -> UsageLedger:
    """P2 收权后成本唯一来源是 UsageLedger；测试显式注入 tmp ledger 保证隔离。"""
    ledger = UsageLedger(db_path=tmp_path / "llm_usage_test.db")
    for index, cost in enumerate(costs):
        ledger.record_usage_event(
            usage_source="provider",
            usage_details={"input": 100.0, "output": 50.0, "total": 150.0},
            cost_details={"total": cost, "currency": "USD"},
            model="deepseek-v4-flash",
            metadata={"provider_name": "dashscope"},
            turn_id=f"ledger_turn_{index}",
        )
    return ledger


class _QuietMemberService:
    def get_dashboard(self, days: int = 30) -> dict[str, object]:
        return {
            "total_count": 0,
            "active_count": 0,
            "expiring_soon_count": 0,
            "new_today_count": 0,
            "new_7d_count": 0,
            "new_30d_count": 0,
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
                    "created_at": "2026-06-22T10:00:00+08:00",
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
                    "created_at": "2026-06-22T10:00:00+08:00",
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


class _BiProjectionMemberService(_QuietMemberService):
    def list_members_for_bi(self) -> list[dict[str, object]]:
        return [
            {
                "user_id": "member_projection",
                "canonical_user_id": "member_projection",
                "alias_user_ids": ["member_projection"],
                "phone": "15558866509",
                "tier": "svip",
                "status": "active",
                "risk_level": "low",
                "auto_renew": True,
                "created_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "2026-05-20T10:00:00+08:00",
                "last_active_at": "2026-04-22T10:00:00+08:00",
                "chapter_mastery": {
                    "施工组织": {"name": "施工组织", "mastery": 62},
                },
            },
            {
                "user_id": "member_no_mastery",
                "canonical_user_id": "member_no_mastery",
                "alias_user_ids": ["member_no_mastery"],
                "phone": "15558866510",
                "tier": "trial",
                "status": "active",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "2026-05-20T10:00:00+08:00",
                "last_active_at": "2026-04-22T10:00:00+08:00",
            },
        ]

    def get_member_360(self, user_id: str) -> dict[str, object]:
        raise AssertionError(f"BI aggregate must not load heavyweight member 360: {user_id}")


class _RecentMemberProjectionService(_QuietMemberService):
    def list_members_for_bi(self) -> list[dict[str, object]]:
        now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))

        def _member(user_id: str, *, days_ago: int, phone: str = "15558866508") -> dict[str, object]:
            return {
                "user_id": user_id,
                "canonical_user_id": user_id,
                "alias_user_ids": [user_id],
                "phone": phone,
                "tier": "trial",
                "status": "active",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": (now - timedelta(days=days_ago)).isoformat(),
                "expire_at": (now + timedelta(days=60)).isoformat(),
                "last_active_at": now.isoformat(),
            }

        return [
            _member("member_today", days_ago=0),
            _member("member_3d", days_ago=3, phone="15558866509"),
            _member("member_20d", days_ago=20, phone="15558866510"),
            _member("member_40d", days_ago=40, phone="15558866511"),
            _member("internal_no_phone", days_ago=0, phone=""),
        ]


class _CommerceMemberService(_QuietMemberService):
    def list_members_for_bi(self) -> list[dict[str, object]]:
        return [
            {
                "user_id": "legacy_member_1",
                "canonical_user_id": "legacy_member_1",
                "alias_user_ids": ["legacy_member_1"],
                "phone": "15558866511",
                "tier": "trial",
                "status": "active",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "2026-05-20T10:00:00+08:00",
                "last_active_at": "2026-04-22T10:00:00+08:00",
                "points_balance": 120,
                "ledger": [
                    {
                        "id": "legacy_signup_bonus",
                        "delta": 120,
                        "reason": "signup_bonus",
                        "created_at": "2026-06-22T10:00:00+08:00",
                    }
                ],
            }
        ]

    @staticmethod
    def _default_packages() -> list[dict[str, object]]:
        return [
            {
                "id": "advance",
                "label": "精学版",
                "points": 4400,
                "price": "99",
            }
        ]


class _UnconfiguredWalletService:
    is_configured = False


def test_registered_member_identity_index_supports_trace_aliases_without_unmapped_ids() -> None:
    service = BIService(member_service=_QuietMemberService())
    service._load_all_members = lambda: [
        {
            "user_id": "wx_live_alias",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "external_auth_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "alias_user_ids": ["legacy_chat_user_1"],
            "phone": "13912345678",
            "wx_openid": "oTHl56liveOpenid",
            "wx_unionid": "union_live_user",
        }
    ]

    identity_index = service._registered_member_identity_index()

    assert identity_index["wx_live_alias"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert identity_index["legacy_chat_user_1"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert identity_index["oTHl56liveOpenid"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert identity_index["13912345678"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert "72af0948-a253-45b8-8b3b-a9eba9e5a1d6" not in identity_index


def test_member_stats_groups_channels_from_identity_metadata() -> None:
    """渠道归因读侧：get_member_stats 按 identity_metadata.reg_channel 分组（总量+窗口内新增）。"""
    service = BIService(member_service=_QuietMemberService())
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=1)).isoformat()
    stale = (now - timedelta(days=45)).isoformat()
    service._load_all_members = lambda: [
        {
            "user_id": "m1",
            "phone": "15558866501",
            "tier": "trial",
            "status": "active",
            "created_at": recent,
            "identity_metadata": {"reg_channel": "test1", "reg_scene": "1047"},
        },
        {
            "user_id": "m2",
            "phone": "15558866502",
            "tier": "trial",
            "status": "active",
            "created_at": recent,
            "identity_metadata": {"reg_channel": "test1"},
        },
        {
            "user_id": "m3",
            "phone": "15558866503",
            "tier": "vip",
            "status": "active",
            "created_at": stale,
            "identity_metadata": {},
        },
    ]

    stats = asyncio.run(service.get_member_stats(days=30))

    channels = {row["channel"]: row for row in stats["channels"]}
    assert channels["test1"]["count"] == 2
    assert channels["test1"]["new_count"] == 2
    assert channels["unknown"]["count"] == 1
    assert channels["unknown"]["new_count"] == 0
    assert stats["attribution"]["coverage_rate"] == pytest.approx(2 / 3, abs=0.0001)
    assert stats["registration_scenes"] == [
        {"scene": "1047", "count": 1, "label": "1047", "value": 1}
    ]


def test_member_stats_channels_all_unknown_when_no_attribution() -> None:
    """上线第一天真实形态：存量成员 metadata 全空/缺键，渠道分组必须全归 unknown，
    不崩不除零，且分组计数总和 == 成员总数。"""
    service = BIService(member_service=_QuietMemberService())
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=1)).isoformat()
    stale = (now - timedelta(days=45)).isoformat()
    service._load_all_members = lambda: [
        # metadata 键存在但为空 dict（生产存量行的形态）
        {
            "user_id": "m1",
            "phone": "15558866501",
            "tier": "trial",
            "status": "active",
            "created_at": recent,
            "identity_metadata": {},
        },
        # identity_metadata 键整个缺失
        {
            "user_id": "m2",
            "phone": "15558866502",
            "tier": "trial",
            "status": "active",
            "created_at": recent,
        },
        # identity_metadata 为 None
        {
            "user_id": "m3",
            "phone": "15558866503",
            "tier": "vip",
            "status": "active",
            "created_at": stale,
            "identity_metadata": None,
        },
    ]

    stats = asyncio.run(service.get_member_stats(days=30))

    assert stats["channels"] == [
        {"channel": "unknown", "count": 3, "new_count": 2, "label": "unknown", "value": 3}
    ]
    assert sum(row["count"] for row in stats["channels"]) == 3
    assert stats["attribution"] == {
        "authority": "member_directory.identity_metadata.reg_channel",
        "status": "degraded",
        "member_count": 3,
        "attributed_count": 0,
        "unattributed_count": 3,
        "coverage_rate": 0.0,
        "unknown_semantics": "unattributed_not_organic",
        "historical_recovery": "unavailable_without_auditable_campaign_mapping",
    }


def test_member_stats_channels_empty_when_no_members() -> None:
    """零成员时渠道分组返回空列表，不崩不除零。"""
    service = BIService(member_service=_QuietMemberService())
    service._load_all_members = lambda: []

    stats = asyncio.run(service.get_member_stats(days=30))

    assert stats["channels"] == []


class _SignupBonusWalletService:
    is_configured = True

    def list_recent_wallet_ledger(self, *, limit: int = 100, offset: int = 0):
        rows = [
            SimpleNamespace(
                id="wallet_signup_bonus",
                user_id="legacy_member_1",
                event_type="grant",
                delta_micros=120_000_000,
                balance_after_micros=120_000_000,
                frozen_after_micros=0,
                reference_type="signup_bonus",
                reference_id="legacy_member_1",
                idempotency_key="signup_bonus:legacy_member_1:member_console_bootstrap",
                metadata={"source": "member_console_auth_bootstrap"},
                created_at="2026-06-22T10:00:00+08:00",
            ),
            SimpleNamespace(
                id="wallet_usage",
                user_id="legacy_member_1",
                event_type="usage",
                delta_micros=-20_000_000,
                balance_after_micros=100_000_000,
                frozen_after_micros=0,
                reference_type="usage",
                reference_id="turn_1",
                idempotency_key="usage:turn_1",
                metadata={"capability": "deep_question"},
                created_at="2026-06-22T11:00:00+08:00",
            ),
        ]
        return rows[offset : offset + limit]


class _ErrorWalletService:
    is_configured = True

    def list_recent_wallet_ledger(self, *, limit: int = 100, offset: int = 0):
        raise RuntimeError("raw wallet URL should not be shown: https://example.invalid/rest/v1/wallet_ledger")


class _ManualMembershipRevenueWalletService:
    is_configured = True

    def list_recent_wallet_ledger(self, *, limit: int = 100, offset: int = 0):
        now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        rows = [
            SimpleNamespace(
                id="ledger_manual_membership_today",
                user_id="member_paid_today",
                event_type="grant",
                delta_micros=9_000_000_000,
                balance_after_micros=9_000_000_000,
                frozen_after_micros=0,
                reference_type="purchase",
                reference_id="manual_membership_today",
                idempotency_key="purchase:manual_membership:today",
                metadata={
                    "channel": "manual_membership",
                    "amount_cny": 198,
                    "package_id": "vip",
                    "tier": "vip",
                },
                created_at=now.isoformat(),
            ),
            SimpleNamespace(
                id="ledger_manual_membership_old",
                user_id="member_paid_old",
                event_type="grant",
                delta_micros=28_000_000_000,
                balance_after_micros=28_000_000_000,
                frozen_after_micros=0,
                reference_type="purchase",
                reference_id="manual_membership_old",
                idempotency_key="purchase:manual_membership:old",
                metadata={
                    "channel": "manual_membership",
                    "amount_cny": 598,
                    "package_id": "svip",
                    "tier": "svip",
                },
                created_at=(now - timedelta(days=3)).isoformat(),
            ),
            SimpleNamespace(
                id="ledger_signup_bonus_no_revenue",
                user_id="member_paid_today",
                event_type="grant",
                delta_micros=120_000_000,
                balance_after_micros=9_120_000_000,
                frozen_after_micros=0,
                reference_type="signup_bonus",
                reference_id="member_paid_today",
                idempotency_key="signup_bonus:member_paid_today",
                metadata={"amount_cny": 999},
                created_at=now.isoformat(),
            ),
        ]
        return rows[offset : offset + limit]


@pytest.fixture
def store(tmp_path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(db_path=tmp_path / "bi-limits.db")


def test_commerce_does_not_count_legacy_credit_as_recharge(store: SQLiteSessionStore) -> None:
    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_UnconfiguredWalletService(),
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["authority"]["wallet_ledger"] == "member_console.ledger"
    assert payload["authority"]["recharge_records"] == "pending_payment_order_authority"
    assert payload["summary"]["ledger_count"] == 1
    assert payload["summary"]["member_count"] == 0
    assert payload["summary"]["recharge_count"] == 0
    assert payload["summary"]["revenue_status"] == "authority_unavailable"
    assert payload["recharge_records"] == []
    assert payload["ledger"][0]["kind"] == "credit"
    assert any("不计入充值记录" in warning for warning in payload["warnings"])


def test_commerce_does_not_count_wallet_signup_bonus_as_recharge(store: SQLiteSessionStore) -> None:
    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_SignupBonusWalletService(),
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["authority"]["wallet_ledger"] == "wallet_ledger"
    assert payload["authority"]["recharge_records"] == "pending_payment_order_authority"
    assert payload["summary"]["ledger_count"] == 2
    assert payload["summary"]["member_count"] == 0
    assert payload["summary"]["recharge_count"] == 0
    assert payload["recharge_records"] == []
    assert any("不计入充值记录" in warning for warning in payload["warnings"])


def test_commerce_summarizes_manual_membership_revenue_from_wallet_ledger(
    store: SQLiteSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 6, 25, 12, 0, tzinfo=timezone(timedelta(hours=8)))
            return value.astimezone(tz) if tz else value

    monkeypatch.setattr(bi_service_module, "datetime", _FixedDatetime)
    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_ManualMembershipRevenueWalletService(),
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["authority"]["wallet_ledger"] == "wallet_ledger"
    assert payload["summary"]["recharge_count"] == 2
    assert payload["summary"]["revenue_cny"] == 796
    assert payload["summary"]["revenue_status"] == "confirmed_manual_partial"
    assert payload["summary"]["revenue_scope"] == "wallet_ledger_settled_purchases_partial"
    assert payload["summary"]["today_revenue_cny"] == 198
    assert payload["summary"]["recent_revenue_cny"] == 796
    assert payload["summary"]["latest_revenue_amount_cny"] == 198
    assert payload["summary"]["latest_revenue_member_id"] == "member_paid_today"
    assert payload["summary"]["latest_revenue_at"]
    assert payload["summary"]["revenue_count"] == 2


def test_commerce_does_not_present_unknown_recharge_amount_as_zero(
    store: SQLiteSessionStore,
) -> None:
    unknown_amount_row = {
        "id": "manual-recharge-without-amount",
        "user_id": "member_unknown_amount",
        "kind": "credit",
        "amount": 100,
        "event_type": "grant",
        "reference_type": "purchase",
        "reference_id": "manual-membership-without-amount",
        "idempotency_key": "purchase:manual-membership-without-amount",
        "effective_at": "2026-07-22T10:00:00+08:00",
        "metadata": {"channel": "manual_membership"},
        "authority": "wallet_ledger",
    }
    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_SignupBonusWalletService(),
    )
    service._load_commerce_wallet_ledger_rows = (  # type: ignore[method-assign]
        lambda *, limit: ("ok", [unknown_amount_row], "")
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["summary"]["revenue_status"] == "insufficient_evidence"
    assert payload["summary"]["revenue_count"] == 0
    assert payload["summary"]["revenue_cny"] == 0
    assert payload["summary"]["recharge_count"] == 1


def test_commerce_retains_reversal_rows_in_integrated_revenue_summary(
    store: SQLiteSessionStore,
) -> None:
    common = {
        "user_id": "member_reversed",
        "effective_at": "2026-07-22T10:00:00+08:00",
        "authority": "wallet_ledger",
    }
    rows = [
        {
            **common,
            "id": "purchase",
            "kind": "credit",
            "amount": 100,
            "event_type": "grant",
            "reference_type": "purchase",
            "reference_id": "purchase",
            "idempotency_key": "purchase:manual-membership",
            "metadata": {"channel": "manual_membership", "amount_cny": 198},
        },
        {
            **common,
            "id": "reversal",
            "kind": "refund",
            "amount": -100,
            "event_type": "refund",
            "reference_type": "refund",
            "reference_id": "purchase",
            "idempotency_key": "reversal",
            "metadata": {"channel": "manual_membership_reversal", "amount_cny": -198},
        },
    ]
    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_SignupBonusWalletService(),
    )
    service._load_commerce_wallet_ledger_rows = (  # type: ignore[method-assign]
        lambda *, limit: ("ok", rows, "")
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["summary"]["revenue_status"] == "confirmed_manual_partial"
    assert payload["summary"]["revenue_cny"] == 0
    assert payload["summary"]["revenue_count"] == 2
    assert payload["summary"]["reversal_count"] == 1


def test_commerce_excludes_pre_launch_wallet_ledger_rows(
    store: SQLiteSessionStore,
) -> None:
    class _LaunchBoundaryWalletService:
        is_configured = True

        def list_recent_wallet_ledger(self, *, limit: int = 100, offset: int = 0):
            rows = [
                SimpleNamespace(
                    id="ledger_pre_launch_purchase",
                    user_id="legacy_member_1",
                    event_type="grant",
                    delta_micros=50_000_000_000,
                    balance_after_micros=50_000_000_000,
                    frozen_after_micros=0,
                    reference_type="purchase",
                    reference_id="manual_membership_pre_launch",
                    idempotency_key="purchase:manual_membership:pre_launch",
                    metadata={"channel": "manual_membership", "amount_cny": 998},
                    created_at="2026-06-21T23:59:59+08:00",
                ),
                SimpleNamespace(
                    id="ledger_launch_purchase",
                    user_id="legacy_member_1",
                    event_type="grant",
                    delta_micros=9_000_000_000,
                    balance_after_micros=59_000_000_000,
                    frozen_after_micros=0,
                    reference_type="purchase",
                    reference_id="manual_membership_launch",
                    idempotency_key="purchase:manual_membership:launch",
                    metadata={"channel": "manual_membership", "amount_cny": 198},
                    created_at="2026-06-22T00:00:00+08:00",
                ),
            ]
            return rows[offset : offset + limit]

    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_LaunchBoundaryWalletService(),
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["summary"]["operational_start_at"] == "2026-06-22T00:00:00+08:00"
    assert payload["summary"]["ledger_count"] == 1
    assert payload["summary"]["recharge_count"] == 1
    assert payload["summary"]["revenue_cny"] == 198
    assert payload["summary"]["latest_revenue_amount_cny"] == 198
    assert [row["id"] for row in payload["ledger"]] == ["ledger_launch_purchase"]
    assert [row["ledger_event_id"] for row in payload["recharge_records"]] == ["ledger_launch_purchase"]


def test_commerce_today_revenue_uses_china_business_day() -> None:
    china_tz = timezone(timedelta(hours=8))
    effective_at = datetime(2026, 6, 14, 0, 30, tzinfo=china_tz)

    summary = BIService._build_commerce_revenue_summary(
        [
            {
                "id": "ledger_china_today",
                "user_id": "member_china_today",
                "amount": 9000,
                "reference_type": "purchase",
                "idempotency_key": "purchase:manual_membership:china_today",
                "effective_at": effective_at.isoformat(),
                "metadata": {"amount_cny": 198},
            }
        ],
        now=datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
    )

    assert summary["today_revenue_cny"] == 198


def test_commerce_reversal_offsets_manual_membership_revenue() -> None:
    china_tz = timezone(timedelta(hours=8))
    purchase_at = datetime(2026, 6, 14, 9, 0, tzinfo=china_tz)
    reversal_at = datetime(2026, 6, 14, 9, 5, tzinfo=china_tz)

    summary = BIService._build_commerce_revenue_summary(
        [
            {
                "id": "ledger_supreme_purchase",
                "user_id": "member_supreme",
                "amount": 50000,
                "event_type": "grant",
                "reference_type": "purchase",
                "reference_id": "manual_membership_supreme",
                "idempotency_key": "purchase:manual_membership:supreme",
                "effective_at": purchase_at.isoformat(),
                "metadata": {"amount_cny": 998, "tier": "supreme_svip"},
            },
            {
                "id": "ledger_supreme_reversal",
                "user_id": "member_supreme",
                "amount": -50000,
                "event_type": "refund",
                "reference_type": "refund",
                "reference_id": "manual_membership_supreme",
                "idempotency_key": "refund:manual_membership:reversal",
                "effective_at": reversal_at.isoformat(),
                "metadata": {
                    "amount_cny": -998,
                    "tier": "supreme_svip",
                    "channel": "manual_membership_reversal",
                },
            },
        ],
        now=datetime(2026, 6, 14, 12, 0, tzinfo=china_tz),
    )

    assert summary["revenue_cny"] == 0
    assert summary["today_revenue_cny"] == 0
    assert summary["recent_revenue_cny"] == 0
    assert summary["latest_revenue_amount_cny"] == -998
    assert summary["latest_revenue_member_id"] == "member_supreme"
    assert summary["latest_revenue_at"] == reversal_at.isoformat()
    assert summary["revenue_count"] == 2
    assert summary["reversal_count"] == 1


def test_commerce_uses_managed_membership_packages(store: SQLiteSessionStore) -> None:
    class _ManagedPackageMemberService(_CommerceMemberService):
        @staticmethod
        def list_membership_packages() -> list[dict[str, object]]:
            return [
                {
                    "id": "svip_plus",
                    "label": "SVIP Plus",
                    "tier": "svip",
                    "points": 36000,
                    "turns": 1800,
                    "price": "698",
                    "original_price": "898",
                    "badge": "高频答疑",
                    "per": "1800 次 AI 学习额度",
                    "desc": "AI答疑、案例批改、错因专训、班主任督学服务",
                    "status": "active",
                }
            ]

        @staticmethod
        def get_wallet(_user_id: str) -> dict[str, object]:
            return {"packages": [{"id": "wallet_legacy", "label": "旧投影", "points": 1, "price": "1"}]}

    service = BIService(
        session_store=store,
        member_service=_ManagedPackageMemberService(),
        wallet_service=_UnconfiguredWalletService(),
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["authority"]["packages"] == "member_console.packages"
    assert payload["packages"][0]["id"] == "svip_plus"
    assert payload["packages"][0]["turns"] == 1800
    assert payload["packages"][0]["badge"] == "高频答疑"


def test_commerce_sanitizes_wallet_reader_errors(store: SQLiteSessionStore) -> None:
    service = BIService(
        session_store=store,
        member_service=_CommerceMemberService(),
        wallet_service=_ErrorWalletService(),
    )

    payload = asyncio.run(service.get_commerce(limit=10))

    assert payload["summary"]["revenue_status"] == "authority_unavailable"
    assert any("RuntimeError" in warning for warning in payload["warnings"])
    assert not any("https://" in warning for warning in payload["warnings"])


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


def test_boss_workbench_exposes_daily_cost_from_usage_ledger(
    store: SQLiteSessionStore, tmp_path: Path
) -> None:
    service = BIService(
        session_store=store,
        member_service=_RegisteredMemberService(),
        usage_ledger=_seeded_ledger(tmp_path, 0.125),
    )

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

    assert boss["daily_cost"]["today_usd"] is None
    assert boss["daily_cost"]["window_total_usd"] is None
    assert boss["daily_cost"]["status"] == "insufficient_turn_linkage"
    assert overview["summary"]["platform_cost_by_currency"] == {"USD": 0.125}
    assert boss["daily_cost"]["source"] == "usage_ledger"
    assert any(item["label"] == "今日成本" for item in boss["kpis"])


def test_boss_workbench_counts_only_registered_member_activity(
    store: SQLiteSessionStore, tmp_path: Path
) -> None:
    # 经营成本只认同一 turn-id cohort；未关联 ledger 事件只保留在平台成本中。
    service = BIService(
        session_store=store,
        member_service=_RegisteredMemberService(),
        usage_ledger=_seeded_ledger(tmp_path, 0.1, 0.2),
    )

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

    context_loads = 0
    member_loads = 0
    original_load_context = service._load_context
    original_load_members = service._load_all_members

    async def _count_context_loads(days: int):
        nonlocal context_loads
        context_loads += 1
        return await original_load_context(days)

    service._load_context = _count_context_loads  # type: ignore[method-assign]

    def _count_member_loads():
        nonlocal member_loads
        member_loads += 1
        return original_load_members()

    service._load_all_members = _count_member_loads  # type: ignore[method-assign]
    overview = asyncio.run(service.get_overview(days=7))
    assert context_loads == 1
    assert member_loads == 1
    assert sum(point["sessions"] for point in overview["active_trend"]["points"]) == 2
    assert max(point["active"] for point in overview["active_trend"]["points"]) == 1

    trend = asyncio.run(service.get_active_trend(days=7))

    assert overview["summary"]["total_sessions"] == 2
    assert overview["summary"]["active_learners"] == 1
    assert overview["summary"]["total_turns"] == 2
    assert overview["summary"]["success_turn_rate"] == 100
    assert overview["boss_workbench"]["daily_cost"]["window_total_usd"] is None
    assert overview["summary"]["platform_cost_by_currency"] == {"USD": 0.3}
    assert not any("失败回合" in item for item in overview["risk_alerts"])
    assert sum(point["sessions"] for point in trend["points"]) == 2
    assert max(point["active"] for point in trend["points"]) == 1


def test_business_bi_endpoints_share_registered_turn_scope(
    store: SQLiteSessionStore, tmp_path: Path
) -> None:
    service = BIService(
        session_store=store,
        member_service=_RegisteredMemberService(),
        usage_ledger=_seeded_ledger(tmp_path, 0.25),
    )

    async def _create_session(session_id: str, user_id: str, *, status: str, cost: float) -> None:
        session = await store.create_session(title=session_id, session_id=session_id)
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": user_id,
                "knowledge_bases": ["construction-exam"],
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.append_turn_event(
            turn["id"],
            {
                "type": "tool_call",
                "content": "rag",
                "metadata": {"args": {"query": session_id}},
            },
        )
        await store.append_turn_event(
            turn["id"],
            {"type": "tool_result", "metadata": {"tool": "rag"}},
        )
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
        await _create_session("eval_probe", "qa_eval_turn_scope", status="completed", cost=8.8)

    asyncio.run(_seed())

    overview = asyncio.run(service.get_overview(days=7))
    capabilities = asyncio.run(service.get_capability_stats(days=7))
    tools = asyncio.run(service.get_tool_stats(days=7))
    knowledge = asyncio.run(service.get_knowledge_stats(days=7))
    anomalies = asyncio.run(service.get_anomalies(days=7))

    assert overview["summary"]["total_turns"] == sum(
        item["turns"] for item in capabilities["items"]
    ) == 1
    assert [item["capability"] for item in capabilities["items"]] == ["chat"]
    assert tools["items"] == [
        {
            "tool_name": "rag",
            "label": "rag",
            "value": 1,
            "calls": 1,
            "result_events": 1,
            "turns_with_tool": 1,
            "success_rate": 100.0,
            "avg_cost_per_turn_usd": 0.25,
            "avg_tokens_per_turn": 100.0,
            "hint": "成功率 100.0%",
            "secondary": "均成本 $0.25",
            "capabilities": [{"capability": "chat", "count": 2}],
            "entrypoints": [{"entrypoint": "wx_miniprogram", "count": 2}],
        }
    ]
    assert knowledge["items"][0]["kb_name"] == "construction-exam"
    assert knowledge["items"][0]["session_count"] == 1
    assert knowledge["items"][0]["rag_turns"] == 1
    assert {item["session_id"] for item in anomalies["items"]} == {"real_member"}

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
    commerce = asyncio.run(service.get_commerce(limit=500))
    assert overview["unit_economics"]["revenue_status"] == commerce["summary"]["revenue_status"]
    assert overview["unit_economics"]["revenue_status"] != "pending"
    assert overview["unit_economics"]["cost_per_effective_learning_usd"] is None
    assert overview["unit_economics"]["value"] is None
    assert overview["summary"]["platform_cost_by_currency"] == {"USD": 0.25}
    assert overview["teaching_effect"]["chapter_progress"][0]["name"] == "地基基础"
    assert overview["teaching_effect"]["chapter_progress"][0]["mastery"] == 58
    assert overview["teaching_effect"]["chapter_progress"][0]["member_count"] == 1
    assert all(item["name"] != "内部压测" for item in overview["teaching_effect"]["chapter_progress"])
    assert overview["data_trust"]["status"] == "degraded"
    behavior_module = next(
        item for item in overview["data_trust"]["degraded_modules"]
        if item["id"] == "product_behavior"
    )
    assert behavior_module["status"] != "pending"
    assert all(
        {"metric_id", "label", "definition", "authority", "trust_level", "owner", "drilldown"}
        <= set(metric)
        for metric in overview["data_trust"]["metric_definitions"]
    )


def test_business_turn_window_uses_created_at_not_updated_at(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_RegisteredMemberService())

    async def _seed() -> tuple[str, str]:
        session = await store.create_session(title="Window", session_id="window_session")
        await store.update_session_preferences(
            session["id"],
            {"source": "wx_miniprogram", "user_id": "member_1"},
        )
        old_turn = await store.create_turn(session["id"], capability="chat")
        await store.update_turn_status(old_turn["id"], "completed")
        new_turn = await store.create_turn(session["id"], capability="deep_question")
        await store.update_turn_status(new_turn["id"], "completed")
        return old_turn["id"], new_turn["id"]

    old_turn_id, new_turn_id = asyncio.run(_seed())
    now = time.time()
    outside_window = now - (8 * 86400)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE turns SET created_at = ?, updated_at = ? WHERE id = ?",
            (outside_window, now, old_turn_id),
        )
        conn.execute(
            "UPDATE turns SET created_at = ?, updated_at = ? WHERE id = ?",
            (now, outside_window, new_turn_id),
        )
        conn.commit()

    overview = asyncio.run(service.get_overview(days=7))
    capabilities = asyncio.run(service.get_capability_stats(days=7))

    assert overview["summary"]["total_turns"] == 1
    assert [(item["capability"], item["turns"]) for item in capabilities["items"]] == [
        ("deep_question", 1)
    ]
    assert overview["active_trend"]["points"][0]["turns"] == 1


def test_cost_and_capability_share_registered_turn_scope(
    store: SQLiteSessionStore, tmp_path: Path
) -> None:
    ledger = UsageLedger(db_path=tmp_path / "scoped_usage.db")
    service = BIService(
        session_store=store,
        member_service=_RegisteredMemberService(),
        usage_ledger=ledger,
    )

    async def _seed() -> tuple[str, str]:
        real_session = await store.create_session(title="real", session_id="real_cost")
        await store.update_session_preferences(
            real_session["id"], {"user_id": "member_1", "source": "wx_miniprogram"}
        )
        real_turn = await store.create_turn(real_session["id"], capability="chat")
        await store.update_turn_status(real_turn["id"], "completed")
        anon_session = await store.create_session(title="anon", session_id="anon_cost")
        anon_turn = await store.create_turn(anon_session["id"], capability="deep_question")
        await store.update_turn_status(anon_turn["id"], "completed")
        return real_turn["id"], anon_turn["id"]

    real_turn_id, anon_turn_id = asyncio.run(_seed())
    for turn_id, cost in ((real_turn_id, 0.25), (anon_turn_id, 7.70), ("", 9.0)):
        ledger.record_usage_event(
            usage_source="provider",
            usage_details={"input": 100, "output": 50, "total": 150},
            cost_details={"total": cost, "currency": "USD"},
            model="deepseek-v4-flash",
            metadata={"provider_name": "dashscope", "billing_currency": "USD"},
            turn_id=turn_id,
        )

    overview = asyncio.run(service.get_overview(days=7))
    capabilities = asyncio.run(service.get_capability_stats(days=7))
    costs = asyncio.run(service.get_cost_stats(days=7))
    total_cost_card = next(card for card in costs["cards"] if card["label"] == "总成本")
    avg_cost_card = next(card for card in costs["cards"] if card["label"] == "平均回合成本")

    assert overview["summary"]["total_turns"] == 1
    assert sum(item["turns"] for item in capabilities["items"]) == 1
    assert costs["business_turn_count"] == 1
    assert costs["business_turns_with_usage"] == 1
    assert total_cost_card["value"] == 0.25
    assert avg_cost_card["value"] == 0.25
    assert costs["business_scope"]["currency_amounts"] == {"USD": 0.25}
    assert costs["platform_scope"]["currency_amounts"] == {"USD": 16.95}
    assert overview["summary"]["total_cost_usd"] == 0.25


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


def test_member_stats_uses_lightweight_bi_projection_not_member_360(
    store: SQLiteSessionStore,
) -> None:
    service = BIService(session_store=store, member_service=_BiProjectionMemberService())

    stats = asyncio.run(service.get_member_stats(days=30))

    assert stats["dashboard"]["total_count"] == 2
    assert stats["chapter_progress"] == [
        {
            "chapter_id": "施工组织",
            "name": "施工组织",
            "mastery": 62,
            "member_count": 1,
            "status": "stable",
            "evidence": "1 名真实会员样本平均掌握度 62%",
        }
    ]


def test_member_stats_counts_recent_registered_members_by_created_window(
    store: SQLiteSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 8, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))
            return value.astimezone(tz) if tz else value

    monkeypatch.setattr(bi_service_module, "datetime", _FixedDatetime)
    service = BIService(session_store=store, member_service=_RecentMemberProjectionService())

    stats = asyncio.run(service.get_member_stats(days=30))

    assert stats["dashboard"]["total_count"] == 4
    assert stats["dashboard"]["new_today_count"] == 1
    assert stats["dashboard"]["new_7d_count"] == 2
    assert stats["dashboard"]["new_30d_count"] == 3


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


def _inject_internal_account_rows(service: BIService, rows: list[dict[str, object]]) -> None:
    """在唯一 REST 读取边界（_supabase_internal_accounts）注入 bi_internal_accounts 行。

    rows 语义与生产一致：审计流水按 created_at.desc 排列，
    每个 user_id 的最新一行决定当前 is_internal 状态。
    """

    def _fake_rest(method: str, *, params: dict | None = None, body: dict | None = None):
        assert method == "GET"
        return rows

    service._supabase_internal_accounts = _fake_rest  # type: ignore[method-assign]


def test_member_dashboard_excludes_marked_internal_accounts(
    store: SQLiteSessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 断点防回归：bi_internal_accounts 里 is_internal=true 的账号必须从
    会员统计口径（total/new_today/new_7d/new_30d）消失；排除逻辑唯一收口在
    _load_all_members，最新一行为准（取消标记可恢复）。"""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 8, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))
            return value.astimezone(tz) if tz else value

    monkeypatch.setattr(bi_service_module, "datetime", _FixedDatetime)
    service = BIService(
        session_store=store,
        member_service=_RecentMemberProjectionService(),
        wallet_service=_UnconfiguredWalletService(),
    )
    _inject_internal_account_rows(
        service,
        [
            # member_3d：最新一行 is_internal=true → 排除
            {"user_id": "member_3d", "is_internal": True, "created_at": "2026-07-10T12:00:00+08:00"},
            # member_20d：曾标记为内部，但最新一行取消标记 → 保留
            {"user_id": "member_20d", "is_internal": False, "created_at": "2026-07-10T11:00:00+08:00"},
            {"user_id": "member_20d", "is_internal": True, "created_at": "2026-07-01T10:00:00+08:00"},
        ],
    )

    stats = asyncio.run(service.get_member_stats(days=30))

    # 未标记基线（见 test_member_stats_counts_recent_registered_members_by_created_window）：
    # total 4 / today 1 / 7d 2 / 30d 3。排除 member_3d 后：
    assert stats["dashboard"]["total_count"] == 3
    assert stats["dashboard"]["new_today_count"] == 1
    assert stats["dashboard"]["new_7d_count"] == 1
    assert stats["dashboard"]["new_30d_count"] == 2


def test_growth_funnel_retention_and_active_learners_exclude_internal_accounts(
    store: SQLiteSessionStore, tmp_path: Path
) -> None:
    """内部账号（按 alias 标记也算）不得出现在增长漏斗、留存 cohort 和活跃学习者里。"""

    async def _seed() -> None:
        session = await store.create_session(title="Internal Session", session_id="internal_session")
        await store.update_session_preferences(
            session["id"],
            {"source": "wx_miniprogram", "user_id": "member_1"},
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.update_turn_status(turn["id"], "completed")

    asyncio.run(_seed())

    def _service() -> BIService:
        return BIService(
            session_store=store,
            member_service=_RegisteredMemberService(),
            usage_ledger=_seeded_ledger(tmp_path, 0.1),
            wallet_service=_UnconfiguredWalletService(),
        )

    # 对照组（未标记）：会员计入漏斗，会话计入留存与活跃学习者。
    control = _service()
    _inject_internal_account_rows(control, [])
    control_overview = asyncio.run(control.get_overview(days=7))
    control_retention = asyncio.run(control.get_retention(days=7))
    control_registered = next(
        step for step in control_overview["growth_funnel"]["steps"] if step["id"] == "registered_members"
    )
    assert control_registered["value"] == 1
    assert control_overview["summary"]["active_learners"] == 1
    assert control_retention["cohorts"], "control cohorts must not be empty"

    # 实验组：通过 alias（wx_member_1）标记 member_1 为内部账号。
    marked = _service()
    _inject_internal_account_rows(
        marked,
        [{"user_id": "wx_member_1", "is_internal": True, "created_at": "2026-07-10T12:00:00+08:00"}],
    )
    marked_overview = asyncio.run(marked.get_overview(days=7))
    marked_retention = asyncio.run(marked.get_retention(days=7))
    marked_registered = next(
        step for step in marked_overview["growth_funnel"]["steps"] if step["id"] == "registered_members"
    )
    assert marked_registered["value"] == 0
    assert marked_overview["summary"]["active_learners"] == 0
    assert marked_retention["cohorts"] == []


def test_internal_account_exclusion_fails_open_when_marker_table_unavailable(
    store: SQLiteSessionStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """标记表读失败必须 fail-open：BI 短暂回到未清洗口径，不能整体不可用。

    fail-open 的告警必须是可观测实体：断言 deeptutor.services.bi_service
    logger 真的发出了含失败原因的 WARNING 记录，而不是注释里的"只告警"。"""
    service = BIService(
        session_store=store,
        member_service=_RegisteredMemberService(),
        wallet_service=_UnconfiguredWalletService(),
    )

    def _broken_rest(method: str, *, params: dict | None = None, body: dict | None = None):
        raise RuntimeError("bi_internal_accounts unavailable")

    service._supabase_internal_accounts = _broken_rest  # type: ignore[method-assign]

    with caplog.at_level(logging.WARNING, logger="deeptutor.services.bi_service"):
        stats = asyncio.run(service.get_member_stats(days=30))

    assert stats["dashboard"]["total_count"] == 1
    warning_records = [
        record
        for record in caplog.records
        if record.name == "deeptutor.services.bi_service"
        and record.levelno == logging.WARNING
        and "internal account exclusion unavailable, fail-open" in record.getMessage()
    ]
    assert warning_records, "fail-open path must emit an observable WARNING"
    assert "bi_internal_accounts unavailable" in warning_records[0].getMessage()
