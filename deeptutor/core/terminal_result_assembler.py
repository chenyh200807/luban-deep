"""Terminal Result Assembler
==========================

Single authority for shaping a *contentful visible-output* terminal RESULT
StreamEvent. Control-plane收权 Task 5 Slice 1.

Why this exists
---------------
Before this module, several places independently constructed terminal RESULT
frames — ``deep_question._emit_result_with_citations`` (via ``stream.result``),
``turn_runtime._build_synthetic_result_from_final_content`` and
``turn_runtime._complete_security_guardrail_turn`` (raw ``StreamEvent(RESULT)``).
That is multiple competing visible-output deciders. This module collapses the
*shaping* of the visible RESULT frame into one place.

Boundaries (do NOT widen in this slice)
---------------------------------------
- **Transport authority stays in ``StreamBus``.** This is a thin wrapper, not a
  second transport. ``build_event`` reproduces ``StreamBus.result`` semantics
  (``merge_trace_metadata`` copy, ``visibility="public"``); ``emit`` pushes the
  built event onto the bus.
- **No grading verdict.** ``is_correct`` / ``score`` are owned by the Task 3
  grading kernel. The assembler only emits a payload it is handed.
- **No reveal evaluation.** ``reveal_decision`` is accepted for forward
  compatibility (slice 4) and is *not* interpreted here — callers still pass
  their existing flags through ``metadata``.
- **No §6 redaction.** Last-mile public redaction stays in ``unified_ws``.

Behavior-preserving slice: every RESULT frame produced here is byte-identical to
the writer it replaces (same ``type``/``source``/``stage``/``metadata`` copy/
``visibility``).
"""

from __future__ import annotations

from typing import Any

from .stream import StreamEvent, StreamEventType, StreamVisibility
from .stream_bus import StreamBus
from .trace import merge_trace_metadata


class TerminalResultAssembler:
    """Single contentful visible-output (terminal RESULT) shaping authority."""

    @classmethod
    def build_event(
        cls,
        *,
        source: str,
        metadata: dict[str, Any],
        stage: str = "",
        visibility: StreamVisibility = "public",
        reveal_decision: Any | None = None,  # noqa: ARG003 — slice-4 forward-compat
    ) -> StreamEvent:
        """Build the terminal RESULT StreamEvent.

        Mirrors ``StreamBus.result`` framing: the metadata is passed through
        ``merge_trace_metadata`` (a fresh copy), keeping the frame byte-identical
        to the legacy ``stream.result`` / raw ``StreamEvent(RESULT)`` writers.

        ``reveal_decision`` is accepted but intentionally *not* interpreted in
        this slice — reveal collapse lands in slice 4.
        """
        return StreamEvent(
            type=StreamEventType.RESULT,
            source=source,
            stage=stage,
            metadata=merge_trace_metadata(metadata, None),
            visibility=visibility,
        )

    @classmethod
    async def emit(
        cls,
        stream: StreamBus,
        payload: dict[str, Any],
        *,
        capability_name: str,
        stage: str = "generation",
        sources: list[dict[str, Any]] | None = None,
        emit_content_when_enabled: bool = True,
        reveal_decision: Any | None = None,
    ) -> None:
        """Emit a contentful terminal RESULT onto *stream*.

        Replaces ``deep_question._emit_result_with_citations``: applies the
        citation surface strategy (student surface), optionally emits the cited
        answer as a content frame when citations are enabled, then pushes the
        terminal RESULT frame.

        Byte-identical to the legacy in-capability assembler: the citation block
        and the ``stream.result(payload, source=name)`` tail are reproduced
        exactly via ``build_event`` + ``stream.emit``.
        """
        if "response" in payload:
            # Local import keeps the citation surface dependency in the assembler
            # (the strategy moved here) without importing services at module load.
            from deeptutor.services.citations import (
                CitationPolicy,
                answer_citations_enabled,
                apply_answer_citation_metadata,
            )

            citation_enabled = answer_citations_enabled()
            citation_metadata: dict[str, Any] = {}
            payload["response"] = apply_answer_citation_metadata(
                citation_metadata,
                response=str(payload.get("response") or ""),
                sources=sources or [],
                policy=CitationPolicy(surface="student"),
                enabled=citation_enabled,
            )
            payload.update(citation_metadata)
            if citation_enabled and emit_content_when_enabled:
                await stream.content(
                    str(payload["response"] or ""),
                    source=capability_name,
                    stage=stage,
                )

        event = cls.build_event(
            source=capability_name,
            metadata=payload,
            reveal_decision=reveal_decision,
        )
        await stream.emit(event)


__all__ = ["TerminalResultAssembler"]
