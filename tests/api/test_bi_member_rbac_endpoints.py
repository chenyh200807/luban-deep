from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

bi = importlib.import_module("deeptutor.api.routers.bi")


class _FakeMemberConsole:
    def __init__(self, allowed: set[tuple[str, str, str]]) -> None:
        self.allowed = allowed
        self.calls: list[dict[str, object]] = []

    def get_admin_role(self, user_id: str) -> str | None:
        return "operator" if user_id.startswith("u-") else None

    def can_access(self, user_id: str, tab: str, action: str) -> bool:
        return (user_id, tab, action) in self.allowed

    def manual_membership_purchase(self, **kwargs: object) -> dict[str, object]:
        self.calls.append({"fn": "manual_membership_purchase", **kwargs})
        return {
            "member": {"user_id": kwargs["user_id"], "tier": "vip", "status": "active"},
            "package": {"id": kwargs["package_id"]},
            "amount_cny": kwargs.get("amount_cny") or 198,
            "points": 9000,
            "purchase_id": "manual_membership_1",
            "ledger_event_id": "ledger_manual_1",
            "audit_id": "audit_manual_1",
            "deduped": False,
        }

    def reverse_manual_membership_purchase(self, **kwargs: object) -> dict[str, object]:
        self.calls.append({"fn": "reverse_manual_membership_purchase", **kwargs})
        return {
            "member": {"user_id": kwargs["user_id"], "tier": "supreme_svip", "status": "revoked"},
            "amount_cny": -998,
            "points": -50000,
            "purchase_id": kwargs["purchase_id"],
            "ledger_event_id": "ledger_refund_1",
            "audit_id": "audit_reverse_1",
            "deduped": False,
        }

    def merge_member_accounts(self, **kwargs: object) -> dict[str, object]:
        self.calls.append({"fn": "merge_member_accounts", **kwargs})
        return {
            "member": {"user_id": kwargs["target_user_id"], "tier": "supreme_svip"},
            "merged_source_ids": kwargs["source_user_ids"],
            "points_transferred": 730,
            "audit_id": "audit_merge_1",
            "deduped": False,
            "admin_role_after": "super_admin",
        }

    def record_ops_action_result(self, user_id: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"fn": "record_ops_action_result", "user_id": user_id, **kwargs})
        return {
            "status": kwargs["status"],
            "result": kwargs["result"],
            "action_title": kwargs["action_title"],
            "next_follow_up_at": kwargs["next_follow_up_at"],
            "note_id": "note_ops_1",
            "audit_id": "audit_ops_1",
            "deduped": False,
        }

    def batch_update_members(self, **kwargs: object) -> dict[str, object]:
        self.calls.append({"fn": "batch_update_members", **kwargs})
        return {"success_count": 1, "failure_count": 0, "items": []}


def _build_app(monkeypatch: pytest.MonkeyPatch, svc: _FakeMemberConsole, user_id: str = "u-op") -> FastAPI:
    monkeypatch.setattr(bi, "get_member_console_service", lambda: svc)
    app = FastAPI()
    app.include_router(bi.router, prefix="/api/v1/bi")
    app.dependency_overrides[bi.require_bi_access] = lambda: SimpleNamespace(
        user_id=user_id,
        is_admin=False,
    )
    return app


def test_bi_member_manual_purchase_allows_operator_and_forwards_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole({("u-op", "member_ops", "write")})
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/bi/member/manual-purchase",
            headers={"X-Idempotency-Key": "manual-purchase-1"},
            json={"user_id": "student_1", "package_id": "vip", "days": 365, "amount_cny": 0},
        )

    assert response.status_code == 200
    assert svc.calls == [
        {
            "fn": "manual_membership_purchase",
            "user_id": "student_1",
            "package_id": "vip",
            "days": 365,
            "operator": "u-op",
            "reason": "",
            "idempotency_key": "manual-purchase-1",
            "phone": "",
            "display_name": "",
            "amount_cny": 0.0,
        }
    ]


def test_bi_member_manual_purchase_denies_without_member_ops_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole(set())
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/bi/member/manual-purchase",
            headers={"X-Idempotency-Key": "manual-purchase-1"},
            json={"user_id": "student_1", "package_id": "vip", "days": 365},
        )

    assert response.status_code == 403
    assert svc.calls == []


def test_bi_member_reversal_requires_high_risk_purchase_id_and_uses_original_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole({("u-op", "member_ops", "high_risk")})
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        missing_purchase = client.post(
            "/api/v1/bi/member/manual-purchase/reverse",
            headers={"X-Idempotency-Key": "reverse-1"},
            json={"user_id": "student_1", "reason": "误录"},
        )
        reversed_purchase = client.post(
            "/api/v1/bi/member/manual-purchase/reverse",
            headers={"X-Idempotency-Key": "reverse-2"},
            json={
                "user_id": "student_1",
                "purchase_id": "manual_membership_1",
                "amount_cny": 1,
                "reason": "误录",
            },
        )

    assert missing_purchase.status_code == 400
    assert reversed_purchase.status_code == 200
    assert svc.calls == [
        {
            "fn": "reverse_manual_membership_purchase",
            "user_id": "student_1",
            "purchase_id": "manual_membership_1",
            "amount_cny": None,
            "operator": "u-op",
            "reason": "误录",
            "idempotency_key": "reverse-2",
        }
    ]


def test_bi_member_merge_accounts_requires_high_risk_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole({("u-op", "member_ops", "high_risk")})
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        missing_key = client.post(
            "/api/v1/bi/member/merge-accounts",
            json={"target_user_id": "u_target", "source_user_ids": ["u_wx", "u_account"]},
        )
        merged = client.post(
            "/api/v1/bi/member/merge-accounts",
            headers={"X-Idempotency-Key": "merge-accounts-1"},
            json={
                "target_user_id": "u_target",
                "source_user_ids": ["u_wx", "u_account"],
                "reason": "confirmed_same_owner",
            },
        )

    assert missing_key.status_code == 400
    assert merged.status_code == 200
    assert merged.json()["points_transferred"] == 730
    assert svc.calls == [
        {
            "fn": "merge_member_accounts",
            "target_user_id": "u_target",
            "source_user_ids": ["u_wx", "u_account"],
            "operator": "u-op",
            "reason": "confirmed_same_owner",
            "idempotency_key": "merge-accounts-1",
        }
    ]


def test_bi_member_merge_accounts_denies_without_high_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole({("u-op", "member_ops", "write")})
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/bi/member/merge-accounts",
            headers={"X-Idempotency-Key": "merge-accounts-1"},
            json={"target_user_id": "u_target", "source_user_ids": ["u_wx"]},
        )

    assert response.status_code == 403
    assert svc.calls == []


def test_bi_member_ops_actions_uses_member_console_authority_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole({("u-op", "member_ops", "write")})
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        missing_key = client.post(
            "/api/v1/bi/member/student_1/ops-actions",
            json={"status": "done", "result": "已电话联系", "action_title": "联系"},
        )
        recorded = client.post(
            "/api/v1/bi/member/student_1/ops-actions",
            headers={"X-Idempotency-Key": "ops-action-1"},
            json={"status": "done", "result": "已电话联系", "action_title": "联系"},
        )

    assert missing_key.status_code == 400
    assert recorded.status_code == 200
    assert svc.calls == [
        {
            "fn": "record_ops_action_result",
            "user_id": "student_1",
            "status": "done",
            "result": "已电话联系",
            "action_title": "联系",
            "next_follow_up_at": "",
            "operator": "u-op",
            "idempotency_key": "ops-action-1",
        }
    ]


def test_bi_member_batch_rejects_tier_only_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _FakeMemberConsole({("u-op", "member_ops", "high_risk")})
    app = _build_app(monkeypatch, svc)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/bi/member/batch",
            json={"user_ids": ["student_1"], "action": "grant", "days": 30, "tier": "vip"},
        )

    assert response.status_code == 400
    assert "manual purchase" in response.json()["detail"]
    assert svc.calls == []
