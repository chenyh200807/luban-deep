"""Phase 3.1 — add_record 按 metadata.card_type 分流到 NotebookCardService(durable)。

带 card_type → 走 NotebookCardService.save_card，legacy notebook_manager.add_record 不被调用；
不带 card_type → 走 legacy，NotebookCardService 不被调用。handler 级测试(不起 HTTP 栈)。
"""
from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from deeptutor.api.routers import notebook as nb_router
from deeptutor.services.notebook_card.store import OptimisticConcurrencyError


def _request(card_type: str | None):
    metadata = {"card_type": card_type} if card_type else {}
    return nb_router.AddRecordRequest(
        notebook_ids=["nb_1"], record_type="chat", title="责任主体",
        user_query="记一下", output="...", metadata=metadata,
    )


@pytest.mark.unit
def test_card_type_routes_to_card_service_not_legacy(monkeypatch):
    calls = {"card": 0, "legacy": 0}

    class _CardSvc:
        async def save_card(self, **_k):
            calls["card"] += 1
            return {"note_id": "note_abc", "mastery_effect": "none"}

    monkeypatch.setattr(nb_router, "get_notebook_card_service", lambda: _CardSvc())
    monkeypatch.setattr(nb_router.notebook_manager, "add_record",
                        lambda **_k: calls.__setitem__("legacy", calls["legacy"] + 1) or {"record": {}, "added_to_notebooks": []})

    out = asyncio.run(nb_router.add_record(_request("scoring_card"), current_user=SimpleNamespace(user_id="u1")))
    assert out["note_id"] == "note_abc"
    assert calls["card"] == 1 and calls["legacy"] == 0   # 分流：card 路径，legacy 不动


@pytest.mark.unit
def test_stable_card_entry_routes_to_card_service(monkeypatch):
    entry = importlib.import_module("deeptutor.api.routers.notebook_card_entry")
    calls = []

    class _CardSvc:
        async def save_card(self, **kwargs):
            calls.append(kwargs)
            return {"note_id": "note_stable", "mastery_effect": "none"}

    monkeypatch.setattr(entry, "get_notebook_card_service", lambda: _CardSvc())

    out = asyncio.run(
        entry.add_record(
            entry.AddRecordRequest(
                notebook_ids=[],
                record_type="chat",
                title="答疑学习卡",
                user_query="保存答疑学习卡",
                output="",
                metadata={"card_type": "review_note"},
            ),
            current_user=SimpleNamespace(user_id="u1"),
        )
    )

    assert out["note_id"] == "note_stable"
    assert calls == [
        {
            "user_id": "u1",
            "subject_id": "",
            "source_bot_id": "",
            "card_type": "review_note",
            "source_type": "manual",
            "source_ref": {},
            "evidence_event_ids": [],
            "title": "答疑学习卡",
            "raw_user_content": "保存答疑学习卡",
            "ai_enhanced_content": {},
        }
    ]


@pytest.mark.unit
def test_stable_card_entry_rejects_non_card_request():
    entry = importlib.import_module("deeptutor.api.routers.notebook_card_entry")

    with pytest.raises(entry.HTTPException) as exc:
        asyncio.run(
            entry.add_record(
                entry.AddRecordRequest(
                    notebook_ids=["nb_1"],
                    record_type="chat",
                    title="普通笔记",
                    user_query="记一下",
                    output="",
                    metadata={},
                ),
                current_user=SimpleNamespace(user_id="u1"),
            )
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "notebook_card_type_required"


@pytest.mark.unit
def test_no_card_type_uses_legacy(monkeypatch):
    calls = {"card": 0, "legacy": 0}

    class _CardSvc:
        async def save_card(self, **_k):
            calls["card"] += 1
            return {"note_id": "x"}

    monkeypatch.setattr(nb_router, "get_notebook_card_service", lambda: _CardSvc())
    monkeypatch.setattr(nb_router.notebook_manager, "add_record",
                        lambda **_k: calls.__setitem__("legacy", calls["legacy"] + 1) or {"record": {}, "added_to_notebooks": []})

    async def _fake_summary(_req):
        return "s"
    monkeypatch.setattr(nb_router, "_build_record_summary", _fake_summary)

    asyncio.run(nb_router.add_record(_request(None), current_user=SimpleNamespace(user_id="u1")))
    assert calls["legacy"] == 1 and calls["card"] == 0   # 无 card_type：legacy，card 不动


@pytest.mark.unit
def test_update_card_handler_maps_stale_version_to_409(monkeypatch):
    class _CardSvc:
        async def update_card(self, **_k):
            raise OptimisticConcurrencyError("stale")

    monkeypatch.setattr(nb_router, "get_notebook_card_service", lambda: _CardSvc())

    with pytest.raises(nb_router.HTTPException) as exc:
        asyncio.run(nb_router.update_notebook_card(
            "note_abc",
            nb_router.UpdateNotebookCardRequest(expected_version=1, title="新标题"),
            current_user=SimpleNamespace(user_id="u1"),
        ))

    assert exc.value.status_code == 409
    assert exc.value.detail == "notebook_card_version_conflict"


@pytest.mark.unit
def test_delete_card_handler_archives_via_card_service(monkeypatch):
    calls = []

    class _CardSvc:
        async def delete_card(self, **kwargs):
            calls.append(kwargs)
            return {"note_id": kwargs["note_id"], "archived_at": "2026-06-09T00:00:00+08:00"}

    monkeypatch.setattr(nb_router, "get_notebook_card_service", lambda: _CardSvc())

    out = asyncio.run(nb_router.delete_notebook_card(
        "note_abc",
        nb_router.DeleteNotebookCardRequest(expected_version=3),
        current_user=SimpleNamespace(user_id="u1"),
    ))

    assert out["success"] is True
    assert calls == [{"user_id": "u1", "note_id": "note_abc", "expected_version": 3}]
