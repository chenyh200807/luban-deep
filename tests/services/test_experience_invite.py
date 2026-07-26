from decimal import Decimal
from pathlib import Path

import pytest

from deeptutor.services.experience_invite import (
    ExperienceInviteAuthority,
    ExperienceInviteRejected,
    ExperienceInviteUnavailable,
    experience_cost_from_usage_summary,
    experience_usage_has_incurred_cost,
)


def test_cost_prefers_measured_langfuse_cost_with_explicit_provenance() -> None:
    cost = experience_cost_from_usage_summary(
        {"total_cost_usd": "0.0125"}
    )
    assert cost.amount_micros_cny == 90_000
    assert cost.provenance == "langfuse_measured_usd_fixed_fx_7_20"


def test_cost_sums_mixed_measured_and_estimated_calls() -> None:
    cost = experience_cost_from_usage_summary(
        {"total_cost_usd": "0.0125", "estimated_total_cost_usd": "0.01"}
    )
    assert cost.amount_micros_cny == 162_000
    assert cost.provenance == "langfuse_measured_plus_model_estimated_usd_fixed_fx_7_20"


def test_cost_uses_estimate_then_conservative_reservation_when_measurement_missing() -> None:
    estimated = experience_cost_from_usage_summary({"estimated_total_cost_usd": Decimal("0.01")})
    missing = experience_cost_from_usage_summary({})
    assert estimated.amount_micros_cny == 72_000
    assert estimated.provenance == "model_usage_estimated_usd_fixed_fx_7_20"
    assert missing.amount_micros_cny == 800_000
    assert missing.provenance == "reservation_estimate_missing_model_cost"
    assert experience_usage_has_incurred_cost({"total_cost_usd": "0.01"}) is True
    assert experience_usage_has_incurred_cost({"estimated_total_cost_usd": Decimal("0.01")}) is True
    assert experience_usage_has_incurred_cost({"total_calls": 1, "total_cost_usd": 0}) is True
    assert experience_usage_has_incurred_cost({}) is False


def test_reservation_returns_server_authored_context_without_cost_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    rpc_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        authority,
        "status",
        lambda _user_id: {"state": "active", "active": True, "expires_at": "2099-01-01T00:00:00Z"},
    )
    monkeypatch.setattr(
        authority,
        "_rpc",
        lambda _name, payload: (
            rpc_calls.append(dict(payload))
            or {"allowed": True, "reason": "reserved", "turn_key": "turn-1"}
        ),
    )
    assert authority.reserve_turn(user_id="member-1", turn_key="turn-1") == {
        "experience": "reserved",
        "experience_turn_key": "turn-1",
    }
    assert rpc_calls == [
        {
            "p_user_id": "member-1",
            "p_turn_key": "turn-1",
            "p_reservation_micros": 200_000,
            "p_daily_limit_micros": 1_000_000,
        }
    ]


def test_reservation_fails_closed_at_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    monkeypatch.setattr(authority, "status", lambda _user_id: {"active": True})
    monkeypatch.setattr(
        authority,
        "_rpc",
        lambda _name, _payload: {"allowed": False, "reason": "daily_limit"},
    )
    with pytest.raises(ExperienceInviteRejected, match="daily_limit"):
        authority.reserve_turn(user_id="member-1", turn_key="turn-2")


def test_expired_experience_does_not_fall_back_as_active_invite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    monkeypatch.setattr(authority, "status", lambda _user_id: {"state": "expired", "active": False})
    with pytest.raises(ExperienceInviteRejected, match="expired"):
        authority.reserve_turn(user_id="member-1", turn_key="turn-3")


def test_settlement_retry_reports_database_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    monkeypatch.setattr(
        authority,
        "_rpc",
        lambda _name, _payload: {
            "status": "settled",
            "daily_blocked": False,
            "provenance": "langfuse_measured_usd_fixed_fx_7_20",
        },
    )
    result = authority.settle_turn(user_id="member-1", turn_key="turn-1", usage_summary={})
    assert result["provenance"] == "langfuse_measured_usd_fixed_fx_7_20"


def test_settlement_without_reservation_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    monkeypatch.setattr(
        authority,
        "_rpc",
        lambda _name, _payload: {
            "status": "missing_reservation",
            "daily_blocked": True,
            "provenance": None,
        },
    )
    with pytest.raises(ExperienceInviteUnavailable, match="missing_reservation"):
        authority.settle_turn(user_id="member-1", turn_key="missing", usage_summary={})


def test_batch_invite_creation_is_one_atomic_rest_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    calls: list[dict[str, object]] = []

    def fake_request(_method, _path, **kwargs):
        calls.append(kwargs)
        return [
            {
                **row,
                "id": f"invite-{index}",
            }
            for index, row in enumerate(kwargs["json"], start=1)
        ]

    monkeypatch.setattr(authority, "_request", fake_request)
    created = authority.create_invites(
        actor_id="operator-1",
        source="yousen_paid_student",
        quantity=3,
        max_redemptions=2,
        valid_until="2099-01-01T00:00:00Z",
    )

    assert len(calls) == 1
    assert len(calls[0]["json"]) == 3
    assert len(created) == 3
    assert all(item["code"].startswith("YS-") for item in created)
    assert all("code_hash" not in item for item in created)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("quantity", 0, "quantity"),
        ("quantity", 101, "quantity"),
        ("max_redemptions", 0, "max_redemptions"),
        ("max_redemptions", 1001, "max_redemptions"),
        ("valid_until", "not-a-date", "valid_until"),
    ],
)
def test_invite_creation_rejects_invalid_admin_limits(
    field: str,
    value: object,
    message: str,
) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    kwargs = {
        "actor_id": "operator-1",
        "source": "yousen_paid_student",
        "quantity": 1,
        "max_redemptions": 1,
        "valid_until": None,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=message):
        authority.create_invites(**kwargs)


def test_status_projects_only_temporary_entitlement(monkeypatch: pytest.MonkeyPatch) -> None:
    authority = ExperienceInviteAuthority(base_url="https://example.test", service_key="secret")
    monkeypatch.setattr(
        authority,
        "_request",
        lambda *_args, **_kwargs: [
            {
                "redeemed_at": "2026-07-26T00:00:00Z",
                "expires_at": "2099-08-09T00:00:00Z",
                "source": "yousen_paid_student",
            }
        ],
    )
    status = authority.status("member-1")
    assert status["active"] is True
    assert status["video_access_limit"] == 30
    assert "amount" not in status
    assert "remaining" not in status


def test_migration_keeps_redeem_and_cost_transitions_database_atomic() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260726000100_experience_invites.sql"
    ).read_text(encoding="utf-8")
    assert migration.count("pg_advisory_xact_lock(hashtextextended(p_user_id, 0))") == 4
    assert "from public.experience_access where user_id = p_user_id for update" in migration
    assert "primary key (user_id, turn_key)" in migration
    assert "where user_id = p_user_id and turn_key = p_turn_key" in migration
    assert "v_existing.status in ('reserved', 'settled')" in migration
    assert "when v_existing.status = 'reserved' then 'in_progress'" in migration
    assert "else 'already_settled'" in migration
    assert "v_existing_found := found;" in migration
    assert "status = 'reserved'" in migration
    assert "status in ('reserved', 'settled')" in migration
    assert migration.count("security definer set search_path = public") == 4
    assert migration.count("force row level security") == 3
    assert migration.count("comment on table public.experience_") == 3
    assert (
        "revoke all on public.experience_invites, public.experience_access, "
        "public.experience_turn_costs from anon;"
    ) in migration
    assert (
        "revoke all on public.experience_invites, public.experience_access, "
        "public.experience_turn_costs from authenticated;"
    ) in migration
    assert "revoke all on function public.redeem_experience_invite" in migration
