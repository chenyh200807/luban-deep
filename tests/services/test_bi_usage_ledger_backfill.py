from __future__ import annotations

import asyncio

from deeptutor.services.bi_service import BIService
from deeptutor.services.observability.usage_ledger import UsageLedger
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def test_bi_service_backfills_turn_result_cost_summaries_into_usage_ledger(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")
    service = BIService(session_store=store, usage_ledger=ledger)

    async def _prepare() -> None:
        session = await store.create_session(title="Backfill Session")
        await store.update_session_preferences(
            session["id"],
            {
                "source": "wx_miniprogram",
                "user_id": "u-backfill",
            },
        )
        turn = await store.create_turn(session["id"], capability="chat")
        await store.append_turn_event(
            turn["id"],
            {
                "type": "result",
                "content": "done",
                "metadata": {
                    "metadata": {
                        "cost_summary": {
                            "scope_id": "turn:backfill",
                            "total_input_tokens": 120,
                            "total_output_tokens": 30,
                            "total_tokens": 150,
                            "total_cost_usd": 0.12,
                            "estimated_input_tokens": 20,
                            "estimated_output_tokens": 10,
                            "estimated_total_tokens": 30,
                            "estimated_total_cost_usd": 0.03,
                            "usage_accuracy": "mixed",
                            "usage_sources": {"provider": 1, "tiktoken": 1},
                            "models": {"deepseek-v3.2": 2},
                        }
                    }
                },
            },
        )

    asyncio.run(_prepare())

    stats = asyncio.run(service.backfill_usage_ledger(days=3650, provider_name="dashscope"))
    totals = ledger.get_totals(start_ts=0, end_ts=9_999_999_999, provider_name="dashscope")
    repeated_stats = asyncio.run(service.backfill_usage_ledger(days=3650, provider_name="dashscope"))

    assert stats["scanned_result_events"] == 1
    assert stats["inserted_ledger_events"] == 2
    assert stats["inserted_measured_events"] == 1
    assert stats["inserted_estimated_events"] == 1
    assert totals.measured_total_tokens == 150
    assert totals.estimated_total_tokens == 30
    assert totals.total_cost == 0.15
    assert totals.events == 2
    assert repeated_stats["inserted_ledger_events"] == 0


def test_bi_service_backfill_skips_turns_already_recorded_in_live_ledger(tmp_path) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")
    ledger = UsageLedger(db_path=tmp_path / "llm_usage.db")
    service = BIService(session_store=store, usage_ledger=ledger)

    async def _prepare() -> str:
        session = await store.create_session(title="Existing Live Usage")
        turn = await store.create_turn(session["id"], capability="chat")
        await store.append_turn_event(
            turn["id"],
            {
                "type": "result",
                "content": "done",
                "metadata": {
                    "metadata": {
                        "cost_summary": {
                            "scope_id": "turn:existing",
                            "total_input_tokens": 100,
                            "total_output_tokens": 20,
                            "total_tokens": 120,
                            "total_cost_usd": 0.1,
                            "models": {"deepseek-v3.2": 1},
                        }
                    }
                },
            },
        )
        return turn["id"]

    turn_id = asyncio.run(_prepare())
    ledger.record_usage_event(
        usage_source="provider",
        usage_details={"input": 100.0, "output": 20.0, "total": 120.0},
        cost_details={"total": 0.1},
        model="deepseek-v3.2",
        metadata={"provider_name": "dashscope"},
        session_id="s-live",
        turn_id=turn_id,
        capability="chat",
        scope_id="turn:existing",
    )

    stats = asyncio.run(service.backfill_usage_ledger(days=3650, provider_name="dashscope"))
    totals = ledger.get_totals(start_ts=0, end_ts=9_999_999_999, provider_name="dashscope")

    assert stats["scanned_result_events"] == 1
    assert stats["inserted_ledger_events"] == 0
    assert stats["skipped_existing_turns"] == 1
    assert totals.total_tokens == 120
    assert totals.events == 1
