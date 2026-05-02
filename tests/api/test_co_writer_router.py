from __future__ import annotations

import importlib


co_writer_module = importlib.import_module("deeptutor.api.routers.co_writer")


def test_react_edit_tools_drop_web_search_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(co_writer_module, "is_web_search_runtime_available", lambda: False)

    assert co_writer_module._normalize_react_edit_tools(["rag", "web_search", "reason"]) == [
        "rag",
        "reason",
    ]


def test_react_edit_tools_allow_web_search_only_when_available(monkeypatch) -> None:
    monkeypatch.setattr(co_writer_module, "is_web_search_runtime_available", lambda: True)

    assert co_writer_module._normalize_react_edit_tools(["web_search"]) == ["web_search"]
