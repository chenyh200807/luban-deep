from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
wallet_service_module = importlib.import_module("deeptutor.services.wallet.service")
router = mobile_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


class _FakeWalletSnapshot:
    def __init__(
        self,
        *,
        user_id: str,
        balance_micros: int,
        frozen_micros: int = 0,
        plan_id: str = "free",
        version: int = 1,
        created_at: str = "2026-04-19T12:00:00+08:00",
    ) -> None:
        self.user_id = user_id
        self.balance_micros = balance_micros
        self.frozen_micros = frozen_micros
        self.plan_id = plan_id
        self.version = version
        self.created_at = created_at


class _FakeLedgerEntry:
    def __init__(
        self,
        *,
        id: str,
        user_id: str,
        event_type: str,
        delta_micros: int,
        balance_after_micros: int,
        reference_type: str,
        reference_id: str,
        idempotency_key: str,
        created_at: str,
        metadata: dict[str, object] | None = None,
        frozen_after_micros: int = 0,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.event_type = event_type
        self.delta_micros = delta_micros
        self.balance_after_micros = balance_after_micros
        self.reference_type = reference_type
        self.reference_id = reference_id
        self.idempotency_key = idempotency_key
        self.created_at = created_at
        self.metadata = dict(metadata or {})
        self.frozen_after_micros = frozen_after_micros


def test_billing_wallet_prefers_canonical_uid_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_verify_access_token(_token: str) -> dict[str, str]:
        return {
            "uid": "user_2008",
            "canonical_uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "provider": "local",
        }

    class _FakeWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            captured["user_id"] = user_id
            return _FakeWalletSnapshot(user_id=user_id, balance_micros=360_000_000, version=9)

        @staticmethod
        def list_wallet_ledger(_user_id: str, *, limit: int = 20, offset: int = 0):
            del limit, offset
            return []

    def _fake_get_wallet(user_id: str) -> dict[str, object]:
        captured["user_id"] = user_id
        return {"balance": 360, "tier": "free", "expire_at": "", "packages": []}

    monkeypatch.setattr(mobile_module.member_service, "verify_access_token", _fake_verify_access_token)
    monkeypatch.setattr(mobile_module.member_service, "get_wallet", _fake_get_wallet)
    monkeypatch.setattr(mobile_module, "wallet_service", _FakeWalletService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/billing/wallet", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json()["balance"] == 360
    assert response.json()["balance_micros"] == 360_000_000
    assert response.json()["points"] == 360
    assert captured["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"


def test_profile_endpoint_uses_single_canonical_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_verify_access_token(_token: str) -> dict[str, str]:
        return {
            "uid": "user_2008",
            "canonical_uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "provider": "local",
        }

    class _FakeWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            captured["wallet_user_id"] = user_id
            return _FakeWalletSnapshot(user_id=user_id, balance_micros=999_000_000, version=7)

        @staticmethod
        def list_wallet_ledger(_user_id: str, *, limit: int = 20, offset: int = 0):
            del limit, offset
            return []

    def _fake_get_profile(user_id: str) -> dict[str, object]:
        captured["user_id"] = user_id
        return {"user_id": user_id, "username": "chenyh2008", "display_name": "铁", "points": 0}

    monkeypatch.setattr(mobile_module.member_service, "verify_access_token", _fake_verify_access_token)
    monkeypatch.setattr(mobile_module.member_service, "get_profile", _fake_get_profile)
    monkeypatch.setattr(mobile_module, "wallet_service", _FakeWalletService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/auth/profile", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert response.json()["username"] == "chenyh2008"
    assert response.json()["display_name"] == "铁"
    assert response.json()["points"] == 999
    assert response.json()["balance_micros"] == 999_000_000
    assert captured["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert captured["wallet_user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"


def test_billing_points_and_ledger_use_wallet_service(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_verify_access_token(_token: str) -> dict[str, str]:
        return {
            "uid": "user_2008",
            "canonical_uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "provider": "local",
        }

    class _FakeWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            captured["wallet_user_id"] = user_id
            return _FakeWalletSnapshot(user_id=user_id, balance_micros=128_000_000, frozen_micros=2_000_000, version=6)

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            captured["ledger_user_id"] = user_id
            captured["ledger_limit"] = limit
            captured["ledger_offset"] = offset
            return [
                _FakeLedgerEntry(
                    id="evt_2",
                    user_id=user_id,
                    event_type="debit",
                    delta_micros=-20_000_000,
                    balance_after_micros=128_000_000,
                    reference_type="ai_usage",
                    reference_id="msg_2",
                    idempotency_key="debit:msg_2",
                    created_at="2026-04-19T12:05:00+08:00",
                ),
                _FakeLedgerEntry(
                    id="evt_1",
                    user_id=user_id,
                    event_type="grant",
                    delta_micros=500_000_000,
                    balance_after_micros=148_000_000,
                    reference_type="order",
                    reference_id="ord_1",
                    idempotency_key="grant:ord_1",
                    created_at="2026-04-19T12:00:00+08:00",
                ),
                _FakeLedgerEntry(
                    id="evt_0",
                    user_id=user_id,
                    event_type="grant",
                    delta_micros=100_000_000,
                    balance_after_micros=648_000_000,
                    reference_type="plan",
                    reference_id="free",
                    idempotency_key="grant:free",
                    created_at="2026-04-19T11:55:00+08:00",
                ),
            ]

    monkeypatch.setattr(mobile_module.member_service, "verify_access_token", _fake_verify_access_token)
    monkeypatch.setattr(mobile_module, "wallet_service", _FakeWalletService())

    with TestClient(_build_app()) as client:
        points_response = client.get("/api/v1/billing/points", headers={"Authorization": "Bearer test-token"})
        ledger_response = client.get(
            "/api/v1/billing/ledger?limit=2&offset=0",
            headers={"Authorization": "Bearer test-token"},
        )

    assert points_response.status_code == 200
    assert points_response.json()["points"] == 128
    assert points_response.json()["balance_micros"] == 128_000_000

    assert ledger_response.status_code == 200
    body = ledger_response.json()
    assert body["has_more"] is True
    assert len(body["entries"]) == 2
    assert body["entries"][0]["delta"] == -20
    assert body["entries"][0]["reason"] == "capture"
    assert body["entries"][0]["delta_micros"] == -20_000_000
    assert body["entries"][1]["reason"] == "purchase"
    assert captured["wallet_user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert captured["ledger_user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert captured["ledger_limit"] == 3
    assert captured["ledger_offset"] == 0


def test_billing_ledger_merges_legacy_capture_history(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {"legacy_profile_calls": [], "legacy_ledger_calls": []}
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    monkeypatch.setattr(
        mobile_module,
        "resolve_auth_context",
        lambda _authorization: mobile_module.AuthContext(
            user_id=canonical_uid,
            provider="local",
            token="test-token",
            claims={"uid": "legacy_user_2008", "canonical_uid": canonical_uid},
        ),
    )
    monkeypatch.setattr(mobile_module, "resolve_wallet_user_id", lambda _authorization: canonical_uid)

    class _FakeWalletService:
        is_configured = True

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            captured["wallet_user_id"] = user_id
            captured["wallet_limit"] = limit
            captured["wallet_offset"] = offset
            return [
                _FakeLedgerEntry(
                    id="evt_wallet_1",
                    user_id=user_id,
                    event_type="grant",
                    delta_micros=99_000_000,
                    balance_after_micros=199_000_000,
                    reference_type="order",
                    reference_id="ord_99",
                    idempotency_key="grant:ord_99",
                    created_at="2026-04-21T12:00:00+08:00",
                )
            ]

    def _fake_get_profile(user_id: str) -> dict[str, object]:
        captured["legacy_profile_calls"].append(user_id)
        if user_id == "legacy_user_2008":
            return {"user_id": user_id, "points": 66}
        raise RuntimeError("legacy member not found")

    def _fake_get_ledger(user_id: str, limit: int = 20, offset: int = 0) -> dict[str, object]:
        captured["legacy_ledger_calls"].append((user_id, limit, offset))
        if user_id == "legacy_user_2008":
            return {
                "entries": [
                    {
                        "id": "legacy_capture_1",
                        "delta": -20,
                        "reason": "capture",
                        "created_at": "2026-04-20T21:00:00+08:00",
                    }
                ],
                "has_more": False,
                "total": 1,
            }
        raise RuntimeError("legacy member not found")

    monkeypatch.setattr(mobile_module.member_service, "get_profile", _fake_get_profile)
    monkeypatch.setattr(mobile_module.member_service, "get_ledger", _fake_get_ledger)
    monkeypatch.setattr(mobile_module, "wallet_service", _FakeWalletService())

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/billing/ledger?limit=5&offset=0", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["has_more"] is False
    assert [item["reason"] for item in body["entries"]] == ["purchase", "capture"]
    assert body["entries"][1]["delta"] == -20
    assert body["entries"][1]["metadata"]["source"] == "legacy_member_console"
    assert body["entries"][1]["user_id"] == canonical_uid
    assert captured["wallet_user_id"] == canonical_uid
    assert captured["wallet_limit"] == 6
    assert captured["wallet_offset"] == 0
    assert captured["legacy_profile_calls"] == [canonical_uid, "legacy_user_2008"]
    assert captured["legacy_ledger_calls"] == [("legacy_user_2008", 6, 0)]


def test_homepage_dashboard_uses_single_canonical_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mobile_module,
        "_resolve_authenticated_user_id",
        lambda _authorization: "legacy_user_2008",
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_home_dashboard",
        lambda user_id: (
            captured.setdefault("user_id", user_id),
            {"review": {}, "mastery": {"weak_nodes": []}, "today": {"hint": ""}},
        )[1],
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/homepage/dashboard", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert captured["user_id"] == "legacy_user_2008"


def test_homepage_dashboard_prefers_canonical_uid_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mobile_module.member_service,
        "verify_access_token",
        lambda _token: {
            "uid": "user_2008",
            "canonical_uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "provider": "local",
        },
    )
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_home_dashboard",
        lambda user_id: (
            captured.setdefault("user_id", user_id),
            {"review": {}, "mastery": {"weak_nodes": []}, "today": {"hint": ""}},
        )[1],
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/homepage/dashboard", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert captured["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"


def test_wallet_endpoints_return_zero_when_wallet_identity_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mobile_module,
        "resolve_auth_context",
        lambda _authorization: mobile_module.AuthContext(
            user_id="wx_GJBK5wy1CMs4",
            provider="wechat_mp",
            token="test-token",
            claims={"uid": "wx_GJBK5wy1CMs4"},
        ),
    )
    monkeypatch.setattr(mobile_module, "resolve_wallet_user_id", lambda _authorization: "wx_GJBK5wy1CMs4")
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_profile",
        lambda user_id: (
            captured.setdefault("profile_user_id", user_id),
            {"user_id": user_id, "username": "", "display_name": "微信用户", "points": 0},
        )[1],
    )

    class _FakeWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            captured["wallet_user_id"] = user_id
            return None

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            captured["ledger_user_id"] = user_id
            captured["ledger_limit"] = limit
            captured["ledger_offset"] = offset
            return []

    monkeypatch.setattr(mobile_module, "wallet_service", _FakeWalletService())

    with TestClient(_build_app()) as client:
        profile_response = client.get("/api/v1/auth/profile", headers={"Authorization": "Bearer test-token"})
        points_response = client.get("/api/v1/billing/points", headers={"Authorization": "Bearer test-token"})
        wallet_response = client.get("/api/v1/billing/wallet", headers={"Authorization": "Bearer test-token"})
        ledger_response = client.get("/api/v1/billing/ledger", headers={"Authorization": "Bearer test-token"})

    assert profile_response.status_code == 200
    assert profile_response.json()["user_id"] == "wx_GJBK5wy1CMs4"
    assert profile_response.json()["points"] == 0
    assert profile_response.json()["wallet"]["balance"] == 0

    assert points_response.status_code == 200
    assert points_response.json()["user_id"] == "wx_GJBK5wy1CMs4"
    assert points_response.json()["points"] == 0

    assert wallet_response.status_code == 200
    assert wallet_response.json()["user_id"] == "wx_GJBK5wy1CMs4"
    assert wallet_response.json()["balance"] == 0

    assert ledger_response.status_code == 200
    assert ledger_response.json() == {"entries": [], "has_more": False, "total": 0}
    assert captured["wallet_user_id"] == "wx_GJBK5wy1CMs4"
    assert captured["ledger_user_id"] == "wx_GJBK5wy1CMs4"
    assert captured["profile_user_id"] == "wx_GJBK5wy1CMs4"


def test_wallet_endpoints_preserve_raw_legacy_uid_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mobile_module,
        "resolve_auth_context",
        lambda _authorization: mobile_module.AuthContext(
            user_id="legacy_user_2008",
            provider="local",
            token="test-token",
            claims={"uid": "legacy_user_2008"},
        ),
    )
    monkeypatch.setattr(mobile_module, "resolve_wallet_user_id", lambda _authorization: "legacy_user_2008")
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_profile",
        lambda user_id: {
            "user_id": user_id,
            "username": "legacy_user_2008",
            "display_name": "老用户",
            "points": 0,
        },
    )

    class _FakeWalletService:
        is_configured = True

        @staticmethod
        def get_wallet(user_id: str):
            captured["wallet_user_id"] = user_id
            return _FakeWalletSnapshot(user_id=user_id, balance_micros=66_000_000, version=3)

        @staticmethod
        def list_wallet_ledger(user_id: str, *, limit: int = 20, offset: int = 0):
            captured["ledger_user_id"] = user_id
            captured["ledger_limit"] = limit
            captured["ledger_offset"] = offset
            return [
                _FakeLedgerEntry(
                    id="evt_legacy_1",
                    user_id=user_id,
                    event_type="grant",
                    delta_micros=66_000_000,
                    balance_after_micros=66_000_000,
                    reference_type="legacy_import",
                    reference_id="legacy_user_2008",
                    idempotency_key="legacy:legacy_user_2008",
                    created_at="2026-04-21T10:00:00+08:00",
                )
            ]

    monkeypatch.setattr(mobile_module, "wallet_service", _FakeWalletService())

    with TestClient(_build_app()) as client:
        profile_response = client.get("/api/v1/auth/profile", headers={"Authorization": "Bearer test-token"})
        wallet_response = client.get("/api/v1/billing/wallet", headers={"Authorization": "Bearer test-token"})
        ledger_response = client.get("/api/v1/billing/ledger", headers={"Authorization": "Bearer test-token"})

    assert profile_response.status_code == 200
    assert profile_response.json()["points"] == 66
    assert wallet_response.status_code == 200
    assert wallet_response.json()["balance"] == 66
    assert ledger_response.status_code == 200
    assert ledger_response.json()["entries"][0]["delta"] == 66
    assert captured["wallet_user_id"] == "legacy_user_2008"
    assert captured["ledger_user_id"] == "legacy_user_2008"


def test_wallet_endpoints_treat_invalid_uuid_wallet_lookup_as_empty_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _InvalidUuidWalletRestClient:
        @staticmethod
        def get(url: str, headers=None, params=None):
            del headers
            request = wallet_service_module.httpx.Request("GET", url, params=params)
            user_id = str((params or {}).get("user_id", "")).removeprefix("eq.")
            if user_id.startswith("wx_"):
                response = wallet_service_module.httpx.Response(
                    400,
                    request=request,
                    json={
                        "code": "22P02",
                        "details": None,
                        "hint": None,
                        "message": f'invalid input syntax for type uuid: "{user_id}"',
                    },
                )
                raise wallet_service_module.httpx.HTTPStatusError("request failed", request=request, response=response)
            return wallet_service_module.httpx.Response(200, request=request, json=[])

    monkeypatch.setattr(
        mobile_module,
        "resolve_auth_context",
        lambda _authorization: mobile_module.AuthContext(
            user_id="wx_O4aNJg7O_wRk",
            provider="wechat_mp",
            token="test-token",
            claims={"uid": "wx_O4aNJg7O_wRk"},
        ),
    )
    monkeypatch.setattr(mobile_module, "resolve_wallet_user_id", lambda _authorization: "wx_O4aNJg7O_wRk")
    monkeypatch.setattr(
        mobile_module.member_service,
        "get_profile",
        lambda user_id: {"user_id": user_id, "username": "", "display_name": "微信用户", "points": 0},
    )

    monkeypatch.setattr(
        mobile_module,
        "wallet_service",
        wallet_service_module.SupabaseWalletService(
            base_url="https://example.supabase.co",
            service_key="service-role-key",
            client=_InvalidUuidWalletRestClient(),
        ),
    )

    with TestClient(_build_app()) as client:
        profile_response = client.get("/api/v1/auth/profile", headers={"Authorization": "Bearer test-token"})
        points_response = client.get("/api/v1/billing/points", headers={"Authorization": "Bearer test-token"})
        wallet_response = client.get("/api/v1/billing/wallet", headers={"Authorization": "Bearer test-token"})
        ledger_response = client.get("/api/v1/billing/ledger", headers={"Authorization": "Bearer test-token"})

    assert profile_response.status_code == 200
    assert profile_response.json()["points"] == 0
    assert points_response.status_code == 200
    assert points_response.json()["points"] == 0
    assert wallet_response.status_code == 200
    assert wallet_response.json()["balance"] == 0
    assert ledger_response.status_code == 200
    assert ledger_response.json() == {"entries": [], "has_more": False, "total": 0}
