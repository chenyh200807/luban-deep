from __future__ import annotations

import asyncio

import pytest

from deeptutor.api.dependencies.auth import AuthContext
from deeptutor.api.routers import bi, mobile


def test_public_experience_projection_never_exposes_internal_cost_or_counts() -> None:
    payload = mobile._public_experience_status(
        {
            "state": "active",
            "active": True,
            "expires_at": "2026-08-09T00:00:00Z",
            "source": "yousen_paid_student",
            "video_access_limit": 30,
            "settled_micros": 999_999,
            "remaining_micros": 1,
        }
    )
    assert payload == {
        "state": "active",
        "active": True,
        "expires_at": "2026-08-09T00:00:00Z",
        "video_access_limit": 30,
        "message": "精选体验进行中",
    }


def test_paid_video_entitlement_wins_over_invite(monkeypatch) -> None:
    monkeypatch.setattr(
        mobile.member_service,
        "get_billing_entitlement_read_model",
        lambda _user_id: {
            "tier": "light_98",
            "status": "active",
            "expire_at": "2099-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        mobile.experience_invite_authority,
        "status",
        lambda _user_id: {"active": True, "video_access_limit": 30},
    )
    assert mobile._teaching_video_limit_for_user("member-1") is None


def test_invite_video_entitlement_reuses_existing_gate_only_without_paid_membership(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_EXPERIENCE_INVITE_ENABLED", "true")
    monkeypatch.setattr(
        mobile.member_service,
        "get_billing_entitlement_read_model",
        lambda _user_id: {"tier": "", "status": "", "expire_at": ""},
    )
    monkeypatch.setattr(mobile.experience_invite_authority, "_base_url", "https://example.test")
    monkeypatch.setattr(mobile.experience_invite_authority, "_service_key", "secret")
    monkeypatch.setattr(
        mobile.experience_invite_authority,
        "status",
        lambda user_id: {
            "active": user_id == "auth-member-1",
            "video_access_limit": 30,
        },
    )
    assert (
        mobile._teaching_video_limit_for_user(
            "wallet-member-1",
            experience_user_id="auth-member-1",
        )
        == 30
    )


@pytest.mark.parametrize("reason", ["in_progress", "already_settled"])
def test_duplicate_experience_turn_is_fail_closed(monkeypatch, reason: str) -> None:
    class FakeAuthority:
        is_enabled = True
        is_configured = True

        def reserve_turn(self, **_kwargs):
            raise mobile.ExperienceInviteRejected(reason)

    monkeypatch.setattr(mobile, "experience_invite_authority", FakeAuthority())
    monkeypatch.setattr(mobile, "is_billing_enforcement_enabled", lambda: True)
    monkeypatch.setattr(mobile, "_resolve_legacy_ledger_candidate_user_ids", lambda *_args: [])
    monkeypatch.setattr(mobile, "_internal_qa_member_identity_candidates", lambda *_args: [])
    monkeypatch.setattr(mobile, "internal_qa_billing_bypass_allowed", lambda *_args: False)
    monkeypatch.setattr(mobile, "_record_experience_product_event", lambda **_kwargs: None)
    monkeypatch.setattr(
        mobile,
        "wallet_service",
        type("Wallet", (), {"is_configured": False})(),
    )

    with pytest.raises(mobile.HTTPException) as exc_info:
        mobile._assert_billing_quota_available(
            None,
            wallet_user_id="qa_eval_wallet_1",
            authenticated_user_id="qa_eval_member_1",
            client_turn_id="client-turn-1",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": reason,
        "message": "这次提问正在处理或已完成，请勿重复提交。",
        "limited_by": "experience",
    }


def test_mobile_redeem_projects_only_public_experience_fields(monkeypatch) -> None:
    class FakeAuthority:
        is_enabled = True

        def redeem(self, *, user_id: str, code: str):
            assert user_id == "qa_eval_member_1"
            assert code == "YS-ABCDEF1234"
            return {
                "state": "active",
                "active": True,
                "expires_at": "2099-01-15T00:00:00Z",
                "source": "yousen_paid_student",
                "video_access_limit": 30,
                "settled_micros": 123,
            }

    monkeypatch.setattr(mobile, "experience_invite_authority", FakeAuthority())
    monkeypatch.setattr(
        mobile,
        "_resolve_authenticated_user_id",
        lambda _authorization: "qa_eval_member_1",
    )
    monkeypatch.setattr(mobile, "_record_experience_product_event", lambda **_kwargs: None)

    result = asyncio.run(
        mobile.billing_experience_redeem(
            mobile.ExperienceRedeemRequest(code="YS-ABCDEF1234"),
            authorization="Bearer test-token",
        )
    )

    assert result == {
        "state": "active",
        "active": True,
        "expires_at": "2099-01-15T00:00:00Z",
        "video_access_limit": 30,
        "message": "精选体验进行中",
    }


def test_bi_batch_generator_delegates_one_atomic_authority_call(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeAuthority:
        def create_invites(self, **kwargs):
            calls.append(kwargs)
            return [
                {"id": "invite-1", "code": "YS-ONE", "code_prefix": "YS-ONE"},
                {"id": "invite-2", "code": "YS-TWO", "code_prefix": "YS-TWO"},
            ]

    monkeypatch.setattr(bi, "get_experience_invite_authority", lambda: FakeAuthority())
    auth = AuthContext(
        user_id="qa_eval_operator_1",
        provider="test",
        token="test-token",
        claims={},
        is_admin=True,
    )
    result = asyncio.run(
        bi.bi_create_experience_invite(
            {
                "source": "yousen_paid_student",
                "quantity": 2,
                "max_redemptions": 1,
                "valid_until": "2099-01-01T00:00:00Z",
            },
            auth=auth,
        )
    )

    assert result["count"] == 2
    assert len(result["items"]) == 2
    assert calls == [
        {
            "actor_id": "qa_eval_operator_1",
            "source": "yousen_paid_student",
            "quantity": 2,
            "max_redemptions": 1,
            "valid_until": "2099-01-01T00:00:00Z",
        }
    ]
