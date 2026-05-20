"""Regression: streaming CONTENT deltas must keep whitespace verbatim.

Previously _sanitize_public_terminal_event ran every CONTENT delta through
normalize_markdown_for_tutorbot(coerce_user_visible_answer(...)), which is a
paragraph-level transform. For per-token deltas it dropped pure-newline
deltas to "" and stripped leading/trailing whitespace, breaking ATX heading
and list parsing in the frontend markdown renderer.
"""

from __future__ import annotations

import pytest

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.turn_runtime import _sanitize_public_terminal_event


def _make_content_event(content: str) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.CONTENT,
        content=content,
        source="tutorbot",
        metadata={"call_kind": "llm_final_response"},
    )


@pytest.mark.parametrize("delta", ["\n", "\n\n", " ", "  \n  "])
def test_pure_whitespace_content_delta_is_preserved(delta: str) -> None:
    event = _make_content_event(delta)
    _sanitize_public_terminal_event(event, dict(event.metadata or {}))
    assert event.content == delta


def test_trailing_newline_in_content_delta_is_preserved() -> None:
    delta = "结论：\n"
    event = _make_content_event(delta)
    _sanitize_public_terminal_event(event, dict(event.metadata or {}))
    assert event.content == delta


def test_leading_newline_in_content_delta_is_preserved() -> None:
    delta = "\n### 一、基本原则"
    event = _make_content_event(delta)
    _sanitize_public_terminal_event(event, dict(event.metadata or {}))
    assert event.content == delta


def test_appended_deltas_round_trip_to_markdown_heading() -> None:
    deltas = [
        "位置的主要要求：\n",
        "\n",
        "### 一、基本原则",
        "\n",
        "\n",
        "施工缝应留置在 ",
    ]
    out: list[str] = []
    for delta in deltas:
        event = _make_content_event(delta)
        _sanitize_public_terminal_event(event, dict(event.metadata or {}))
        assert isinstance(event.content, str)
        out.append(event.content)
    joined = "".join(out)
    assert "\n\n### 一、基本原则" in joined
    assert "### 一、基本原则\n\n施工缝应留置在" in joined
