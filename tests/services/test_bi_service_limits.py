from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import deeptutor.services.bi_service as bi_service_module
from deeptutor.services.bi_service import BIService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class _QuietMemberService:
    def get_dashboard(self, days: int = 30) -> dict[str, object]:
        return {
            "total_count": 0,
            "active_count": 0,
            "expiring_soon_count": 0,
            "new_today_count": 0,
            "churn_risk_count": 0,
            "health_score": 100,
            "auto_renew_coverage": 100,
            "recommendations": [],
        }

    def list_members(self, page: int = 1, page_size: int = 200, **_: object) -> dict[str, object]:
        return {"items": [], "page": page, "page_size": page_size, "pages": 1, "total": 0}


@pytest.fixture
def store(tmp_path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(db_path=tmp_path / "bi-limits.db")


def test_bi_context_loader_caps_each_collection(
    monkeypatch: pytest.MonkeyPatch,
    store: SQLiteSessionStore,
) -> None:
    monkeypatch.setattr(bi_service_module, "_BI_CONTEXT_ROW_LIMIT", 2)
    service = BIService(session_store=store, member_service=_QuietMemberService())

    async def _seed() -> None:
        for index in range(3):
            session = await store.create_session(title=f"Session {index}", session_id=f"session_{index}")
            await store.update_session_preferences(
                session["id"],
                {
                    "source": "wx_miniprogram",
                    "user_id": f"user_{index}",
                },
            )
            turn = await store.create_turn(session["id"], capability="chat")
            await store.append_turn_event(
                turn["id"],
                {
                    "type": "tool_call",
                    "content": "rag",
                    "metadata": {"args": {"query": f"q_{index}"}},
                },
            )
            await store.append_turn_event(
                turn["id"],
                {
                    "type": "result",
                    "content": "done",
                    "metadata": {"cost_summary": {"total_tokens": index + 1, "total_cost_usd": 0.001}},
                },
            )
            await store.update_turn_status(turn["id"], "completed")
            await store.upsert_notebook_entries(
                session["id"],
                [
                    {
                        "question_id": f"q_{index}",
                        "question": f"Question {index}",
                        "question_type": "choice",
                        "is_correct": False,
                    }
                ],
            )

    asyncio.run(_seed())
    context = asyncio.run(service._load_context_since(0.0))

    assert len(context.sessions) == 2
    assert len(context.turns) == 2
    assert len(context.result_events) == 2
    assert len(context.tool_events) == 2
    assert len(context.notebook_entries) == 2
    assert set(context.truncated_collections) == {
        "sessions",
        "turns",
        "result_events",
        "tool_events",
        "notebook_entries",
    }
