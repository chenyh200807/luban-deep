from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from deeptutor.services.learner_state.outbox import LearnerStateOutbox, LearnerStateOutboxItem


@runtime_checkable
class LearnerStateOutboxWriter(Protocol):
    def write(self, item: LearnerStateOutboxItem) -> Any: ...


@dataclass(frozen=True)
class LearnerStateOutboxFlushResult:
    claimed: int
    sent: int
    failed: int


class LearnerStateOutboxFlusher:
    """Single-pass flusher for learner-state durable outbox items."""

    def __init__(
        self,
        outbox: LearnerStateOutbox,
        writer: LearnerStateOutboxWriter | Any,
    ) -> None:
        self._outbox = outbox
        self._writer = writer

    async def _write_item(self, item: LearnerStateOutboxItem) -> Any:
        writer = self._writer
        if hasattr(writer, "write"):
            result = writer.write(item)
        elif hasattr(writer, "write_item"):
            result = writer.write_item(item)
        else:
            raise TypeError("writer must define write(item) or write_item(item)")
        if inspect.isawaitable(result):
            result = await result
        if getattr(result, "ok", None) is False:
            reason = str(getattr(result, "reason", "") or "").strip()
            raise RuntimeError(reason or "writer returned ok=False")
        return result

    async def flush_once(self, *, limit: int = 20) -> LearnerStateOutboxFlushResult:
        claimed_items = self._outbox.claim_pending(limit=limit)
        sent = 0
        failed = 0

        for item in claimed_items:
            try:
                await self._write_item(item)
                self._outbox.mark_sent(item.id)
                sent += 1
            except Exception as exc:
                self._outbox.mark_failed(item.id, last_error=str(exc))
                failed += 1

        return LearnerStateOutboxFlushResult(
            claimed=len(claimed_items),
            sent=sent,
            failed=failed,
        )


__all__ = [
    "LearnerStateOutboxFlusher",
    "LearnerStateOutboxFlushResult",
    "LearnerStateOutboxWriter",
]
