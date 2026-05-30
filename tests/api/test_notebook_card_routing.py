"""Phase 3.1 — add_record 按 metadata.card_type 分流到 NotebookCardService(durable)。

带 card_type → 走 NotebookCardService.save_card，legacy notebook_manager.add_record 不被调用；
不带 card_type → 走 legacy，NotebookCardService 不被调用。handler 级测试(不起 HTTP 栈)。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from deeptutor.api.routers import notebook as nb_router


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
