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


def test_usage_ledger_marks_turn_billable_only_after_wallet_capture(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 10.0, "output": 5.0, "total": 15.0},
        cost_details={"total": 0.02},
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "charged_provider_name": "deepseek",
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
        },
        session_id="session-1",
        turn_id="turn-1",
        scope_id="turn-1",
    )

    before = ledger.get_totals(
        start_ts=0,
        end_ts=9_999_999_999,
        provider_name="deepseek",
        billable_only=True,
    )
    assert before.total_tokens == 0

    updated = ledger.mark_turn_billable(
        turn_id="turn-1",
        billing_capture={
            "status": "captured",
            "idempotency_key": "mini_program_capture:turn-1",
            "amount_points": 20,
            "billing_amount_source": "fallback_minimum",
        },
    )

    assert updated == 1
    after = ledger.get_totals(
        start_ts=0,
        end_ts=9_999_999_999,
        provider_name="deepseek",
        billable_only=True,
    )
    assert after.billable_turns == 1
    assert after.provider_calls == 1
    assert after.total_tokens == 15


def test_usage_ledger_rolls_up_deepseek_cache_metadata(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={
            "input": 1000.0,
            "input_cache_hit": 700.0,
            "input_cache_miss": 300.0,
            "output": 200.0,
            "total": 1200.0,
        },
        cost_details={"input": 0.000044, "output": 0.000056, "total": 0.0001},
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "charged_provider_name": "deepseek",
            "requested_provider_name": "deepseek",
            "api_key_fingerprint": "sha256:test",
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
            "billable_unit": "conversation_turn",
            "billable_turn_id": "turn-1",
            "billing_capture_status": "captured",
            "raw_model": "deepseek-v4-flash",
            "pricing_model": "deepseek-v4-flash",
            "pricing_currency": "USD",
            "billing_currency": "USD",
            "pricing_source_checked_at": "2026-06-03",
            "official_usage_fields": {
                "prompt_cache_hit_tokens": 700,
                "prompt_cache_miss_tokens": 300,
            },
        },
    )

    totals = ledger.get_totals(start_ts=0, end_ts=9_999_999_999, provider_name="deepseek")

    assert totals.total_tokens == 1200
    assert totals.metadata_breakdown["input_cache_hit_tokens"] == 700
    assert totals.metadata_breakdown["input_cache_miss_tokens"] == 300
    assert totals.currency_amounts["USD"] == 0.0001
    assert totals.billable_turns == 1
    assert totals.provider_calls == 1
    assert totals.cost_center_amounts["prod_user_chat"]["USD"] == 0.0001


def test_usage_ledger_billable_only_requires_wallet_capture(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")

    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 1000.0, "output": 200.0, "total": 1200.0},
        cost_details={"total": 0.0001},
        model="deepseek-v4-flash",
        metadata={
            "provider_name": "deepseek",
            "runtime_environment": "production",
            "cost_center": "prod_user_chat",
            "billable_unit": "conversation_turn",
            "billable_turn_id": "turn-pending",
        },
    )

    totals = ledger.get_totals(
        start_ts=0,
        end_ts=9_999_999_999,
        provider_name="deepseek",
        billable_only=True,
    )

    assert totals.total_tokens == 0
    assert totals.billable_turns == 0
    assert totals.provider_calls == 0


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


def test_usage_ledger_window_summary_breaks_down_by_model_and_source(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")
    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 100.0, "output": 50.0, "total": 150.0},
        cost_details={"total": 0.10},
        model="deepseek-v4-flash",
        metadata={"provider_name": "dashscope"},
        turn_id="t1",
    )
    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 200.0, "output": 0.0, "total": 200.0},
        cost_details={"total": 0.05},
        model="gte-rerank",
        metadata={"provider_name": "dashscope"},
        turn_id="t2",
    )
    ledger.record_usage_event(
        usage_source="tiktoken",
        usage_details={"input": 30.0, "output": 10.0, "total": 40.0},
        cost_details={"total": 0.02},
        model="deepseek-v4-flash",
        metadata={"provider_name": "dashscope"},
        turn_id="t1",
    )

    summary = ledger.get_window_summary(start_ts=0, end_ts=9_999_999_999)

    totals = summary["totals"]
    assert totals["measured_total_cost_usd"] == 0.15
    assert totals["estimated_total_cost_usd"] == 0.02
    assert totals["total_cost_usd"] == 0.17
    assert totals["total_tokens"] == 390

    by_model = {row["model"]: row for row in summary["by_model"]}
    assert by_model["deepseek-v4-flash"]["events"] == 2
    assert by_model["deepseek-v4-flash"]["total_cost_usd"] == 0.12
    assert by_model["gte-rerank"]["total_cost_usd"] == 0.05

    by_source = {row["usage_source"]: row for row in summary["by_usage_source"]}
    assert by_source["provider"]["events"] == 2
    assert by_source["tiktoken"]["events"] == 1


def test_usage_ledger_window_summary_empty_window(tmp_path) -> None:
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")
    summary = ledger.get_window_summary(start_ts=0, end_ts=1)
    assert summary["totals"]["total_cost_usd"] == 0.0
    assert summary["by_model"] == []
    assert summary["by_usage_source"] == []
