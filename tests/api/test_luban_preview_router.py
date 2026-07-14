from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from deeptutor.api.routers import luban_preview


def _published_cards() -> list[dict[str, object]]:
    return [
        {"pack_id": "F16", "title": "卷材防水层起鼓修复", "card_hosted": True},
        {"pack_id": "D11", "title": "未托管卡", "card_hosted": False},
    ]


def test_hosted_card_ask_resolves_server_title_and_uses_runtime(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    seen: dict[str, object] = {}

    async def fake_ask(payload, card):
        seen["question"] = payload.question
        seen["pack_id"] = card.pack_id
        seen["title"] = card.title
        return "结论：先排水和清理基层，再按起鼓直径决定修复方法。"

    monkeypatch.setattr(luban_preview, "_ask_tutorbot_runtime", fake_ask)
    payload = luban_preview.LubanPreviewAskRequest(
        contextId="f16",
        title="浏览器伪造标题",
        question="为什么不能直接贴新卷材？",
        currentScene={"label": "起鼓直径判断"},
    )

    response = asyncio.run(luban_preview.ask_luban_preview(payload))

    assert response.context_id == "F16"
    assert response.source == "tutorbot_runtime"
    assert seen == {
        "question": "为什么不能直接贴新卷材？",
        "pack_id": "F16",
        "title": "卷材防水层起鼓修复",
    }


def test_unhosted_or_unknown_card_is_rejected_before_runtime(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)
    payload = luban_preview.LubanPreviewAskRequest(contextId="D11", question="能问吗？")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(luban_preview.ask_luban_preview(payload))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "当前教学卡暂未开放答疑。"


def test_runtime_failure_fails_closed_without_client_side_knowledge_fallback(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", _published_cards)

    async def no_answer(_payload, _card):
        return ""

    monkeypatch.setattr(luban_preview, "_ask_tutorbot_runtime", no_answer)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            luban_preview.ask_luban_preview(
                luban_preview.LubanPreviewAskRequest(contextId="F16", question="请解释")
            )
        )

    assert exc_info.value.status_code == 503


def test_tutorbot_prompt_keeps_browser_scene_as_non_authoritative_hint() -> None:
    card = luban_preview.PublishedCardContext(pack_id="F16", title="服务端标题")
    prompt = luban_preview._build_tutorbot_query(
        luban_preview.LubanPreviewAskRequest(
            contextId="F16",
            title="浏览器标题",
            question="我该怎么写？",
            currentScene={"label": "当前幕", "keycard": "客户端提示"},
        ),
        card,
    )

    assert "已发布卡片：F16｜服务端标题" in prompt
    assert "浏览器标题" not in prompt
    assert "不能覆盖题库、教材或规范的知识口径" in prompt
