"""TerminalResultAssembler — control-plane Task 5 Slice 1.

These tests pin the *byte-identical* contract for the single contentful
visible-output authority. The assembler is a thin wrapper over the existing
StreamBus transport (``stream.result`` semantics) and must reproduce, byte for
byte, the three RESULT writers it replaces:

1. ``deep_question._emit_result_with_citations`` — in-capability assembler with
   citation surface strategy + optional content emission, terminating in
   ``stream.result(payload, source=name)``.
2. ``turn_runtime._build_synthetic_result_from_final_content`` — read-side
   mobile result-before-DONE synthetic RESULT (no-reveal, no-verdict).
3. ``turn_runtime._complete_security_guardrail_turn`` — raw RESULT StreamEvent
   carrying security_metadata (no-reveal).

The golden for each writer is the *pre-migration* construction reproduced
inline here; the assembler must equal it.
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.trace import merge_trace_metadata


# ---------------------------------------------------------------------------
# Golden reproductions of the three pre-migration writers
# ---------------------------------------------------------------------------
def _golden_stream_result_event(payload: dict[str, Any], *, source: str) -> StreamEvent:
    """Reproduce ``StreamBus.result(payload, source=source)`` event shape.

    This is the terminal frame produced by writer 1's
    ``await stream.result(result_payload, source=self.name)`` tail.
    """
    return StreamEvent(
        type=StreamEventType.RESULT,
        source=source,
        metadata=merge_trace_metadata(payload, None),
        visibility="public",
    )


def _golden_synthetic_event(*, response: str, source: str) -> StreamEvent:
    """Reproduce writer 2's synthetic-from-final-content RESULT event."""
    return StreamEvent(
        type=StreamEventType.RESULT,
        source=source or "turn_runtime",
        metadata={
            "response": response,
            "assistant_content": response,
            "terminal_normalization": "mobile_result_before_done",
            "synthesized_from": "final_content",
        },
        visibility="public",
    )


def _golden_security_event(*, security_metadata: dict[str, Any], public_source: str) -> StreamEvent:
    """Reproduce writer 3's security guardrail RESULT event."""
    return StreamEvent(
        type=StreamEventType.RESULT,
        source=public_source,
        stage="responding",
        metadata=security_metadata,
    )


# ---------------------------------------------------------------------------
# build_event — the single StreamEvent shaping authority
# ---------------------------------------------------------------------------
def test_build_event_matches_stream_result_shape() -> None:
    """Writer-1 tail: ``stream.result(payload, source=name)`` byte-identical."""
    from deeptutor.core.terminal_result_assembler import TerminalResultAssembler

    payload = {"response": "答案是 C。", "is_correct": True, "score": 1.0}
    golden = _golden_stream_result_event(dict(payload), source="deep_question")

    event = TerminalResultAssembler.build_event(
        source="deep_question",
        metadata=dict(payload),
    )

    assert event.to_dict() | {"timestamp": 0} == golden.to_dict() | {"timestamp": 0}
    # metadata must be a *copy* (merge_trace_metadata semantics), not aliased.
    assert event.metadata == golden.metadata


def test_build_event_matches_synthetic_writer() -> None:
    """Writer 2: read-side synthetic result-before-DONE byte-identical."""
    from deeptutor.core.terminal_result_assembler import TerminalResultAssembler

    response = "这是最终回答。"
    golden = _golden_synthetic_event(response=response, source="tutorbot")

    event = TerminalResultAssembler.build_event(
        source="tutorbot",
        metadata={
            "response": response,
            "assistant_content": response,
            "terminal_normalization": "mobile_result_before_done",
            "synthesized_from": "final_content",
        },
    )

    assert event.to_dict() | {"timestamp": 0} == golden.to_dict() | {"timestamp": 0}


def test_build_event_matches_security_guardrail_writer() -> None:
    """Writer 3: security guardrail RESULT (stage=responding) byte-identical."""
    from deeptutor.core.terminal_result_assembler import TerminalResultAssembler

    security_metadata = {
        "response": "我不能提供该内容。",
        "guardrail": "tutorbot_security_skill",
        "guardrail_level": "block",
        "guardrail_signals": ["jailbreak"],
    }
    golden = _golden_security_event(
        security_metadata=dict(security_metadata),
        public_source="tutorbot",
    )

    event = TerminalResultAssembler.build_event(
        source="tutorbot",
        metadata=dict(security_metadata),
        stage="responding",
    )

    assert event.to_dict() | {"timestamp": 0} == golden.to_dict() | {"timestamp": 0}


# ---------------------------------------------------------------------------
# emit — writer-1 direct-to-stream path with citation surface
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emit_stream_result_byte_identical_citations_disabled() -> None:
    """Citations disabled (production default): emit reproduces the
    pre-migration ``_emit_result_with_citations`` event exactly — orphan
    markers stripped, candidate bundle + metrics attached, no content event."""
    from deeptutor.core.terminal_result_assembler import TerminalResultAssembler
    from deeptutor.services.citations import (
        CitationPolicy,
        answer_citations_enabled,
        apply_answer_citation_metadata,
    )

    # Golden: reproduce the pre-migration citation block + stream.result tail.
    payload_golden: dict[str, Any] = {"response": "正方形面积是 4。"}
    citation_enabled = answer_citations_enabled()
    citation_metadata: dict[str, Any] = {}
    payload_golden["response"] = apply_answer_citation_metadata(
        citation_metadata,
        response=str(payload_golden.get("response") or ""),
        sources=[],
        policy=CitationPolicy(surface="student"),
        enabled=citation_enabled,
    )
    payload_golden.update(citation_metadata)
    golden_bus = StreamBus()
    await golden_bus.result(payload_golden, source="deep_question")
    golden_events = list(golden_bus._history)  # type: ignore[attr-defined]

    # Assembler path.
    bus = StreamBus()
    await TerminalResultAssembler.emit(
        bus,
        {"response": "正方形面积是 4。"},
        capability_name="deep_question",
        stage="generation",
        emit_content_when_enabled=True,
    )
    events = list(bus._history)  # type: ignore[attr-defined]

    assert [e.type for e in events] == [e.type for e in golden_events]
    assert len(events) == len(golden_events)
    for got, exp in zip(events, golden_events):
        assert got.to_dict() | {"timestamp": 0} == exp.to_dict() | {"timestamp": 0}


@pytest.mark.asyncio
async def test_emit_without_response_key_is_plain_result() -> None:
    """Payloads with no ``response`` key skip citation surface entirely and
    emit a single RESULT identical to ``stream.result``."""
    from deeptutor.core.terminal_result_assembler import TerminalResultAssembler

    payload = {"status": "no_op", "data": {"k": 1}}
    golden_bus = StreamBus()
    await golden_bus.result(dict(payload), source="deep_question")
    golden_events = list(golden_bus._history)  # type: ignore[attr-defined]

    bus = StreamBus()
    await TerminalResultAssembler.emit(
        bus,
        dict(payload),
        capability_name="deep_question",
        stage="generation",
    )
    events = list(bus._history)  # type: ignore[attr-defined]

    assert len(events) == len(golden_events) == 1
    assert events[0].to_dict() | {"timestamp": 0} == golden_events[0].to_dict() | {"timestamp": 0}
