"""TerminalResultAssembler — grading RESULT byte-identity (Task 5 Slice 2).

deep_question grading is the *student-facing verdict* terminal RESULT. Slice 2
migrates ``deep_question._emit_grading_result``'s terminal tail
(``await stream.result(result_payload, source=self.name)``) onto the single
contentful visible-output authority (``TerminalResultAssembler.build_event`` +
``stream.emit``) — **byte-identical**.

These tests pin two things:

1. **Byte-identity** — the assembler-built grading RESULT frame equals, byte for
   byte (``type``/``source``/``stage``/``visibility``/``metadata`` via
   ``merge_trace_metadata``), the pre-migration ``stream.result(payload)`` frame,
   for a realistic grading payload carrying ``is_correct``/``score``/
   ``diagnosis``/citation/reveal fields.

2. **Wiring** — ``_emit_grading_result`` actually routes its terminal frame
   through ``TerminalResultAssembler`` (not a bare ``stream.result``). This is the
   RED assertion before migration.

The slice does NOT touch the grading verdict (``is_correct``/``score``/
``diagnosis`` are handed in by the grading kernel) nor collapse reveal (existing
flags pass through unchanged via ``metadata``).
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


def _grading_payload() -> dict[str, Any]:
    """A realistic deep_question grading ``result_payload``.

    Carries the student-facing verdict (is_correct/score/diagnosis), citation
    surface fields, and reveal flags — all of which must survive byte-identical
    through the assembler.
    """
    return {
        "response": "## 📊 阅卷结论\n你的作答正确。",
        "mode": "grading",
        "question_id": "q-123",
        "user_answer": "C",
        "is_correct": True,
        "score": 1.0,
        "diagnosis": "概念掌握牢固",
        "answer_citations": [{"index": 1, "title": "教材 §3.2"}],
        "reveal_reference": False,
        "construction_grading_result": {"node_code": "kc:foo", "score": 1.0},
        "grading_explanation_grounded": True,
    }


# ---------------------------------------------------------------------------
# 1. Byte-identity: assembler-built grading RESULT == legacy stream.result frame
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_grading_result_build_event_byte_identical_to_stream_result() -> None:
    """``build_event`` reproduces ``stream.result(payload, source=name)`` exactly
    for a grading verdict payload — verdict + citation + reveal fields intact."""
    payload = _grading_payload()

    # Golden: the pre-migration terminal tail.
    golden_bus = StreamBus()
    await golden_bus.result(dict(payload), source="deep_question")
    golden_events = list(golden_bus._history)  # type: ignore[attr-defined]
    assert len(golden_events) == 1
    golden = golden_events[0]

    # Assembler path (what _emit_grading_result calls after migration).
    event = TerminalResultAssembler.build_event(
        source="deep_question",
        metadata=dict(payload),
    )

    assert event.type == StreamEventType.RESULT
    assert event.to_dict() | {"timestamp": 0} == golden.to_dict() | {"timestamp": 0}
    # Verdict fields survive byte-identical (kernel owns the values; assembler
    # only emits — it must not drop or mutate them).
    assert event.metadata["is_correct"] is True
    assert event.metadata["score"] == 1.0
    assert event.metadata["diagnosis"] == "概念掌握牢固"
    assert event.metadata["answer_citations"] == [{"index": 1, "title": "教材 §3.2"}]
    # Reveal flag passes through unchanged (slice 2 does NOT collapse reveal).
    assert event.metadata["reveal_reference"] is False
    # merge_trace_metadata copy semantics: metadata is a fresh dict, not aliased.
    assert event.metadata == merge_trace_metadata(payload, None)


# ---------------------------------------------------------------------------
# 2. Wiring (RED before migration): _emit_grading_result routes through assembler
# ---------------------------------------------------------------------------
def test_emit_grading_result_terminal_frame_goes_through_assembler() -> None:
    """The grading terminal frame must be emitted via ``TerminalResultAssembler``
    (not a bare ``stream.result``). RED before slice-2 migration."""
    from deeptutor.capabilities.deep_question import DeepQuestionCapability

    src = inspect.getsource(DeepQuestionCapability._emit_grading_result)
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
        "_emit_grading_result must emit its terminal RESULT via "
        "TerminalResultAssembler (single visible-output authority)."
    )
    assert not calls_stream_result, (
        "_emit_grading_result must NOT call stream.result directly after the "
        "slice-2 migration (it competes with the assembler authority)."
    )
