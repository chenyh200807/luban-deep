from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.outbox import LearnerStateOutbox


def _fetch_all_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            select id, user_id, event_type, payload_json, dedupe_key,
                   status, retry_count, created_at, last_error, next_attempt_at
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
    assert claimed[0].next_attempt_at

    rows = _fetch_all_rows(outbox.db_path)
    assert rows[0]["status"] == "processing"
    assert rows[0]["next_attempt_at"]

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


def test_claim_pending_recovers_stale_processing_items(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")
    queued = outbox.enqueue(
        user_id="student_demo",
        event_type="memory_event",
        payload_json={"event": 1},
        dedupe_key="memory:stale-processing",
    )
    assert outbox.claim_pending(limit=1)[0].id == queued.id

    expired_lease = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(outbox.db_path) as conn:
        conn.execute(
            """
            update learner_state_outbox
            set status = 'processing',
                next_attempt_at = ?
            where id = ?
            """,
            (expired_lease, queued.id),
        )

    reclaimed = outbox.claim_pending(limit=1)

    assert [item.id for item in reclaimed] == [queued.id]
    assert reclaimed[0].status == "processing"
    assert reclaimed[0].next_attempt_at != expired_lease


def test_claim_pending_recovers_legacy_processing_items_without_lease(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")
    queued = outbox.enqueue(
        user_id="student_demo",
        event_type="memory_event",
        payload_json={"event": 1},
        dedupe_key="memory:legacy-processing",
    )
    assert outbox.claim_pending(limit=1)[0].id == queued.id

    with sqlite3.connect(outbox.db_path) as conn:
        conn.execute(
            """
            update learner_state_outbox
            set status = 'processing',
                next_attempt_at = null
            where id = ?
            """,
            (queued.id,),
        )

    reclaimed = outbox.claim_pending(limit=1)

    assert [item.id for item in reclaimed] == [queued.id]


def test_claim_pending_skips_retry_backoff_items(tmp_path) -> None:
    outbox = LearnerStateOutbox(db_path=tmp_path / "outbox.db")
    first = outbox.enqueue(
        user_id="student_demo",
        event_type="summary_refresh",
        payload_json={"summary": "blocked"},
        dedupe_key="summary:blocked",
        created_at="2026-04-24T10:00:00+00:00",
    )
    second = outbox.enqueue(
        user_id="student_demo",
        event_type="summary_refresh",
        payload_json={"summary": "fresh"},
        dedupe_key="summary:fresh",
        created_at="2026-04-24T10:00:01+00:00",
    )

    failed = outbox.mark_failed(first.id, last_error="HTTP 409: foreign key violation")
    assert failed is not None
    assert failed.status == "pending"
    assert failed.next_attempt_at

    claimed = outbox.claim_pending(limit=10)

    assert [item.id for item in claimed] == [second.id]
