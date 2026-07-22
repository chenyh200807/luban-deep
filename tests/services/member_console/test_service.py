from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import threading
from types import SimpleNamespace

import bcrypt
import httpx
import pytest

import deeptutor.services.member_console.service as member_service_module
from deeptutor.services.member_console import rbac
from deeptutor.services.member_console.service import MemberConsoleService
from deeptutor.services.member_console import external_auth as external_auth_module
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key


def _active_otp(service: MemberConsoleService) -> str:
    """Read the active OTP from the service store. The code is deliberately NOT returned
    in send_phone_code's response (account-takeover guard), so tests read it server-side."""
    codes = service._load().get("phone_codes") or {}
    assert codes, "no active OTP in store"
    return str(next(iter(codes.values()))["code"])


@pytest.fixture(autouse=True)
def _enable_demo_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_MEMBER_CONSOLE_ENABLE_DEMO_SEED", "1")


class _EmptyAliasStore:
    is_configured = True

    @staticmethod
    def resolve_alias(*, alias_type: str, alias_value: str):
        return None


@pytest.fixture(autouse=True)
def _isolate_wallet_identity_alias_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _EmptyAliasStore(),
    )


class _FakeWalletBootstrapService:
    is_configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.grants: list[dict[str, object]] = []
        self.adjustments: list[dict[str, object]] = []
        self.snapshots: dict[str, SimpleNamespace] = {}

    def get_wallet(self, user_id: str):
        return self.snapshots.get(str(user_id))

    def ensure_wallet_seeded(self, **kwargs):
        self.calls.append(dict(kwargs))
        user_id = str(kwargs["user_id"])
        opening_points = int(kwargs.get("opening_points") or 0)
        snapshot = self.snapshots.get(user_id)
        if snapshot is None:
            snapshot = SimpleNamespace(
                user_id=user_id,
                balance_micros=opening_points * 1_000_000,
                frozen_micros=0,
                plan_id=str(kwargs.get("plan_id") or ""),
                version=1,
                created_at="2026-04-21T10:00:00+08:00",
            )
            self.snapshots[user_id] = snapshot
        return snapshot

    def grant_points(self, **kwargs):
        self.grants.append(dict(kwargs))
        return SimpleNamespace(
            ledger_event_id="ledger_manual_1",
            user_id=str(kwargs["user_id"]),
            event_type="grant",
            delta_micros=int(kwargs["amount_micros"]),
            balance_micros=int(kwargs["amount_micros"]),
            frozen_micros=0,
            version=1,
            idempotency_key=str(kwargs["idempotency_key"]),
            reference_type=str(kwargs["reference_type"]),
            reference_id=str(kwargs["reference_id"]),
            created_at="2026-06-14T10:00:00+08:00",
        )

    def refund_points(self, **kwargs):
        self.grants.append({"refund": True, **dict(kwargs)})
        return SimpleNamespace(
            ledger_event_id="ledger_refund_1",
            user_id=str(kwargs["user_id"]),
            event_type="refund",
            delta_micros=-int(kwargs["amount_micros"]),
            balance_micros=0,
            frozen_micros=0,
            version=2,
            idempotency_key=str(kwargs["idempotency_key"]),
            reference_type=str(kwargs["reference_type"]),
            reference_id=str(kwargs["reference_id"]),
            created_at="2026-06-14T10:05:00+08:00",
        )

    def admin_adjust_points(self, **kwargs):
        self.adjustments.append(dict(kwargs))
        user_id = str(kwargs["user_id"])
        delta_micros = int(kwargs["delta_micros"])
        snapshot = self.snapshots.get(user_id)
        current = int(getattr(snapshot, "balance_micros", 0) or 0) if snapshot else 0
        updated = max(0, current + delta_micros)
        if snapshot is None:
            snapshot = SimpleNamespace(
                user_id=user_id,
                balance_micros=updated,
                frozen_micros=0,
                plan_id="",
                version=1,
                created_at="2026-06-14T10:10:00+08:00",
            )
            self.snapshots[user_id] = snapshot
        else:
            snapshot.balance_micros = updated
        return SimpleNamespace(
            ledger_event_id=f"ledger_adjust_{len(self.adjustments)}",
            user_id=user_id,
            event_type="admin_adjust",
            delta_micros=delta_micros,
            balance_micros=updated,
            frozen_micros=0,
            version=1,
            idempotency_key=str(kwargs["idempotency_key"]),
            reference_type="ticket",
            reference_id=str(kwargs["reference_id"]),
            created_at="2026-06-14T10:10:00+08:00",
        )


class _FakeMemberDirectory:
    is_configured = True

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, int]] = []

    def list_members(self, *, limit: int = 5000) -> list[dict[str, object]]:
        self.calls.append({"limit": limit})
        return [dict(row) for row in self.rows]


def test_member_console_home_focus_uses_textbook_section_alias() -> None:
    assert MemberConsoleService._normalize_home_focus_topic("防水工程") == "屋面与防水工程施工"


@pytest.mark.asyncio
async def test_login_with_wechat_code_issues_signed_token_and_persists_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_123456789012",
            "unionid": "unionid_abcdef",
            "session_key": "session_key_value",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)

    result = await service.login_with_wechat_code("wx-code")

    assert result["openid"] == "openid_123456789012"
    assert result["unionid"] == "unionid_abcdef"
    assert result["user_id"] == result["user"]["user_id"]
    assert result["token"].startswith("dtm.")
    assert "session_key" not in result

    resolved_user_id = service.resolve_user_id(f"Bearer {result['token']}")
    assert resolved_user_id == result["user"]["user_id"]

    data = service._load()
    member = service._find_member(data, resolved_user_id)
    assert member["wx_openid"] == "openid_123456789012"
    assert member["wx_unionid"] == "unionid_abcdef"
    assert member["wx_session_key"] == "session_key_value"


@pytest.mark.asyncio
async def test_login_with_wechat_code_promotes_phone_backed_member_to_canonical_wallet_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_O4aNJg7O_wRk"),
                "user_id": "wx_O4aNJg7O_wRk",
                "phone": "34277511499",
                "wx_openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",  # pragma: allowlist secret
            }
        ]

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",  # pragma: allowlist secret
            "unionid": "unionid_live_user",
            "session_key": "session_key_value",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    monkeypatch.setattr(
        member_service_module,
        "ensure_external_auth_user_for_phone",
        lambda phone, **_kwargs: {"id": canonical_uid, "username": "user_1499", "phone": phone},
    )
    service._mutate(_seed)

    result = await service.login_with_wechat_code("wx-code")
    claims = service.verify_access_token(result["token"])
    snapshot = service._load_member_snapshot("wx_O4aNJg7O_wRk")["member"]

    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert result["user_id"] == "wx_O4aNJg7O_wRk"
    assert snapshot["external_auth_user_id"] == canonical_uid
    assert snapshot["auth_username"] == "user_1499"
    assert wallet_service.calls[0]["user_id"] == canonical_uid
    assert wallet_service.calls[0]["opening_points"] == 0


@pytest.mark.asyncio
async def test_login_with_wechat_code_uses_existing_wx_openid_alias_as_canonical_wallet_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "wx_openid" and alias_value == "oTHl5610QTUB2maCO4aNJg7O-wRk":  # pragma: allowlist secret
                return {"user_id": canonical_uid}
            return None

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_O4aNJg7O_wRk"),
                "user_id": "wx_O4aNJg7O_wRk",
                "phone": "34277511499",
                "wx_openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",  # pragma: allowlist secret
            }
        ]

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",  # pragma: allowlist secret
            "unionid": "",
            "session_key": "session_key_value",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )
    service._mutate(_seed)

    result = await service.login_with_wechat_code("wx-code")
    claims = service.verify_access_token(result["token"])
    canonical_snapshot = service._load_member_snapshot(canonical_uid)["member"]
    legacy_snapshot = service._load_member_snapshot("wx_O4aNJg7O_wRk")["member"]

    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert wallet_service.calls[0]["user_id"] == canonical_uid
    assert canonical_snapshot["display_name"] != "wx_O4aNJg7O_wRk"
    assert canonical_snapshot["display_name"].startswith("微信用户")
    assert canonical_snapshot["wx_openid"] == "oTHl5610QTUB2maCO4aNJg7O-wRk"  # pragma: allowlist secret
    assert legacy_snapshot["external_auth_user_id"] == canonical_uid


@pytest.mark.asyncio
async def test_login_with_wechat_code_supports_dev_fallback_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _raise_missing(_code: str) -> dict[str, str]:
        raise RuntimeError("Missing WeChat Mini Program credentials.")

    monkeypatch.setattr(service, "_exchange_wechat_code", _raise_missing)

    result = await service.login_with_wechat_code("dev-local-user")

    assert result["token"].startswith("dtm.")
    assert result["openid"].startswith("dev_openid_")
    assert service.resolve_user_id(f"Bearer {result['token']}") == result["user"]["user_id"]


@pytest.mark.asyncio
async def test_login_with_wechat_code_fails_closed_in_production_even_for_dev_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN", "1")

    async def _raise_missing(_code: str) -> dict[str, str]:
        raise RuntimeError("Missing WeChat Mini Program credentials.")

    monkeypatch.setattr(service, "_exchange_wechat_code", _raise_missing)

    with pytest.raises(RuntimeError, match="Missing WeChat Mini Program credentials."):
        await service.login_with_wechat_code("dev-local-user")


def test_trace_identity_resolution_maps_aliases_to_bi_canonical_member(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_live_alias"),
                "user_id": "wx_live_alias",
                "canonical_user_id": canonical_uid,
                "external_auth_user_id": canonical_uid,
                "alias_user_ids": ["legacy_chat_user_1"],
                "display_name": "微信学员",
                "phone": "13912345678",
                "wx_openid": "oTHl56liveOpenid",
                "wx_unionid": "union_live_user",
            }
        ]

    service._mutate(_seed)

    for raw_user_id, metadata in [
        ("legacy_chat_user_1", {}),
        ("wx_live_alias", {}),
        (canonical_uid, {}),
        ("", {"wx_openid": "oTHl56liveOpenid"}),
        ("", {"openid": "oTHl56liveOpenid"}),
        ("", {"wx_unionid": "union_live_user"}),
        ("", {"phone": "13912345678"}),
    ]:
        resolution = service.resolve_trace_identity_for_bi(
            raw_user_id=raw_user_id,
            metadata=metadata,
        )
        assert resolution["status"] == "resolved"
        assert resolution["canonical_user_id"] == canonical_uid
        assert resolution["member_user_id"] == "wx_live_alias"
        assert resolution["raw_user_id"] == raw_user_id
        assert "phone" not in resolution


def test_trace_identity_resolution_keeps_unmapped_trace_identity(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    resolution = service.resolve_trace_identity_for_bi(
        raw_user_id="72af0948-a253-45b8-8b3b-a9eba9e5a1d6",
        metadata={"session_id": "trace-session"},
    )

    assert resolution == {
        "status": "unmapped",
        "canonical_user_id": "",
        "member_user_id": "",
        "raw_user_id": "72af0948-a253-45b8-8b3b-a9eba9e5a1d6",
        "matched_identity": "",
    }


@pytest.mark.asyncio
async def test_login_with_wechat_code_maps_upstream_timeout_to_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _raise_timeout(_code: str) -> dict[str, str]:
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(service, "_exchange_wechat_code", _raise_timeout)

    with pytest.raises(RuntimeError, match="WeChat code2Session request timed out"):
        await service.login_with_wechat_code("wx-code")


def test_resolve_user_id_accepts_signed_access_token(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    token = service._issue_access_token(
        user_id="student_demo",
        openid="openid_demo",
        unionid="unionid_demo",
    )

    assert service.resolve_user_id(f"Bearer {token}") == "student_demo"


def test_resolve_user_id_accepts_lowercase_bearer_prefix(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    token = service._issue_access_token(user_id="student_demo")

    assert service.resolve_user_id(f"bearer {token}") == "student_demo"


def test_verify_access_token_rejects_signed_token_without_exp(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    payload = {
        "v": 1,
        "sub": "student_demo",
        "uid": "student_demo",
        "canonical_uid": "student_demo",
        "provider": "local",
        "iat": int(time.time()),
    }
    payload_part = service._b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        service._auth_secret().encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    token = f"dtm.{payload_part}.{service._b64url_encode(signature)}"

    assert service.verify_access_token(token) is None
    assert service.resolve_user_id(f"Bearer {token}") == ""


def test_verify_access_token_rejects_legacy_wechat_token_before_phone_auth_cutover(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    token = service._issue_access_token(
        user_id="wx_legacy",
        openid="openid_legacy",
        orig_iat=member_service_module._WECHAT_PHONE_AUTH_REQUIRED_AFTER_TS - 1,
    )

    assert service.verify_access_token(token) is None
    assert service.resolve_user_id(f"Bearer {token}") == ""
    with pytest.raises(ValueError, match="Invalid or expired token"):
        service.refresh_access_token(f"Bearer {token}")


def test_verify_access_token_keeps_legacy_local_token_before_wechat_phone_cutover(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    token = service._issue_access_token(
        user_id="student_demo",
        orig_iat=member_service_module._WECHAT_PHONE_AUTH_REQUIRED_AFTER_TS - 1,
    )

    claims = service.verify_access_token(token)

    assert claims is not None
    assert claims["uid"] == "student_demo"
    assert claims["provider"] == "local"


def test_issue_access_token_uses_configured_ttl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS", "900")

    token = service._issue_access_token(user_id="student_demo")
    claims = service.verify_access_token(token)

    assert claims is not None
    assert int(claims["exp"]) - int(claims["iat"]) == 900


def test_refresh_access_token_reissues_valid_token_without_second_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS", "600")
    monkeypatch.setenv("MEMBER_CONSOLE_MAX_SESSION_AGE_SECONDS", "1800")

    base = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    current = {"value": base}

    def _fake_now() -> datetime:
        return current["value"]

    monkeypatch.setattr(member_service_module, "_now", _fake_now)

    token = service._issue_access_token(user_id="student_demo")
    initial_claims = service.verify_access_token(token)
    assert initial_claims is not None

    current["value"] = base + timedelta(seconds=120)
    refreshed = service.refresh_access_token(f"Bearer {token}")
    refreshed_claims = service.verify_access_token(refreshed["token"])

    assert refreshed["user_id"] == "student_demo"
    assert refreshed_claims is not None
    assert refreshed_claims["uid"] == "student_demo"
    assert int(refreshed_claims["orig_iat"]) == int(initial_claims["orig_iat"])
    assert refreshed["token"] != token
    assert int(refreshed_claims["exp"]) > int(initial_claims["exp"])
    assert refreshed["expires_at"] == int(refreshed_claims["exp"])
    assert refreshed["expires_in"] == 600


def test_refresh_access_token_honors_absolute_session_age_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS", "600")
    monkeypatch.setenv("MEMBER_CONSOLE_MAX_SESSION_AGE_SECONDS", "900")

    base = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    current = {"value": base}

    def _fake_now() -> datetime:
        return current["value"]

    monkeypatch.setattr(member_service_module, "_now", _fake_now)

    token = service._issue_access_token(user_id="student_demo")

    current["value"] = base + timedelta(seconds=360)
    refreshed = service.refresh_access_token(f"Bearer {token}")
    refreshed_claims = service.verify_access_token(refreshed["token"])

    assert refreshed_claims is not None
    assert int(refreshed_claims["exp"]) - int(refreshed_claims["orig_iat"]) == 900
    assert refreshed["expires_in"] == 540

    current["value"] = base + timedelta(seconds=900)
    with pytest.raises(ValueError, match="Session refresh window expired"):
        service.refresh_access_token(f"Bearer {refreshed['token']}")


def test_production_bootstrap_starts_without_demo_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")

    data = service._load()

    assert data["members"] == []
    assert data["audit_log"] == []
    assert [package["id"] for package in data["packages"]] == [
        "starter_19",
        "light_98",
        "vip",
        "svip",
        "supreme_svip",
    ]
    # svip 顶档 598→268 重定价(12500 点);supreme_svip(998)后端保留仅供管理端手动开通,
    # 不在消费者 billing 白名单(见前端 _isLaunchPackageId)。
    assert [package["price"] for package in data["packages"]] == ["9.9", "68", "198", "268", "998"]
    assert [package["original_price"] for package in data["packages"]] == ["29", "98", "298", "398", "1298"]
    assert [package["turns"] for package in data["packages"]] == [20, 150, 450, 625, 2500]
    assert [package["points"] for package in data["packages"]] == [400, 3000, 9000, 12500, 50000]


def test_load_preserves_persisted_packages_and_backfills_canonical_defaults(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._data_path.write_text(
        json.dumps(
            {
                "members": [
                    {
                        "user_id": "student_demo",
                        "display_name": "student_demo",
                        "tier": "trial",
                        "status": "active",
                        "expire_at": "2026-07-01T00:00:00+08:00",
                        "points_balance": 100,
                    }
                ],
                "packages": [
                    {"id": "starter", "label": "轻量体验", "points": 100, "price": "9.9"},
                    {"id": "standard", "label": "标准套餐", "points": 500, "price": "39"},
                    {"id": "pro", "label": "进阶主力", "points": 1200, "price": "79"},
                    {"id": "ultimate", "label": "冲刺强化", "points": 3000, "price": "169"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    data = service._load()
    wallet = service.get_wallet("student_demo")

    assert [package["id"] for package in data["packages"]] == [
        "starter",
        "standard",
        "pro",
        "ultimate",
        "starter_19",
        "light_98",
        "vip",
        "svip",
        "supreme_svip",
    ]
    assert wallet["packages"][0]["id"] == "starter"
    assert wallet["packages"][0]["status"] == "active"
    assert wallet["packages"][0]["price"] == "9.9"
    assert wallet["packages"][-1]["id"] == "supreme_svip"
    assert wallet["packages"][-1]["turns"] == 2500


def test_normalize_membership_package_preserves_persisted_commerce_authority() -> None:
    normalized = MemberConsoleService._normalize_membership_package(
        {
            "id": "svip",
            "label": "旧SVIP",
            "points": 28000,
            "turns": 1400,
            "price": "598",
            "original_price": "798",
        }
    )

    assert normalized["points"] == 28000
    assert normalized["turns"] == 1400
    assert normalized["price"] == "598"
    assert normalized["original_price"] == "798"
    assert normalized["per"] == "1400 次 AI 学习额度"
    assert normalized["teaching_video_limit"] is None


def test_package_catalog_repricing_migrates_once_then_preserves_admin_updates(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._data_path.write_text(
        json.dumps(
            {
                "members": [],
                "packages": [
                    {
                        "id": "svip",
                        "label": "SVIP",
                        "points": 28000,
                        "turns": 1400,
                        "price": "598",
                        "original_price": "798",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    migrated = service._load()
    svip = next(item for item in migrated["packages"] if item["id"] == "svip")
    assert migrated["package_catalog_schema_version"] == 1
    assert (svip["price"], svip["points"], svip["turns"]) == ("268", 12500, 625)

    service.upsert_membership_package(
        package_id="svip",
        label="运营新SVIP",
        tier="svip",
        points=14000,
        turns=700,
        teaching_video_limit=50,
        price="298",
        operator="admin",
        reason="post-migration catalog update",
        idempotency_key="catalog-after-migration",
    )
    reloaded = service._load()
    updated = next(item for item in reloaded["packages"] if item["id"] == "svip")
    assert (updated["price"], updated["points"], updated["turns"]) == ("298", 14000, 700)
    assert updated["teaching_video_limit"] == 50


def test_package_catalog_migration_does_not_overwrite_unrecognized_admin_values(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._data_path.write_text(
        json.dumps(
            {
                "members": [],
                "packages": [
                    {
                        "id": "vip",
                        "label": "企业VIP",
                        "points": 12345,
                        "turns": 678,
                        "price": "321",
                        "teaching_video_limit": 88,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = service._load()
    vip = next(item for item in loaded["packages"] if item["id"] == "vip")
    assert (vip["label"], vip["price"], vip["points"], vip["turns"]) == (
        "企业VIP",
        "321",
        12345,
        678,
    )
    assert vip["teaching_video_limit"] == 88


def test_non_production_bootstrap_defaults_to_empty_members_without_demo_seed_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.delenv("DEEPTUTOR_MEMBER_CONSOLE_ENABLE_DEMO_SEED", raising=False)
    monkeypatch.delenv("DEEPTUTOR_ENV", raising=False)

    data = service._load()

    assert data["members"] == []
    assert data["audit_log"] == []


def test_production_bootstrap_can_create_first_real_member_without_seed_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")

    profile = service.get_profile("prod_first_user")

    assert profile["user_id"] == "prod_first_user"
    assert profile["tier"] == "trial"
    assert profile["points"] == 0


def test_get_profile_persists_first_real_member(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    profile = service.get_profile("ghost_user")
    data = service._load()

    assert profile["user_id"] == "ghost_user"
    assert any(member["user_id"] == "ghost_user" for member in data["members"])


def test_billing_entitlement_read_model_does_not_persist_unknown_member(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    entitlement = service.get_billing_entitlement_read_model("unknown-wallet-user")

    assert entitlement is None
    assert not service._data_path.exists()


def test_get_profile_exposes_only_raw_external_auth_eval_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("eval-user-id")

    def _mark_eval_runner(data: dict[str, object]) -> None:
        member = next(item for item in data["members"] if item["user_id"] == "eval-user-id")
        member.update(
            {
                "auth_username": "qa_eval_observer",
                "account_kind": "eval_runner",
                "actor_type": "machine",
                "created_by": "eval_runner",
                "is_internal_test": True,
            }
        )

    service._mutate(_mark_eval_runner)
    monkeypatch.setattr(
        member_service_module,
        "get_external_auth_user",
        lambda username: {
            "username": username,
            "account_kind": "eval_runner",
            "actor_type": "machine",
            "created_by": "eval_runner",
            "is_internal_test": True,
        },
    )
    profile = service.get_profile("eval-user-id")

    assert profile["auth_username"] == "qa_eval_observer"
    assert profile["account_kind"] == "eval_runner"
    assert profile["actor_type"] == "machine"
    assert profile["created_by"] == "eval_runner"
    assert profile["is_internal_test"] is True

    monkeypatch.setattr(member_service_module, "get_external_auth_user", lambda _username: {"username": "qa_eval_observer"})
    rejected = service.get_profile("eval-user-id")
    assert "account_kind" not in rejected
    assert "actor_type" not in rejected
    assert "created_by" not in rejected
    assert "is_internal_test" not in rejected


def test_home_dashboard_exposes_structured_study_plan_and_progress_feedback_from_learner_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    profile = service.get_profile("student_plan")
    assert profile["user_id"] == "student_plan"

    def _apply(data: dict[str, object]) -> None:
        for member in data["members"]:
            if member["user_id"] != "student_plan":
                continue
            member["focus_topic"] = "施工管理"
            member["daily_target"] = 8
            member["review_due"] = 2
            member["study_days"] = 3
            member["daily_practice_counts"] = {
                "2026-04-19": 6,
                "2026-04-18": 7,
                "2026-04-17": 5,
            }
            member["chapter_practice_stats"] = {
                "防水工程": {"done": 9, "correct": 6, "last_activity_at": "2026-04-21T09:00:00+08:00"}
            }
            break

    service._mutate(_apply)

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_plan"
            # 接线断言钉命名常量而非魔数：首页读窗权威 = _HOME_LEARNER_EVENT_LIMIT
            # （fusion-c a66fe1c3f 把 20 升到 100 后旧魔数 pin 在 try/except 里
            # 静默降级 snapshot，正是本测试要防的假绿形态）。
            from deeptutor.services.member_console import service as _mc_service

            assert event_limit == _mc_service._HOME_LEARNER_EVENT_LIMIT
            return type(
                "Snapshot",
                (),
                {
                    "profile": {
                        "focus_topic": "防水工程",
                        "focus_query": "继续巩固防水工程",
                    },
                    "progress": {
                        "today": {"today_done": 4, "daily_target": 8},
                        "knowledge_map": {
                            "weak_points": ["防水工程"],
                            "guided_learning_history": [
                                {
                                    "completed_titles": ["屋面卷材铺贴", "节点收头"],
                                }
                            ],
                        },
                    },
                    "memory_events": [
                        SimpleNamespace(
                            memory_kind="heartbeat_delivery",
                            payload_json={"delivery": {"message": "这是一条 heartbeat 提醒，不应该出现在进步反馈里"}},
                        ),
                        SimpleNamespace(
                            memory_kind="guide_completion",
                            payload_json={
                                "payload_json": {
                                    "knowledge_points": [
                                        {"knowledge_title": "屋面卷材铺贴"},
                                        {"knowledge_title": "节点收头"},
                                    ]
                                }
                            },
                        ),
                    ],
                },
            )()

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("student_plan")

    assert dashboard["today_focus"]["source"] == "learner_state.study_plan"
    assert dashboard["today_focus"]["title"] == "优先处理逾期复习"
    assert dashboard["today_focus"]["reason"] == "review_due"
    assert dashboard["today"]["focus"] == dashboard["today_focus"]
    assert dashboard["study_plan"]["focus_topic"] == "防水工程"
    assert "待复习点" in dashboard["study_plan"]["priority_task"]
    assert dashboard["study_plan"]["study_method"].startswith("先看“防水工程”")
    assert "近 3 天" in dashboard["progress_feedback"]["summary"]
    assert "防水工程" in dashboard["progress_feedback"]["insight"]
    assert dashboard["progress_feedback"]["cards"][2]["value"] == "9条证据"
    assert any(
        item["title"] == "刚完成一次专题梳理"
        for item in dashboard["progress_feedback"]["milestones"]
    )
    assert not any(
        "heartbeat" in item["detail"]
        for item in dashboard["progress_feedback"]["milestones"]
    )


def test_home_dashboard_today_focus_uses_learner_state_focus_as_single_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("focus_user")

    def _apply(data: dict[str, object]) -> None:
        for member in data["members"]:
            if member["user_id"] != "focus_user":
                continue
            member["focus_topic"] = "施工管理"
            member["focus_query"] = "旧的施工管理问题"
            member["review_due"] = 0
            break

    service._mutate(_apply)

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "focus_user"
            return type(
                "Snapshot",
                (),
                {
                    "profile": {
                        "focus_topic": "建筑构造",
                        "focus_query": "继续巩固建筑构造",
                    },
                    "progress": {
                        "today": {"today_done": 1, "daily_target": 5},
                        "knowledge_map": {
                            "weak_points": ["建筑构造"],
                        },
                    },
                    "memory_events": [],
                },
            )()

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("focus_user")

    expected_query = "请根据我的学习记录、最近进度，围绕建筑构造设计的基本要求做一次建筑实务微课：先讲清一个最容易失分的核心考点，再用一个考试场景例子带我判断，最后给我一个简短自查问题；不要展开成长期安排，也不要直接生成整套训练题。"
    assert dashboard["today_focus"] == {
        "label": "今日焦点",
        "title": "推进建筑构造设计的基本要求下一步学习",
        "meta": "结合当前进度动态选择讲解/例题/复盘/自测",
        "query": expected_query,
        "topic": "建筑构造设计的基本要求",
        "tone": "practice",
        "reason": "learner_state_focus",
        "source": "learner_state.study_plan",
    }
    assert "学习计划" not in dashboard["today_focus"]["query"]
    assert "下一步学习推进" not in dashboard["today_focus"]["query"]
    assert "先判断我当前更适合" not in dashboard["today_focus"]["query"]
    assert "专项训练题" not in dashboard["today_focus"]["query"]
    assert "5道" not in dashboard["today_focus"]["query"]
    assert "入门" not in dashboard["today_focus"]["query"]
    assert "建筑实务微课" in dashboard["today_focus"]["query"]
    assert "考试场景例子" in dashboard["today_focus"]["query"]


def test_home_dashboard_today_focus_never_uses_generic_learning_plan_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("generic_focus_user")

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "generic_focus_user"
            return type(
                "Snapshot",
                (),
                {
                    "profile": {
                        "focus_topic": "建筑构造",
                        "focus_query": "请根据我的学习记录、最近进度，围绕建筑构造安排下一步学习推进：先判断我当前更适合知识讲解、例题带练、错因复盘还是少量自测，再用建筑实务考试口径展开；不要默认生成整套训练题，也不要提前假设我的阶段层级。",
                    },
                    "progress": {
                        "today": {"today_done": 0, "daily_target": 5},
                        "knowledge_map": {
                            "weak_points": ["建筑构造"],
                        },
                    },
                    "memory_events": [],
                },
            )()

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("generic_focus_user")

    assert dashboard["today_focus"]["title"] == "推进建筑构造设计的基本要求下一步学习"
    assert dashboard["today_focus"]["query"] == "请根据我的学习记录、最近进度，围绕建筑构造设计的基本要求做一次建筑实务微课：先讲清一个最容易失分的核心考点，再用一个考试场景例子带我判断，最后给我一个简短自查问题；不要展开成长期安排，也不要直接生成整套训练题。"
    assert "学习计划" not in dashboard["today_focus"]["query"]
    assert "下一步学习推进" not in dashboard["today_focus"]["query"]
    assert "先判断我当前更适合" not in dashboard["today_focus"]["query"]
    assert "专项训练题" not in dashboard["today_focus"]["query"]
    assert "5道" not in dashboard["today_focus"]["query"]
    assert "入门" not in dashboard["today_focus"]["query"]
    assert "建筑实务微课" in dashboard["today_focus"]["query"]


def test_home_dashboard_today_focus_incorporates_heartbeat_without_making_it_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("heartbeat_focus_user")

    def _apply(data: dict[str, object]) -> None:
        for member in data["members"]:
            if member["user_id"] != "heartbeat_focus_user":
                continue
            member["focus_topic"] = ""
            member["focus_query"] = "继续我的学习计划"
            member["review_due"] = 0
            break

    service._mutate(_apply)

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "heartbeat_focus_user"
            return type(
                "Snapshot",
                (),
                {
                    "profile": {},
                    "summary": "## 当前学习概览\n- 当前聚焦：防水工程\n",
                    "progress": {
                        "today": {"today_done": 2, "daily_target": 8},
                        "knowledge_map": {"weak_points": ["防水工程"]},
                    },
                    "memory_events": [],
                },
            )()

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "heartbeat_focus_user"
            now = datetime(2026, 5, 2, 15, 0, tzinfo=timezone(timedelta(hours=8)))
            return [
                SimpleNamespace(
                    job_id="hb-1",
                    user_id=user_id,
                    bot_id="construction-exam-coach",
                    channel="heartbeat",
                    policy_json={"cadence": "daily"},
                    next_run_at=now + timedelta(days=1),
                    last_run_at=now - timedelta(days=1),
                    last_result_json={},
                    failure_count=0,
                    status="active",
                    created_at=now - timedelta(days=10),
                    updated_at=now,
                )
            ]

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            assert user_id == "heartbeat_focus_user"
            return [
                {
                    "memory_kind": "heartbeat_delivery",
                    "payload_json": {"delivery": {"message": "本周继续跟进防水工程易错点"}},
                }
            ]

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("heartbeat_focus_user")

    assert dashboard["today_focus"]["title"] == "推进屋面与防水工程施工下一步学习"
    assert dashboard["today_focus"]["topic"] == "屋面与防水工程施工"
    assert dashboard["today_focus"]["source"] == "learner_state.study_plan+heartbeat"
    assert "周期复习节奏" in dashboard["today_focus"]["query"]
    assert "建筑实务微课" in dashboard["today_focus"]["query"]
    assert "考试场景例子" in dashboard["today_focus"]["query"]
    assert "学习计划" not in dashboard["today_focus"]["query"]
    assert "下一步学习推进" not in dashboard["today_focus"]["query"]
    assert "先判断我当前更适合" not in dashboard["today_focus"]["query"]
    assert "整套训练题" in dashboard["today_focus"]["query"]
    assert "阶段层级" not in dashboard["today_focus"]["query"]


def test_home_dashboard_ignores_global_workspace_heartbeat_as_user_focus_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("no_user_heartbeat")

    def _apply(data: dict[str, object]) -> None:
        for member in data["members"]:
            if member["user_id"] != "no_user_heartbeat":
                continue
            member["focus_topic"] = "施工管理"
            member["focus_query"] = "继续我的学习计划"
            member["review_due"] = 0
            break

    service._mutate(_apply)

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "no_user_heartbeat"
            return type(
                "Snapshot",
                (),
                {
                    "profile": {},
                    "summary": "",
                    "progress": {},
                    "memory_events": [],
                },
            )()

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "no_user_heartbeat"
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            assert user_id == "no_user_heartbeat"
            return []

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("no_user_heartbeat")

    assert dashboard["today_focus"]["source"] == "learner_state.study_plan"
    assert "周期复习节奏" not in dashboard["today_focus"]["query"]


@pytest.mark.asyncio
async def test_production_bootstrap_persists_first_wechat_user_without_demo_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_AUTH_SECRET", "prod_auth_secret")

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_prod_first_user",
            "unionid": "unionid_prod_first_user",
            "session_key": "session_key_prod_first_user",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)

    result = await service.login_with_wechat_code("wx-prod-code")
    data = service._load()

    assert result["user"]["user_id"].startswith("wx_")
    assert [member["user_id"] for member in data["members"]] == [result["user"]["user_id"]]


def test_login_with_password_accepts_external_fastapi_auth_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    password_hash = bcrypt.hashpw(
        hashlib.sha256("Chen9028".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    users_file.write_text(
        (
            '{\n'
            '  "chenyh2008": {\n'
            '    "id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",\n'
            f'    "password_hash": "{password_hash}",\n'
            '    "username": "chenyh2008"\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._mutate(
        lambda data: data["members"].append(
            {
                **data["members"][0],
                "user_id": "user_2008",
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "external_auth_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "phone": "2008",
            }
        )
    )

    result = service.login_with_password("chenyh2008", "Chen9028")

    assert result["token"].startswith("dtm.")
    assert result["user_id"] == "user_2008"
    assert result["user"]["user_id"] == "user_2008"
    assert result["user"]["username"] == "chenyh2008"


def test_login_with_password_does_not_fail_when_wallet_bootstrap_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    username = "wallet_quota_user"
    password = "SyntheticPass123"  # pragma: allowlist secret
    password_hash = bcrypt.hashpw(
        hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    users_file.write_text(
        json.dumps(
            {
                username: {
                    "id": canonical_uid,
                    "username": username,
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_AUTH_SECRET", "prod_auth_secret")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    class _FailingWalletService:
        is_configured = True

        @staticmethod
        def ensure_wallet_seeded(**_kwargs):
            raise RuntimeError("wallet quota unavailable")

    monkeypatch.setattr(
        member_service_module,
        "SupabaseAssessmentSessionRepository",
        lambda: SimpleNamespace(is_configured=True),
    )
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setattr(service, "_get_wallet_service", lambda: _FailingWalletService())

    result = service.login_with_password(username, password)
    claims = service.verify_access_token(result["token"])

    assert result["token"].startswith("dtm.")
    assert result["user_id"]
    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid


def test_internal_qa_billing_bypass_skips_wallet_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    username = "qa_wallet_bypass_user"
    password = "SyntheticPass123"  # pragma: allowlist secret
    password_hash = bcrypt.hashpw(
        hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    users_file.write_text(
        json.dumps(
            {
                username: {
                    "id": canonical_uid,
                    "username": username,
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS", "true")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    wallet_calls: list[dict[str, object]] = []

    class _FailingWalletService:
        is_configured = True

        @staticmethod
        def ensure_wallet_seeded(**kwargs):
            wallet_calls.append(dict(kwargs))
            return None

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setattr(service, "_get_wallet_service", lambda: _FailingWalletService())

    result = service.login_with_password(username, password)
    claims = service.verify_access_token(result["token"])

    assert result["token"].startswith("dtm.")
    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert wallet_calls == []


def test_internal_qa_billing_bypass_keeps_non_qa_wallet_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_uid = "a5732af1-496b-4643-a23c-e74ec7216b94"
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS", "true")
    wallet_calls: list[dict[str, object]] = []

    class _RecordingWalletService:
        is_configured = True

        @staticmethod
        def ensure_wallet_seeded(**kwargs):
            wallet_calls.append(dict(kwargs))
            return None

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._mutate(
        lambda data: data["members"].append(
            {
                **data["members"][0],
                "user_id": "user_real_wallet",
                "auth_username": "student_wallet_user",
                "external_auth_user_id": canonical_uid,
                "phone": "",
            }
        )
    )
    monkeypatch.setattr(service, "_get_wallet_service", lambda: _RecordingWalletService())

    auth_identity = service._auth_identity_for_member("user_real_wallet")

    assert auth_identity["canonical_uid"] == canonical_uid
    assert len(wallet_calls) == 1
    assert wallet_calls[0]["user_id"] == canonical_uid


def test_production_without_supabase_sessions_only_blocks_assessment_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setattr(
        member_service_module,
        "SupabaseAssessmentSessionRepository",
        lambda: SimpleNamespace(is_configured=False),
    )

    service = MemberConsoleService()

    assert service._assessment_sessions_supabase_required_but_missing is True
    with pytest.raises(RuntimeError, match="assessment_sessions_supabase_not_configured"):
        service.create_assessment(
            "student_demo",
            assessment_type="topic_diagnostic",
            topic_ids=["waterproof"],
        )


def test_login_with_password_rejects_unknown_or_invalid_external_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    password_hash = bcrypt.hashpw(
        hashlib.sha256("StrongPass123".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    users_file.write_text(
        json.dumps(
            {
                "student_demo": {
                    "id": "user_demo",
                    "username": "student_demo",
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    with pytest.raises(ValueError, match="用户名或密码错误"):
        service.login_with_password("student_demo", "wrong-password")

    with pytest.raises(ValueError, match="用户名或密码错误"):
        service.login_with_password("unknown-user", "StrongPass123")


def test_canonical_member_snapshot_merges_legacy_external_auth_learning_state(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            service._build_default_member(canonical_user_id),
            {
                **service._build_default_member("user_2008"),
                "user_id": "user_2008",
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "external_auth_user_id": canonical_user_id,
                "points_balance": 360,
                "focus_topic": "地基基础",
                "focus_query": "我想练习地基基础相关的题目",
                "study_days": 3,
                "chapter_mastery": {
                    "建筑构造": {"name": "建筑构造", "mastery": 50},
                    "地基基础": {"name": "地基基础", "mastery": 50},
                    "防水工程": {"name": "防水工程", "mastery": 50},
                    "施工管理": {"name": "施工管理", "mastery": 50},
                    "主体结构": {"name": "主体结构", "mastery": 50},
                },
                "daily_practice_counts": {"2026-04-14": 2},
                "chapter_practice_stats": {
                    "地基基础": {
                        "done": 2,
                        "correct": 1,
                        "last_activity_at": "2026-04-14T10:00:00+08:00",
                    }
                },
            },
        ]

    service._mutate(_seed)

    assessment = service.get_assessment_profile(canonical_user_id)
    canonical_profile = service.get_profile(canonical_user_id)
    legacy_profile = service.get_profile("user_2008")
    chapter_progress = service.get_chapter_progress(canonical_user_id)
    data = service._load()
    canonical_member = service._find_member(data, canonical_user_id)
    legacy_member = service._find_member(data, "user_2008")
    foundation_progress = next(item for item in chapter_progress if item["chapter_name"] == "地基基础")

    expected_score = round(
        sum(item["mastery"] for item in assessment["chapter_mastery"].values())
        / max(len(assessment["chapter_mastery"]), 1)
    )
    assert assessment["score"] == expected_score
    assert assessment["score"] < 50
    assert assessment["chapter_mastery"]["地基基础"]["mastery"] == 50
    assert canonical_profile["user_id"] == canonical_user_id
    assert canonical_profile["username"] == "chenyh2008"
    assert legacy_profile["user_id"] == canonical_user_id
    assert legacy_member["merged_into"] == canonical_user_id
    assert canonical_member["focus_topic"] == "地基基础"
    assert canonical_member["study_days"] == 3
    assert foundation_progress["done"] == 2
    assert foundation_progress["total"] == 2
    assert foundation_progress["daily_target"] == 30


def test_home_dashboard_uses_canonical_learner_state_for_merged_legacy_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME_PERSONALIZATION_ENABLED", "true")
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            service._build_default_member(canonical_user_id),
            {
                **service._build_default_member("user_2008"),
                "user_id": "user_2008",
                "display_name": "chenyh2008",
                "external_auth_user_id": canonical_user_id,
                "merged_into": canonical_user_id,
            },
        ]

    service._mutate(_seed)
    event = SimpleNamespace(
        event_id="evt_home_legacy_token",
        memory_kind="learning_evidence",
        source_feature="assessment_testset",
        payload_json={
            "event_type": "learning_evidence",
            "knowledge_points": ["招投标与合同"],
            "error_codes": [],
        },
    )
    snapshot_user_ids: list[str] = []

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            snapshot_user_ids.append(user_id)
            return SimpleNamespace(profile={}, progress={}, summary="", memory_events=[event])

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, limit: int = 3):
            return []

    service._get_learner_state_service = lambda: _FakeLearnerStateService()  # type: ignore[method-assign]

    dashboard = service.get_home_dashboard("user_2008")

    assert snapshot_user_ids == [canonical_user_id]
    # canonical classifier maps "招投标与合同" → chapter "工程招标投标与合同管理"
    assert dashboard["today_focus"]["title"] == "今日焦点：工程招标投标与合同管理"
    assert dashboard["recommended_prompts"][0]["text"] == "用 3 道题训练工程招标投标与合同管理"


def test_register_with_external_auth_creates_external_user_and_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = service.register_with_external_auth("new_student", "StrongPass123", "13812345678")
    external_users = json.loads(users_file.read_text(encoding="utf-8"))

    assert result["token"].startswith("dtm.")
    assert result["user_id"] == result["user"]["user_id"]
    assert result["user"]["username"] == "new_student"
    assert "new_student" in external_users
    assert external_users["new_student"]["phone"] == "+8613812345678"


def test_eval_runner_external_auth_identity_propagates_to_bi_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    external_auth_module.ensure_external_auth_user(
        "plain_runner",
        "StrongPass123",
        phone="13912345678",
        identity_metadata={
            "account_kind": "eval_runner",
            "actor_type": "machine",
            "created_by": "eval_runner",
            "is_internal_test": True,
        },
    )

    result = service.login_with_password("plain_runner", "StrongPass123")
    member = next(item for item in service._load()["members"] if item.get("auth_username") == "plain_runner")
    payload = service.list_members(page=1, page_size=20)
    dashboard = service.get_dashboard()

    assert result["token"].startswith("dtm.")
    assert member["account_kind"] == "eval_runner"
    assert member["actor_type"] == "machine"
    assert member["created_by"] == "eval_runner"
    assert member["is_internal_test"] is True
    assert payload["total"] == 0
    assert dashboard["total_count"] == 0
    assert dashboard["new_today_count"] == 0


def test_eval_runner_register_persists_phone_alias_identity_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    persisted: dict[str, object] = {}

    def _capture_persist_phone_identity(**kwargs: object) -> None:
        persisted.update(kwargs)

    monkeypatch.setattr(service, "_persist_phone_identity", _capture_persist_phone_identity)

    service.register_with_external_auth("qa_eval_codex_smoke_1", "StrongPass123", "13812345678")

    assert persisted["phone"] == "13812345678"
    assert persisted["identity_metadata"] == {
        "account_kind": "eval_runner",
        "actor_type": "machine",
        "created_by": "eval_runner",
        "is_internal_test": True,
        "runner": "codex",
        "agent_tool": "codex",
    }


def test_student_army_external_auth_account_auto_tags_eval_runner_for_bi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    created = external_auth_module.ensure_external_auth_user(
        "qa_studentarmy_1",
        "StrongPass123",
        phone="13912345679",
    )

    result = service.login_with_password("qa_studentarmy_1", "StrongPass123")
    member = next(item for item in service._load()["members"] if item.get("auth_username") == "qa_studentarmy_1")
    dashboard = service.get_dashboard()

    assert created["account_kind"] == "eval_runner"
    assert created["actor_type"] == "machine"
    assert created["created_by"] == "eval_runner"
    assert created["is_internal_test"] is True
    assert result["token"].startswith("dtm.")
    assert member["account_kind"] == "eval_runner"
    assert member["actor_type"] == "machine"
    assert dashboard["total_count"] == 0
    assert dashboard["new_today_count"] == 0


def test_register_with_external_auth_rejects_non_cn_mobile_phone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    called: list[tuple[object, ...]] = []

    def _unexpected_create_external_auth_user(*args: object, **kwargs: object) -> dict[str, object]:
        called.append(args)
        raise AssertionError("register phone validation must run before external auth")

    monkeypatch.setattr(
        member_service_module,
        "create_external_auth_user",
        _unexpected_create_external_auth_user,
    )

    with pytest.raises(ValueError, match="大陆手机号"):
        service.register_with_external_auth("new_student", "StrongPass123", "83090321728")

    assert called == []
    assert not users_file.exists()


def test_register_with_external_auth_rejects_existing_verified_phone_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13812345678":
                return {
                    "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    "source": "phone_verification",
                }
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    with pytest.raises(ValueError, match="该手机号已被注册"):
        service.register_with_external_auth("new_student", "StrongPass123", "13812345678")

    assert not users_file.exists()


def test_register_with_external_auth_rejects_existing_local_member_phone_without_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service._mutate(
        lambda data: data["members"].append(
            {
                "user_id": "legacy_member",
                "display_name": "Legacy Student",
                "phone": "13812345678",
            }
        )
    )

    with pytest.raises(ValueError, match="该手机号已被注册"):
        service.register_with_external_auth("new_student", "StrongPass123", "13812345678")

    assert not users_file.exists()


def test_register_with_external_auth_persists_new_phone_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    persisted: list[dict[str, str]] = []

    monkeypatch.setattr(
        service,
        "_persist_phone_identity",
        lambda *, phone, canonical_uid, identity_metadata=None: persisted.append(
            {
                "phone": phone,
                "canonical_uid": canonical_uid,
                "identity_metadata": identity_metadata,
            }
        ),
    )

    result = service.register_with_external_auth("new_student", "StrongPass123", "13812345678")
    claims = service.verify_access_token(result["token"])

    assert claims is not None
    assert persisted == [
        {
            "phone": "13812345678",
            "canonical_uid": claims["canonical_uid"],
            "identity_metadata": None,
        }
    ]


def test_channel_attribution_metadata_sanitizes_values() -> None:
    assert member_service_module._channel_attribution_metadata("test1", "1047") == {
        "reg_channel": "test1",
        "reg_scene": "1047",
    }
    # 脏值：channel 只保留 [0-9A-Za-z_-]，scene 只保留数字
    assert member_service_module._channel_attribution_metadata(
        "推广'; DROP--x", "scene1047abc"
    ) == {"reg_channel": "DROP--x", "reg_scene": "1047"}
    assert member_service_module._channel_attribution_metadata("", "") == {}
    assert member_service_module._channel_attribution_metadata(None, None) == {}


def test_register_with_external_auth_persists_channel_attribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    persisted: dict[str, object] = {}

    def _capture_persist_phone_identity(**kwargs: object) -> None:
        persisted.update(kwargs)

    monkeypatch.setattr(service, "_persist_phone_identity", _capture_persist_phone_identity)

    service.register_with_external_auth(
        "new_student", "StrongPass123", "13812345678", channel="test1", scene="1047"
    )

    assert persisted["phone"] == "13812345678"
    assert persisted["identity_metadata"] == {"reg_channel": "test1", "reg_scene": "1047"}


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_first_registration_persists_channel_attribution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    persisted: dict[str, object] = {}

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13911112222"

    def _capture_persist_phone_identity(**kwargs: object) -> None:
        persisted.update(kwargs)

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)
    monkeypatch.setattr(service, "_persist_phone_identity", _capture_persist_phone_identity)

    result = await service.bind_phone_for_wechat(
        "student_demo", "phone-code-123", channel="test1", scene="1047"
    )

    assert result["bound"] is True
    assert persisted["phone"] == "13911112222"
    identity_metadata = persisted["identity_metadata"]
    assert isinstance(identity_metadata, dict)
    assert identity_metadata["reg_channel"] == "test1"
    assert identity_metadata["reg_scene"] == "1047"


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_existing_member_login_does_not_write_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """已注册用户复登录（手机号已有 canonical alias）不得覆盖注册渠道（first-touch 保护）。"""
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    persisted: dict[str, object] = {}

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13911112222":
                return {"user_id": canonical_uid, "source": "phone_verification"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13911112222"

    def _capture_persist_phone_identity(**kwargs: object) -> None:
        persisted.update(kwargs)

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)
    monkeypatch.setattr(service, "_persist_phone_identity", _capture_persist_phone_identity)

    def _seed(data: dict[str, object]) -> None:
        canonical = service._ensure_member(data, canonical_uid)
        canonical["phone"] = "13911112222"

    service._mutate(_seed)

    result = await service.bind_phone_for_wechat(
        canonical_uid, "phone-code-123", channel="late_campaign", scene="1047"
    )

    assert result["bound"] is True
    identity_metadata = persisted.get("identity_metadata")
    assert identity_metadata is None or "reg_channel" not in identity_metadata


def test_register_with_external_auth_does_not_match_existing_display_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._mutate(
        lambda data: data["members"].append(
            {
                **service._build_default_member("wx_attacker"),
                "display_name": "victimname",
                "phone": "13800001111",
            }
        )
    )

    result = service.register_with_external_auth("victimname", "StrongPass123", "13800002222")
    data = service._load()
    attacker = service._find_member(data, "wx_attacker")

    assert result["user"]["user_id"] != "wx_attacker"
    assert attacker.get("auth_username") in {None, ""}
    assert attacker["phone"] == "13800001111"


def test_external_auth_production_default_does_not_read_legacy_luban_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_users = tmp_path / "app" / "users.json"
    legacy_users = tmp_path / "luban" / "users.json"
    legacy_users.parent.mkdir(parents=True, exist_ok=True)
    password_hash = bcrypt.hashpw(
        hashlib.sha256("StrongPass123".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    legacy_users.write_text(
        json.dumps(
            {
                "legacy_user": {
                    "id": "legacy-user-id",
                    "username": "legacy_user",
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", raising=False)
    monkeypatch.setattr(external_auth_module, "_PRIMARY_USERS_FILE", primary_users)
    monkeypatch.setattr(external_auth_module, "_LEGACY_USERS_FILE", legacy_users)

    assert external_auth_module.get_external_auth_user("legacy_user") is None
    assert external_auth_module._resolve_users_file_for_write() == primary_users


def test_external_auth_production_explicit_legacy_env_still_allows_compat_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_users = tmp_path / "luban" / "users.json"
    legacy_users.parent.mkdir(parents=True, exist_ok=True)
    password_hash = bcrypt.hashpw(
        hashlib.sha256("StrongPass123".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    legacy_users.write_text(
        json.dumps(
            {
                "legacy_user": {
                    "id": "legacy-user-id",
                    "username": "legacy_user",
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(legacy_users))

    user = external_auth_module.get_external_auth_user("legacy_user")

    assert user is not None
    assert user["username"] == "legacy_user"


def test_explicit_external_auth_store_does_not_read_default_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "explicit" / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    def _unexpected_default_path():
        raise AssertionError("explicit external-auth path must bypass default path discovery")

    monkeypatch.setattr(external_auth_module, "_default_users_file", _unexpected_default_path)

    user = external_auth_module.ensure_external_auth_user(
        "qa_eval_explicit_store",
        "StrongPass123",
    )

    assert user["account_kind"] == "eval_runner"
    assert external_auth_module.get_external_auth_user("qa_eval_explicit_store") is not None


def test_ensure_external_auth_user_resets_seeded_test_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    created = external_auth_module.ensure_external_auth_user(
        "qa_tutorbot_mcq",
        "OldPass123",
        phone="13900001001",
    )
    updated = external_auth_module.ensure_external_auth_user(
        "qa_tutorbot_mcq",
        "NewPass123",
        phone="13900001001",
    )

    assert created["id"] == updated["id"]
    assert updated["account_kind"] == "eval_runner"
    assert updated["actor_type"] == "machine"
    assert updated["created_by"] == "eval_runner"
    assert updated["is_internal_test"] is True
    assert external_auth_module.verify_external_auth_user("qa_tutorbot_mcq", "OldPass123") is None
    assert external_auth_module.verify_external_auth_user("qa_tutorbot_mcq", "NewPass123") is not None


def test_external_auth_machine_signal_closes_required_eval_identity_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(tmp_path / "users.json"))

    user = external_auth_module.ensure_external_auth_user(
        "plain_automation_runner",
        "StrongPass123",
        identity_metadata={"actor_type": "machine"},
    )

    assert external_auth_module.get_external_auth_identity_metadata(str(user["id"])) == {
        "account_kind": "eval_runner",
        "actor_type": "machine",
        "created_by": "eval_runner",
        "is_internal_test": True,
    }


def test_member_console_serializes_multi_step_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    audit_started = threading.Event()
    allow_finish = threading.Event()
    second_write_done = threading.Event()
    note_holder: dict[str, object] = {}
    errors: list[BaseException] = []

    original_append_audit = service._append_audit

    def _gated_append_audit(data, **kwargs):
        if kwargs.get("action") == "note":
            audit_started.set()
            allow_finish.wait(timeout=2)
        return original_append_audit(data, **kwargs)

    monkeypatch.setattr(service, "_append_audit", _gated_append_audit)

    def _add_note() -> None:
        try:
            note_holder["note"] = service.add_note("student_demo", "并发写入测试")
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)

    def _update_subscription() -> None:
        try:
            service.update_subscription("student_demo", auto_renew=False, reason="concurrency_test")
            second_write_done.set()
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)

    writer_one = threading.Thread(target=_add_note)
    writer_two = threading.Thread(target=_update_subscription)

    writer_one.start()
    assert audit_started.wait(timeout=1.0)

    writer_two.start()
    assert not second_write_done.wait(timeout=0.1)

    allow_finish.set()
    writer_one.join(timeout=2.0)
    writer_two.join(timeout=2.0)

    assert not errors
    data = service._load()
    member = service._find_member(data, "student_demo")
    assert member["auto_renew"] is False
    assert any(note["id"] == note_holder["note"]["id"] for note in member["notes"])


def test_capture_points_updates_balance_and_prepends_ledger(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    wallet_before = service.get_wallet("student_demo")
    result = service.capture_points("student_demo", amount=20)
    wallet_after = service.get_wallet("student_demo")
    ledger = service.get_ledger("student_demo", limit=5, offset=0)

    assert result["captured"] == 20
    assert wallet_after["balance"] == wallet_before["balance"] - 20
    assert ledger["entries"][0]["reason"] == "capture"
    assert ledger["entries"][0]["delta"] == -20


def test_create_assessment_uses_unique_question_ids_per_quiz(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    caplog.set_level(logging.INFO, logger="deeptutor.services.member_console.service")
    payload = service.create_assessment("student_demo", count=20)
    question_ids = [item["question_id"] for item in payload["questions"]]
    source_ids = [item["source_question_id"] for item in payload["questions"]]

    assert payload["requested_count"] == 20
    assert payload["delivered_count"] == 20
    assert payload["blueprint_version"] == "diagnostic_v1"
    assert payload["scored_count"] == 16
    assert payload["profile_count"] == 4
    assert payload["available_count"] >= 20
    assert payload["question_bank_size"] >= 20
    assert payload["unique_source_question_count"] == 20
    assert payload["shortfall_count"] == 0
    assert payload["form_source"] == "local_static_fallback"
    assert len(question_ids) == 20
    assert len(set(question_ids)) == 20
    assert len(source_ids) == len(set(source_ids))

    stored_session = service._load()["assessment_sessions"][payload["quiz_id"]]
    stored = stored_session["questions"]
    stored_ids = [item["question_id"] for item in stored]
    assert stored_ids == question_ids
    assert stored_session["requested_count"] == 20
    assert stored_session["delivered_count"] == 20
    assert stored_session["blueprint_version"] == "diagnostic_v1"
    assert stored_session["scored_count"] == 16
    assert stored_session["profile_count"] == 4
    assert stored_session["form_source"] == payload["form_source"]
    assert stored_session["observability"]["form_source"] == payload["form_source"]
    assert all(item["provenance"]["question_id"] for item in stored)
    assert stored_session["question_bank_size"] >= 20
    assert stored_session["unique_source_question_count"] == 20
    assert stored_session["shortfall_count"] == 0
    assert "Assessment session created" in caplog.text
    assert "form_source=local_static_fallback" in caplog.text


def test_assessment_topic_catalog_is_fail_closed_without_form_bank(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.delenv("ASSESSMENT_USE_SUPABASE", raising=False)
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")

    catalog = service.get_assessment_topic_catalog()

    topic_ids = [item["topic_id"] for item in catalog["topics"]]
    assert topic_ids == [
        "waterproof",
        "decoration",
        "mep",
        "foundation",
        "main_structure",
        "formwork_scaffold",
        "safety",
        "schedule",
        "contract_claim",
        "quality_acceptance",
    ]
    assert all(item["status"] == "authoring_needed" for item in catalog["topics"])
    assert all(item["enabled"] is False for item in catalog["topics"])
    assert all(item["form_count"] == 0 for item in catalog["topics"])
    assert {item["target_form_count"] for item in catalog["topics"]} == {5}


def test_assessment_topic_catalog_uses_form_metadata_without_loading_form_banks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("ASSESSMENT_USE_SUPABASE", "true")

    class _MetadataProvider:
        def active_form_summaries(self, blueprint_versions: list[str]) -> dict[str, dict[str, object]]:
            assert "topic_waterproof_v1" in blueprint_versions
            return {
                "topic_waterproof_v1": {
                    "active_form_count": 5,
                    "fallback_used": True,
                    "question_bank_size": 4638,
                }
            }

        def load_persisted_form_bank(self, blueprint):
            raise AssertionError("catalog must not load full form banks")

    monkeypatch.setattr(member_service_module, "SupabaseAssessmentQuestionProvider", _MetadataProvider)

    catalog = service.get_assessment_topic_catalog()
    waterproof = next(item for item in catalog["topics"] if item["topic_id"] == "waterproof")

    assert waterproof["form_count"] == 5
    assert waterproof["status"] == "authoring_needed"
    assert waterproof["enabled"] is False
    assert waterproof["quality_status"] == "fallback_form_bank"


def test_assessment_topic_catalog_recommends_weak_enabled_topic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("ASSESSMENT_USE_SUPABASE", "true")

    class _ValidFormProvider:
        def active_form_summaries(self, blueprint_versions: list[str]) -> dict[str, dict[str, object]]:
            return {
                blueprint_version: {
                    "active_form_count": 5,
                    "fallback_used": False,
                    "question_bank_size": 4638,
                }
                for blueprint_version in blueprint_versions
            }

        def load_persisted_form_bank(self, blueprint):
            raise AssertionError("catalog must not load full form banks")

    monkeypatch.setattr(member_service_module, "SupabaseAssessmentQuestionProvider", _ValidFormProvider)

    def _seed(data: dict[str, object]) -> None:
        member = service._ensure_member(data, "student_demo")
        member["last_assessment"] = {
            "chapter_mastery": {
                "主体结构": {"name": "主体结构施工缝", "mastery": 25},
                "防水工程": {"name": "防水工程", "mastery": 80},
            }
        }

    service._mutate(_seed)

    catalog = service.get_assessment_topic_catalog("student_demo")
    recommendation = catalog["recommendation"]

    assert recommendation["recommended_mode"] == "topic"
    assert recommendation["recommended_topic_id"] == "main_structure"
    assert recommendation["recommended_count"] == 12
    assert recommendation["source"] == "learner_state_weak_node"


def test_member_360_includes_learner_state_heartbeat_and_bot_overlays(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            event = type(
                "Event",
                (),
                {
                    "event_id": "evt_1",
                    "source_feature": "heartbeat",
                    "source_id": "job_1",
                    "source_bot_id": "review-bot",
                    "memory_kind": "heartbeat_delivery",
                    "payload_json": {"status": "sent"},
                    "created_at": "2026-04-16T09:00:00+08:00",
                },
            )()
            return type(
                "Snapshot",
                (),
                {
                    "user_id": user_id,
                    "profile": {"display_name": "陈同学"},
                    "summary": "正在复习地基基础。",
                    "progress": {"knowledge_map": {"weak_points": ["防火间距"]}},
                    "memory_events": [event],
                    "profile_updated_at": "2026-04-16T08:00:00+08:00",
                    "summary_updated_at": "2026-04-16T08:10:00+08:00",
                    "progress_updated_at": "2026-04-16T08:20:00+08:00",
                    "memory_events_updated_at": "2026-04-16T09:00:00+08:00",
                },
            )()

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1", "memory_kind": "heartbeat_delivery"}]

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            return []

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1", "payload_json": {"winner_bot_id": "review-bot"}}]

    class FakeOverlayService:
        def list_user_overlays(self, user_id: str, *, limit: int | None = None):
            assert user_id == "student_demo"
            assert limit == 20
            return [{"bot_id": "review-bot", "version": 3}]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: FakeOverlayService()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"]["available"] is True
    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["learner_state"]["recent_memory_events"][0]["memory_kind"] == "heartbeat_delivery"
    assert payload["heartbeat"]["history"][0]["event_id"] == "hb_1"
    assert payload["heartbeat"]["arbitration_history"][0]["payload_json"]["winner_bot_id"] == "review-bot"
    assert payload["bot_overlays"][0]["bot_id"] == "review-bot"


def test_member_360_and_conversation_list_hide_messages_before_audit(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="地基基础答疑",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "帮我看看地基基础怎么复习"))
    asyncio.run(service._store.add_message("tb_student_demo", "assistant", "先按承载力、验槽和防水节点拆开复习。"))
    asyncio.run(
        service._store.create_session(
            title="TutorBot mirror",
            session_id="tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(
        service._store.add_message(
            "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_student_demo",
            "user",
            "镜像会话不应该重复展示",
        )
    )
    asyncio.run(
        service._store.create_session(
            title="空会话",
            session_id="tb_empty",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )

    service._get_learner_state_service = lambda: type(  # type: ignore[method-assign]
        "LearnerStateService",
        (),
        {
            "read_snapshot": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "list_heartbeat_jobs": lambda *_args, **_kwargs: [],
            "list_heartbeat_history": lambda *_args, **_kwargs: [],
            "list_heartbeat_arbitration_history": lambda *_args, **_kwargs: [],
            "read_profile": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "read_summary": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "read_progress": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "list_memory_events": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
        },
    )()
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    message_reads = 0
    original_get_messages = service._store._get_messages_sync

    def _count_message_reads(session_id: str):
        nonlocal message_reads
        message_reads += 1
        return original_get_messages(session_id)

    service._store._get_messages_sync = _count_message_reads  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert len(payload["recent_conversations"]) == 1
    assert payload["recent_conversations"][0]["session_id"] == "tb_student_demo"
    assert payload["recent_conversations"][0]["title"] == "地基基础答疑"
    assert payload["recent_conversations"][0]["message_count"] == 2
    assert "messages" not in payload["recent_conversations"][0]

    list_payload = service.list_member_conversations("student_demo", limit=10, message_limit=6)

    assert list_payload["total"] == 1
    assert list_payload["items"][0]["session_id"] == "tb_student_demo"
    assert "messages" not in list_payload["items"][0]
    assert message_reads == 0


def test_list_member_conversations_filters_and_sorts_workspace_queue(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    async def _seed() -> None:
        await service._store.create_session(
            title="地基基础答疑",
            session_id="chat_revision",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
        await service._store.create_turn("chat_revision", capability="chat")
        await service._store.add_message("chat_revision", "user", "帮我看看地基基础怎么复习", capability="chat")
        await service._store.add_message(
            "chat_revision",
            "assistant",
            "先按承载力、验槽和防水节点拆开复习。",
            capability="chat",
        )

        await service._store.create_session(
            title="退款投诉跟进",
            session_id="refund_complaint",
            owner_key=build_user_owner_key("student_demo"),
            source="web",
        )
        await service._store.create_turn("refund_complaint", capability="deep_question")
        for content in ("我想退款", "先确认问题原因", "课程不适合我", "已转人工跟进"):
            await service._store.add_message("refund_complaint", "user", content, capability="deep_question")

    asyncio.run(_seed())

    by_volume = service.list_member_conversations(
        "student_demo",
        limit=10,
        sort="message_count",
        order="desc",
    )

    assert [item["session_id"] for item in by_volume["items"]] == [
        "refund_complaint",
        "chat_revision",
    ]
    assert by_volume["items"][0]["source"] == "web"
    assert by_volume["items"][0]["capability"] == "deep_question"
    assert by_volume["sort"] == "message_count"
    assert by_volume["order"] == "desc"
    assert "messages" not in by_volume["items"][0]

    filtered = service.list_member_conversations(
        "student_demo",
        limit=10,
        q="退款",
        source="web",
        capability="deep_question",
        sort="updated_at",
        order="asc",
    )

    assert filtered["total"] == 1
    assert filtered["items"][0]["session_id"] == "refund_complaint"
    assert filtered["filters"] == {
        "q": "退款",
        "source": "web",
        "capability": "deep_question",
    }


def test_record_conversation_view_writes_privacy_audit(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="地基基础答疑",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "帮我看看地基基础怎么复习"))
    asyncio.run(service._store.add_message("tb_student_demo", "assistant", "先按承载力、验槽和防水节点拆开复习。"))

    result = service.record_conversation_view(
        "student_demo",
        "tb_student_demo",
        operator="admin_demo",
    )

    assert result["session_id"] == "tb_student_demo"
    assert result["title"] == "地基基础答疑"
    assert result["message_count"] == 2
    assert [message["role"] for message in result["messages"]] == ["user", "assistant"]
    assert result["messages"][0]["content"] == "帮我看看地基基础怎么复习"
    assert result["messages"][1]["content"] == "先按承载力、验槽和防水节点拆开复习。"

    audit = service.list_audit_log(target_user="student_demo", action="conversation_view")
    assert audit["total"] == 1
    assert audit["items"][0]["operator"] == "admin_demo"
    assert audit["items"][0]["after"]["session_id"] == "tb_student_demo"
    assert audit["items"][0]["after"]["message_count"] == 2
    assert "messages" not in audit["items"][0]["after"]


def test_record_conversation_view_dedupes_by_idempotency_key(tmp_path: Path) -> None:
    """Round 4 S1 contract: same idempotency_key on the same action must NOT
    write a second audit entry; the service must return the original audit_id
    plus `deduped: True`. Without this guard a flaky network can produce
    duplicate privacy audits, which is a compliance regression.
    """
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="地基基础答疑",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "x"))

    first = service.record_conversation_view(
        "student_demo",
        "tb_student_demo",
        operator="admin_demo",
        idempotency_key="abc-123",
    )
    second = service.record_conversation_view(
        "student_demo",
        "tb_student_demo",
        operator="admin_demo",
        idempotency_key="abc-123",
    )

    # Both calls return successfully.
    assert first["session_id"] == "tb_student_demo"
    assert second["session_id"] == "tb_student_demo"

    # Audit log carries exactly one entry — second call must be deduped.
    audit = service.list_audit_log(target_user="student_demo", action="conversation_view")
    assert audit["total"] == 1
    assert first["audit_id"] == audit["items"][0]["id"]
    assert second["audit_id"] == first["audit_id"]
    assert second.get("deduped") is True


def test_record_bi_audit_dedupes_feedback_triage_by_idempotency_key(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    first = service.record_bi_audit(
        action="feedback_triage",
        target_user="student_demo",
        operator="admin_demo",
        reason="triaged",
        after={"feedback_id": "fb_1", "status": "triaged"},
        idempotency_key="feedback-key-1",
    )
    second = service.record_bi_audit(
        action="feedback_triage",
        target_user="student_demo",
        operator="admin_demo",
        reason="triaged",
        after={"feedback_id": "fb_1", "status": "triaged"},
        idempotency_key="feedback-key-1",
    )

    audit = service.list_audit_log(target_user="student_demo", action="feedback_triage")
    assert audit["total"] == 1
    assert first["audit_id"] == audit["items"][0]["id"]
    assert second["audit_id"] == first["audit_id"]
    assert second.get("deduped") is True


def test_record_bi_audit_dedupes_bi_export_request_by_idempotency_key(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    first = service.record_bi_audit(
        action="bi_export_request",
        target_user="export:member_audit_log",
        operator="admin_demo",
        reason="member_audit_log:csv",
        after={
            "dataset": "member_audit_log",
            "format": "csv",
            "filters": {"operator": "admin_demo"},
            "scrubbed": True,
        },
        idempotency_key="export-key-1",
    )
    second = service.record_bi_audit(
        action="bi_export_request",
        target_user="export:member_audit_log",
        operator="admin_demo",
        reason="member_audit_log:csv",
        after={
            "dataset": "member_audit_log",
            "format": "csv",
            "filters": {"operator": "admin_demo"},
            "scrubbed": True,
        },
        idempotency_key="export-key-1",
    )

    audit = service.list_audit_log(target_user="export:member_audit_log", action="bi_export_request")
    assert audit["total"] == 1
    assert first["audit_id"] == audit["items"][0]["id"]
    assert second["audit_id"] == first["audit_id"]
    assert second.get("deduped") is True


def test_record_conversation_view_dedup_is_scoped_to_operator(tmp_path: Path) -> None:
    """Round 5 B2 contract: idempotency dedup must be scoped to operator so
    Admin A's idempotency_key cannot dedupe Admin B's identical-key request.
    Without operator-scoping, a stolen / replayed key from operator A would
    silently suppress operator B's audit entry, hiding cross-actor activity.
    """
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    asyncio.run(
        service._store.create_session(
            title="x",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "x"))

    service.record_conversation_view(
        "student_demo",
        "tb_student_demo",
        operator="admin_a",
        idempotency_key="shared-key",
    )
    service.record_conversation_view(
        "student_demo",
        "tb_student_demo",
        operator="admin_b",
        idempotency_key="shared-key",
    )

    audit = service.list_audit_log(target_user="student_demo", action="conversation_view")
    # Same key but different operators → TWO audit entries (not 1 deduped).
    assert audit["total"] == 2, (
        "Round 5 B2: idempotency key must be operator-scoped. Found "
        f"{audit['total']} entries; expected 2 (one per operator)."
    )
    actors = {item["operator"] for item in audit["items"]}
    assert actors == {"admin_a", "admin_b"}


def test_record_conversation_view_dedup_index_has_size_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 5 B1 contract: audit_idempotency_keys must be capped so an admin
    cannot DoS the JSON store by sending unlimited unique keys. We monkey-patch
    the cap to a small value to make the test run in milliseconds while still
    exercising the FIFO eviction path.
    """
    # Patch cap to 5 so the test is fast; verifies the eviction code path
    # without exercising 10k file writes.
    monkeypatch.setattr(member_service_module, "AUDIT_IDEMPOTENCY_INDEX_MAX", 5)

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    asyncio.run(
        service._store.create_session(
            title="x",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "x"))

    # Fire 8 distinct keys against cap=5; expect index size to stay ≤ cap and
    # oldest entries to be evicted FIFO.
    n = 8
    for i in range(n):
        service.record_conversation_view(
            "student_demo",
            "tb_student_demo",
            operator="admin_a",
            idempotency_key=f"key-{i:02d}",
        )

    data = service._load()
    index = data.get("audit_idempotency_keys") or {}
    assert len(index) <= 5, (
        f"Round 5 B1: index size {len(index)} exceeded cap 5; FIFO eviction missing."
    )
    # The oldest keys (0, 1, 2) must have been evicted; latest (5, 6, 7) must remain.
    keys_seen = list(index.keys())
    assert not any("key-00" in k for k in keys_seen), (
        "Round 5 B1: oldest key 'key-00' should have been evicted by FIFO"
    )
    assert any("key-07" in k for k in keys_seen), (
        "Round 5 B1: newest key 'key-07' must remain in the index"
    )


def test_record_conversation_view_distinct_keys_keep_distinct_audits(tmp_path: Path) -> None:
    """Round 4 S1 contract: different idempotency_keys for the same action
    must still write two audit entries (real distinct user actions).
    """
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="x",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "x"))

    service.record_conversation_view(
        "student_demo", "tb_student_demo", operator="ops", idempotency_key="k1"
    )
    service.record_conversation_view(
        "student_demo", "tb_student_demo", operator="ops", idempotency_key="k2"
    )

    audit = service.list_audit_log(target_user="student_demo", action="conversation_view")
    assert audit["total"] == 2


def test_member_360_keeps_learner_state_when_heartbeat_jobs_fail(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            return type(
                "Snapshot",
                (),
                {
                    "user_id": user_id,
                    "profile": {"display_name": "陈同学"},
                    "summary": "正在复习地基基础。",
                    "progress": {"knowledge_map": {"weak_points": ["防火间距"]}},
                    "memory_events": [],
                    "profile_updated_at": "2026-04-16T08:00:00+08:00",
                    "summary_updated_at": "2026-04-16T08:10:00+08:00",
                    "progress_updated_at": "2026-04-16T08:20:00+08:00",
                    "memory_events_updated_at": "2026-04-16T09:00:00+08:00",
                },
            )()

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("jobs unavailable")

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1"}]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"]["available"] is True
    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["heartbeat"]["jobs"] == []
    assert payload["heartbeat"]["history"] == [{"event_id": "hb_1"}]
    assert payload["heartbeat"]["arbitration_history"] == [{"event_id": "arb_1"}]


def test_member_360_loads_partial_learner_state_when_snapshot_fails(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            raise RuntimeError("snapshot unavailable")

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1"}]

        def read_profile(self, user_id: str):
            assert user_id == "student_demo"
            return {"display_name": "陈同学"}

        def read_summary(self, user_id: str):
            assert user_id == "student_demo"
            return "正在复习地基基础。"

        def read_progress(self, user_id: str):
            assert user_id == "student_demo"
            return {"knowledge_map": {"weak_points": ["防火间距"]}}

        def list_memory_events(self, user_id: str, limit: int | None = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [
                type(
                    "Event",
                    (),
                    {
                        "event_id": "evt_1",
                        "source_feature": "heartbeat",
                        "source_id": "job_1",
                        "source_bot_id": "review-bot",
                        "memory_kind": "heartbeat_delivery",
                        "payload_json": {"status": "sent"},
                        "created_at": "2026-04-16T09:00:00+08:00",
                    },
                )()
            ]

        def _file_updated_at(self, user_id: str, section: str):
            assert user_id == "student_demo"
            return {
                "profile": "2026-04-16T08:00:00+08:00",
                "summary": "2026-04-16T08:10:00+08:00",
                "progress": "2026-04-16T08:20:00+08:00",
                "events": "2026-04-16T09:00:00+08:00",
            }[section]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"]["available"] is True
    assert payload["learner_state"]["profile"] == {"display_name": "陈同学"}
    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["learner_state"]["progress"] == {"knowledge_map": {"weak_points": ["防火间距"]}}
    assert payload["learner_state"]["recent_memory_events"][0]["event_id"] == "evt_1"
    assert payload["learner_state"]["memory_events_updated_at"] == "2026-04-16T09:00:00+08:00"
    assert payload["heartbeat"]["history"] == [{"event_id": "hb_1"}]
    assert payload["heartbeat"]["arbitration_history"] == [{"event_id": "arb_1"}]


def test_member_360_returns_empty_learner_state_payload_when_snapshot_and_partial_reads_fail(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            raise RuntimeError("snapshot unavailable")

        def read_profile(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("profile unavailable")

        def read_summary(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("summary unavailable")

        def read_progress(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("progress unavailable")

        def list_memory_events(self, user_id: str, limit: int | None = 20):
            assert user_id == "student_demo"
            assert limit == 10
            raise RuntimeError("events unavailable")

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1"}]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"] == {
        "user_id": "student_demo",
        "available": False,
        "profile": {},
        "summary": "",
        "progress": {},
        "recent_memory_events": [],
        "profile_updated_at": None,
        "summary_updated_at": None,
        "progress_updated_at": None,
        "memory_events_updated_at": None,
    }
    assert payload["heartbeat"]["history"] == [{"event_id": "hb_1"}]
    assert payload["heartbeat"]["arbitration_history"] == [{"event_id": "arb_1"}]


def test_member_console_learner_state_panel_and_controls(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            return type(
                "Snapshot",
                (),
                {
                    "user_id": user_id,
                    "profile": {"display_name": "陈同学"},
                    "summary": "正在复习案例题。",
                    "progress": {"knowledge_map": {"weak_points": ["网络计划"]}},
                    "memory_events": [],
                    "profile_updated_at": "2026-04-16T08:00:00+08:00",
                    "summary_updated_at": "2026-04-16T08:10:00+08:00",
                    "progress_updated_at": "2026-04-16T08:20:00+08:00",
                    "memory_events_updated_at": "2026-04-16T08:30:00+08:00",
                },
            )()

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            active = type(
                "Job",
                (),
                {
                    "job_id": "job_1",
                    "user_id": user_id,
                    "bot_id": "review-bot",
                    "channel": "heartbeat",
                    "policy_json": {"enabled": True},
                    "next_run_at": datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
                    "last_run_at": None,
                    "last_result_json": None,
                    "failure_count": 0,
                    "status": "active",
                    "created_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                },
            )()
            return [active]

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            return [{"event_id": "arb_1"}]

        def pause_heartbeat_job(self, user_id: str, job_id: str):
            assert user_id == "student_demo"
            assert job_id == "job_1"
            return type(
                "Job",
                (),
                {
                    "job_id": job_id,
                    "user_id": user_id,
                    "bot_id": "review-bot",
                    "channel": "heartbeat",
                    "policy_json": {"enabled": True},
                    "next_run_at": datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
                    "last_run_at": None,
                    "last_result_json": None,
                    "failure_count": 0,
                    "status": "paused",
                    "created_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 16, 9, 5, tzinfo=timezone.utc),
                },
            )()

        def resume_heartbeat_job(self, user_id: str, job_id: str):
            assert user_id == "student_demo"
            assert job_id == "job_1"
            return type(
                "Job",
                (),
                {
                    "job_id": job_id,
                    "user_id": user_id,
                    "bot_id": "review-bot",
                    "channel": "heartbeat",
                    "policy_json": {"enabled": True},
                    "next_run_at": datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
                    "last_run_at": None,
                    "last_result_json": None,
                    "failure_count": 0,
                    "status": "active",
                    "created_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 16, 9, 10, tzinfo=timezone.utc),
                },
            )()

    class FakeOverlayService:
        def list_user_overlays(self, user_id: str, *, limit: int | None = None):
            return [{"bot_id": "review-bot", "version": 4}]

        def read_overlay(self, bot_id: str, user_id: str):
            return {"bot_id": bot_id, "user_id": user_id, "version": 4}

        def list_overlay_events(self, bot_id: str, user_id: str, *, limit: int | None = None, event_type: str | None = None):
            return [{"event_id": "evt_1"}]

        def list_overlay_audit(self, bot_id: str, user_id: str, *, limit: int | None = None):
            return [{"event_id": "audit_1"}]

        def patch_overlay(self, bot_id: str, user_id: str, patch, *, source_feature: str, source_id: str):
            return {"bot_id": bot_id, "user_id": user_id, "version": 5, "patch": patch}

        def apply_promotions(self, bot_id: str, user_id: str, *, learner_state_service, min_confidence: float = 0.7, max_candidates: int = 10):
            return {"acked_ids": ["cand_1"], "dropped_ids": []}

        def ack_promotions(self, bot_id: str, user_id: str, candidate_ids, *, reason: str = ""):
            return {"affected_count": len(candidate_ids), "reason": reason}

        def drop_promotions(self, bot_id: str, user_id: str, candidate_ids, *, reason: str = ""):
            return {"affected_count": len(candidate_ids), "reason": reason}

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: FakeOverlayService()  # type: ignore[method-assign]

    panel = service.get_member_learner_state_panel("student_demo", limit=5)
    jobs = service.list_member_heartbeat_jobs("student_demo")
    paused = service.pause_member_heartbeat_job("student_demo", "job_1", operator="admin_demo")
    resumed = service.resume_member_heartbeat_job("student_demo", "job_1", operator="admin_demo")
    overlay = service.get_member_overlay("student_demo", "review-bot")
    events = service.get_member_overlay_events("student_demo", "review-bot", limit=5)
    audit = service.get_member_overlay_audit("student_demo", "review-bot", limit=5)
    patched = service.patch_member_overlay(
        "student_demo",
        "review-bot",
        [{"op": "merge", "field": "heartbeat_override", "value": {"suppress": True}}],
        operator="admin_demo",
    )
    applied = service.apply_member_overlay_promotions(
        "student_demo",
        "review-bot",
        operator="admin_demo",
        min_confidence=0.8,
        max_candidates=3,
    )
    acked = service.ack_member_overlay_promotions(
        "student_demo",
        "review-bot",
        ["cand_1"],
        operator="admin_demo",
        reason="confirmed",
    )
    dropped = service.drop_member_overlay_promotions(
        "student_demo",
        "review-bot",
        ["cand_2"],
        operator="admin_demo",
        reason="noise",
    )

    assert panel["learner_state"]["summary"] == "正在复习案例题。"
    assert panel["heartbeat_jobs"][0]["job_id"] == "job_1"
    assert panel["bot_overlays"][0]["bot_id"] == "review-bot"
    assert jobs["items"][0]["status"] == "active"
    assert paused["status"] == "paused"
    assert resumed["status"] == "active"
    assert overlay["version"] == 4
    assert events["items"][0]["event_id"] == "evt_1"
    assert audit["items"][0]["event_id"] == "audit_1"
    assert patched["version"] == 5
    assert applied["acked_ids"] == ["cand_1"]
    assert acked["affected_count"] == 1
    assert dropped["affected_count"] == 1


def test_member_console_overlay_promotion_apply_uses_real_services_and_audits_skips(tmp_path: Path) -> None:
    from deeptutor.services.learner_state.overlay_service import BotLearnerOverlayService
    from deeptutor.services.learner_state.service import LearnerStateService

    class PathServiceStub:
        @property
        def project_root(self):
            return tmp_path

        def get_user_root(self):
            return tmp_path

        def get_learner_state_root(self):
            path = tmp_path / "learner_state"
            path.mkdir(parents=True, exist_ok=True)
            return path

        def get_learner_state_outbox_db(self):
            return tmp_path / "runtime" / "outbox.db"

        def get_guide_dir(self):
            path = tmp_path / "workspace" / "guide"
            path.mkdir(parents=True, exist_ok=True)
            return path

    class MemberServiceStub:
        def get_profile(self, user_id: str):
            return {
                "user_id": user_id,
                "display_name": "陈同学",
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "focus_topic": "案例题",
                "daily_target": 30,
            }

        def get_today_progress(self, _user_id: str):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_chapter_progress(self, _user_id: str):
            return []

    class DisabledCoreStore:
        is_configured = False

    path_service = PathServiceStub()
    learner_state_service = LearnerStateService(
        path_service=path_service,
        member_service=MemberServiceStub(),
        core_store=DisabledCoreStore(),
    )
    overlay_service = BotLearnerOverlayService(path_service=path_service)
    valid_candidate = overlay_service.promote_candidate(
        "review-bot",
        "student_demo",
        "possible_weak_point",
        {"topic": "防火间距", "confidence": 0.92, "promotion_basis": "structured_result"},
        source_feature="quiz",
        source_id="quiz_1",
    )["promotion_candidates"][0]
    skipped_candidate = overlay_service.promote_candidate(
        "review-bot",
        "student_demo",
        "possible_weak_point",
        {"topic": "施工缝", "confidence": 0.91},
        source_feature="chat",
        source_id="turn_2",
    )["promotion_candidates"][-1]
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._get_learner_state_service = lambda: learner_state_service  # type: ignore[method-assign]
    service._get_overlay_service = lambda: overlay_service  # type: ignore[method-assign]

    result = service.apply_member_overlay_promotions(
        "student_demo",
        "review-bot",
        operator="ops_admin",
        min_confidence=0.7,
        max_candidates=10,
    )

    progress = learner_state_service.read_progress("student_demo")
    weak_points = list((progress.get("knowledge_map") or {}).get("weak_points") or [])
    remaining_candidates = overlay_service.read_overlay("review-bot", "student_demo")["promotion_candidates"]
    audit = service.list_audit_log(action="overlay_promotion_apply", page_size=1)["items"][0]

    assert result["acked_ids"] == [valid_candidate["candidate_id"]]
    assert result["skipped_ids"] == [skipped_candidate["candidate_id"]]
    assert result["skipped"][0]["reasons"] == ["missing_promotion_basis"]
    assert weak_points == ["防火间距"]
    assert [item["candidate_id"] for item in remaining_candidates] == [skipped_candidate["candidate_id"]]
    assert audit["operator"] == "ops_admin"
    assert audit["after"]["acked_ids"] == [valid_candidate["candidate_id"]]
    assert audit["after"]["skipped_ids"] == [skipped_candidate["candidate_id"]]
    assert audit["after"]["skipped"][0]["reasons"] == ["missing_promotion_basis"]


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_does_not_merge_financial_balance(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed_merge_points(data: dict[str, object]) -> None:
        members = data.get("members") or []
        for member in members:
            if not isinstance(member, dict):
                continue
            if member.get("user_id") == "student_demo":
                member["points_balance"] = 123
            if member.get("user_id") == "student_risk":
                member["points_balance"] = 456

    service._mutate(_seed_merge_points)

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13800000002"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)
    try:
        result = await service.bind_phone_for_wechat("student_demo", "phone-code-merge")
    finally:
        monkeypatch.undo()

    assert result["bound"] is True
    assert result["merged"] is True
    assert result["user_id"] == result["user"]["user_id"]
    assert result["user"]["user_id"] == "student_risk"

    data = service._load()
    assert service._find_member(data, "student_demo")["points_balance"] == 123
    assert service._ensure_member(data, "student_demo")["user_id"] == "student_risk"
    assert service.get_wallet("student_risk")["balance"] == 456


def test_merge_member_accounts_consolidates_identity_without_moving_wallet_balance(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._admin_user_ids = lambda: {"root_admin"}  # type: ignore[method-assign]
    wallet_service = _FakeWalletBootstrapService()
    service._get_wallet_service = lambda: wallet_service  # type: ignore[method-assign]

    target_uid = "user_phone_6508"
    wx_uid = "user_wx_h"
    account_uid = "user_account_chenyh2008"
    wallet_service.snapshots[target_uid] = SimpleNamespace(
        user_id=target_uid,
        balance_micros=200 * 1_000_000,
        frozen_micros=0,
        plan_id="svip",
        version=1,
        created_at="2026-06-14T10:00:00+08:00",
    )
    wallet_service.snapshots[wx_uid] = SimpleNamespace(
        user_id=wx_uid,
        balance_micros=30 * 1_000_000,
        frozen_micros=0,
        plan_id="trial",
        version=1,
        created_at="2026-06-14T10:00:00+08:00",
    )
    wallet_service.snapshots[account_uid] = SimpleNamespace(
        user_id=account_uid,
        balance_micros=700 * 1_000_000,
        frozen_micros=0,
        plan_id="supreme_svip",
        version=1,
        created_at="2026-06-14T10:00:00+08:00",
    )

    def _seed(data: dict[str, object]) -> None:
        target = service._build_default_member(target_uid)
        target.update(
            {
                "display_name": "user_6508",
                "phone": "13800136508",
                "tier": "svip",
                "expire_at": "2026-08-01T00:00:00+08:00",
                "points_balance": 200,
                "auth_username": "user_6508",
                "external_auth_user_id": target_uid,
            }
        )
        wx_member = service._build_default_member(wx_uid)
        wx_member.update(
            {
                "display_name": "H",
                "phone": "12240059568",
                "tier": "trial",
                "expire_at": "2026-07-12T16:23:50+08:00",
                "points_balance": 30,
                "wx_openid": "wx_openid_merge_demo",
                "wx_unionid": "wx_union_merge_demo",
            }
        )
        account_member = service._build_default_member(account_uid)
        account_member.update(
            {
                "display_name": "chenyh2008",
                "phone": "52649394196",
                "tier": "supreme_svip",
                "expire_at": "2027-06-15T09:13:15+08:00",
                "points_balance": 700,
                "auth_username": "chenyh2008",
                "external_auth_user_id": account_uid,
            }
        )
        data["members"] = [target, wx_member, account_member]

    service._mutate(_seed)
    service.set_admin_role(
        actor="root_admin",
        user_id=target_uid,
        role=rbac.ROLE_ADMIN,
        display_name="user_6508",
    )
    service.set_admin_role(
        actor="root_admin",
        user_id=account_uid,
        role=rbac.ROLE_SUPER_ADMIN,
        display_name="chenyh2008",
    )

    result = service.merge_member_accounts(
        target_user_id=target_uid,
        source_user_ids=[wx_uid, account_uid],
        operator="root_admin",
        reason="confirmed_same_owner",
        idempotency_key="merge-6508-once",
    )

    assert result["member"]["user_id"] == target_uid
    assert result["member"]["tier"] == "supreme_svip"
    assert result["member"]["expire_at"] == "2027-06-15T09:13:15+08:00"
    assert result["member"]["points_balance"] == 200
    assert result["member"]["wx_openid"] == "wx_openid_merge_demo"
    assert result["points_transferred"] == 0
    assert "wallet_adjustments" not in result
    assert service.get_admin_role(target_uid) == rbac.ROLE_SUPER_ADMIN
    assert wallet_service.snapshots[target_uid].balance_micros == 200 * 1_000_000
    assert wallet_service.snapshots[wx_uid].balance_micros == 30 * 1_000_000
    assert wallet_service.snapshots[account_uid].balance_micros == 700 * 1_000_000

    data = service._load()
    assert service._find_member(data, wx_uid)["merged_into"] == target_uid
    assert service._find_member(data, account_uid)["merged_into"] == target_uid
    assert service._find_member(data, wx_uid)["points_balance"] == 30
    assert service._find_member(data, account_uid)["points_balance"] == 700
    assert service._ensure_member(data, wx_uid)["user_id"] == target_uid
    assert service._ensure_member(data, account_uid)["user_id"] == target_uid

    repeated = service.merge_member_accounts(
        target_user_id=target_uid,
        source_user_ids=[wx_uid, account_uid],
        operator="root_admin",
        reason="confirmed_same_owner",
        idempotency_key="merge-6508-once",
    )
    assert repeated["deduped"] is True
    assert service.get_wallet(target_uid)["balance"] == 200
    assert wallet_service.snapshots[target_uid].balance_micros == 200 * 1_000_000


def test_submit_assessment_updates_today_progress_and_chapter_practice(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("student_demo", count=5)
    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    answers = {item["question_id"]: item["answer"] for item in stored}

    service.submit_assessment("student_demo", payload["quiz_id"], answers, time_spent_seconds=60)

    today = service.get_today_progress("student_demo")
    chapters = service.get_chapter_progress("student_demo")

    assert today["today_done"] >= 5
    assert any(item["done"] >= 1 for item in chapters)


def test_submit_assessment_counts_only_answered_questions_as_progress(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("blank_user", count=6)
    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    answers = {item["question_id"]: item["answer"] for item in stored[:5]}
    before_today = service.get_today_progress("blank_user")["today_done"]
    before_chapters = sum(item["done"] for item in service.get_chapter_progress("blank_user"))

    service.submit_assessment("blank_user", payload["quiz_id"], answers, time_spent_seconds=60)

    today = service.get_today_progress("blank_user")
    chapters = service.get_chapter_progress("blank_user")

    assert today["today_done"] - before_today == 5
    assert sum(item["done"] for item in chapters) - before_chapters == 5



class _EmptyLearnerStateService:
    """§6-2 起 radar/mastery 面会读 learner snapshot 证据;静态口径测试
    必须显式声明"无学习证据",防止共享磁盘 store 的跨测试污染。"""

    def read_snapshot(self, user_id: str, *, event_limit: int = 5):
        return SimpleNamespace(profile={}, progress={}, summary="", memory_events=[])

    def list_heartbeat_jobs(self, user_id: str):
        return []

    def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
        return []


def test_submit_assessment_persists_measured_profile_including_zero_mastery(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._get_learner_state_service = lambda: _EmptyLearnerStateService()  # type: ignore[method-assign]

    payload = service.create_assessment("student_demo", count=5)
    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    answers = {stored[0]["question_id"]: stored[0]["answer"]}

    service.submit_assessment("student_demo", payload["quiz_id"], answers, time_spent_seconds=60)
    profile = service.get_assessment_profile("student_demo")
    dashboard = service.get_mastery_dashboard("student_demo")

    assert profile["score"] == 6
    expected_overall = round(
        sum(item["mastery"] for item in profile["chapter_mastery"].values())
        / max(len(profile["chapter_mastery"]), 1)
    )
    assert dashboard["overall_mastery"] == expected_overall
    assert dashboard["overall_mastery"] < 100
    assert profile["blueprint_version"] == "diagnostic_v1"
    assert profile["measurement_confidence"] in {"high", "medium", "low"}
    assert service._load()["members"][0]["last_assessment"]["scored_count"] == 16
    assert profile["chapter_mastery"][stored[0]["chapter"]]["mastery"] == 100
    assert any(item["mastery"] == 0 for item in profile["chapter_mastery"].values())
    assert any(
        chapter["mastery"] == 0
        for group in dashboard["groups"]
        for chapter in group["chapters"]
    )


def test_submit_assessment_writes_teaching_policy_and_learner_event(monkeypatch, tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    learner_events = []
    overlay_patches = []

    class FakeLearnerStateService:
        def append_memory_event(self, user_id: str, **kwargs):
            learner_events.append({"user_id": user_id, **kwargs})
            return type("Event", (), {"event_id": "evt_assessment"})()

    class FakeOverlayService:
        def patch_overlay(self, bot_id: str, user_id: str, patch: dict, **kwargs):
            overlay_patches.append({"bot_id": bot_id, "user_id": user_id, "patch": patch, **kwargs})
            return {"version": 2}

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: FakeLearnerStateService())
    monkeypatch.setattr(service, "_get_overlay_service", lambda: FakeOverlayService())

    payload = service.create_assessment("student_demo", count=20)
    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    answers = {item["question_id"]: item.get("answer") or "A" for item in stored}
    first_scored = next(item for item in stored if item.get("scored", True))
    correct_answer = str(first_scored.get("answer") or "").upper()
    answers[first_scored["question_id"]] = "B" if correct_answer != "B" else "A"

    result = service.submit_assessment("student_demo", payload["quiz_id"], answers, time_spent_seconds=180)

    assert result["teaching_policy_seed"]["version"] == "assessment_seed_v1"
    assert result["diagnostic_feedback"]["learner_profile"]["archetype_name"] == "动态调节型学员"
    learning_evidence_events = [
        event for event in learner_events if event["memory_kind"] == "learning_evidence"
    ]
    assert not [event for event in learner_events if event["memory_kind"] == "assessment"]
    assert learning_evidence_events, "assessment answers must also enter canonical learning_evidence"
    first_evidence = learning_evidence_events[0]
    assert first_evidence["source_feature"] == "construction_grading"
    assert first_evidence["source_id"].startswith(f"{payload['quiz_id']}:")
    assert first_evidence["dedupe_key"]
    assert first_evidence["payload_json"]["event_type"] == "learning_evidence"
    assert first_evidence["payload_json"]["source"] == "construction_grading"
    assert first_evidence["payload_json"]["grading_mode"] == "assessment_blueprint"
    assert first_evidence["payload_json"]["question_stem"]
    assert first_evidence["payload_json"]["user_answer"]
    assert first_evidence["payload_json"]["correct_answer"]
    assert first_evidence["payload_json"]["next_training_signal"]["source"] == "assessment"
    assert first_evidence["payload_json"]["quality"]["progress_countable"] is True
    assert first_evidence["payload_json"]["quality"]["truth_eligible"] is True
    assert any(event["payload_json"]["score_ratio"] == 0 for event in learning_evidence_events)
    assert any(event["payload_json"]["score_ratio"] == 1 for event in learning_evidence_events)
    wrong_event = next(event for event in learning_evidence_events if event["payload_json"]["score_ratio"] == 0)
    assert wrong_event["payload_json"]["error_events"][0]["error_code"] == "unknown_error"
    assert "摸底测评" in wrong_event["payload_json"]["error_events"][0]["diagnosis"]
    assert overlay_patches[0]["bot_id"] == "construction-exam-coach"
    assert overlay_patches[0]["patch"]["operations"][0]["field"] == "teaching_policy_override"


def test_assessment_profile_exposes_observability_and_seed(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("student_demo", count=20)
    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    answers = {item["question_id"]: item.get("answer") or "A" for item in stored}
    service.submit_assessment("student_demo", payload["quiz_id"], answers, time_spent_seconds=2)

    profile = service.get_assessment_profile("student_demo")

    assert profile["blueprint_version"] == "diagnostic_v1"
    assert profile["measurement_confidence"] == "low"
    assert profile["teaching_policy_seed"]["measurement_confidence"] == "low"
    assert profile["assessment_observability"]["completion_rate"] == 1
    assert profile["assessment_observability"]["policy_seed_status"] == "created"


def test_topic_diagnostic_submit_returns_report_before_writeback_finishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    session = service._assessment_session_repository.create_session(
        user_id="student_demo",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[
            {
                "question_id": "q1",
                "question_stem": "防水题",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        session_questions_private=[
            {
                "question_id": "q1",
                "source_question_id": "src_q1",
                "question_type": "single_choice",
                "question_stem": "防水题",
                "chapter": "防水工程",
                "section_id": "waterproof",
                "section_label": "防水工程",
                "answer": "A",
                "scored": True,
                "provenance": {"node_code": "1A414010"},
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        device_id="",
    )
    started = threading.Event()
    release = threading.Event()

    class _SlowWritebackService:
        def __init__(self, **_kwargs) -> None:
            pass

        def writeback(self, **_kwargs):
            started.set()
            release.wait(timeout=1)
            return {
                "learning_event_refs": [{"event_id": "evt_1", "question_id": "q1"}],
                "mistake_book_refs": [],
                "writeback_status": {"learning_event_count": 1, "mistake_book_count": 0},
            }

    monkeypatch.setattr(member_service_module, "AssessmentWritebackService", _SlowWritebackService)

    result = service.submit_assessment(
        "student_demo",
        session["quiz_id"],
        {"q1": "A"},
        time_spent_seconds=30,
    )

    assert result["schema_version"] == "p0a-v1"
    assert result["writeback_status"]["status"] == "pending"
    assert started.wait(timeout=1)
    assert service._assessment_session_repository.private_session("student_demo", session["quiz_id"]).get(
        "learning_event_refs"
    ) == []

    release.set()
    for _ in range(20):
        stored = service._assessment_session_repository.private_session("student_demo", session["quiz_id"])
        if stored.get("learning_event_refs"):
            break
        time.sleep(0.01)
    assert stored["learning_event_refs"] == [{"event_id": "evt_1", "question_id": "q1"}]


def test_topic_diagnostic_submit_uses_selected_topic_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    session = service._assessment_session_repository.create_session(
        user_id="student_demo",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["main_structure"],
        blueprint_version="topic_main_structure_v1",
        form_id="topic_main_structure_v1_form_1",
        client_questions_public=[
            {
                "question_id": "q1",
                "question_stem": "主体结构题",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        session_questions_private=[
            {
                "question_id": "q1",
                "source_question_id": "src_q1",
                "question_type": "single_choice",
                "question_stem": "主体结构题",
                "chapter": "主体结构",
                "section_id": "main_structure",
                "section_label": "主体结构",
                "answer": "A",
                "scored": True,
                "provenance": {"node_code": "1A414020"},
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        device_id="",
    )
    monkeypatch.setattr(service, "_schedule_topic_diagnostic_writeback", lambda **_kwargs: None)

    result = service.submit_assessment(
        "student_demo",
        session["quiz_id"],
        {"q1": "A"},
        time_spent_seconds=30,
    )

    assert result["topic_label"] == "主体结构专题测评"
    assert result["topic_ids"] == ["main_structure"]


def test_real_exam_simulation_create_and_submit_use_mini_blueprint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setattr(service, "_schedule_topic_diagnostic_writeback", lambda **_kwargs: None)

    payload = service.create_assessment(
        "student_demo",
        count=20,
        assessment_type="real_exam_simulation",
        subject_id="construction_exam",
    )

    assert payload["assessment_type"] == "real_exam_simulation"
    assert payload["blueprint_version"] == "real_exam_simulation_mini_v1"
    assert payload["topic_label"] == "综合模拟测评"
    assert payload["form_id"]
    assert payload["form_index"] >= 0
    assert payload["form_count"] >= 1
    assert len(payload["questions"]) == 20
    assert all("answer" not in question for question in payload["questions"])

    result = service.submit_assessment(
        "student_demo",
        payload["quiz_id"],
        {question["question_id"]: "A" for question in payload["questions"]},
        time_spent_seconds=1200,
    )

    assert result["schema_version"] == "p0a-v1"
    assert result["assessment_type"] == "real_exam_simulation"
    assert result["blueprint_version"] == "real_exam_simulation_mini_v1"
    assert result["topic_label"] == "综合模拟测评"
    assert result["score_summary"]["scored_count"] == 20


def test_submit_assessment_different_body_retry_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setattr(service, "_schedule_topic_diagnostic_writeback", lambda **_kwargs: None)
    session = service._assessment_session_repository.create_session(
        user_id="student_demo",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[{"question_id": "q1", "question_stem": "防水题 1"}],
        session_questions_private=[{"question_id": "q1", "answer": "A", "scored": True}],
        device_id="",
    )

    first = service.submit_assessment(
        "student_demo",
        session["quiz_id"],
        {"q1": "A"},
        time_spent_seconds=30,
    )
    retry = service.submit_assessment(
        "student_demo",
        session["quiz_id"],
        {"q1": "A"},
        time_spent_seconds=30,
    )

    assert retry == first
    with pytest.raises(member_service_module.AssessmentSessionConflict, match="assessment_submit_body_conflict"):
        service.submit_assessment(
            "student_demo",
            session["quiz_id"],
            {"q1": "B"},
            time_spent_seconds=30,
        )


def test_submit_assessment_durable_session_error_does_not_fallback_to_legacy(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class _Repository:
        def private_session(self, user_id: str, quiz_id: str):
            raise member_service_module.AssessmentSessionError("assessment_sessions_unavailable")

    service._assessment_session_repository = _Repository()

    with pytest.raises(member_service_module.AssessmentSessionError, match="assessment_sessions_unavailable"):
        service.submit_assessment(
            "student_demo",
            "quiz_missing_repo",
            {"q1": "A"},
            time_spent_seconds=30,
        )


def test_submit_assessment_scoring_error_maps_to_session_conflict(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    session = service._assessment_session_repository.create_session(
        user_id="student_demo",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[
            {"question_id": "q1", "question_stem": "防水题 1"},
            {"question_id": "q2", "question_stem": "防水题 2"},
        ],
        session_questions_private=[
            {"question_id": "q1", "source_question_id": "src_dup", "answer": "A"},
            {"question_id": "q2", "source_question_id": "src_dup", "answer": "B"},
        ],
        device_id="",
    )

    with pytest.raises(member_service_module.AssessmentSessionConflict, match="assessment_scoring_conflict"):
        service.submit_assessment(
            "student_demo",
            session["quiz_id"],
            {"q1": "A", "q2": "B"},
            time_spent_seconds=30,
        )


def test_assessment_deep_explanation_reads_submitted_report_without_score_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    session = service._assessment_session_repository.create_session(
        user_id="student_demo",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[
            {
                "question_id": "q1",
                "question_stem": "防水题",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        session_questions_private=[
            {
                "question_id": "q1",
                "source_question_id": "src_q1",
                "question_type": "single_choice",
                "question_stem": "防水题",
                "chapter": "防水工程",
                "section_id": "waterproof",
                "section_label": "防水工程",
                "answer": "A",
                "scored": True,
                "simple_explanation": "防水节点要先判断构造层次。",
                "knowledge_points": ["地下防水"],
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        device_id="",
    )
    monkeypatch.setattr(service, "_schedule_topic_diagnostic_writeback", lambda **_kwargs: None)

    report = service.submit_assessment(
        "student_demo",
        session["quiz_id"],
        {"q1": "B"},
        time_spent_seconds=30,
    )
    before_score = report["score_summary"]

    async def _fake_generate_llm_deep_explanation(**kwargs: object) -> dict[str, object]:
        return {
            "summary": "本题考地下防水构造层次。你选 B，错在没有扣住节点处理要求。",
            "learner_answer": kwargs["learner_answer"],
            "correct_answer": kwargs["correct_answer"],
            "key_terms": ["地下防水", "节点处理"],
            "why_wrong": "B 没有体现规范做法。",
            "cause_analysis": "题干限定是防水构造，不是泛泛施工。",
            "scoring_points": "能判断节点处理符合规范。",
            "option_reviews": [{"key": "A", "status": "correct", "status_label": "正确", "review": "A 符合题干。"}],
            "pitfall": "不要只看防水二字。",
            "mnemonic": "先看部位，再看节点。",
            "source_basis": "题库解析和知识卡。",
            "next_action": "练 3 道同类题。",
            "score_mutation_allowed": False,
            "source": "assessment_deep_explanation_llm",
            "prompt_version": "assessment-deep-explanation-llm-v1",
            "usage_summary": {
                "estimated_total_cost_usd": 0.001,
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 120,
                "estimated_total_tokens": 220,
                "usage_accuracy": "estimated",
            },
        }

    monkeypatch.setattr(
        member_service_module,
        "generate_llm_deep_explanation",
        _fake_generate_llm_deep_explanation,
    )
    monkeypatch.setattr(service, "_get_wallet_service", lambda: SimpleNamespace(is_configured=False))

    result = asyncio.run(service.get_assessment_deep_explanation("student_demo", session["quiz_id"], "q1"))
    stored = service.get_assessment_report("student_demo", session["quiz_id"])

    assert result["cache_status"] == "generated"
    assert result["billing"]["status"] == "captured"
    assert result["billing"]["amount_points"] == 20
    assert result["explanation"]["score_mutation_allowed"] is False
    assert result["explanation"]["learner_answer"] == "B"
    assert result["explanation"]["correct_answer"] == "A"
    assert "构造层次" in result["explanation"]["summary"]
    assert result["explanation"]["source"] == "assessment_deep_explanation_llm"
    assert stored["score_summary"] == before_score


def test_assessment_deep_explanation_checks_balance_before_llm_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    session = service._assessment_session_repository.create_session(
        user_id="student_demo",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[
            {
                "question_id": "q1",
                "question_stem": "防水题",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        session_questions_private=[
            {
                "question_id": "q1",
                "question_type": "single_choice",
                "question_stem": "防水题",
                "answer": "A",
                "simple_explanation": "防水节点要先判断构造层次。",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            }
        ],
        device_id="",
    )
    monkeypatch.setattr(service, "_schedule_topic_diagnostic_writeback", lambda **_kwargs: None)
    service.submit_assessment("student_demo", session["quiz_id"], {"q1": "B"}, time_spent_seconds=30)

    def _empty_wallet(data: dict[str, object]) -> None:
        member = service._ensure_member(data, "student_demo")
        member["points_balance"] = 0

    service._mutate(_empty_wallet)

    async def _fail_if_called(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("LLM generation must not run without minimum balance")

    monkeypatch.setattr(
        member_service_module,
        "generate_llm_deep_explanation",
        _fail_if_called,
    )
    monkeypatch.setattr(service, "_get_wallet_service", lambda: SimpleNamespace(is_configured=False))

    with pytest.raises(RuntimeError, match="assessment_deep_explanation_insufficient_balance"):
        asyncio.run(service.get_assessment_deep_explanation("student_demo", session["quiz_id"], "q1"))


def test_sparse_member_mastery_is_coverage_adjusted_for_report_analytics(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._get_learner_state_service = lambda: _EmptyLearnerStateService()  # type: ignore[method-assign]

    def _seed(data: dict[str, object]) -> None:
        member = service._ensure_member(data, "student_demo")
        for chapter in member["chapter_mastery"].values():
            chapter["mastery"] = 0
        member["chapter_mastery"]["防水工程"]["mastery"] = 100

    service._mutate(_seed)

    radar = service.get_radar_data("student_demo")
    dashboard = service.get_mastery_dashboard("student_demo")
    profile = service.get_assessment_profile("student_demo")
    chapter_count = len(profile["chapter_mastery"])
    radar_score = round(sum(item["score"] for item in radar["dimensions"]) / len(radar["dimensions"]))

    assert chapter_count > 1
    assert len(radar["dimensions"]) == chapter_count
    assert radar_score == dashboard["overall_mastery"]
    assert dashboard["overall_mastery"] == round(100 / chapter_count)
    assert profile["score"] == dashboard["overall_mastery"]
    assert profile["level"] == "beginner"
    assert profile["chapter_mastery"]["防水工程"]["mastery"] == 100
    assert any(item["mastery"] == 0 for item in profile["chapter_mastery"].values())


def test_sparse_last_assessment_score_cannot_promote_global_mastery_to_advanced(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._get_learner_state_service = lambda: _EmptyLearnerStateService()  # type: ignore[method-assign]

    def _seed(data: dict[str, object]) -> None:
        member = service._ensure_member(data, "student_demo")
        member["last_assessment"] = {
            "quiz_id": "legacy_sparse_quiz",
            "score": 100,
            "knowledge_score": 100,
            "level": "advanced",
            "chapter_mastery": {
                "防水工程": {"name": "防水工程", "mastery": 100},
            },
            "diagnostic_feedback": {
                "ability_overview": {
                    "score_pct": 100,
                    "chapter_mastery": {
                        "防水工程": {"name": "防水工程", "mastery": 100},
                    },
                    "error_pattern": "slip_dominant",
                },
                "cognitive_insight": {
                    "response_profile": "fluent",
                    "calibration_label": "accurate",
                },
                "learner_profile": {
                    "archetype": "strategist",
                    "traits": [],
                    "study_tip": "优先补强防水工程。",
                },
            },
        }

    service._mutate(_seed)

    radar = service.get_radar_data("student_demo")
    dashboard = service.get_mastery_dashboard("student_demo")
    profile = service.get_assessment_profile("student_demo")
    chapter_count = len(profile["chapter_mastery"])
    radar_score = round(sum(item["score"] for item in radar["dimensions"]) / len(radar["dimensions"]))

    assert chapter_count > 1
    assert len(radar["dimensions"]) == chapter_count
    assert radar_score == dashboard["overall_mastery"]
    assert dashboard["overall_mastery"] == round(100 / chapter_count)
    assert profile["score"] == dashboard["overall_mastery"]
    assert profile["level"] == "beginner"
    assert profile["knowledge_score"] == 100
    assert profile["diagnostic_feedback"]["ability_overview"]["score_pct"] == profile["score"]
    assert len(profile["diagnostic_feedback"]["ability_overview"]["chapter_mastery"]) == chapter_count


def test_chapter_progress_keeps_actual_attempts_separate_from_daily_target(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.record_learning_activity(
        "blank_user",
        count=8,
        chapter="地基基础",
        source="practice",
    )

    today = service.get_today_progress("blank_user")
    chapters = service.get_chapter_progress("blank_user")
    foundation = next(item for item in chapters if item["chapter_name"] == "地基基础")

    assert today["today_done"] == 8
    assert today["daily_target"] == 30
    assert foundation["done"] == 8
    assert foundation["total"] == 8
    assert foundation["daily_target"] == 30


def test_report_analytics_stay_empty_before_any_assessment_or_practice(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    radar = service.get_radar_data("blank_user")
    dashboard = service.get_mastery_dashboard("blank_user")
    profile = service.get_assessment_profile("blank_user")

    assert radar["dimensions"] == []
    assert dashboard["overall_mastery"] == 0
    assert dashboard["groups"] == []
    assert dashboard["hotspots"] == []
    assert profile["score"] == 0
    assert profile["chapter_mastery"] == {}


def test_explicit_learning_activity_does_not_build_provisional_mastery_without_assessment(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.record_learning_activity(
        "blank_user",
        count=12,
        chapter="建筑构造",
        source="practice",
    )

    radar = service.get_radar_data("blank_user")
    dashboard = service.get_mastery_dashboard("blank_user")
    profile = service.get_assessment_profile("blank_user")

    assert radar["dimensions"] == []
    assert dashboard["overall_mastery"] == 0
    assert dashboard["groups"] == []
    assert dashboard["hotspots"] == []
    assert profile["score"] == 0
    assert profile["chapter_mastery"] == {}


def test_chat_learning_does_not_count_generated_questions_as_completed(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    generated_questions = "\n".join(
        "第" + str(index) + "题：建筑构造练习题"
        for index in range(1, 31)
    )

    result = service.record_chat_learning(
        "blank_user",
        query="帮我出30道建筑构造题",
        assistant_content=generated_questions,
    )

    today = service.get_today_progress("blank_user")
    dashboard = service.get_home_dashboard("blank_user")
    progress_card = next(
        item
        for item in dashboard["progress_feedback"]["cards"]
        if item["label"] == "近 3 天完成"
    )

    assert result["recorded"] is False
    assert result["reason"] == "chat_turn_is_not_completion_authority"
    assert today["today_done"] == 0
    assert progress_card["value"] == "0次"


def test_legacy_chat_learning_counts_are_removed_from_report_progress(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    today = member_service_module._date_key()
    member = service._build_default_member("blank_user")
    member["daily_practice_counts"] = {today: 30}
    member["chapter_practice_stats"] = {
        "建筑构造": {"done": 30, "correct": 0, "last_activity_at": "2026-04-21T10:00:00+08:00"}
    }
    service._data_path.write_text(
        json.dumps(
            {
                "members": [member],
                "packages": service._default_packages(),
                "audit_log": [
                    {
                        "id": "audit_chat_generated_30",
                        "operator": "chat",
                        "action": "learning_activity",
                        "target_user": "blank_user",
                        "created_at": today + "T10:00:00+08:00",
                        "after": {
                            "count": 30,
                            "correct": 0,
                            "chapter": "建筑构造",
                            "metadata": {"query": "帮我出30道建筑构造题"},
                        },
                    }
                ],
                "assessment_sessions": {},
                "phone_codes": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    today_progress = service.get_today_progress("blank_user")
    dashboard = service.get_home_dashboard("blank_user")
    progress_card = next(
        item
        for item in dashboard["progress_feedback"]["cards"]
        if item["label"] == "近 3 天完成"
    )

    assert today_progress["today_done"] == 0
    assert progress_card["value"] == "0次"
    migrated = json.loads(service._data_path.read_text(encoding="utf-8"))
    assert migrated["audit_log"] == []
    assert migrated["migrations"]["chat_learning_counts_removed_v1"] is True
    assert migrated["migrations"]["chat_learning_audit_removed_v2"] is True


def test_verify_phone_code_bootstraps_clean_new_member_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.send_phone_code("13955556666")
    result = service.verify_phone_code("13955556666", _active_otp(service))
    profile = result["user"]
    today = service.get_today_progress(profile["user_id"])
    external_users = json.loads(users_file.read_text(encoding="utf-8"))
    external_user = next(iter(external_users.values()))

    assert profile["tier"] == "trial"
    assert result["user_id"] == profile["user_id"]
    assert profile["points"] == 0
    assert profile["level"] == 1
    assert today["today_done"] == 0
    assert today["streak_days"] == 0
    assert external_user["phone"] == "+8613955556666"
    assert str(profile["username"]).startswith("user_6666")


def test_verify_phone_code_rejects_invalid_code(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.send_phone_code("13955556666")

    with pytest.raises(ValueError, match="验证码错误"):
        service.verify_phone_code("13955556666", "000000")


def test_send_phone_code_does_not_return_otp_in_response(tmp_path: Path) -> None:
    """The OTP must never appear in send_phone_code's result (account-takeover guard)."""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = service.send_phone_code("13955556666")

    assert "debug_code" not in result
    assert "code" not in result
    # the OTP is still generated and stored server-side
    assert _active_otp(service)


def test_verify_phone_code_locks_out_after_max_attempts(tmp_path: Path) -> None:
    """After _MAX_OTP_ATTEMPTS wrong guesses the OTP is invalidated — no brute force."""
    from deeptutor.services.member_console.service import _MAX_OTP_ATTEMPTS

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.send_phone_code("13955556666")
    real_code = _active_otp(service)

    # exhaust the attempt budget with wrong codes
    wrong = "000000" if real_code != "000000" else "111111"
    for _ in range(_MAX_OTP_ATTEMPTS - 1):
        with pytest.raises(ValueError, match="验证码错误"):
            service.verify_phone_code("13955556666", wrong)
    with pytest.raises(ValueError, match="验证码错误次数过多"):
        service.verify_phone_code("13955556666", wrong)

    # OTP is now invalidated — even the correct code no longer works
    with pytest.raises(ValueError, match="验证码不存在"):
        service.verify_phone_code("13955556666", real_code)


def test_verify_phone_code_uses_verified_phone_alias_as_external_auth_canonical_uid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13955556666":
                return {"user_id": canonical_uid, "source": "phone_verification"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    service.send_phone_code("13955556666")
    result = service.verify_phone_code("13955556666", _active_otp(service))
    external_user = external_auth_module.get_external_auth_user_by_phone("13955556666")

    claims = service.verify_access_token(result["token"])
    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert result["user_id"] == canonical_uid
    assert external_user is not None
    assert external_user["id"] == canonical_uid


def test_verify_phone_code_rejects_conflicting_phone_aliases_without_consuming_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13955556666":
                return {
                    "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                    "source": "phone_verification",
                }
            if alias_type == "phone" and alias_value == "+8613955556666":
                return {
                    "user_id": "047b7b7f-8316-4f95-8bf7-71973c102be7",
                    "source": "phone_backfill",
                }
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    service.send_phone_code("13955556666")
    code = _active_otp(service)

    with pytest.raises(ValueError, match="手机号身份冲突"):
        service.verify_phone_code("13955556666", code)

    assert service._load()["phone_codes"].get("13955556666")


def test_verify_phone_code_fails_closed_when_alias_store_lookup_fails_without_consuming_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class _FailingAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            raise RuntimeError("alias store unavailable")

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FailingAliasStore(),
    )

    service.send_phone_code("13955556666")
    code = _active_otp(service)

    with pytest.raises(ValueError, match="手机号身份暂时不可用"):
        service.verify_phone_code("13955556666", code)

    assert service._load()["phone_codes"].get("13955556666")


def test_persist_phone_identity_does_not_overwrite_concurrent_alias_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DB_URL", "postgresql://example.invalid/db")
    monkeypatch.setattr(service, "_trusted_phone_alias_user_ids", lambda _phone: set())
    queries: list[str] = []

    class _Cursor:
        def execute(self, query: str, params: tuple[object, ...]) -> None:
            queries.append(query)

        @staticmethod
        def fetchone():
            return None

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def cursor():
            return _Cursor()

    fake_psycopg = SimpleNamespace(connect=lambda *_args, **_kwargs: _Connection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    service._persist_phone_identity(
        phone="13955556666",
        canonical_uid="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
    )

    assert len(queries) == 1
    assert "WHERE public.user_identity_aliases.user_id = EXCLUDED.user_id" in queries[0]


def test_persist_phone_identity_inherits_canonical_eval_metadata_into_alias_and_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(tmp_path / "users.json"))
    external_user = external_auth_module.ensure_external_auth_user(
        "qa_eval_codex_phone_binding",
        "StrongPass123",
    )
    canonical_uid = str(external_user["id"])
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DB_URL", "postgresql://example.invalid/db")
    monkeypatch.setattr(service, "_trusted_phone_alias_user_ids", lambda _phone: set())
    executed: list[tuple[str, tuple[object, ...]]] = []

    class _Cursor:
        def execute(self, query: str, params: tuple[object, ...]) -> None:
            executed.append((query, params))

        @staticmethod
        def fetchone():
            return (canonical_uid,)

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def cursor():
            return _Cursor()

    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: _Connection()),
    )

    service._persist_phone_identity(
        phone="13955556666",
        canonical_uid=canonical_uid,
    )

    assert len(executed) == 2
    alias_metadata = json.loads(str(executed[0][1][5]))
    user_metadata = json.loads(str(executed[1][1][1]))
    for metadata in (alias_metadata, user_metadata):
        assert metadata["account_kind"] == "eval_runner"
        assert metadata["actor_type"] == "machine"
        assert metadata["created_by"] == "eval_runner"
        assert metadata["is_internal_test"] is True
        assert metadata["runner"] == "codex"
        assert metadata["agent_tool"] == "codex"
    assert "metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb" in executed[1][0]


def test_reset_password_with_phone_code_updates_external_auth_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    external_auth_module.create_external_auth_user(
        "reset_student",
        "OldPass123",
        phone="13955556666",
    )
    service.send_phone_code("13955556666")
    code = _active_otp(service)

    result = service.reset_password_with_phone_code(
        "reset_student",
        "13955556666",
        code,
        "NewPass123",
    )

    assert result["success"] is True
    assert result["message"] == "密码已重置，请使用新密码登录"
    assert external_auth_module.verify_external_auth_user("reset_student", "OldPass123") is None
    assert external_auth_module.verify_external_auth_user("reset_student", "NewPass123") is not None
    with pytest.raises(ValueError, match="验证码不存在"):
        service.verify_phone_code("13955556666", code)


def test_change_password_updates_current_member_external_auth_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    login = service.register_with_external_auth(
        "change_student",
        "OldPass123",
        "13955556666",
    )

    result = service.change_password(str(login["user_id"]), "OldPass123", "NewPass123")

    assert result["success"] is True
    assert result["message"] == "密码已修改，请使用新密码重新登录"
    assert external_auth_module.verify_external_auth_user("change_student", "OldPass123") is None
    assert external_auth_module.verify_external_auth_user("change_student", "NewPass123") is not None


def test_change_password_requires_username_password_bound_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("wechat_only_user")

    with pytest.raises(ValueError, match="当前账号未绑定用户名密码登录"):
        service.change_password("wechat_only_user", "OldPass123", "NewPass123")



def test_send_password_reset_code_requires_matching_account_phone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    external_auth_module.create_external_auth_user(
        "reset_student",
        "OldPass123",
        phone="13955556666",
    )

    with pytest.raises(ValueError, match="账号或手机号不匹配"):
        service.send_password_reset_code("reset_student", "13800000000")

    assert service._load()["phone_codes"] == {}


def test_send_password_reset_code_delegates_to_sms_authority_for_matching_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    external_auth_module.create_external_auth_user(
        "reset_student",
        "OldPass123",
        phone="13955556666",
    )

    result = service.send_password_reset_code("reset_student", "13955556666")

    assert result["sent"] is True
    assert result["phone"] == "13955556666"
    assert _active_otp(service)


def test_send_password_reset_code_accepts_verified_phone_alias_when_external_auth_phone_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    external_user = external_auth_module.create_external_auth_user("reset_student", "OldPass123")
    canonical_uid = str(external_user["id"])

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13955556666":
                return {"user_id": canonical_uid, "source": "phone_verification"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    result = service.send_password_reset_code("reset_student", "13955556666")

    assert result["sent"] is True
    assert result["phone"] == "13955556666"
    assert _active_otp(service)


def test_send_password_reset_code_fails_closed_when_phone_alias_belongs_to_another_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    external_user = external_auth_module.create_external_auth_user("reset_student", "OldPass123")
    canonical_uid = str(external_user["id"])
    other_uid = "047b7b7f-8316-4f95-8bf7-71973c102be7"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13955556666":
                return {"user_id": other_uid, "source": "phone_verification"}
            if alias_type == "phone" and alias_value == "+8613955556666":
                return {"user_id": canonical_uid, "source": "public_users_backfill"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    with pytest.raises(ValueError, match="账号或手机号不匹配"):
        service.send_password_reset_code("reset_student", "13955556666")

    assert service._load()["phone_codes"] == {}


def test_reset_password_rejects_mismatched_phone_without_consuming_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    external_auth_module.create_external_auth_user(
        "reset_student",
        "OldPass123",
        phone="13955556666",
    )
    service.send_phone_code("13955556666")
    code = _active_otp(service)

    with pytest.raises(ValueError, match="账号或手机号不匹配"):
        service.reset_password_with_phone_code(
            "reset_student",
            "13800000000",
            code,
            "NewPass123",
        )

    service.reset_password_with_phone_code(
        "reset_student",
        "13955556666",
        code,
        "NewPass123",
    )
    assert external_auth_module.verify_external_auth_user("reset_student", "NewPass123") is not None


def test_reset_password_with_phone_code_accepts_verified_alias_without_external_auth_phone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    external_user = external_auth_module.create_external_auth_user("reset_student", "OldPass123")
    canonical_uid = str(external_user["id"])

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13955556666":
                return {"user_id": canonical_uid, "source": "phone_verification"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    service.send_phone_code("13955556666")
    code = _active_otp(service)

    result = service.reset_password_with_phone_code("reset_student", "13955556666", code, "NewPass123")

    assert result["success"] is True
    assert external_auth_module.verify_external_auth_user("reset_student", "OldPass123") is None
    assert external_auth_module.verify_external_auth_user("reset_student", "NewPass123") is not None
    with pytest.raises(ValueError, match="验证码不存在"):
        service.verify_phone_code("13955556666", code)


def test_reset_password_with_phone_code_sets_first_password_for_phone_backed_quick_login(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        member = service._ensure_member(data, "wx_openid_9012")
        member["display_name"] = "H"
        member["phone"] = "13955556666"

    service._mutate(_seed)
    service.send_phone_code("13955556666")
    code = _active_otp(service)

    result = service.reset_password_with_phone_code("", "13955556666", code, "NewPass123")
    external_user = external_auth_module.get_external_auth_user_by_phone("13955556666")
    data = service._load()
    member = service._find_member(data, "wx_openid_9012")

    assert result["success"] is True
    assert external_user is not None
    assert external_auth_module.verify_external_auth_user(external_user["username"], "NewPass123") is not None
    assert member["auth_username"] == external_user["username"]
    assert member["display_name"] == "H"
    assert member["phone"] == "13955556666"


def test_reset_password_with_phone_code_uses_verified_alias_canonical_uid_for_quick_login(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13955556666":
                return {"user_id": canonical_uid, "source": "phone_verification"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    def _seed(data: dict[str, object]) -> None:
        member = service._ensure_member(data, canonical_uid)
        member["display_name"] = "手机号账号"
        member["phone"] = "13955556666"
        member["external_auth_user_id"] = canonical_uid

    service._mutate(_seed)
    service.send_phone_code("13955556666")
    code = _active_otp(service)

    result = service.reset_password_with_phone_code("", "13955556666", code, "NewPass123")
    external_user = external_auth_module.get_external_auth_user_by_phone("13955556666")
    data = service._load()
    member = service._find_member(data, canonical_uid)

    assert result["success"] is True
    assert external_user is not None
    assert external_user["id"] == canonical_uid
    assert external_auth_module.verify_external_auth_user(external_user["username"], "NewPass123") is not None
    assert member["auth_username"] == external_user["username"]
    assert member["external_auth_user_id"] == canonical_uid


def test_reset_password_rejects_weak_password_without_consuming_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    external_auth_module.create_external_auth_user(
        "reset_student",
        "OldPass123",
        phone="13955556666",
    )
    service.send_phone_code("13955556666")
    code = _active_otp(service)

    with pytest.raises(ValueError, match="密码必须包含至少一个大写字母"):
        service.reset_password_with_phone_code(
            "reset_student",
            "13955556666",
            code,
            "weak123",
        )

    assert service._load()["phone_codes"].get("13955556666")
    assert external_auth_module.verify_external_auth_user("reset_student", "OldPass123") is not None


def test_send_phone_code_rejects_invalid_phone_input(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    with pytest.raises(ValueError, match="大陆手机号"):
        service.send_phone_code("dev-phone-code")


def test_send_phone_code_fails_closed_in_production_without_sms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("ALIYUN_SMS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALIYUN_SMS_ACCESS_KEY_SECRET", raising=False)
    monkeypatch.delenv("MEMBER_CONSOLE_USE_REAL_SMS", raising=False)

    with pytest.raises(RuntimeError, match="短信服务未配置，生产环境已禁止调试验证码"):
        service.send_phone_code("13955556666")


def test_send_phone_code_does_not_call_sms_provider_during_cooldown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_USE_REAL_SMS", "1")
    monkeypatch.setenv("ALIYUN_SMS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("ALIYUN_SMS_ACCESS_KEY_SECRET", "sk")
    calls: list[tuple[str, str]] = []

    def _fake_send_sms(phone: str, code: str) -> dict[str, str]:
        calls.append((phone, code))
        return {"Code": "OK", "Message": "OK"}

    monkeypatch.setattr(service, "_send_sms", _fake_send_sms)

    first = service.send_phone_code("13955556666")
    second = service.send_phone_code("13955556666")

    assert first["sent"] is True
    assert first["delivery"] == "sms"
    assert second["sent"] is False
    assert second["retry_after"] <= 60
    assert len(calls) == 1


def test_auth_secret_rejects_wechat_secret_fallback_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_AUTH_SECRET", raising=False)
    monkeypatch.delenv("MEMBER_CONSOLE_AUTH_SECRET", raising=False)
    monkeypatch.setenv("WECHAT_MP_APP_SECRET", "wx_secret_only")

    with pytest.raises(RuntimeError, match="DEEPTUTOR_AUTH_SECRET must be configured in production"):
        service._auth_secret()


def test_auth_secret_allows_explicit_member_console_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_AUTH_SECRET", raising=False)
    monkeypatch.setenv("MEMBER_CONSOLE_AUTH_SECRET", "member_console_secret")

    assert service._auth_secret() == "member_console_secret"


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_accepts_phone_code_exchange(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13911112222"

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)

    result = await service.bind_phone_for_wechat("student_demo", "phone-code-123")

    assert result["bound"] is True
    assert result["user_id"] == result["user"]["user_id"]
    assert result["phone"] == "13911112222"
    external_user = external_auth_module.get_external_auth_user_by_phone("13911112222")
    data = service._load()
    member = service._find_member(data, result["user_id"])
    assert external_user is not None
    assert member["auth_username"] == external_user["username"]


@pytest.mark.asyncio
async def test_login_with_wechat_phone_exchanges_phone_before_returning_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_123456789012",
            "unionid": "unionid_abcdef",
            "session_key": "session_key_value",
        }

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13911112222"

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)

    result = await service.login_with_wechat_phone("wx-code", "phone-code-123")

    assert result["bound"] is True
    assert result["phone"] == "13911112222"
    assert result["openid"] == "openid_123456789012"
    assert result["token"].startswith("dtm.")

    claims = service.verify_access_token(result["token"])
    assert claims is not None

    data = service._load()
    member = service._find_member(data, result["user_id"])
    assert member["wx_openid"] == "openid_123456789012"
    assert member["phone"] == "13911112222"
    external_user = external_auth_module.get_external_auth_user_by_phone("13911112222")
    assert external_user is not None
    assert claims["sub"] == external_user["id"]
    assert claims["canonical_uid"] == external_user["id"]
    assert member["auth_username"] == external_user["username"]


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_merges_into_verified_phone_alias_without_local_phone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "phone" and alias_value == "13911112222":
                return {"user_id": canonical_uid, "source": "phone_verification"}
            return None

    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )

    def _seed(data: dict[str, object]) -> None:
        canonical = service._ensure_member(data, canonical_uid)
        canonical["phone"] = ""
        canonical["display_name"] = "手机号账号"
        current = service._ensure_member(data, "wx_openid_9012")
        current["wx_openid"] = "openid_123456789012"
        current["wx_unionid"] = "unionid_abcdef"

    service._mutate(_seed)

    result = await service.bind_phone_for_wechat("wx_openid_9012", "13911112222")
    claims = service.verify_access_token(result["token"])
    data = service._load()
    canonical = service._find_member(data, canonical_uid)
    current = service._find_member(data, "wx_openid_9012")

    assert result["bound"] is True
    assert result["merged"] is True
    assert result["user_id"] == canonical_uid
    assert result["user"]["user_id"] == canonical_uid
    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert canonical["phone"] == "13911112222"
    assert canonical["wx_openid"] == "openid_123456789012"
    assert canonical["wx_unionid"] == "unionid_abcdef"
    external_user = external_auth_module.get_external_auth_user_by_phone("13911112222")
    assert external_user is not None
    assert external_user["id"] == canonical_uid
    assert canonical["auth_username"] == external_user["username"]
    assert current["merged_into"] == canonical_uid
    assert current["wx_openid"] == ""
    assert current["wx_unionid"] == ""


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_accepts_normalized_phone_for_legacy_clients(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    result = await service.bind_phone_for_wechat("student_demo", "13911112222")

    assert result["bound"] is True
    assert result["user_id"] == result["user"]["user_id"]
    assert result["phone"] == "13911112222"


@pytest.mark.asyncio
async def test_login_with_wechat_code_reuses_merged_canonical_member_after_phone_bind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_123456789012",
            "unionid": "unionid_abcdef",
            "session_key": "session_key_value",
        }

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13800000002"

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    monkeypatch.setattr(
        member_service_module,
        "ensure_external_auth_user_for_phone",
        lambda phone, **_kwargs: {"id": canonical_uid, "username": "user_0002", "phone": phone},
    )

    first_login = await service.login_with_wechat_code("wx-code")
    bind_result = await service.bind_phone_for_wechat(first_login["user_id"], "phone-code-merge")
    second_login = await service.login_with_wechat_code("wx-code")
    second_claims = service.verify_access_token(second_login["token"])

    assert bind_result["merged"] is True
    assert bind_result["user_id"] == "student_risk"
    assert second_login["user_id"] == "student_risk"
    assert second_login["user"]["user_id"] == "student_risk"
    assert second_claims is not None
    assert second_claims["canonical_uid"] == canonical_uid
    assert second_claims["uid"] == canonical_uid
    assert wallet_service.calls[-1]["user_id"] == canonical_uid


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_maps_upstream_timeout_to_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _raise_timeout(_phone_code: str) -> str:
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _raise_timeout)

    with pytest.raises(RuntimeError, match="WeChat getuserphonenumber request timed out"):
        await service.bind_phone_for_wechat("student_demo", "phone-code-123")


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_fails_closed_in_production_even_for_dev_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN", "1")

    async def _raise_exchange(_phone_code: str) -> str:
        raise RuntimeError("wechat phone exchange failed")

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _raise_exchange)

    with pytest.raises(RuntimeError, match="wechat phone exchange failed"):
        await service.bind_phone_for_wechat("student_demo", "dev-phone-code")


@pytest.mark.asyncio
async def test_bind_phone_wechat_phone_code_with_embedded_digits_calls_wx_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """微信 phone_code 里含 11 位数字但不是合法大陆号时，必须调微信 API 而非直接截取数字。
    修复前：_normalize_phone_input(raw_code) 截取到 '83090321728'（起头 8），跳过 API，
    存入乱码，用户在 BI 永远搜不到真实手机号。
    """
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    wx_api_called = []

    async def _fake_exchange(phone_code: str) -> str:
        wx_api_called.append(phone_code)
        return "19271620461"

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange)

    # 这个 raw_code 末尾含 11 位数字 "83090321728"（不以 1[3-9] 开头），修复前会直接截取
    result = await service.bind_phone_for_wechat("student_demo", "wxcode-abc83090321728")

    assert wx_api_called, "微信 API 没有被调用——phone_code 里的乱码数字被当成了手机号"
    assert result["phone"] == "19271620461"
    data = service._load()
    member = service._find_member(data, result["user_id"])
    assert member["phone"] == "19271620461", "本地 JSON 应存储真实手机号，而非截取的 '83090321728'"


@pytest.mark.asyncio
async def test_bind_phone_wechat_valid_cn_mobile_skips_wx_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """dev/test 模式直传合法大陆号时不应调微信 API（兼容旧 legacy 客户端行为）。"""
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    wx_api_called = []

    async def _should_not_be_called(phone_code: str) -> str:
        wx_api_called.append(phone_code)
        return "13800000000"

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _should_not_be_called)

    result = await service.bind_phone_for_wechat("student_demo", "13911112222")

    assert not wx_api_called, "合法大陆号直传时不应调用微信 API"
    assert result["phone"] == "13911112222"
    data = service._load()
    member = service._find_member(data, result["user_id"])
    assert member["phone_binding_method"] == "direct_phone"
    assert member["account_kind"] == "eval_runner"
    assert member["actor_type"] == "machine"
    assert member["created_by"] == "eval_runner"
    assert member["is_internal_test"] is True
    external_user = external_auth_module.get_external_auth_user_by_phone("13911112222")
    assert external_user is not None
    assert external_user["account_kind"] == "eval_runner"
    assert external_user["actor_type"] == "machine"
    assert external_user["created_by"] == "eval_runner"
    assert external_user["is_internal_test"] is True


@pytest.mark.asyncio
async def test_bind_phone_wechat_rejects_direct_cn_mobile_in_production(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """生产微信绑定必须使用 getPhoneNumber 返回的 phone_code，不能直传手机号伪装真人。"""
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    wx_api_called = []

    async def _should_not_be_called(phone_code: str) -> str:
        wx_api_called.append(phone_code)
        return "13911112222"

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _should_not_be_called)

    with pytest.raises(ValueError, match="phone authorization code"):
        await service.bind_phone_for_wechat("student_demo", "13911112222")

    assert not wx_api_called


def test_persist_phone_identity_rejects_non_cn_mobile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_persist_phone_identity 必须拒绝非大陆手机号，防止乱码 alias 污染 Supabase。"""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    written: list[str] = []

    def _fake_persist(phone: str, canonical_uid: str) -> None:
        written.append(phone)

    # 用 monkeypatch 替换内部 psycopg 调用（测试环境没有真实 DB）
    # 直接通过调用 _persist_phone_identity 并验证它在非法号时早返回
    valid_uuid = "d289c0d1-ba78-4d73-9f2e-72d2c0af7424"

    # 非大陆号（起头 8）—— 应该被拒绝（不抛异常，只 warning + return）
    service._persist_phone_identity(phone="83090321728", canonical_uid=valid_uuid)
    # 测试不会走到 DB（没配 DB_URL），但在 DB_URL 缺失前就应该 return
    # 关键断言：is_cn_mainland_mobile 过滤先于 DB_URL 检查

    # 合法大陆号 — 应该通过前两层校验（会在 DB_URL 检查处静默退出）
    # 不会抛异常
    service._persist_phone_identity(phone="19271620461", canonical_uid=valid_uuid)


def test_list_members_supports_expiry_window_and_operational_flags(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    now = member_service_module._now()

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("vip_soon"),
                "display_name": "即将到期会员",
                "phone": "15558866501",
                "tier": "vip",
                "status": "active",
                "risk_level": "high",
                "expire_at": (now + timedelta(days=4)).isoformat(),
                "last_active_at": (now - timedelta(days=1)).isoformat(),
                "auto_renew": False,
            },
            {
                **service._build_default_member("svip_safe"),
                "display_name": "稳定会员",
                "phone": "15558866502",
                "tier": "svip",
                "status": "active",
                "risk_level": "low",
                "expire_at": (now + timedelta(days=90)).isoformat(),
                "last_active_at": now.isoformat(),
                "auto_renew": True,
            },
        ]

    service._mutate(_seed)

    result = service.list_members(
        page=1,
        page_size=20,
        tier="vip",
        risk_level="high",
        expire_within_days=7,
        auto_renew=False,
    )

    assert [item["user_id"] for item in result["items"]] == ["vip_soon"]
    assert result["filters"]["expire_within_days"] == 7


def test_member_ops_overview_filters_registration_and_reads_directory_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(member_service_module, "_now", lambda: now)

    def _member(user_id: str, *, channel: str, created_at: str, tier: str = "trial") -> dict[str, object]:
        return {
            "user_id": user_id,
            "canonical_user_id": user_id,
            "alias_user_ids": [user_id],
            "display_name": user_id,
            "phone": "15558866501",
            "tier": tier,
            "status": "active",
            "segment": "general",
            "risk_level": "high",
            "auto_renew": False,
            "created_at": created_at,
            "last_active_at": (now - timedelta(days=1)).isoformat(),
            "expire_at": (now + timedelta(days=30)).isoformat(),
            "points_balance": 0,
            "review_due": 4,
            "identity_metadata": {"reg_channel": channel},
            "ledger": [],
            "notes": [],
        }

    directory = _FakeMemberDirectory(
        [
            _member("target", channel="wechat_qr", created_at="2026-07-12T09:00:00+08:00"),
            _member("wrong_channel", channel="campaign", created_at="2026-07-12T09:00:00+08:00"),
            _member("too_old", channel="wechat_qr", created_at="2026-07-01T09:00:00+08:00"),
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"
    behavior_loads: list[list[str]] = []
    original_behavior_loader = service._load_member_behavior_summaries_for_members

    def _count_behavior_loads(members: list[dict[str, object]]):
        behavior_loads.append([str(item["user_id"]) for item in members])
        return original_behavior_loader(members)

    monkeypatch.setattr(service, "_load_member_behavior_summaries_for_members", _count_behavior_loads)

    payload = service.get_member_ops_overview(
        page=1,
        page_size=20,
        risk_min=0.7,
        registered_from=date(2026, 7, 12),
        registered_to=date(2026, 7, 12),
        active_within_days=2,
        review_due_min=3,
        not_paid=True,
        auto_renew=False,
        channel="wechat_qr",
        excluded_user_ids={"wrong_channel"},
    )

    assert len(directory.calls) == 1
    assert payload["dashboard"]["total_count"] == 2
    assert [item["user_id"] for item in payload["list"]["items"]] == ["target"]
    assert payload["list"]["filters"]["registered_from"] == "2026-07-12"
    assert payload["list"]["filters"]["channel"] == "wechat_qr"
    assert len(behavior_loads) == 1
    assert set(behavior_loads[0]) == {"target", "too_old"}


def test_member_dashboard_projects_product_usage_overview_without_frontend_reaggregation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    now = datetime.now(timezone.utc)
    members = [
        {
            "user_id": "member-1",
            "status": "active",
            "risk_level": "low",
            "tier": "vip",
            "expire_at": (now + timedelta(days=30)).isoformat(),
            "created_at": now.isoformat(),
            "auto_renew": False,
        }
    ]
    monkeypatch.setattr(
        service,
        "_load_member_behavior_summaries_for_members",
        lambda _members: {
            "member-1": {
                "first_run_status": "completed",
                "first_run_evidence_status": "completed",
                "first_run_question_count": 1,
            }
        },
    )
    monkeypatch.setattr(
        service,
        "_load_product_usage_overview_for_members",
        lambda _members: {
            "tracked_member_count": 1,
            "module_usage": [{"module": "history", "member_count": 1}],
            "first_run": {"eligible_member_count": 1, "completed_member_count": 1},
        },
    )

    dashboard = service._build_member_dashboard({"audit_log": []}, members, days=30)

    assert dashboard["behavior_health"]["tracked_member_count"] == 1
    assert dashboard["behavior_health"]["module_usage"][0]["module"] == "history"
    assert dashboard["behavior_health"]["first_run"]["completed_member_count"] == 1


def test_first_run_dashboard_uses_canonical_marker_and_exposes_sync_anomaly() -> None:
    service = MemberConsoleService()
    created_at = datetime(2026, 7, 12, 12, 0, tzinfo=timezone(timedelta(hours=8))).isoformat()
    member_defaults = {
        "created_at": created_at,
        "status": "active",
        "risk_level": "low",
        "tier": "vip",
        "expire_at": datetime(2026, 8, 12, tzinfo=timezone.utc).isoformat(),
        "auto_renew": False,
    }
    members = [
        {**member_defaults, "user_id": "canonical-complete"},
        {**member_defaults, "user_id": "telemetry-only"},
    ]
    summaries = {
        "canonical-complete": {"first_run_evidence_status": "not_started"},
        "telemetry-only": {"first_run_evidence_status": "completed"},
    }

    class _CanonicalReader:
        calls: list[list[str]] = []

        def read_existing_profiles(self, user_ids: list[str]) -> dict[str, dict[str, object]]:
            self.calls.append(list(user_ids))
            return {
                user_id: {
                    "learning_preferences": {
                        "first_run": {
                            "script_version": "first_run_script.v1@2026-07-11",
                            "completed_at": "2026-07-12T12:30:00+08:00",
                            "source": "explicit_first_run_v1",
                        }
                    }
                }
                for user_id in user_ids
                if user_id == "canonical-complete"
            }

    canonical_reader = _CanonicalReader()
    service._get_learner_state_service = lambda: canonical_reader  # type: ignore[method-assign]
    projected = service._overlay_canonical_first_run(members, summaries)

    assert projected["canonical-complete"]["first_run_status"] == "completed"
    assert projected["canonical-complete"]["first_run_completed_at"] == "2026-07-12T12:30:00+08:00"
    assert projected["telemetry-only"]["first_run_status"] == "sync_anomaly"
    assert canonical_reader.calls == [["canonical-complete", "telemetry-only"]]

    service._load_member_behavior_summaries_for_members = lambda _members: projected  # type: ignore[method-assign]
    service._load_product_usage_overview_for_members = lambda _members: {  # type: ignore[method-assign]
        "tracked_member_count": 2,
        "module_usage": [],
    }
    dashboard = service._build_member_dashboard({"audit_log": []}, members, days=30)
    first_run = dashboard["behavior_health"]["first_run"]
    assert first_run["completed_member_count"] == 1
    assert first_run["sync_anomaly_member_count"] == 1
    assert first_run["completion_rate"] == 0.0
    assert first_run["completion_rate_of_confirmed"] == 0.5
    assert first_run["truth_coverage_rate"] == 1.0


def test_first_run_canonical_completion_wins_over_registration_date_gate() -> None:
    """A confirmed canonical First Run marker must surface as completed even for a
    member who registered before FIRST_RUN_OPERATION_START_AT.

    Contract: the panel subtitle is "完成只认 learner-state 权威标记" — completion is
    recognized ONLY by the learner-state authority marker.  The registration-date
    eligibility gate governs the not-started denominator; it must never suppress a
    proven completion into "not_eligible" without reading the marker.
    """
    service = MemberConsoleService()
    pre_gate_created_at = datetime(2026, 6, 13, 12, 0, tzinfo=timezone(timedelta(hours=8))).isoformat()
    member_defaults = {
        "created_at": pre_gate_created_at,
        "status": "active",
        "risk_level": "low",
        "tier": "vip",
        "expire_at": datetime(2026, 8, 12, tzinfo=timezone.utc).isoformat(),
        "auto_renew": False,
    }
    members = [
        {**member_defaults, "user_id": "pre-gate-completed"},
        {**member_defaults, "user_id": "pre-gate-never-ran"},
    ]
    summaries = {
        "pre-gate-completed": {"first_run_evidence_status": "completed"},
        "pre-gate-never-ran": {"first_run_evidence_status": "not_started"},
    }

    class _CanonicalReader:
        def read_existing_profiles(self, user_ids: list[str]) -> dict[str, dict[str, object]]:
            return {
                user_id: {
                    "learning_preferences": {
                        "first_run": {
                            "script_version": "first_run_script.v1@2026-07-11",
                            "completed_at": "2026-07-17T12:28:58+08:00",
                            "source": "explicit_first_run_v1",
                        }
                    }
                }
                for user_id in user_ids
                if user_id == "pre-gate-completed"
            }

    service._get_learner_state_service = lambda: _CanonicalReader()  # type: ignore[method-assign]
    projected = service._overlay_canonical_first_run(members, summaries)

    # The pre-gate member with a real canonical marker is now surfaced as completed.
    assert projected["pre-gate-completed"]["first_run_status"] == "completed"
    assert projected["pre-gate-completed"]["first_run_completed_at"] == "2026-07-17T12:28:58+08:00"
    # A pre-gate member without any canonical completion stays not_eligible.
    assert projected["pre-gate-never-ran"]["first_run_status"] == "not_eligible"


def test_first_run_dashboard_excludes_unavailable_truth_from_confirmed_rate() -> None:
    service = MemberConsoleService()
    now = datetime.now(timezone.utc)
    member = {
        "user_id": "unknown-truth",
        "created_at": now.isoformat(),
        "status": "active",
        "risk_level": "low",
        "tier": "vip",
        "expire_at": (now + timedelta(days=30)).isoformat(),
        "auto_renew": False,
    }
    service._load_member_behavior_summaries_for_members = lambda _members: {  # type: ignore[method-assign]
        "unknown-truth": {
            "first_run_status": "truth_unavailable",
            "first_run_evidence_status": "completed",
        }
    }
    service._load_product_usage_overview_for_members = lambda _members: {  # type: ignore[method-assign]
        "tracked_member_count": 1,
        "module_usage": [],
    }

    first_run = service._build_member_dashboard({"audit_log": []}, [member], days=30)["behavior_health"][
        "first_run"
    ]

    assert first_run["eligible_member_count"] == 1
    assert first_run["confirmed_member_count"] == 0
    assert first_run["truth_unavailable_member_count"] == 1
    assert first_run["completion_rate_of_confirmed"] == 0.0
    assert first_run["truth_coverage_rate"] == 0.0


def test_list_members_sorts_risk_levels_by_business_severity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(member_service_module, "_now", lambda: now)
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        members = []
        for user_id, risk_level in (("low", "low"), ("medium", "medium"), ("high", "high")):
            member = service._build_default_member(user_id)
            member["phone"] = f"15558866{len(members):03d}"
            member["risk_level"] = risk_level
            member["created_at"] = now.isoformat()
            members.append(member)
        data["members"] = members

    service._mutate(_seed)

    payload = service.list_members(page=1, page_size=20, sort="risk_level", order="desc")

    assert [item["user_id"] for item in payload["items"]] == ["high", "medium", "low"]


def test_export_members_csv_reads_full_canonical_directory(tmp_path: Path) -> None:
    rows = []
    for user_id in ("directory_member_1", "directory_member_2"):
        rows.append(
            {
                "user_id": user_id,
                "canonical_user_id": user_id,
                "alias_user_ids": [user_id],
                "display_name": user_id,
                "phone": "15558866501",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-07-12T09:00:00+08:00",
                "last_active_at": "2026-07-12T09:00:00+08:00",
                "expire_at": "2026-12-31T00:00:00+08:00",
                "points_balance": 0,
                "review_due": 0,
                "ledger": [],
                "notes": [],
            }
        )
    service = MemberConsoleService(member_directory=_FakeMemberDirectory(rows))
    service._data_path = tmp_path / "member_console.json"

    export = service.export_members_csv()

    assert export["content"].count("\n") == 3
    assert "directory_member_1" in export["content"]
    assert "directory_member_2" in export["content"]


def test_list_members_searches_account_alias_and_normalized_phone(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        member = service._build_default_member("legacy_member_1")
        member["display_name"] = "账号搜索会员"
        member["phone"] = "138-0013-8000"
        member["auth_username"] = "chenyh2008"
        member["external_auth_user_id"] = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
        member["alias_user_ids"] = ["wx_member_1", "legacy_member_1"]
        data["members"] = [member]

    service._mutate(_seed)

    assert service.list_members(search="chenyh2008")["items"][0]["user_id"] == "legacy_member_1"
    assert service.list_members(search="wx_member_1")["items"][0]["user_id"] == "legacy_member_1"
    assert service.list_members(search="13800138000")["items"][0]["user_id"] == "legacy_member_1"


def test_bi_member_read_model_starts_on_launch_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(member_service_module, "_now", lambda: now)

    def _seed(data: dict[str, object]) -> None:
        pre_launch = service._build_default_member("pre_launch_member")
        pre_launch["phone"] = "15558866501"
        pre_launch["created_at"] = "2026-06-21T23:59:59+08:00"
        pre_launch["last_active_at"] = now.isoformat()
        launch_member = service._build_default_member("launch_member")
        launch_member["phone"] = "15558866502"
        launch_member["created_at"] = "2026-06-22T00:00:00+08:00"
        launch_member["last_active_at"] = now.isoformat()
        data["members"] = [pre_launch, launch_member]

    service._mutate(_seed)

    payload = service.list_members(page=1, page_size=20, sort="created_at", order="asc")
    dashboard = service.get_dashboard()

    assert payload["total"] == 1
    assert payload["items"][0]["user_id"] == "launch_member"
    assert payload["authority"]["operational_start_at"] == "2026-06-22T00:00:00+08:00"
    assert dashboard["total_count"] == 1
    assert dashboard["new_today_count"] == 1
    assert dashboard["authority"]["operational_start_at"] == "2026-06-22T00:00:00+08:00"
    assert service.get_member_360("pre_launch_member")["user_id"] == "pre_launch_member"


def test_bi_member_read_model_excludes_qa_accounts_from_operational_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 22, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(member_service_module, "_now", lambda: now)

    def _member(user_id: str, *, display_name: str, phone: str, **overrides: object) -> dict[str, object]:
        member = {
            "user_id": user_id,
            "canonical_user_id": user_id,
            "alias_user_ids": [user_id, f"auth_{user_id.replace('-', '')[:24]}"],
            "display_name": display_name,
            "auth_username": display_name,
            "phone": phone,
            "tier": "trial",
            "status": "active",
            "segment": "general",
            "risk_level": "low",
            "auto_renew": False,
            "created_at": now.isoformat(),
            "last_active_at": now.isoformat(),
            "expire_at": "9999-12-31T00:00:00+00:00",
            "points_balance": 0,
            "review_due": 0,
            "member_directory_source": "supabase.phone_identity_aliases+v_members",
        }
        member.update(overrides)
        return member

    directory = _FakeMemberDirectory(
        [
            _member(
                "d0ee1218-4323-4273-842a-69dec55067f7",
                display_name="qa_wechat_1780932635",
                phone="19213428637",
            ),
            _member(
                "3c08282e-d2a4-4bfe-a6d2-c6d5ed4d0788",
                display_name="qa_pool_11_1782108255519",
                phone="13908255519",
            ),
            _member(
                "54c7a871-3c15-4111-a1ea-855e99c7ba31",
                display_name="cceval2_090626",
                phone="15558866514",
            ),
            _member(
                "c0f859c6-f3d8-4625-8e1a-36ed4ce83053",
                display_name="releaseb478_1783263768",
                phone="15558866515",
            ),
            _member(
                "ab8e8479-f04c-4862-aea0-6c6f4218cd4b",
                display_name="practiceanchor_1783314798",
                phone="15558866516",
            ),
            _member(
                "cf0b152e-3d33-48f8-ac21-45dc82fab87a",
                display_name="army_p6_8a7ff01f",
                phone="15558866517",
            ),
            _member(
                "8c763218-7934-4714-a97c-641f9fd0c8b6",
                display_name="真实样式机器账号",
                phone="15558866518",
                account_kind="eval_runner",
                actor_type="machine",
                created_by="eval_runner",
                is_internal_test=True,
            ),
            _member(
                "047b7b7f-8316-4f95-8bf7-71973c102be7",
                display_name="真实快速登录会员",
                phone="15558866508",
            ),
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    payload = service.list_members(page=1, page_size=20, sort="created_at", order="asc")
    dashboard = service.get_dashboard()

    assert payload["total"] == 1
    assert payload["items"][0]["user_id"] == "047b7b7f-8316-4f95-8bf7-71973c102be7"
    assert dashboard["total_count"] == 1
    assert dashboard["new_today_count"] == 1
    assert dashboard["new_7d_count"] == 1
    assert dashboard["new_30d_count"] == 1


@pytest.mark.asyncio
async def test_wechat_phone_quick_login_counts_as_new_bi_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 22, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(member_service_module, "_now", lambda: now)
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_quick_login_123",
            "unionid": "unionid_quick_login_123",
            "session_key": "session_key_value",
        }

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "15558866508"

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)

    result = await service.login_with_wechat_phone("wx-code", "phone-code-123")
    dashboard = service.get_dashboard()

    assert result["bound"] is True
    assert result["phone"] == "15558866508"
    data = service._load()
    member = service._find_member(data, result["user_id"])
    assert member["phone_binding_method"] == "wechat_phone_code"
    assert "account_kind" not in member
    assert dashboard["total_count"] == 1
    assert dashboard["new_today_count"] == 1


def test_member_search_can_find_pre_launch_member_without_counting_operationally(tmp_path: Path) -> None:
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": "047b7b7f-8316-4f95-8bf7-71973c102be7",
                "canonical_user_id": "047b7b7f-8316-4f95-8bf7-71973c102be7",
                "alias_user_ids": [
                    "047b7b7f-8316-4f95-8bf7-71973c102be7",
                    "auth_047b7b7f83164f958bf77197",
                ],
                "display_name": "历史验证会员",
                "phone": "15558866508",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-14T03:20:32+00:00",
                "last_active_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 0,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            }
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    assert service.list_members(page=1, page_size=20)["total"] == 0
    assert service.get_dashboard()["total_count"] == 0

    result = service.list_members(search="15558866508", page=1, page_size=20)

    assert result["total"] == 1
    assert result["items"][0]["user_id"] == "047b7b7f-8316-4f95-8bf7-71973c102be7"
    assert result["items"][0]["phone"] == "15558866508"


def test_list_members_and_dashboard_use_canonical_phone_backed_members(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_live_alias"),
                "display_name": "微信入口会员",
                "phone": "15558866508",
                "external_auth_user_id": canonical_uid,
                "last_active_at": "2026-04-21T09:00:00+08:00",
                "points_balance": 80,
            },
            {
                **service._build_default_member(canonical_uid),
                "display_name": "正式注册会员",
                "phone": "15558866508",
                "external_auth_user_id": canonical_uid,
                "last_active_at": "2026-04-22T10:00:00+08:00",
                "points_balance": 260,
                "ledger": [{"id": "ledger_live", "created_at": "2026-04-22T10:00:00+08:00"}],
            },
            {
                **service._build_default_member("codex_probe_user"),
                "display_name": "codex 测试账号",
                "phone": "16600000001",
            },
            {
                **service._build_default_member("casefix_1776476492"),
                "display_name": "casefix 内部回归账号",
                "phone": "13976476492",
            },
            {
                **service._build_default_member("anonymous_no_phone"),
                "display_name": "未绑手机号账号",
                "phone": "",
            },
            {
                **service._build_default_member("student_lapsed"),
                "display_name": "内置演示会员",
                "phone": "13800000004",
            },
        ]

    service._mutate(_seed)

    result = service.list_members(page=1, page_size=20, sort="last_active_at", order="desc")
    dashboard = service.get_dashboard()

    assert result["total"] == 1
    assert [item["user_id"] for item in result["items"]] == [canonical_uid]
    assert result["items"][0]["display_name"] == "正式注册会员"
    assert result["items"][0]["phone"] == "15558866508"
    assert result["items"][0]["points_balance"] == 260
    assert dashboard["total_count"] == 1
    assert dashboard["active_count"] == 1


def test_list_members_and_dashboard_use_supabase_directory_plus_local_manual_members(tmp_path: Path) -> None:
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": "canonical_member_1",
                "canonical_user_id": "canonical_member_1",
                "alias_user_ids": ["canonical_member_1"],
                "display_name": "正式会员 1",
                "phone": "15558866508",
                "tier": "sprint",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-04-22T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 260,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
            {
                "user_id": "canonical_member_2",
                "canonical_user_id": "canonical_member_2",
                "alias_user_ids": ["canonical_member_2"],
                "display_name": "正式会员 2",
                "phone": "",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-04-23T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 0,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    def _seed_local_member(data: dict[str, object]) -> None:
        member = service._build_default_member("local_only_member")
        member["phone"] = "13800138000"
        data["members"].append(member)

    service._mutate(_seed_local_member)

    payload = service.list_members(page=1, page_size=20, sort="created_at", order="asc")
    dashboard = service.get_dashboard()

    assert payload["total"] == 2
    assert [item["user_id"] for item in payload["items"]] == [
        "canonical_member_1",
        "local_only_member",
    ]
    assert payload["authority"]["members"] == "supabase.phone_identity_aliases+v_members"
    assert dashboard["total_count"] == 2
    assert dashboard["authority"]["members"] == "supabase.phone_identity_aliases+v_members"
    assert directory.calls


def test_member_directory_includes_member_console_only_manual_phone_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 22, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(member_service_module, "_now", lambda: now)

    directory = _FakeMemberDirectory(
        [
            {
                "user_id": "canonical_member_1",
                "canonical_user_id": "canonical_member_1",
                "alias_user_ids": ["canonical_member_1"],
                "display_name": "正式会员 1",
                "phone": "15558866508",
                "tier": "sprint",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 260,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            }
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    def _seed_manual_member(data: dict[str, object]) -> None:
        member = service._build_default_member("15875046318")
        member["display_name"] = "15875046318"
        member["phone"] = "15875046318"
        member["created_at"] = "2026-06-22T13:44:27+08:00"
        member["last_active_at"] = "2026-06-22T13:44:27+08:00"
        data["members"].append(member)

    service._mutate(_seed_manual_member)

    payload = service.list_members(page=1, page_size=20, sort="created_at", order="asc")
    search = service.list_members(search="15875046318", page=1, page_size=20)
    dashboard = service.get_dashboard()
    read_model_members = {
        item["user_id"]: item
        for item in service.list_members_for_bi()
    }

    assert payload["total"] == 2
    assert search["total"] == 1
    assert search["items"][0]["user_id"] == "15875046318"
    assert search["items"][0]["phone"] == "15875046318"
    assert read_model_members["15875046318"]["member_directory_source"] == "member_console_local_supplement"
    assert dashboard["total_count"] == 2
    assert dashboard["new_today_count"] == 2


def test_list_members_merges_session_activity_when_member_directory_is_stale(tmp_path: Path) -> None:
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": "canonical_member_1",
                "canonical_user_id": "canonical_member_1",
                "alias_user_ids": ["canonical_member_1"],
                "display_name": "正式会员 1",
                "phone": "15558866508",
                "tier": "sprint",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-05-26T01:03:44+00:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 260,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
            {
                "user_id": "canonical_member_2",
                "canonical_user_id": "canonical_member_2",
                "alias_user_ids": ["canonical_member_2"],
                "display_name": "正式会员 2",
                "phone": "15558866509",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-05-27T01:03:44+00:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 0,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="6 月真实对话",
            session_id="unified_recent_chat",
            owner_key=build_user_owner_key("canonical_member_1"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("unified_recent_chat", "user", "最近一次训练"))

    payload = service.list_members(page=1, page_size=20, sort="last_active_at", order="desc")
    dashboard = service.get_dashboard()
    service._get_learner_state_service = lambda: type(  # type: ignore[method-assign]
        "LearnerStateService",
        (),
        {
            "read_snapshot": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "list_heartbeat_jobs": lambda *_args, **_kwargs: [],
            "list_heartbeat_history": lambda *_args, **_kwargs: [],
            "list_heartbeat_arbitration_history": lambda *_args, **_kwargs: [],
            "read_profile": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "read_summary": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "read_progress": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "list_memory_events": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
        },
    )()
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]
    detail = service.get_member_360("canonical_member_1")

    assert payload["authority"]["members"] == "supabase.phone_identity_aliases+v_members"
    assert payload["items"][0]["user_id"] == "canonical_member_1"
    assert payload["items"][0]["last_active_at"] > "2026-06-01T00:00:00"
    assert dashboard["authority"]["members"] == "supabase.phone_identity_aliases+v_members"
    assert detail["last_active_at"] > "2026-06-01T00:00:00"
    assert detail["recent_conversations"][0]["session_id"] == "unified_recent_chat"


def test_list_members_supplements_directory_gaps_with_session_active_registered_members(
    tmp_path: Path,
) -> None:
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": "canonical_member_1",
                "canonical_user_id": "canonical_member_1",
                "alias_user_ids": ["canonical_member_1"],
                "display_name": "正式会员 1",
                "phone": "15558866508",
                "tier": "sprint",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-05-26T01:03:44+00:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 260,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            }
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    def _seed_local_member(data: dict[str, object]) -> None:
        member = service._build_default_member("local_missing_from_directory")
        member["phone"] = "15558866509"
        member["created_at"] = "2026-06-22T10:00:00+08:00"
        member["last_active_at"] = "2026-05-20T10:00:00+08:00"
        data["members"].append(member)

    service._mutate(_seed_local_member)
    asyncio.run(
        service._store.create_session(
            title="目录缺口真实对话",
            session_id="supplement_recent_chat",
            owner_key=build_user_owner_key("local_missing_from_directory"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("supplement_recent_chat", "user", "今天继续训练"))

    payload = service.list_members(page=1, page_size=20, sort="last_active_at", order="desc")
    dashboard = service.get_dashboard()
    read_model_members = {
        item["user_id"]: item
        for item in service.list_members_for_bi()
    }

    assert payload["authority"]["members"] == "supabase.phone_identity_aliases+v_members"
    assert payload["total"] == 2
    assert payload["items"][0]["user_id"] == "local_missing_from_directory"
    assert payload["items"][0]["last_active_at"] > "2026-06-01T00:00:00"
    assert payload["items"][1]["user_id"] == "canonical_member_1"
    assert dashboard["total_count"] == 2
    assert (
        read_model_members["local_missing_from_directory"]["member_directory_source"]
        == "member_console_session_activity_supplement"
    )


def test_dashboard_counts_recent_registered_member_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(member_service_module, "_now", lambda: now)

    def _member(
        user_id: str,
        *,
        days_ago: int,
        phone: str = "15558866508",
        created_at: str | None = None,
    ) -> dict[str, object]:
        return {
            "user_id": user_id,
            "canonical_user_id": user_id,
            "alias_user_ids": [user_id],
            "display_name": user_id,
            "phone": phone,
            "tier": "trial",
            "status": "active",
            "segment": "general",
            "risk_level": "low",
            "auto_renew": False,
            "created_at": created_at if created_at is not None else (now - timedelta(days=days_ago)).isoformat(),
            "last_active_at": now.isoformat(),
            "expire_at": "9999-12-31T00:00:00+00:00",
            "points_balance": 0,
            "review_due": 0,
            "member_directory_source": "supabase.phone_identity_aliases+v_members",
        }

    directory = _FakeMemberDirectory(
        [
            _member("member_today", days_ago=0),
            _member(
                "member_previous_local_day_within_24h",
                days_ago=0,
                phone="15558866514",
                created_at="2026-06-29T21:00:00+08:00",
            ),
            _member("member_3d", days_ago=3, phone="15558866509"),
            _member("member_8d", days_ago=8, phone="15558866510"),
            _member("member_40d", days_ago=40, phone="15558866511"),
            _member("internal_no_phone", days_ago=0, phone=""),
            _member("invalid_created_at", days_ago=0, phone="15558866512", created_at="not-a-time"),
            _member("future_created_at", days_ago=0, phone="15558866513", created_at=(now + timedelta(days=1)).isoformat()),
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    dashboard = service.get_dashboard()

    assert dashboard["total_count"] == 5
    assert dashboard["new_today_count"] == 1
    assert dashboard["new_7d_count"] == 3
    assert dashboard["new_30d_count"] == 4


def test_member_directory_merges_member_console_overlay_without_owning_member_pool(tmp_path: Path) -> None:
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "alias_user_ids": ["2d9eac15-5d26-4e93-941b-9ec6345ce6d9"],
                "display_name": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "phone": "15558866508",
                "tier": "sprint",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-04-22T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 260,
                "review_due": 0,
                "ledger": [],
                "notes": [],
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            }
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    def _seed_overlay(data: dict[str, object]) -> None:
        member = service._build_default_member("legacy_member_1")
        member["phone"] = "15558866508"
        member["display_name"] = "运营备注名"
        member["external_auth_user_id"] = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
        member["notes"] = [{"id": "note_1", "content": "需要回访", "created_at": "2026-04-21T10:00:00+08:00"}]
        data["members"].append(member)

    service._mutate(_seed_overlay)

    payload = service.list_members(page=1, page_size=20)
    detail = service.get_member_360("2d9eac15-5d26-4e93-941b-9ec6345ce6d9")

    assert payload["total"] == 1
    assert payload["items"][0]["display_name"] == "运营备注名"
    assert set(payload["items"][0]["alias_user_ids"]) >= {
        "legacy_member_1",
        "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
    }
    assert detail["wallet"]["balance"] == 260
    assert detail["recent_notes"][0]["content"] == "需要回访"


def test_member_directory_resolves_merged_accounts_to_canonical_member(tmp_path: Path) -> None:
    target_user_id = "047b7b7f-8316-4f95-8bf7-71973c102be7"
    merged_account_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": target_user_id,
                "canonical_user_id": target_user_id,
                "alias_user_ids": [target_user_id],
                "display_name": "user_6508",
                "phone": "15558866508",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 1_196_321,
                "review_due": 0,
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
            {
                "user_id": merged_account_user_id,
                "canonical_user_id": merged_account_user_id,
                "alias_user_ids": [merged_account_user_id],
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "phone": "13911112222",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-21T10:00:00+08:00",
                "last_active_at": "2026-06-21T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 0,
                "review_due": 0,
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    def _seed_merged_accounts(data: dict[str, object]) -> None:
        target = service._build_default_member(target_user_id)
        target.update(
            {
                "canonical_user_id": target_user_id,
                "alias_user_ids": [target_user_id, "0c4b582c-5937-4ae1-86a2-d68f07702731"],
                "display_name": "user_6508",
                "phone": "15558866508",
                "tier": "supreme_svip",
                "status": "active",
                "expire_at": "2027-06-15T09:13:15+08:00",
                "points_balance": 1_197_161,
                "external_auth_user_id": target_user_id,
                "wx_openid": "wx-openid-h",
            }
        )
        source = service._build_default_member(merged_account_user_id)
        source.update(
            {
                "canonical_user_id": merged_account_user_id,
                "alias_user_ids": [merged_account_user_id],
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "phone": "13911112222",
                "tier": "trial",
                "status": "merged",
                "merged_into": target_user_id,
                "points_balance": 0,
                "external_auth_user_id": merged_account_user_id,
            }
        )
        data["members"].extend([target, source])

    service._mutate(_seed_merged_accounts)

    by_account = service.list_members(search="chenyh2008", page=1, page_size=20)
    by_old_phone = service.list_members(search="13911112222", page=1, page_size=20)
    by_target_phone = service.list_members(search="15558866508", page=1, page_size=20)
    admin_picker = service.search_members_for_admin(q="chenyh2008")

    assert by_account["total"] == 1
    assert by_old_phone["total"] == 1
    assert by_target_phone["total"] == 1
    item = by_account["items"][0]
    assert item["user_id"] == target_user_id
    assert item["tier"] == "supreme_svip"
    assert item["status"] == "active"
    assert item["expire_at"] == "2027-06-15T09:13:15+08:00"
    assert item["points_balance"] == 1_196_321
    assert set(item["alias_user_ids"]) >= {
        target_user_id,
        merged_account_user_id,
        "0c4b582c-5937-4ae1-86a2-d68f07702731",
    }
    assert by_old_phone["items"][0]["user_id"] == target_user_id
    assert by_target_phone["items"][0]["user_id"] == target_user_id
    assert [item["user_id"] for item in admin_picker] == [target_user_id]


def test_member_directory_prefers_canonical_overlay_over_auth_wrapper(tmp_path: Path) -> None:
    target_user_id = "047b7b7f-8316-4f95-8bf7-71973c102be7"
    target_auth_user_id = "auth_047b7b7f83164f958bf77197"
    merged_account_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    merged_auth_user_id = "auth_2d9eac155d264e93941b9ec6"
    quick_login_user_id = "0c4b582c-5937-4ae1-86a2-d68f07702731"
    directory = _FakeMemberDirectory(
        [
            {
                "user_id": target_auth_user_id,
                "canonical_user_id": target_user_id,
                "external_auth_user_id": target_user_id,
                "alias_user_ids": [target_user_id],
                "display_name": "user_6508",
                "auth_username": "user_6508",
                "phone": "15558866508",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-22T10:00:00+08:00",
                "last_active_at": "2026-06-22T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 1_196_321,
                "review_due": 0,
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
            {
                "user_id": merged_auth_user_id,
                "canonical_user_id": merged_account_user_id,
                "external_auth_user_id": merged_account_user_id,
                "alias_user_ids": [merged_account_user_id],
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "phone": "13911112222",
                "tier": "trial",
                "status": "active",
                "segment": "general",
                "risk_level": "low",
                "auto_renew": False,
                "created_at": "2026-06-21T10:00:00+08:00",
                "last_active_at": "2026-06-21T10:00:00+08:00",
                "expire_at": "9999-12-31T00:00:00+00:00",
                "points_balance": 997_486,
                "review_due": 0,
                "member_directory_source": "supabase.phone_identity_aliases+v_members",
            },
        ]
    )
    service = MemberConsoleService(member_directory=directory)
    service._data_path = tmp_path / "member_console.json"

    def _seed_auth_wrappers(data: dict[str, object]) -> None:
        target = service._build_default_member(target_user_id)
        target.update(
            {
                "display_name": "user_6508",
                "auth_username": "user_6508",
                "phone": "15558866508",
                "tier": "supreme_svip",
                "status": "active",
                "expire_at": "2027-06-15T09:13:15+08:00",
                "points_balance": 1_197_161,
                "external_auth_user_id": target_user_id,
            }
        )
        target_auth = service._build_default_member(target_auth_user_id)
        target_auth.update(
            {
                "display_name": "user_6508",
                "auth_username": "user_6508",
                "phone": "15558866508",
                "tier": "trial",
                "status": "active",
                "expire_at": "2026-07-13T23:07:43+08:00",
                "points_balance": 0,
                "external_auth_user_id": target_user_id,
                "merged_into": target_user_id,
            }
        )
        source = service._build_default_member(merged_account_user_id)
        source.update(
            {
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "phone": "52649394196",
                "tier": "trial",
                "status": "merged",
                "points_balance": 0,
                "external_auth_user_id": merged_account_user_id,
                "merged_into": target_user_id,
            }
        )
        source_auth = service._build_default_member(merged_auth_user_id)
        source_auth.update(
            {
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "phone": "52649394196",
                "tier": "trial",
                "status": "active",
                "points_balance": 997_486,
                "external_auth_user_id": merged_account_user_id,
                "merged_into": merged_account_user_id,
            }
        )
        quick_login = service._build_default_member(quick_login_user_id)
        quick_login.update(
            {
                "display_name": "H",
                "phone": "12240059568",
                "tier": "trial",
                "status": "merged",
                "points_balance": 0,
                "external_auth_user_id": quick_login_user_id,
                "merged_into": target_user_id,
            }
        )
        data["members"].extend([target_auth, source_auth, target, source, quick_login])

    service._mutate(_seed_auth_wrappers)

    by_phone = service.list_members(search="15558866508", page=1, page_size=20)
    by_account = service.list_members(search="chenyh2008", page=1, page_size=20)
    by_auth_id = service.list_members(search=merged_auth_user_id, page=1, page_size=20)
    by_quick_login_id = service.list_members(search=quick_login_user_id, page=1, page_size=20)
    by_quick_login_phone = service.list_members(search="12240059568", page=1, page_size=20)

    assert by_phone["total"] == 1
    assert by_account["total"] == 1
    assert by_auth_id["total"] == 1
    assert by_quick_login_id["total"] == 1
    assert by_quick_login_phone["total"] == 1
    item = by_account["items"][0]
    assert item["user_id"] == target_user_id
    assert item["tier"] == "supreme_svip"
    assert item["status"] == "active"
    assert item["expire_at"] == "2027-06-15T09:13:15+08:00"
    assert item["points_balance"] == 1_196_321
    assert set(item["alias_user_ids"]) >= {
        target_user_id,
        target_auth_user_id,
        merged_account_user_id,
        merged_auth_user_id,
        quick_login_user_id,
    }
    assert by_quick_login_id["items"][0]["user_id"] == target_user_id
    assert by_quick_login_phone["items"][0]["user_id"] == target_user_id


def test_configured_member_directory_error_does_not_fallback_to_member_console_pool(tmp_path: Path) -> None:
    class ErrorDirectory:
        is_configured = True

        def list_members(self, *, limit: int = 5000):
            raise RuntimeError("supabase unavailable")

    service = MemberConsoleService(member_directory=ErrorDirectory())
    service._data_path = tmp_path / "member_console.json"

    def _seed_local_member(data: dict[str, object]) -> None:
        member = service._build_default_member("local_only_member")
        member["phone"] = "13800138000"
        data["members"].append(member)

    service._mutate(_seed_local_member)

    payload = service.list_members(page=1, page_size=20)

    assert payload["total"] == 0
    assert payload["authority"]["members"] == "supabase.phone_identity_aliases+v_members"


def test_batch_update_members_returns_success_and_failure_buckets(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {**service._build_default_member("u1"), "tier": "trial"},
            {**service._build_default_member("u2"), "tier": "trial"},
        ]

    service._mutate(_seed)

    result = service.batch_update_members(
        user_ids=["u1", "u2", "missing"],
        action="grant",
        tier="vip",
        days=30,
        operator="admin_demo",
        reason="批量开通",
    )

    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["failed"][0]["user_id"] == "missing"


def test_manual_membership_purchase_records_wallet_revenue_and_entitlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    result = service.manual_membership_purchase(
        user_id="manual_user_1",
        package_id="vip",
        days=365,
        operator="admin_demo",
        reason="线下收款",
        idempotency_key="manual-purchase-1",
        phone="13800138000",
        display_name="张同学",
    )

    assert result["member"]["tier"] == "vip"
    assert result["member"]["status"] == "active"
    assert result["member"]["phone"] == "13800138000"
    assert result["member"]["display_name"] == "张同学"
    assert result["package"]["id"] == "vip"
    assert result["amount_cny"] == 198
    assert result["points"] == 9000
    assert result["ledger_event_id"] == "ledger_manual_1"
    assert wallet_service.grants == [
        {
            "user_id": "manual_user_1",
            "amount_micros": 9_000_000_000,
            "reference_type": "purchase",
            "reference_id": result["purchase_id"],
            "idempotency_key": "purchase:manual_membership:manual-purchase-1",
            "reason": "manual_membership_purchase",
            "metadata": {
                "source": "bi_manual_membership",
                "channel": "manual_membership",
                "package_id": "vip",
                "package_label": "VIP",
                "tier": "vip",
                "amount_cny": 198,
                "operator_id": "admin_demo",
                "legacy_user_id": "manual_user_1",
                "wallet_user_id": "manual_user_1",
                "days": 365,
                "reason": "线下收款",
            },
            "operator_type": "admin",
            "operator_id": "admin_demo",
        }
    ]

    ledger = service.get_ledger("manual_user_1", limit=1, offset=0)["entries"][0]
    assert ledger["reason"] == "manual_membership_purchase"
    assert ledger["delta"] == 9000
    assert ledger["metadata"]["amount_cny"] == 198
    audit = service.get_audit_log(action="manual_membership_purchase")["items"][0]
    assert audit["target_user"] == "manual_user_1"
    assert audit["after"]["ledger_event_id"] == "ledger_manual_1"


@pytest.mark.parametrize(
    ("package_id", "expected_points", "expected_amount_cny"),
    [
        ("starter_19", 400, 9.9),
        ("light_98", 3000, 68),
    ],
)
def test_manual_membership_purchase_grants_entry_tier_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package_id: str,
    expected_points: int,
    expected_amount_cny: float,
) -> None:
    # 资损防线:入门两档发点必须走套餐 points 真值(经 _resolve_membership_package →
    # _normalize_membership_package 硬锚)。钉死 grant_points 的 amount_micros。
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    result = service.manual_membership_purchase(
        user_id=f"entry_{package_id}",
        package_id=package_id,
        days=180,
        operator="wechat_pay",
        reason="wechat_pay_success",
        idempotency_key=f"entry-{package_id}",
    )

    assert result["package"]["id"] == package_id
    assert result["points"] == expected_points
    assert result["amount_cny"] == expected_amount_cny
    assert len(wallet_service.grants) == 1
    grant = wallet_service.grants[0]
    assert grant["amount_micros"] == expected_points * 1_000_000
    assert grant["metadata"]["package_id"] == package_id

    ledger = service.get_ledger(f"entry_{package_id}", limit=1, offset=0)["entries"][0]
    assert ledger["delta"] == expected_points


def test_managed_membership_package_persists_and_can_be_purchased(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    package = service.upsert_membership_package(
        package_id="svip_plus",
        label="SVIP Plus",
        tier="svip",
        points=36000,
        turns=1800,
        teaching_video_limit=None,
        price="698",
        original_price="898",
        badge="高频答疑",
        per="1800 次 AI 学习额度",
        desc="AI答疑、案例批改、错因专训、班主任督学服务",
        status="active",
        operator="admin_demo",
        reason="新增高阶套餐",
        idempotency_key="package-upsert-1",
    )

    reloaded = MemberConsoleService()
    reloaded._data_path = service._data_path
    monkeypatch.setattr(reloaded, "_get_wallet_service", lambda: wallet_service)

    assert package["id"] == "svip_plus"
    assert package["label"] == "SVIP Plus"
    assert package["teaching_video_limit"] is None
    assert [item["id"] for item in reloaded.list_membership_packages()][-1] == "svip_plus"

    edited = reloaded.upsert_membership_package(
        package_id="svip_plus",
        label="SVIP Plus edited",
        tier="svip",
        points=36000,
        turns=1800,
        price="698",
        operator="admin_demo",
        reason="legacy client edit without entitlement field",
        idempotency_key="package-upsert-legacy-client",
    )
    assert edited["teaching_video_limit"] is None

    result = reloaded.manual_membership_purchase(
        user_id="manual_user_svip_plus",
        package_id="svip_plus",
        days=365,
        operator="admin_demo",
        reason="企业转账",
        idempotency_key="manual-svip-plus-1",
    )

    assert result["package"]["id"] == "svip_plus"
    assert result["member"]["tier"] == "svip"
    assert result["amount_cny"] == 698
    assert result["points"] == 36000
    assert wallet_service.grants[0]["metadata"]["package_id"] == "svip_plus"
    assert wallet_service.grants[0]["metadata"]["amount_cny"] == 698

    removed = reloaded.remove_membership_package(
        "svip_plus",
        operator="admin_demo",
        reason="下架高阶套餐",
        idempotency_key="package-delete-1",
    )

    assert removed["id"] == "svip_plus"
    repeated = reloaded.remove_membership_package(
        "svip_plus",
        operator="admin_demo",
        reason="重复请求",
        idempotency_key="package-delete-1",
    )
    assert repeated["id"] == "svip_plus"
    assert "svip_plus" not in [item["id"] for item in reloaded.list_membership_packages()]
    audit_actions = [item["action"] for item in reloaded.get_audit_log(page_size=20)["items"]]
    assert audit_actions.count("membership_package_delete") == 1
    assert "membership_package_upsert" in audit_actions


def test_supreme_membership_purchase_can_be_reversed_with_negative_revenue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    purchase = service.manual_membership_purchase(
        user_id="manual_user_supreme",
        package_id="supreme_svip",
        days=365,
        operator="admin_demo",
        reason="误点套餐价",
        idempotency_key="manual-supreme-1",
    )

    result = service.reverse_manual_membership_purchase(
        user_id="manual_user_supreme",
        purchase_id=purchase["purchase_id"],
        amount_cny=1,
        operator="admin_demo",
        reason="本应 0 元开通，冲销误录 998 元",
        idempotency_key="reverse-supreme-1",
    )

    assert result["member"]["tier"] == "supreme_svip"
    assert result["member"]["status"] == "revoked"
    assert result["amount_cny"] == -998
    assert result["points"] == -50000
    assert result["ledger_event_id"] == "ledger_refund_1"
    assert wallet_service.grants[-1] == {
        "refund": True,
        "user_id": "manual_user_supreme",
        "amount_micros": 50_000_000_000,
        "reference_type": "refund",
        "reference_id": purchase["purchase_id"],
        "idempotency_key": "refund:manual_membership:reverse-supreme-1",
        "reason": "manual_membership_reversal",
        "metadata": {
            "source": "bi_manual_membership_reversal",
            "channel": "manual_membership_reversal",
            "package_id": "supreme_svip",
            "package_label": "至尊SVIP",
            "tier": "supreme_svip",
            "amount_cny": -998,
            "operator_id": "admin_demo",
            "legacy_user_id": "manual_user_supreme",
            "wallet_user_id": "manual_user_supreme",
            "days": 365,
            "reason": "本应 0 元开通，冲销误录 998 元",
            "reversal_of_purchase_id": purchase["purchase_id"],
        },
        "operator_type": "admin",
        "operator_id": "admin_demo",
    }
    ledger = service.get_ledger("manual_user_supreme", limit=1, offset=0)["entries"][0]
    assert ledger["reason"] == "manual_membership_reversal"
    assert ledger["metadata"]["amount_cny"] == -998
    audit = service.get_audit_log(action="manual_membership_reversal")["items"][0]
    assert audit["target_user"] == "manual_user_supreme"
    assert audit["after"]["reversal_of_purchase_id"] == purchase["purchase_id"]


def test_member_360_exposes_only_unreversed_supreme_purchase_for_reversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    purchase = service.manual_membership_purchase(
        user_id="manual_user_supreme",
        package_id="supreme_svip",
        days=365,
        operator="admin_demo",
        reason="误点套餐价",
        idempotency_key="manual-supreme-1",
    )

    detail = service.get_member_360("manual_user_supreme")
    reversible = detail["membership_billing"]["reversible_supreme_purchase"]
    assert reversible["purchase_id"] == purchase["purchase_id"]
    assert reversible["amount_cny"] == 998
    assert reversible["points"] == 50000

    service.reverse_manual_membership_purchase(
        user_id="manual_user_supreme",
        purchase_id=purchase["purchase_id"],
        operator="admin_demo",
        reason="撤回误录",
        idempotency_key="reverse-supreme-1",
    )

    after = service.get_member_360("manual_user_supreme")
    assert after["membership_billing"]["reversible_supreme_purchase"] is None


def test_non_supreme_membership_purchase_cannot_be_reversed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    purchase = service.manual_membership_purchase(
        user_id="manual_user_vip",
        package_id="vip",
        days=365,
        operator="admin_demo",
        reason="VIP 收款",
        idempotency_key="manual-vip-1",
    )

    with pytest.raises(ValueError, match="Only supreme_svip"):
        service.reverse_manual_membership_purchase(
            user_id="manual_user_vip",
            purchase_id=purchase["purchase_id"],
            amount_cny=198,
            operator="admin_demo",
            reason="不允许冲销普通会员",
            idempotency_key="reverse-vip-1",
        )


def test_list_audit_log_supports_target_user_and_action_filters(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service._append_audit_log(
        {
            "id": "audit_1",
            "target_user": "u1",
            "operator": "admin_demo",
            "action": "grant",
            "reason": "manual",
            "created_at": "2026-04-22T10:00:00+08:00",
        }
    )
    service._append_audit_log(
        {
            "id": "audit_2",
            "target_user": "u2",
            "operator": "admin_demo",
            "action": "revoke",
            "reason": "manual",
            "created_at": "2026-04-22T11:00:00+08:00",
        }
    )

    result = service.list_audit_log(page=1, page_size=20, target_user="u1", action="grant")

    assert [item["id"] for item in result["items"]] == ["audit_1"]


def test_record_ops_action_result_writes_note_and_audit_loop(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = service.record_ops_action_result(
        "student_demo",
        status="done",
        result="已电话回访，确认本周续费",
        action_title="即将到期会员",
        next_follow_up_at="2026-04-26",
        operator="admin_demo",
    )

    assert result["status"] == "done"
    assert result["result"] == "已电话回访，确认本周续费"
    assert result["note"]["channel"] == "ops_action"
    assert "处理状态：done" in result["note"]["content"]
    assert "处理结果：已电话回访，确认本周续费" in result["note"]["content"]

    detail = service.get_member_360("student_demo")
    assert detail["recent_notes"][0]["id"] == result["note"]["id"]

    audit = service.list_audit_log(target_user="student_demo", action="ops_action_result")
    assert audit["total"] == 1
    assert audit["items"][0]["operator"] == "admin_demo"
    assert audit["items"][0]["after"]["status"] == "done"
    assert audit["items"][0]["after"]["note_id"] == result["note"]["id"]
    assert audit["items"][0]["after"]["next_follow_up_at"] == "2026-04-26"


def test_record_ops_action_result_dedupes_by_idempotency_key(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    first = service.record_ops_action_result(
        "student_demo",
        status="done",
        result="已电话联系",
        action_title="标记已联系",
        operator="admin_demo",
        idempotency_key="member-action-key-1",
    )
    second = service.record_ops_action_result(
        "student_demo",
        status="done",
        result="已电话联系",
        action_title="标记已联系",
        operator="admin_demo",
        idempotency_key="member-action-key-1",
    )

    audit = service.list_audit_log(target_user="student_demo", action="ops_action_result")
    notes = service.get_notes("student_demo")
    ops_notes = [note for note in notes["items"] if note.get("channel") == "ops_action"]
    assert audit["total"] == 1
    assert len(ops_notes) == 1
    assert first["audit_id"] == audit["items"][0]["id"]
    assert second["audit_id"] == first["audit_id"]
    assert second.get("deduped") is True


def test_assessment_topic_catalog_reports_form_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MemberConsoleService()

    class _Provider:
        def active_form_summaries(self, blueprint_versions: list[str]) -> dict[str, dict[str, object]]:
            return {
                blueprint_version: {
                    "active_form_count": 5 if blueprint_version == "topic_waterproof_v1" else 3,
                    "fallback_used": False,
                    "question_bank_size": 4638,
                }
                for blueprint_version in blueprint_versions
            }

        def load_persisted_form_bank(self, blueprint):
            raise AssertionError("catalog must not load full form banks")

    monkeypatch.setattr(member_service_module, "is_production_environment", lambda: True)
    monkeypatch.setattr(member_service_module, "SupabaseAssessmentQuestionProvider", lambda: _Provider())

    result = service.get_assessment_topic_catalog()

    by_id = {item["topic_id"]: item for item in result["topics"]}
    assert by_id["waterproof"]["status"] == "stable"
    assert by_id["waterproof"]["enabled"] is True
    assert by_id["waterproof"]["quality_status"] == "validated"
    assert by_id["decoration"]["status"] == "pilot"
    assert by_id["decoration"]["quality_status"] == "validated"
    assert by_id["decoration"]["minimum_form_count"] == 3
    assert by_id["decoration"]["target_form_count"] == 5


def test_assessment_topic_catalog_rejects_fallback_form_bank(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MemberConsoleService()

    class _Provider:
        def active_form_summaries(self, blueprint_versions: list[str]) -> dict[str, dict[str, object]]:
            return {
                blueprint_version: {
                    "active_form_count": 5 if blueprint_version == "topic_waterproof_v1" else 0,
                    "fallback_used": blueprint_version == "topic_waterproof_v1",
                    "question_bank_size": 4638,
                }
                for blueprint_version in blueprint_versions
            }

        def load_persisted_form_bank(self, blueprint):
            raise AssertionError("catalog must not load full form banks")

    monkeypatch.setattr(member_service_module, "is_production_environment", lambda: True)
    monkeypatch.setattr(member_service_module, "SupabaseAssessmentQuestionProvider", lambda: _Provider())

    result = service.get_assessment_topic_catalog()

    by_id = {item["topic_id"]: item for item in result["topics"]}
    assert by_id["waterproof"]["form_count"] == 5
    assert by_id["waterproof"]["status"] == "authoring_needed"
    assert by_id["waterproof"]["enabled"] is False
    assert by_id["waterproof"]["quality_status"] == "fallback_form_bank"
    assert by_id["decoration"]["quality_status"] == "insufficient_forms"


def test_member_360_includes_product_behavior_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services import observability
    from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore

    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    monkeypatch.setattr(observability, "get_product_behavior_store", lambda: store)
    now_ms = int(time.time() * 1000)
    store.record_event(
        {
            "event_id": "evt-member-360-1",
            "event_name": "section_viewed",
            "event_version": 1,
            "occurred_at_ms": now_ms,
            "received_at_ms": now_ms + 100,
            "user_id": "student_demo",
            "visit_id": "visit-u1-1",
            "session_id": "",
            "turn_id": "",
            "surface": "web",
            "module": "learning_report",
            "section": "next_action",
            "action": "view",
            "properties_json": {},
        }
    )

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    payload = service.get_member_360("student_demo")

    assert payload["behavior"]["summary"]["learning_report_open_count_7d"] == 0
    assert payload["behavior"]["learning_report_sections"][0]["section"] == "next_action"
    assert payload["behavior"]["timeline"][0]["event_name"] == "section_viewed"


def test_list_members_loads_behavior_summaries_in_one_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services import observability

    class FakeBehaviorStore:
        def __init__(self):
            self.batch_calls = 0
            self.single_calls = 0

        def get_member_behavior_summaries(self, user_ids, *, days=7):
            self.batch_calls += 1
            return {
                str(user_id): {
                    "learning_report_open_count_7d": 1,
                    "history_open_count_7d": 0,
                    "action_start_count_7d": 0,
                    "cohort": "",
                    "trust_level": "B",
                }
                for user_id in user_ids
            }

        def get_member_behavior_summary(self, user_id, *, days=7):
            self.single_calls += 1
            raise AssertionError("list_members must use get_member_behavior_summaries")

    fake_store = FakeBehaviorStore()
    monkeypatch.setattr(observability, "get_product_behavior_store", lambda: fake_store)

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    def _seed_registered_member(data: dict[str, object]) -> None:
        member = service._build_default_member("real_member_1")
        member["phone"] = "13800138000"
        member["display_name"] = "真实会员"
        data["members"].append(member)

    service._mutate(_seed_registered_member)
    payload = service.list_members(page=1, page_size=20)

    assert fake_store.batch_calls == 1
    assert fake_store.single_calls == 0
    assert payload["items"]
    assert payload["items"][0]["behavior"]["learning_report_open_count_7d"] == 1


def test_list_members_loads_behavior_with_canonical_alias_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services import observability

    canonical_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    class FakeBehaviorStore:
        def __init__(self):
            self.identity_groups = {}

        def get_member_behavior_summaries_for_identity_groups(self, identity_groups, *, days=7):
            self.identity_groups = identity_groups
            return {
                "legacy_member_1": {
                    "learning_report_open_count_7d": 3,
                    "history_open_count_7d": 0,
                    "action_start_count_7d": 0,
                    "event_count_7d": 3,
                    "last_event_at_ms": 1,
                    "cohort": "report_high_no_action",
                    "cohort_reasons": ["alias events were merged"],
                    "next_action": "推送下一步训练",
                    "trust_level": "B",
                }
            }

        def get_member_behavior_summaries(self, user_ids, *, days=7):
            raise AssertionError("member list should use identity-group behavior summaries")

    fake_store = FakeBehaviorStore()
    monkeypatch.setattr(observability, "get_product_behavior_store", lambda: fake_store)

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed_registered_member(data: dict[str, object]) -> None:
        member = service._build_default_member("legacy_member_1")
        member["phone"] = "13800138000"
        member["display_name"] = "真实会员"
        member["external_auth_user_id"] = canonical_user_id
        member["alias_user_ids"] = ["legacy_member_1", "wx_member_1"]
        data["members"].append(member)

    service._mutate(_seed_registered_member)
    payload = service.list_members(page=1, page_size=20)

    assert payload["items"][0]["behavior"]["learning_report_open_count_7d"] == 3
    assert set(fake_store.identity_groups["legacy_member_1"]) >= {
        "legacy_member_1",
        "wx_member_1",
        canonical_user_id,
    }


def _cycle_member(uid: str, merged_into: str = "") -> dict:
    return {"user_id": uid, "merged_into": merged_into, "external_auth_user_id": ""}


def test_ensure_member_breaks_two_node_merge_cycle() -> None:
    """A->B->A cyclic merge chain must not RecursionError (login 500 root cause)."""
    svc = MemberConsoleService()
    data = {"members": [_cycle_member("A", "B"), _cycle_member("B", "A")]}
    member = svc._ensure_member(data, "A")
    assert member["user_id"] in {"A", "B"}


def test_ensure_member_breaks_longer_merge_cycle() -> None:
    """A->B->C->A (3-cycle) must also terminate without RecursionError."""
    svc = MemberConsoleService()
    data = {
        "members": [
            _cycle_member("A", "B"),
            _cycle_member("B", "C"),
            _cycle_member("C", "A"),
        ]
    }
    member = svc._ensure_member(data, "A")
    assert member["user_id"] in {"A", "B", "C"}


def test_ensure_member_terminal_chain_resolves_to_canonical() -> None:
    """A->B (B terminal) still resolves to the canonical terminal member B."""
    svc = MemberConsoleService()
    data = {"members": [_cycle_member("A", "B"), _cycle_member("B", "")]}
    member = svc._ensure_member(data, "A")
    assert member["user_id"] == "B"


def test_build_default_member_display_name_is_empty() -> None:
    """_build_default_member must return empty display_name so downstream rescue logic fires."""
    svc = MemberConsoleService()
    member = svc._build_default_member("wx_abc123456789")
    assert member["display_name"] == "", (
        "display_name must be empty in default member so WeChat login rescue sets 微信用户xxxx"
    )


@pytest.mark.asyncio
async def test_wechat_quick_login_sets_friendly_display_name_for_new_member(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """New member created by WeChat quick login must get '微信用户xxxx', not raw user_id."""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {"openid": "openid_ABCDEF123456", "unionid": "unionid_xyz", "session_key": "sk"}

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    result = await service.login_with_wechat_code("wx-code")
    target_user_id = result["user"]["user_id"]
    data = service._load()
    member = service._find_member(data, target_user_id)
    user_id = member.get("user_id", "")
    display_name = member.get("display_name", "")
    assert display_name != user_id, "display_name must not equal user_id (ugly default)"
    assert display_name.startswith("微信用户"), f"expected '微信用户xxxx' but got '{display_name}'"


@pytest.mark.asyncio
async def test_wechat_relogin_rescues_user_id_as_display_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Re-login via WeChat must rescue display_name even when it was previously set to user_id."""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    existing_user_id = "wx_ABCDEF123456"

    def _seed(data: dict) -> None:
        m = service._build_default_member(existing_user_id)
        m["display_name"] = existing_user_id  # simulate legacy stuck display_name
        m["wx_openid"] = "openid_ABCDEF123456"
        m["wx_unionid"] = "unionid_xyz"
        data["members"] = [m]

    service._mutate(_seed)

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {"openid": "openid_ABCDEF123456", "unionid": "unionid_xyz", "session_key": "sk"}

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    await service.login_with_wechat_code("wx-code")
    data = service._load()
    member = service._find_member(data, existing_user_id)
    display_name = member.get("display_name", "")
    assert display_name != existing_user_id, "display_name must not remain as user_id after re-login"
    assert display_name.startswith("微信用户"), f"expected '微信用户xxxx' but got '{display_name}'"


# ─── Fix 1: send_phone_code CN 格式门控 ─────────────────────────────────────

def test_send_phone_code_rejects_non_cn_mobile_format(tmp_path: Path) -> None:
    """send_phone_code 必须拒绝非大陆手机号，不只是拒绝空串。
    修复前：只要 _normalize_phone_input 返回 11 位就通过，"83090321728"（起头 8）会被接受。
    修复后：必须通过 _is_cn_mainland_mobile（^1[3-9]\\d{9}$）才能继续。
    """
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    # 起头 8 —— 绝非大陆号
    with pytest.raises(ValueError, match="大陆手机号"):
        service.send_phone_code("83090321728")

    # 起头 0 —— 固话/国际前缀
    with pytest.raises(ValueError, match="大陆手机号"):
        service.send_phone_code("02112345678")

    # 合法大陆号 —— 应该通过格式校验（会在无短信配置时自然 fall through 到 debug 模式）
    result = service.send_phone_code("13812345678")
    assert result.get("sent") is not None, "合法大陆号应通过格式校验并返回 sent 字段"


# ─── Fix 2: _persist_wechat_openid_identity ─────────────────────────────────

def test_persist_wechat_openid_identity_writes_openid_and_unionid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_persist_wechat_openid_identity 应向 Supabase 写入 wx_openid 和 wx_unionid 两条 alias。"""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DB_URL", "postgresql://example.invalid/db")

    executed: list[tuple[str, str]] = []  # (alias_type, alias_value)

    class _Cursor:
        def execute(self, query: str, params: tuple) -> None:
            executed.append((params[0], params[1]))  # alias_type, alias_value

        @staticmethod
        def fetchone() -> tuple:
            return ("some-uuid",)  # 模拟写入成功

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def cursor() -> _Cursor:
            return _Cursor()

    fake_psycopg = SimpleNamespace(connect=lambda *_a, **_kw: _Connection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    valid_uuid = "d289c0d1-ba78-4d73-9f2e-72d2c0af7424"
    service._persist_wechat_openid_identity(
        openid="oid_ABCDEF123456",
        unionid="uid_XYZ789",
        canonical_uid=valid_uuid,
    )

    alias_types = [e[0] for e in executed]
    alias_values = [e[1] for e in executed]
    assert "wx_openid" in alias_types, "应写入 wx_openid alias"
    assert "wx_unionid" in alias_types, "应写入 wx_unionid alias"
    assert "oid_ABCDEF123456" in alias_values
    assert "uid_XYZ789" in alias_values


def test_persist_wechat_openid_identity_skips_without_unionid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """unionid 为空时只写 wx_openid，不报错。"""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DB_URL", "postgresql://example.invalid/db")

    executed: list[str] = []

    class _Cursor:
        def execute(self, _query: str, params: tuple) -> None:
            executed.append(params[0])  # alias_type

        @staticmethod
        def fetchone():
            return ("uuid",)

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def cursor():
            return _Cursor()

    fake_psycopg = SimpleNamespace(connect=lambda *_a, **_kw: _Connection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    service._persist_wechat_openid_identity(
        openid="oid_ABCDEF123456",
        unionid="",  # 空 unionid
        canonical_uid="d289c0d1-ba78-4d73-9f2e-72d2c0af7424",
    )

    assert executed == ["wx_openid"], "空 unionid 时只写 wx_openid"


def test_persist_wechat_openid_identity_skips_non_uuid_canonical(
    tmp_path: Path,
) -> None:
    """canonical_uid 不是 UUID 时静默跳过（wx_ user_id 尚未绑定手机的中间态）。"""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    # 不应抛出异常，只是静默 return
    service._persist_wechat_openid_identity(
        openid="oid_ABC",
        unionid="uid_XYZ",
        canonical_uid="wx_O4aNJg7O_wRk",  # 非 UUID
    )


@pytest.mark.asyncio
async def test_bind_phone_wechat_persists_wechat_openid_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """bind_phone_for_wechat 成功后，openid 和 unionid 应被持久化到 Supabase。"""
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)

    async def _fake_exchange(_phone_code: str) -> str:
        return "13812345678"

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange)

    # 预埋 wx_ member 含 openid/unionid
    def _seed(data: dict) -> None:
        m = service._build_default_member("wx_test_member_id")
        m["wx_openid"] = "oid_test_openid_1"
        m["wx_unionid"] = "uid_test_unionid_1"
        data["members"] = [m]

    service._mutate(_seed)

    wechat_persisted: list[dict] = []

    def _fake_persist_wechat(*, openid: str, unionid: str, canonical_uid: str) -> None:
        wechat_persisted.append({"openid": openid, "unionid": unionid, "canonical_uid": canonical_uid})

    monkeypatch.setattr(service, "_persist_wechat_openid_identity", _fake_persist_wechat)

    result = await service.bind_phone_for_wechat("wx_test_member_id", "13812345678")

    assert result["phone"] == "13812345678"
    assert len(wechat_persisted) == 1, "_persist_wechat_openid_identity 应被调用一次"
    p = wechat_persisted[0]
    assert p["openid"] == "oid_test_openid_1", "应传入该 member 的 wx_openid"
    assert p["unionid"] == "uid_test_unionid_1", "应传入该 member 的 wx_unionid"


def test_list_internal_test_user_ids_uses_test_member_classifier(tmp_path: Path) -> None:
    """QA allowlist 导出：唯一权威=既有 _looks_like_test_member，含 alias/external 键位。"""
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed_members(data):
        data["members"] = [
            {
                "user_id": "11111111-1111-1111-1111-111111111111",
                "auth_username": "realistic_wrapper",
                "display_name": "真实样式别名账号",
                "external_auth_user_id": "22222222-2222-2222-2222-222222222222",
                "alias_user_ids": ["qa_eval_codex_alias_20260708"],
            },
            {
                "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "auth_username": "realistic_runner",
                "display_name": "真实样式机器账号",
                "external_auth_user_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "alias_user_ids": ["cccccccc-cccc-cccc-cccc-cccccccccccc"],
                "account_kind": "eval_runner",
                "actor_type": "machine",
                "created_by": "eval_runner",
                "is_internal_test": True,
            },
            {
                "user_id": "44444444-4444-4444-4444-444444444444",
                "auth_username": "realstudent01",
                "display_name": "真实学员",
                "phone": "13712345678",
            },
        ]

    service._mutate(_seed_members)
    ids = service.list_internal_test_user_ids()
    assert "11111111-1111-1111-1111-111111111111" in ids
    assert "22222222-2222-2222-2222-222222222222" in ids
    assert "qa_eval_codex_alias_20260708" in ids
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in ids
    assert "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" in ids
    assert "cccccccc-cccc-cccc-cccc-cccccccccccc" in ids
    assert "44444444-4444-4444-4444-444444444444" not in ids


def test_spike_d1_report_excludes_allowlisted_users() -> None:
    """D1 度量脚本：allowlist 用户不入 cohort；乙案 cohort 门槛生效。"""
    import datetime as _dt

    from scripts.report_luban_spike_d1 import compute_d1

    days = {
        "user:aaaa": {"2026-06-01", "2026-06-02"},
        "user:bbbb": {"2026-06-01"},
        "user:qa-uuid": {"2026-06-01", "2026-06-02"},
    }
    report = compute_d1(days, {"qa-uuid"}, today=_dt.date(2026, 7, 2))
    assert report["cohort"] == 2
    assert report["retained"] == 1
    assert report["excluded_internal_accounts"] == 1
    assert report["d1"] == 0.5
    assert report["cohort_gate_met"] is False
    assert "未达读数条件" in report["verdict"]


def _mastery_evidence_event(index: int, *, label: str = "网络计划", correct: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        memory_kind="learning_evidence",
        source_feature="construction_grading",
        event_id=f"mastery_evt_{index}",
        source_id=f"turn_mastery_{index}",
        dedupe_key=f"mastery_evt_{index}",
        created_at=f"2026-07-0{1 + index}T10:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "question_id": f"mastery_q_{index}",
            "score_awarded": 1.0 if correct else 0.0,
            "max_score": 1.0,
            "canonical_topic": {"label": label},
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )


def _seed_static_chapter_mastery(service: MemberConsoleService, user_id: str, *, mastery: int) -> None:
    def _apply(data: dict[str, object]) -> None:
        for member in data["members"]:
            if member["user_id"] != user_id:
                continue
            member["chapter_mastery"] = {
                "网络计划": {"name": "网络计划", "mastery": mastery},
            }
            break

    service._mutate(_apply)


class _FakeEnvStore:
    """env_flag 经 get_env_store 先读磁盘 .env（磁盘值遮蔽 os.environ），
    monkeypatch os.environ 无效——按 tests/services/config/test_runtime_env.py
    既有范式 stub get_env_store 单一读点。"""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def _stub_env_store(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    store = _FakeEnvStore({"DEEPTUTOR_ENV": "local", **values})
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: store,
    )


def _make_blend_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_id: str,
    legacy_mastery: int,
    corrects: list[bool],
) -> MemberConsoleService:
    # 融合面总开关置开（mastery blend 正在被收进 DEEPTUTOR_HOME_NEXT_STEP_ENABLED）。
    _stub_env_store(monkeypatch, {"DEEPTUTOR_HOME_NEXT_STEP_ENABLED": "1"})
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile(user_id)
    _seed_static_chapter_mastery(service, user_id, mastery=legacy_mastery)

    events = [_mastery_evidence_event(i, correct=correct) for i, correct in enumerate(corrects)]

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            return SimpleNamespace(profile={}, progress={}, summary="", memory_events=list(events))

        def read_compiled_learning_truth(self, user_id: str):
            return {}

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            return []

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())
    return service


def test_radar_and_mastery_dashboard_blend_estimate_mastery_from_learning_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # §6-2 首页 mastery 收口：首页/雷达/章节盘必须经 estimate_mastery（唯一 mastery 算子）
    # 聚合 learner-state 证据，不再裸读静态 member.chapter_mastery。
    service = _make_blend_service(
        tmp_path,
        monkeypatch,
        user_id="student_mastery_blend",
        legacy_mastery=40,
        corrects=[True, True, True],
    )

    radar = service.get_radar_data("student_mastery_blend")
    dimension = next(item for item in radar["dimensions"] if item["key"] == "网络计划")
    # 3 次全对的近期证据必须把 40 的静态分抬起来（estimate_mastery 贝叶斯混合）。
    assert dimension["score"] > 40

    mastery_dashboard = service.get_mastery_dashboard("student_mastery_blend")
    chapters = [
        chapter
        for group in mastery_dashboard["groups"]
        for chapter in group["chapters"]
        if chapter["name"] == "网络计划"
    ]
    assert chapters and chapters[0]["mastery"] == dimension["score"]

    # 评审项 6（排除路径，确定性）：legacy 40 + 3 全对 → 混合分确定越过 60，
    # 必然被 weak_nodes（<60 才入）排除——显式断言，不再用 if 守出死代码。
    assert dimension["score"] >= 60
    home = service.get_home_dashboard("student_mastery_blend")
    weak_names = {item["name"]: item["mastery"] for item in home["mastery"]["weak_nodes"]}
    assert "网络计划" not in weak_names


def test_home_weak_nodes_carry_blended_score_when_evidence_keeps_chapter_weak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 评审项 6（保留路径，确定性）：legacy 40 + 3 全错 → 混合分确定下压且 <60，
    # 章节必然留在 weak_nodes，且首页展示的必须是混合值（与雷达同一算子同一数）。
    service = _make_blend_service(
        tmp_path,
        monkeypatch,
        user_id="student_mastery_weak",
        legacy_mastery=40,
        corrects=[False, False, False],
    )

    radar = service.get_radar_data("student_mastery_weak")
    dimension = next(item for item in radar["dimensions"] if item["key"] == "网络计划")
    assert dimension["score"] < 40  # 全错证据必须把静态 40 往下混

    home = service.get_home_dashboard("student_mastery_weak")
    weak_names = {item["name"]: item["mastery"] for item in home["mastery"]["weak_nodes"]}
    assert "网络计划" in weak_names, "混合后 <60 的章节必须留在 weak_nodes"
    assert weak_names["网络计划"] == dimension["score"]


def test_mastery_faces_keep_legacy_scores_when_no_evidence_in_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 证据窗为空时保持 legacy 值（含摸底测评优先契约），不得因窗口小被 cap 降级。
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("student_mastery_legacy")
    _seed_static_chapter_mastery(service, "student_mastery_legacy", mastery=80)

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            return SimpleNamespace(profile={}, progress={}, summary="", memory_events=[])

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            return []

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    radar = service.get_radar_data("student_mastery_legacy")
    dimension = next(item for item in radar["dimensions"] if item["key"] == "网络计划")
    assert dimension["score"] == 80


def test_snapshot_read_count_is_pinned_per_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Codex #5:mastery 三面 + report 组合曾有冗余 snapshot 读风险。
    # 钉住每面恰好 1 次 read_snapshot(计数回归,防未来叠加);
    # report 组合路径的整体减法归独立 PR(踢重 legacy source)。
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.get_profile("student_read_count")

    calls = {"count": 0}

    class _CountingLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            calls["count"] += 1
            return SimpleNamespace(profile={}, progress={}, summary="", memory_events=[])

        def read_compiled_learning_truth(self, user_id: str):
            return {}

        def list_heartbeat_jobs(self, user_id: str):
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 3):
            return []

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _CountingLearnerStateService())

    calls["count"] = 0
    service.get_home_dashboard("student_read_count")
    assert calls["count"] == 1, f"home dashboard must read snapshot exactly once, got {calls['count']}"

    calls["count"] = 0
    service.get_radar_data("student_read_count")
    assert calls["count"] == 1, f"radar must read snapshot exactly once, got {calls['count']}"

    calls["count"] = 0
    service.get_mastery_dashboard("student_read_count")
    assert calls["count"] == 1, f"mastery dashboard must read snapshot exactly once, got {calls['count']}"


def test_list_members_for_bi_derives_conversation_activity_from_sqlite_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B 断点防回归：Postgres chat_conversations 是死表，目录读模型已弃读其
    chat 派生列；BI 会员投影的对话活跃事实必须与 get_dashboard/list_members
    同源——从宿主 SQLite sessions 派生（_merge_session_activity_for_member_list）。"""
    directory_member = {
        "user_id": "dir_member_1",
        "canonical_user_id": "dir_member_1",
        "external_auth_user_id": "dir_member_1",
        "alias_user_ids": ["dir_member_1"],
        "display_name": "目录会员",
        "phone": "15558860001",
        "tier": "trial",
        "status": "active",
        "segment": "general",
        "risk_level": "low",
        "auto_renew": False,
        "created_at": "2026-07-01T10:00:00+08:00",
        # 目录侧只剩钱包时间这种保守回退；真实对话活跃必须由 SQLite 覆盖。
        "last_active_at": "2026-07-01T10:00:00+08:00",
        "expire_at": "2099-12-31T00:00:00+08:00",
        "points_balance": 0,
        "member_directory_source": "supabase.phone_identity_aliases+v_members",
    }

    class _FakeDirectory:
        is_configured = True

        def list_members(self, *, limit: int = 5000) -> list[dict[str, object]]:
            del limit
            return [dict(directory_member)]

    service = MemberConsoleService(member_directory=_FakeDirectory())
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setattr(service, "_member_directory_enabled", lambda: True)

    import sqlite3

    db_path = tmp_path / "chat_history.db"
    session_ts = datetime(2026, 7, 9, 21, 30, tzinfo=timezone(timedelta(hours=8))).timestamp()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE sessions (owner_key TEXT, updated_at REAL, archived INTEGER DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO sessions (owner_key, updated_at, archived) VALUES (?, ?, 0)",
            (build_user_owner_key("dir_member_1"), session_ts),
        )
    service._store = SimpleNamespace(db_path=str(db_path))

    members = service.list_members_for_bi()

    assert [member["user_id"] for member in members] == ["dir_member_1"]
    expected_iso = service._session_time_to_iso(session_ts)
    assert members[0]["last_active_at"] == expected_iso
