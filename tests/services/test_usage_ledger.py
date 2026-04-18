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
