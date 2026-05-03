from __future__ import annotations

import pytest

from deeptutor.tutorbot.agent.tools.web import WebSearchTool


@pytest.mark.asyncio
async def test_tutorbot_web_search_tool_uses_central_search_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_web_search(query: str, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return {
            "provider": "searxng",
            "answer": "2026年一级建造师考试时间为9月12日、13日。",
            "citations": [{"title": "官方计划", "url": "https://example.gov/plan.pdf"}],
            "search_results": [
                {
                    "title": "2026年度专业技术人员职业资格考试工作计划",
                    "url": "https://example.gov/plan.pdf",
                    "content": "建造师（一级）：9月12日、13日",
                }
            ],
        }

    monkeypatch.setattr("deeptutor.services.search.web_search", fake_web_search)

    tool = WebSearchTool()
    result = await tool.execute("2026一建考试时间", count=3)
    trace = tool.consume_trace_metadata()

    assert captured["query"] == "2026一建考试时间"
    assert captured["kwargs"] == {"max_results": 3}
    assert "Provider: searxng" in result
    assert "9月12日、13日" in result
    assert trace == {"provider": "searxng", "citations": 1, "search_results": 1}


@pytest.mark.asyncio
async def test_tutorbot_web_search_tool_fails_closed_without_duckduckgo_fallback(
    monkeypatch,
) -> None:
    def failing_web_search(query: str, **kwargs):
        raise ValueError("searxng requires base_url")

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("DuckDuckGo fallback must not be called")

    monkeypatch.setattr("deeptutor.services.search.web_search", failing_web_search)

    tool = WebSearchTool()
    monkeypatch.setattr(tool, "_search_duckduckgo", fail_if_called)
    result = await tool.execute("2026一建考试时间")

    assert result == "Error: web_search failed (searxng requires base_url)"
    assert tool.consume_trace_metadata() is None
