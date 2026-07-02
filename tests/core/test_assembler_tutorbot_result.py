"""TerminalResultAssembler — tutorbot RESULT byte-identity (Task 5 Slice 3).

TutorBot is the *student-facing* conversational terminal RESULT. Two terminal
frames live in ``TutorBotCapability.run``:

1. The **main terminal** tail (``await stream.result(result_payload,
   source=self.name)`` at the end of ``run``), carrying the visible response plus
   the authority-gated ``presentation`` / ``question_followup_context`` /
   ``active_object`` blocks.
2. The lifecycle **degraded terminal** (the closure
   ``_emit_lifecycle_terminal_response``'s tail ``await stream.result(...)``),
   used for exam-catalog / clarification / fast lifecycle responses.

Slice 3 migrates *both* tails onto the single contentful visible-output authority
(``TerminalResultAssembler.build_event`` + ``stream.emit``) — **byte-identical**.

These tests pin two things:

1. **Byte-identity** — the assembler-built tutorbot RESULT frame equals, byte for
   byte (``type``/``source``/``stage``/``visibility``/``metadata`` via
   ``merge_trace_metadata``), the pre-migration ``stream.result(payload)`` frame,
   for realistic main + lifecycle payloads carrying reveal flags, presentation,
   and question_followup_context.

2. **Wiring** — ``run`` (and its nested ``_emit_lifecycle_terminal_response``
   closure) actually route their terminal frames through
   ``TerminalResultAssembler`` (not a bare ``stream.result``). RED before
   migration.

The slice does NOT touch reveal evaluation: ``reveal_answers`` /
``reveal_explanations`` / ``reveal_reference`` and the ``presentation`` /
``question_followup_context`` blocks are produced by the existing capability
logic and merely pass through unchanged via ``metadata``. Reveal collapse is
slice 4.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest

from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.terminal_result_assembler import TerminalResultAssembler
from deeptutor.core.trace import merge_trace_metadata


def _main_payload() -> dict[str, Any]:
    """A realistic main-terminal ``result_payload`` from ``run``.

    Carries the visible response, reveal flags, the authority-gated
    ``presentation`` block, and the ``question_followup_context`` /
    ``active_object`` continuity blocks — all of which must survive
    byte-identical through the assembler.
    """
    return {
        "response": "我们来一步步看这道题。",
        "bot_id": "tutorbot",
        "execution_engine": "tutorbot_runtime",
        "authority_applied": True,
        "exact_question": {"question_id": "q-77"},
        "reveal_answers": False,
        "reveal_explanations": False,
        "reveal_reference": False,
        "presentation": {"layout": "canonical", "blocks": [{"kind": "stem"}]},
        "question_followup_context": {
            "question_id": "q-77",
            "options": ["A", "B", "C", "D"],
        },
        "active_object": {"object_type": "question", "object_ref": "q-77"},
        "suspended_object_stack": [],
    }


def _lifecycle_payload() -> dict[str, Any]:
    """A realistic lifecycle degraded-terminal ``result_payload``.

    Mirrors ``_emit_lifecycle_terminal_response``'s payload shape: a plain
    visible response with reveal flags forced off and no authority blocks.
    """
    return {
        "response": "这是本科目的考点目录：……",
        "bot_id": "tutorbot",
        "execution_engine": "tutorbot_runtime",
        "authority_applied": False,
        "exact_question": {},
        "rag_rounds": [],
        "rag_saturation": {},
        "execution_path": "tutorbot_exam_catalog_query",
        "exact_fast_path_hit": False,
        "actual_tool_rounds": 0,
        "reveal_answers": False,
        "reveal_explanations": False,
    }


# ---------------------------------------------------------------------------
# 1. Byte-identity: assembler-built RESULT == legacy stream.result frame
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_main_result_build_event_byte_identical_to_stream_result() -> None:
    """``build_event`` reproduces ``stream.result(payload, source=name)`` exactly
    for the main tutorbot terminal payload — reveal flags + presentation +
    question_followup_context intact."""
    payload = _main_payload()

    # Golden: the pre-migration terminal tail.
    golden_bus = StreamBus()
    await golden_bus.result(dict(payload), source="tutorbot")
    golden_events = list(golden_bus._history)  # type: ignore[attr-defined]
    assert len(golden_events) == 1
    golden = golden_events[0]

    # Assembler path (what run() calls after migration).
    event = TerminalResultAssembler.build_event(
        source="tutorbot",
        metadata=dict(payload),
    )

    assert event.type == StreamEventType.RESULT
    assert event.to_dict() | {"timestamp": 0} == golden.to_dict() | {"timestamp": 0}
    # Reveal flags pass through unchanged (slice 3 does NOT collapse reveal).
    assert event.metadata["reveal_answers"] is False
    assert event.metadata["reveal_explanations"] is False
    assert event.metadata["reveal_reference"] is False
    # Authority-gated blocks survive byte-identical.
    assert event.metadata["presentation"] == payload["presentation"]
    assert event.metadata["question_followup_context"] == payload[
        "question_followup_context"
    ]
    assert event.metadata["active_object"] == payload["active_object"]
    # merge_trace_metadata copy semantics: fresh dict, not aliased.
    assert event.metadata == merge_trace_metadata(payload, None)


@pytest.mark.asyncio
async def test_lifecycle_result_build_event_byte_identical_to_stream_result() -> None:
    """``build_event`` reproduces ``stream.result(payload, source=name)`` exactly
    for the lifecycle degraded-terminal payload."""
    payload = _lifecycle_payload()

    golden_bus = StreamBus()
    await golden_bus.result(dict(payload), source="tutorbot")
    golden_events = list(golden_bus._history)  # type: ignore[attr-defined]
    assert len(golden_events) == 1
    golden = golden_events[0]

    event = TerminalResultAssembler.build_event(
        source="tutorbot",
        metadata=dict(payload),
    )

    assert event.type == StreamEventType.RESULT
    assert event.to_dict() | {"timestamp": 0} == golden.to_dict() | {"timestamp": 0}
    assert event.metadata["reveal_answers"] is False
    assert event.metadata["reveal_explanations"] is False
    assert event.metadata["execution_path"] == "tutorbot_exam_catalog_query"
    assert event.metadata == merge_trace_metadata(payload, None)


# ---------------------------------------------------------------------------
# 2. Wiring (RED before migration): both tails route through the assembler
# ---------------------------------------------------------------------------
def test_tutorbot_run_terminal_frames_go_through_assembler() -> None:
    """``run`` (and its nested ``_emit_lifecycle_terminal_response`` closure) must
    emit their terminal RESULT frames via ``TerminalResultAssembler`` (not a bare
    ``stream.result``). RED before slice-3 migration."""
    from deeptutor.capabilities.tutorbot import TutorBotCapability

    src = inspect.getsource(TutorBotCapability.run)
    tree = ast.parse(src.lstrip())

    calls_assembler = False
    calls_stream_result = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            # TerminalResultAssembler.build_event(...) / .emit(...)
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "TerminalResultAssembler"
            ):
                calls_assembler = True
            # stream.result(...)
            if (
                func.attr == "result"
                and isinstance(func.value, ast.Name)
                and func.value.id == "stream"
            ):
                calls_stream_result = True

    assert calls_assembler, (
        "TutorBotCapability.run must emit its terminal RESULT frames via "
        "TerminalResultAssembler (single visible-output authority)."
    )
    assert not calls_stream_result, (
        "TutorBotCapability.run must NOT call stream.result directly after the "
        "slice-3 migration (it competes with the assembler authority); this "
        "covers both the main tail and the _emit_lifecycle_terminal_response "
        "closure."
    )
