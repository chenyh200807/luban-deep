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
