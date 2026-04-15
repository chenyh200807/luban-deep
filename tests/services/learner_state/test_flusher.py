from __future__ import annotations

import asyncio
import sqlite3

from deeptutor.services.learner_state.flusher import LearnerStateOutboxFlusher
from deeptutor.services.learner_state.outbox import LearnerStateOutbox


def _fetch_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            select id, user_id, event_type, payload_json, dedupe_key,
                   status, retry_count, created_at, last_error
            from learner_state_outbox
            order by created_at asc, id asc
            """
        ).fetchall()


class _FakeWriter:
    def __init__(self, *, fail_event_types: set[str] | None = None, fail_without_raise: set[str] | None = None):
        self.fail_event_types = fail_event_types or set()
        self.fail_without_raise = fail_without_raise or set()
        self.written: list[str] = []

    async def write(self, item) -> None:
        self.written.append(item.id)
        if item.event_type in self.fail_event_types:
            raise RuntimeError(f"boom:{item.event_type}")
        if item.event_type in self.fail_without_raise:
            class _Result:
                ok = False
                reason = f"nope:{item.event_type}"

            return _Result()


def test_flush_once_marks_success_and_failure(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")
    first = outbox.enqueue(
        user_id="student_demo",
        event_type="summary_refresh",
        payload_json={"summary": "ok"},
        dedupe_key="summary:1",
    )
    second = outbox.enqueue(
        user_id="student_demo",
        event_type="guide_completion",
        payload_json={"summary": "fail"},
        dedupe_key="guide:1",
    )
    writer = _FakeWriter(fail_event_types={"guide_completion"})
    flusher = LearnerStateOutboxFlusher(outbox, writer)

    result = asyncio.run(flusher.flush_once(limit=10))

    rows = _fetch_rows(outbox.db_path)
    assert result.claimed == 2
    assert result.sent == 1
    assert result.failed == 1
    assert writer.written == [first.id, second.id]
    assert rows[0]["status"] == "sent"
    assert rows[0]["retry_count"] == 0
    assert rows[1]["status"] == "pending"
    assert rows[1]["retry_count"] == 1
    assert rows[1]["last_error"] == "boom:guide_completion"


def test_flush_once_respects_limit_and_can_continue(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")
    for index in range(3):
        outbox.enqueue(
            user_id="student_demo",
            event_type="memory_event",
            payload_json={"index": index},
            dedupe_key=f"memory:{index}",
        )

    writer = _FakeWriter()
    flusher = LearnerStateOutboxFlusher(outbox, writer)

    first_pass = asyncio.run(flusher.flush_once(limit=2))
    second_pass = asyncio.run(flusher.flush_once(limit=2))

    rows = _fetch_rows(outbox.db_path)
    assert first_pass.claimed == 2
    assert first_pass.sent == 2
    assert first_pass.failed == 0
    assert second_pass.claimed == 1
    assert second_pass.sent == 1
    assert second_pass.failed == 0
    assert [row["status"] for row in rows] == ["sent", "sent", "sent"]
    assert writer.written == [row["id"] for row in rows]


def test_flush_once_marks_failed_when_writer_returns_ok_false(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")
    queued = outbox.enqueue(
        user_id="student_demo",
        event_type="summary_refresh",
        payload_json={"summary": "retry"},
        dedupe_key="summary:retry",
    )
    writer = _FakeWriter(fail_without_raise={"summary_refresh"})
    flusher = LearnerStateOutboxFlusher(outbox, writer)

    result = asyncio.run(flusher.flush_once(limit=10))

    rows = _fetch_rows(outbox.db_path)
    assert result.claimed == 1
    assert result.sent == 0
    assert result.failed == 1
    assert writer.written == [queued.id]
    assert rows[0]["status"] == "pending"
    assert rows[0]["retry_count"] == 1
    assert rows[0]["last_error"] == "nope:summary_refresh"
