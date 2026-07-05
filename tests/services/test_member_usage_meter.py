from __future__ import annotations

from deeptutor.services.member_usage_meter import MemberUsageMeter


def test_member_usage_meter_records_deduped_turn_usage(tmp_path) -> None:
    meter = MemberUsageMeter(tmp_path / "member_usage_meter.db")

    first = meter.record_usage_event(
        wallet_user_id="wallet_demo",
        learning_user_id="learner_demo",
        source="wx_miniprogram",
        session_id="session-1",
        turn_id="turn-1",
        amount_points=36,
        dedupe_key="mini_program_meter:turn-1",
        status="metered_not_charged",
        metadata={"billing_amount_source": "measured_cost"},
        created_at=1_700_000_000.0,
    )
    duplicate = meter.record_usage_event(
        wallet_user_id="wallet_demo",
        learning_user_id="learner_demo",
        source="wx_miniprogram",
        session_id="session-1",
        turn_id="turn-1",
        amount_points=99,
        dedupe_key="mini_program_meter:turn-1",
        status="metered_not_charged",
        metadata={},
        created_at=1_700_000_010.0,
    )

    assert first is True
    assert duplicate is False
    events = meter.list_usage_events("wallet_demo", limit=20)
    assert len(events) == 1
    event = events[0]
    assert event.wallet_user_id == "wallet_demo"
    assert event.learning_user_id == "learner_demo"
    assert event.source == "wx_miniprogram"
    assert event.session_id == "session-1"
    assert event.turn_id == "turn-1"
    assert event.amount_points == 36
    assert event.status == "metered_not_charged"
    assert event.metadata == {"billing_amount_source": "measured_cost"}


def test_member_usage_meter_record_after_check_refuses_insert_when_check_fails(tmp_path) -> None:
    meter = MemberUsageMeter(tmp_path / "member_usage_meter.db")
    meter.record_usage_event(
        wallet_user_id="wallet_demo",
        learning_user_id="learner_demo",
        source="wx_miniprogram",
        session_id="session-1",
        turn_id="turn-1",
        amount_points=20,
        dedupe_key="usage:wallet_demo:turn-1",
        status="metered_not_charged",
        metadata={"reason": "existing"},
        created_at=1_700_000_000.0,
    )

    def _reject_existing(events):
        assert len(events) == 1
        raise RuntimeError("quota exceeded")

    try:
        meter.record_usage_event_after_check(
            wallet_user_id="wallet_demo",
            learning_user_id="learner_demo",
            source="wx_miniprogram",
            session_id="session-1",
            turn_id="",
            amount_points=20,
            dedupe_key="free_trial:wallet_demo:client-1",
            status="free_trial_reserved",
            metadata={"reason": "free_trial"},
            created_at=1_700_000_100.0,
            check_existing_events=_reject_existing,
        )
    except RuntimeError as exc:
        assert str(exc) == "quota exceeded"
    else:
        raise AssertionError("quota check should reject insert")

    events = meter.list_usage_events("wallet_demo", limit=20)
    assert len(events) == 1
    assert events[0].turn_id == "turn-1"
    assert events[0].status == "metered_not_charged"


def test_member_usage_meter_updates_free_trial_reservation(tmp_path) -> None:
    meter = MemberUsageMeter(tmp_path / "member_usage_meter.db")
    assert meter.record_usage_event(
        wallet_user_id="wallet_demo",
        learning_user_id="learner_demo",
        source="wx_miniprogram",
        session_id="session-1",
        turn_id="",
        amount_points=20,
        dedupe_key="free_trial:wallet_demo:client-1",
        status="free_trial_reserved",
        metadata={"reason": "free_trial"},
        created_at=1_700_000_000.0,
    )

    updated = meter.update_usage_event(
        "free_trial:wallet_demo:client-1",
        status="free_trial_released",
        turn_id="turn-1",
        metadata_updates={"release_reason": "provider_error"},
    )

    assert updated is True
    event = meter.list_usage_events("wallet_demo", limit=20)[0]
    assert event.status == "free_trial_released"
    assert event.turn_id == "turn-1"
    assert event.metadata == {
        "reason": "free_trial",
        "release_reason": "provider_error",
    }


def test_member_usage_meter_finalizes_only_reserved_free_trial(tmp_path) -> None:
    meter = MemberUsageMeter(tmp_path / "member_usage_meter.db")
    meter.record_usage_event(
        wallet_user_id="wallet_demo",
        learning_user_id="learner_demo",
        source="wx_miniprogram",
        session_id="session-1",
        turn_id="",
        amount_points=20,
        dedupe_key="free_trial:wallet_demo:client-1",
        status="free_trial_reserved",
        metadata={"reason": "free_trial"},
        created_at=1_700_000_000.0,
    )
    assert meter.finalize_free_trial_reservation(
        "free_trial:wallet_demo:client-1",
        chargeable=False,
        turn_id="turn-1",
        metadata_updates={"release_reason": "provider_error"},
    )
    assert not meter.finalize_free_trial_reservation(
        "free_trial:wallet_demo:client-1",
        chargeable=True,
        turn_id="turn-2",
    )

    event = meter.list_usage_events("wallet_demo", limit=20)[0]
    assert event.status == "free_trial_released"
    assert event.turn_id == "turn-1"


def test_member_usage_meter_refuses_to_finalize_non_free_trial_event(tmp_path) -> None:
    meter = MemberUsageMeter(tmp_path / "member_usage_meter.db")
    meter.record_usage_event(
        wallet_user_id="wallet_demo",
        learning_user_id="learner_demo",
        source="wx_miniprogram",
        session_id="session-1",
        turn_id="",
        amount_points=20,
        dedupe_key="usage:wallet_demo:turn-1",
        status="free_trial_reserved",
        metadata={"reason": "other"},
        created_at=1_700_000_000.0,
    )

    assert not meter.finalize_free_trial_reservation(
        "usage:wallet_demo:turn-1",
        chargeable=False,
        turn_id="turn-1",
    )
    event = meter.list_usage_events("wallet_demo", limit=20)[0]
    assert event.status == "free_trial_reserved"
    assert event.turn_id == ""
