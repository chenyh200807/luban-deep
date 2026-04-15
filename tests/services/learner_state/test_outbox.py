from __future__ import annotations

import sqlite3

from deeptutor.services.learner_state.outbox import LearnerStateOutbox


def _fetch_all_rows(db_path):
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


def test_enqueue_deduplicates_by_dedupe_key(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")

    first = outbox.enqueue(
        user_id="student_demo",
        event_type="guide_completion",
        payload_json={"guide_id": "guide_1", "summary": "done"},
        dedupe_key="guide:guide_1:completion",
    )
    second = outbox.enqueue(
        user_id="student_demo",
        event_type="guide_completion",
        payload_json={"guide_id": "guide_1", "summary": "updated"},
        dedupe_key="guide:guide_1:completion",
    )

    rows = _fetch_all_rows(outbox.db_path)
    assert len(rows) == 1
    assert first.id == second.id
    assert first.status == "pending"
    assert second.status == "pending"
    assert rows[0]["event_type"] == "guide_completion"
    assert rows[0]["status"] == "pending"
    assert rows[0]["retry_count"] == 0


def test_claim_pending_marks_processing_and_failure_returns_to_pending(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")

    queued = outbox.enqueue(
        user_id="student_demo",
        event_type="memory_event",
        payload_json={"event": 1},
        dedupe_key="memory:1",
    )

    claimed = outbox.claim_pending(limit=1)
    assert len(claimed) == 1
    assert claimed[0].id == queued.id
    assert claimed[0].status == "processing"

    rows = _fetch_all_rows(outbox.db_path)
    assert rows[0]["status"] == "processing"

    sent = outbox.mark_sent(queued.id)
    assert sent is not None
    assert sent.status == "sent"
    assert sent.last_error is None

    failed = outbox.mark_failed(queued.id, last_error="network error")
    assert failed is not None
    assert failed.status == "pending"
    assert failed.retry_count == 1
    assert failed.last_error == "network error"

    rows = _fetch_all_rows(outbox.db_path)
    assert rows[0]["status"] == "pending"
    assert rows[0]["retry_count"] == 1
    assert rows[0]["last_error"] == "network error"
