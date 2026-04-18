from __future__ import annotations

from deeptutor.services.observability.usage_ledger import UsageLedger


def test_usage_ledger_rolls_up_measured_and_estimated_usage(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 120.0, "output": 30.0, "total": 150.0},
        cost_details={"total": 0.12},
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
        session_id="s1",
        turn_id="t1",
        capability="chat",
        scope_id="scope-1",
    )
    ledger.record_usage_event(
        usage_source="tiktoken",
        usage_details={"input": 20.0, "output": 10.0, "total": 30.0},
        cost_details={"total": 0.03},
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
        session_id="s1",
        turn_id="t1",
        capability="chat",
        scope_id="scope-1",
    )

    totals = ledger.get_totals(start_ts=0, end_ts=9_999_999_999, provider_name="dashscope")

    assert totals.measured_total_tokens == 150
    assert totals.estimated_total_tokens == 30
    assert totals.total_tokens == 180
    assert totals.measured_total_cost == 0.12
    assert totals.estimated_total_cost == 0.03
    assert totals.total_cost == 0.15
    assert totals.events == 2


def test_usage_ledger_dedupe_key_is_idempotent(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    inserted_first = ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 10.0, "output": 2.0, "total": 12.0},
        cost_details={"total": 0.01},
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
        dedupe_key="same-key",
    )
    inserted_second = ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 10.0, "output": 2.0, "total": 12.0},
        cost_details={"total": 0.01},
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
        dedupe_key="same-key",
    )

    totals = ledger.get_totals(start_ts=0, end_ts=9_999_999_999, provider_name="dashscope")

    assert inserted_first is True
    assert inserted_second is False
    assert totals.total_tokens == 12
    assert totals.events == 1


def test_usage_ledger_respects_created_at_override(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 5.0, "output": 1.0, "total": 6.0},
        cost_details={"total": 0.005},
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
        created_at=1234.0,
    )

    old_totals = ledger.get_totals(start_ts=1200.0, end_ts=1300.0, provider_name="dashscope")
    new_totals = ledger.get_totals(start_ts=1301.0, end_ts=1400.0, provider_name="dashscope")

    assert old_totals.total_tokens == 6
    assert old_totals.coverage_start_ts == 1234.0
    assert new_totals.total_tokens == 0
