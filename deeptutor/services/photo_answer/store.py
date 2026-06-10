"""SQLite persistence for photo-answer sessions, pages, jobs and OCR results.

Follows the project's plain-sqlite3 store pattern
(deeptutor/services/observability/product_behavior_store.py). All money
columns are micros. Durable job rows + idempotency keys + leases implement
plan §6 / Codex C3: paid OCR work must never live only in process memory.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from deeptutor.services.photo_answer.models import (
    DEFAULT_DAILY_SESSION_LIMIT,
    HARD_CAP_MICROS,
    SOFT_CAP_MICROS,
    DailyQuotaExceeded,
    assert_transition,
)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class PhotoAnswerStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists photo_answer_sessions (
                  id text primary key,
                  user_id text not null,
                  question_id text not null,
                  question_stem text not null default '',
                  status text not null default 'created',
                  page_count integer not null default 0,
                  cost_budget_soft_micros integer not null,
                  cost_budget_hard_micros integer not null,
                  day_key text not null,
                  created_at real not null
                );
                create index if not exists idx_pa_sessions_user_day
                  on photo_answer_sessions(user_id, day_key);

                create table if not exists photo_answer_pages (
                  id text primary key,
                  session_id text not null references photo_answer_sessions(id),
                  page_index integer not null,
                  image_ref text not null,
                  content_hash text not null default '',
                  is_duplicate integer not null default 0,
                  quality_json text not null default '{}',
                  created_at real not null,
                  unique(session_id, page_index)
                );

                create table if not exists photo_answer_jobs (
                  id text primary key,
                  session_id text not null references photo_answer_sessions(id),
                  idempotency_key text not null,
                  job_version integer not null,
                  status text not null default 'pending',
                  lease_until real not null default 0,
                  attempt_count integer not null default 0,
                  created_at real not null,
                  finished_at real,
                  unique(session_id, idempotency_key)
                );

                create table if not exists photo_answer_ocr_results (
                  id text primary key,
                  job_id text not null references photo_answer_jobs(id),
                  page_index integer not null,
                  engine text not null,
                  engine_model_version text not null default '',
                  preprocess_version text not null default '',
                  request_hash text not null default '',
                  provider_usage_id text not null default '',
                  raw_text text not null default '',
                  line_boxes_json text not null default '[]',
                  char_confidences_json text not null default '[]',
                  alteration_marks_json text not null default '[]',
                  cost_micros integer not null default 0,
                  created_at real not null,
                  unique(job_id, page_index, engine)
                );

                create table if not exists photo_answer_cost_entries (
                  id text primary key,
                  session_id text not null references photo_answer_sessions(id),
                  channel text not null,
                  state text not null default 'reserved',
                  reserved_micros integer not null,
                  actual_micros integer not null default 0,
                  provider_usage_id text not null default '',
                  note text not null default '',
                  created_at real not null,
                  updated_at real not null
                );
                create index if not exists idx_pa_cost_session
                  on photo_answer_cost_entries(session_id);

                create table if not exists photo_answer_suspicions (
                  id text primary key,
                  session_id text not null references photo_answer_sessions(id),
                  job_id text not null default '',
                  page_index integer not null default 0,
                  span_json text not null default '{}',
                  source text not null,
                  severity text not null default 'normal',
                  suggestion text not null default '',
                  resolved_by_user integer not null default 0,
                  created_at real not null
                );

                create table if not exists photo_answer_confirmations (
                  id text primary key,
                  session_id text not null references photo_answer_sessions(id),
                  job_version integer not null,
                  confirmed_text text not null,
                  diff_json text not null default '[]',
                  edited_char_count integer not null default 0,
                  ack_flags_json text not null default '{}',
                  confirmed_at real not null
                );

                create table if not exists photo_answer_error_feedback (
                  id text primary key,
                  session_id text not null references photo_answer_sessions(id),
                  span_id text not null default '',
                  gold_text text not null default '',
                  reported_by text not null default '',
                  created_at real not null
                );
                """
            )

    # ---------- sessions ----------

    def create_session(
        self,
        *,
        user_id: str,
        question_id: str,
        question_stem: str = "",
        soft_cap_micros: int = SOFT_CAP_MICROS,
        hard_cap_micros: int = HARD_CAP_MICROS,
        daily_session_limit: int = DEFAULT_DAILY_SESSION_LIMIT,
        now: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now if now is not None else time.time())
        day_key = time.strftime("%Y-%m-%d", time.localtime(ts))
        session_id = f"pa-{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute("begin immediate")
            count = conn.execute(
                "select count(*) from photo_answer_sessions where user_id=? and day_key=?",
                (user_id, day_key),
            ).fetchone()[0]
            if int(count) >= int(daily_session_limit):
                raise DailyQuotaExceeded(
                    f"User {user_id} reached daily photo-answer session limit {daily_session_limit}"
                )
            conn.execute(
                """
                insert into photo_answer_sessions
                  (id, user_id, question_id, question_stem, status,
                   cost_budget_soft_micros, cost_budget_hard_micros, day_key, created_at)
                values (?,?,?,?, 'created', ?,?,?,?)
                """,
                (
                    session_id,
                    user_id,
                    question_id,
                    question_stem or "",
                    int(soft_cap_micros),
                    int(hard_cap_micros),
                    day_key,
                    ts,
                ),
            )
        session = self.get_session(session_id)
        assert session is not None
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from photo_answer_sessions where id=?", (session_id,)
            ).fetchone()
        return _row_to_dict(row)

    def set_session_status(self, session_id: str, target: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                "select status from photo_answer_sessions where id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown session {session_id}")
            assert_transition(str(row["status"]), target)
            conn.execute(
                "update photo_answer_sessions set status=? where id=?",
                (target, session_id),
            )
        session = self.get_session(session_id)
        assert session is not None
        return session

    # ---------- pages ----------

    def add_page(
        self,
        session_id: str,
        *,
        page_index: int,
        image_ref: str,
        content_hash: str = "",
        quality: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now if now is not None else time.time())
        page_id = f"pap-{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute("begin immediate")
            dup = 0
            if content_hash:
                existing = conn.execute(
                    "select count(*) from photo_answer_pages where session_id=? and content_hash=?",
                    (session_id, content_hash),
                ).fetchone()[0]
                dup = 1 if int(existing) > 0 else 0
            conn.execute(
                """
                insert into photo_answer_pages
                  (id, session_id, page_index, image_ref, content_hash, is_duplicate, quality_json, created_at)
                values (?,?,?,?,?,?,?,?)
                """,
                (
                    page_id,
                    session_id,
                    int(page_index),
                    image_ref,
                    content_hash or "",
                    dup,
                    json.dumps(quality or {}, ensure_ascii=False),
                    ts,
                ),
            )
            conn.execute(
                "update photo_answer_sessions set page_count=(select count(*) from photo_answer_pages where session_id=?) where id=?",
                (session_id, session_id),
            )
            row = conn.execute(
                "select * from photo_answer_pages where id=?", (page_id,)
            ).fetchone()
        page = dict(row)
        page["is_duplicate"] = bool(page["is_duplicate"])
        return page

    def list_pages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from photo_answer_pages where session_id=? order by page_index",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- durable jobs ----------

    def create_job(
        self, session_id: str, *, idempotency_key: str, now: float | None = None
    ) -> dict[str, Any]:
        ts = float(now if now is not None else time.time())
        with self.connect() as conn:
            conn.execute("begin immediate")
            existing = conn.execute(
                "select * from photo_answer_jobs where session_id=? and idempotency_key=?",
                (session_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            version = conn.execute(
                "select coalesce(max(job_version), 0) + 1 from photo_answer_jobs where session_id=?",
                (session_id,),
            ).fetchone()[0]
            job_id = f"paj-{uuid.uuid4().hex}"
            conn.execute(
                """
                insert into photo_answer_jobs
                  (id, session_id, idempotency_key, job_version, status, created_at)
                values (?,?,?,?, 'pending', ?)
                """,
                (job_id, session_id, idempotency_key, int(version), ts),
            )
            row = conn.execute(
                "select * from photo_answer_jobs where id=?", (job_id,)
            ).fetchone()
        return dict(row)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from photo_answer_jobs where id=?", (job_id,)
            ).fetchone()
        return _row_to_dict(row)

    def get_latest_job(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from photo_answer_jobs where session_id=? order by job_version desc limit 1",
                (session_id,),
            ).fetchone()
        return _row_to_dict(row)

    def lease_job(
        self, job_id: str, *, lease_seconds: float, now: float | None = None
    ) -> bool:
        """Claim the job for execution.

        Returns True when claimed. A running job with an unexpired lease is
        not claimable (prevents double execution); an expired lease is
        claimable again — that is the poll-driven crash recovery path.
        """
        ts = float(now if now is not None else time.time())
        with self.connect() as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                "select status, lease_until from photo_answer_jobs where id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            status = str(row["status"])
            if status not in ("pending", "running"):
                return False
            if status == "running" and float(row["lease_until"]) > ts:
                return False
            conn.execute(
                """
                update photo_answer_jobs
                set status='running', lease_until=?, attempt_count=attempt_count+1
                where id=?
                """,
                (ts + float(lease_seconds), job_id),
            )
        return True

    def finish_job(self, job_id: str, status: str, *, now: float | None = None) -> None:
        if status not in ("succeeded", "failed"):
            raise ValueError(f"Invalid terminal job status: {status}")
        ts = float(now if now is not None else time.time())
        with self.connect() as conn:
            conn.execute(
                "update photo_answer_jobs set status=?, finished_at=? where id=?",
                (status, ts, job_id),
            )

    # ---------- OCR results ----------

    def save_ocr_result(
        self,
        job_id: str,
        *,
        page_index: int,
        engine: str,
        raw_text: str,
        line_boxes: list[Any] | None = None,
        char_confidences: list[Any] | None = None,
        alteration_marks: list[Any] | None = None,
        engine_model_version: str = "",
        preprocess_version: str = "",
        request_hash: str = "",
        provider_usage_id: str = "",
        cost_micros: int = 0,
        now: float | None = None,
    ) -> bool:
        """Insert a result; idempotent on (job, page, engine).

        Returns True when a new row was written, False when the result
        already existed (crash-recovery rerun must not double-write).
        """
        ts = float(now if now is not None else time.time())
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    insert into photo_answer_ocr_results
                      (id, job_id, page_index, engine, engine_model_version, preprocess_version,
                       request_hash, provider_usage_id, raw_text, line_boxes_json,
                       char_confidences_json, alteration_marks_json, cost_micros, created_at)
                    values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"par-{uuid.uuid4().hex}",
                        job_id,
                        int(page_index),
                        engine,
                        engine_model_version,
                        preprocess_version,
                        request_hash,
                        provider_usage_id,
                        raw_text,
                        json.dumps(line_boxes or [], ensure_ascii=False),
                        json.dumps(char_confidences or [], ensure_ascii=False),
                        json.dumps(alteration_marks or [], ensure_ascii=False),
                        int(cost_micros),
                        ts,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def has_ocr_result(self, job_id: str, *, page_index: int, engine: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "select 1 from photo_answer_ocr_results where job_id=? and page_index=? and engine=?",
                (job_id, int(page_index), engine),
            ).fetchone()
        return row is not None

    def list_ocr_results(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from photo_answer_ocr_results where job_id=? order by page_index, engine",
                (job_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- suspicions / confirmations / feedback ----------

    def replace_suspicions(
        self, session_id: str, *, job_id: str, items: list[dict[str, Any]], now: float | None = None
    ) -> None:
        ts = float(now if now is not None else time.time())
        with self.connect() as conn:
            conn.execute("begin immediate")
            conn.execute(
                "delete from photo_answer_suspicions where session_id=? and job_id=?",
                (session_id, job_id),
            )
            for item in items:
                conn.execute(
                    """
                    insert into photo_answer_suspicions
                      (id, session_id, job_id, page_index, span_json, source, severity,
                       suggestion, resolved_by_user, created_at)
                    values (?,?,?,?,?,?,?,?,0,?)
                    """,
                    (
                        f"pas-{uuid.uuid4().hex}",
                        session_id,
                        job_id,
                        int(item.get("page_index", 0)),
                        json.dumps(item.get("span") or {}, ensure_ascii=False),
                        str(item.get("source") or "low_conf"),
                        str(item.get("severity") or "normal"),
                        str(item.get("suggestion") or ""),
                        ts,
                    ),
                )

    def list_suspicions(self, session_id: str, *, job_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if job_id is None:
                rows = conn.execute(
                    "select * from photo_answer_suspicions where session_id=? order by page_index",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select * from photo_answer_suspicions where session_id=? and job_id=? order by page_index",
                    (session_id, job_id),
                ).fetchall()
        return [dict(r) for r in rows]

    def mark_suspicions_resolved(self, session_id: str, span_ids: list[str]) -> None:
        if not span_ids:
            return
        with self.connect() as conn:
            conn.executemany(
                "update photo_answer_suspicions set resolved_by_user=1 where session_id=? and id=?",
                [(session_id, sid) for sid in span_ids],
            )

    def save_confirmation(
        self,
        session_id: str,
        *,
        job_version: int,
        confirmed_text: str,
        diff: list[Any] | None = None,
        edited_char_count: int = 0,
        ack_flags: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now if now is not None else time.time())
        confirmation_id = f"pac-{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute(
                """
                insert into photo_answer_confirmations
                  (id, session_id, job_version, confirmed_text, diff_json,
                   edited_char_count, ack_flags_json, confirmed_at)
                values (?,?,?,?,?,?,?,?)
                """,
                (
                    confirmation_id,
                    session_id,
                    int(job_version),
                    confirmed_text,
                    json.dumps(diff or [], ensure_ascii=False),
                    int(edited_char_count),
                    json.dumps(ack_flags or {}, ensure_ascii=False),
                    ts,
                ),
            )
            row = conn.execute(
                "select * from photo_answer_confirmations where id=?", (confirmation_id,)
            ).fetchone()
        return dict(row)

    def add_error_feedback(
        self,
        session_id: str,
        *,
        span_id: str,
        gold_text: str,
        reported_by: str,
        now: float | None = None,
    ) -> None:
        ts = float(now if now is not None else time.time())
        with self.connect() as conn:
            conn.execute(
                """
                insert into photo_answer_error_feedback
                  (id, session_id, span_id, gold_text, reported_by, created_at)
                values (?,?,?,?,?,?)
                """,
                (f"paf-{uuid.uuid4().hex}", session_id, span_id, gold_text, reported_by, ts),
            )
