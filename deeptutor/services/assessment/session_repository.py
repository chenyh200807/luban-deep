from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


logger = logging.getLogger(__name__)

SESSION_SCHEMA_VERSION = "assessment_session_v1"
REPORT_SCHEMA_VERSION = "p0a-v1"
PASS_READINESS_REPORT_SCHEMA_VERSION = "pass-readiness-v1"
# Mirror of the DB CHECK constraint (supabase/migrations/20260805000100_*.sql).
# Report envelopes must carry one of these persisted schema versions.
SUPPORTED_REPORT_SCHEMA_VERSIONS = (REPORT_SCHEMA_VERSION, PASS_READINESS_REPORT_SCHEMA_VERSION)
DEFAULT_TTL = timedelta(hours=24)
DEFAULT_LEASE = timedelta(minutes=30)


class AssessmentSessionError(RuntimeError):
    pass


class AssessmentSessionNotFound(AssessmentSessionError):
    pass


class AssessmentSessionExpired(AssessmentSessionError):
    pass


class AssessmentSessionConflict(AssessmentSessionError):
    pass


class AssessmentLeaseConflict(AssessmentSessionError):
    pass


class AssessmentSessionRateLimited(AssessmentSessionError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _snapshot_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _submit_key(user_id: str, quiz_id: str, submitted_answer_snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(
        f"{user_id}|{quiz_id}|{_snapshot_hash(submitted_answer_snapshot)}".encode("utf-8")
    ).hexdigest()


def _report_hash(value: dict[str, Any]) -> str:
    return _snapshot_hash(value)


def _redacted_session(row: dict[str, Any]) -> dict[str, Any]:
    public = copy.deepcopy(row)
    public.pop("session_questions_private", None)
    public["questions"] = copy.deepcopy(row.get("client_questions_public") or [])
    public.pop("client_questions_public", None)
    return public


class InMemoryAssessmentSessionRepository:
    def __init__(self, *, now_fn: Callable[[], datetime] | None = None) -> None:
        self._rows: dict[str, dict[str, Any]] = {}
        self._now_fn = now_fn or _utc_now

    def create_session(
        self,
        *,
        user_id: str,
        assessment_type: str,
        subject_id: str,
        topic_ids: list[str],
        blueprint_version: str,
        form_id: str,
        client_questions_public: list[dict[str, Any]],
        session_questions_private: list[dict[str, Any]],
        device_id: str = "",
        trace_id: str = "",
    ) -> dict[str, Any]:
        self.expire_stale_sessions()
        reusable = self.find_active_session(
            user_id=user_id,
            assessment_type=assessment_type,
            subject_id=subject_id,
            blueprint_version=blueprint_version,
            topic_ids=topic_ids,
        )
        if reusable is not None:
            return self._reuse_active_session_or_raise(
                reusable,
                device_id=device_id,
                reason="active_session_exists",
            )
        now = self._now_fn()
        quiz_id = f"quiz_{uuid.uuid4().hex[:12]}"
        row = {
            "session_id": quiz_id,
            "quiz_id": quiz_id,
            "user_id": str(user_id or "").strip(),
            "assessment_type": str(assessment_type or "").strip(),
            "subject_id": str(subject_id or "").strip(),
            "topic_ids": [str(item).strip() for item in list(topic_ids or []) if str(item).strip()],
            "blueprint_version": str(blueprint_version or "").strip(),
            "form_id": str(form_id or "").strip(),
            "status": "in_progress",
            "schema_version": SESSION_SCHEMA_VERSION,
            "client_questions_public": copy.deepcopy(client_questions_public or []),
            "session_questions_private": copy.deepcopy(session_questions_private or []),
            "draft_answer_snapshot": {},
            "submitted_answer_snapshot": None,
            "submit_idempotency_key": None,
            "result_report_json": None,
            "result_report_hash": None,
            "learning_event_refs": [],
            "mistake_book_refs": [],
            "degraded_reason": None,
            "device_id": str(device_id or "").strip(),
            "lease_expires_at": _iso(now + DEFAULT_LEASE),
            "lease_history": [
                {
                    "device_id": str(device_id or "").strip(),
                    "started_at": _iso(now),
                    "ended_at": "",
                    "reason": "create",
                }
            ],
            "created_at": _iso(now),
            "submitted_at": None,
            "scored_at": None,
            "expires_at": _iso(now + DEFAULT_TTL),
            "created_trace_id": str(trace_id or "").strip(),
            "updated_at": _iso(now),
        }
        self._rows[quiz_id] = row
        logger.info(
            "assessment_session_started quiz_id=%s assessment_type=%s blueprint_version=%s form_id=%s topic_ids=%s trace_id=%s",
            quiz_id,
            row["assessment_type"],
            row["blueprint_version"],
            row["form_id"],
            ",".join(row["topic_ids"]),
            row["created_trace_id"],
        )
        return copy.deepcopy(row)

    def find_active_session(
        self,
        *,
        user_id: str,
        assessment_type: str,
        subject_id: str,
        blueprint_version: str,
        topic_ids: list[str],
    ) -> dict[str, Any] | None:
        normalized_topics = sorted(str(item).strip() for item in list(topic_ids or []) if str(item).strip())
        for row in self._rows.values():
            if row.get("status") != "in_progress":
                continue
            if str(row.get("user_id")) != str(user_id):
                continue
            if str(row.get("assessment_type")) != str(assessment_type):
                continue
            if str(row.get("subject_id")) != str(subject_id):
                continue
            if str(row.get("blueprint_version")) != str(blueprint_version):
                continue
            if sorted(list(row.get("topic_ids") or [])) != normalized_topics:
                continue
            if _parse_iso(str(row.get("expires_at"))) <= self._now_fn():
                row["status"] = "expired"
                continue
            return copy.deepcopy(row)
        return None

    def latest_scored_session(self, user_id: str, assessment_type: str) -> dict[str, Any] | None:
        """Latest scored session of one type — read-only canonical evidence probe."""

        rows = [
            row
            for row in self._rows.values()
            if str(row.get("user_id")) == str(user_id)
            and str(row.get("assessment_type")) == str(assessment_type)
            and str(row.get("status")) == "scored"
        ]
        if not rows:
            return None
        latest = max(rows, key=lambda row: str(row.get("scored_at") or row.get("created_at") or ""))
        return copy.deepcopy(latest)

    def get_session_for_resume(self, user_id: str, quiz_id: str, *, device_id: str = "") -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        self._expire_if_needed(row)
        if row["status"] == "expired":
            raise AssessmentSessionExpired("assessment_session_expired")
        self._claim_if_lease_expired(row, device_id=device_id)
        logger.info("assessment_session_resumed quiz_id=%s assessment_type=%s", quiz_id, row.get("assessment_type"))
        return _redacted_session(row)

    def private_session(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        return copy.deepcopy(row)

    def mark_submitted_once(
        self,
        user_id: str,
        quiz_id: str,
        *,
        submitted_answer_snapshot: dict[str, Any],
        result_report_json: dict[str, Any],
        device_id: str = "",
    ) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        self._expire_if_needed(row)
        if row["status"] == "expired":
            raise AssessmentSessionExpired("assessment_session_expired")
        self._assert_lease(row, device_id=device_id)
        key = _submit_key(user_id, quiz_id, submitted_answer_snapshot)
        if row.get("submitted_answer_snapshot") is not None:
            if row.get("submit_idempotency_key") == key:
                return copy.deepcopy(row)
            raise AssessmentSessionConflict("assessment_submit_body_conflict")
        if result_report_json.get("schema_version") not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
            raise AssessmentSessionConflict("result_report_schema_version_required")
        now = self._now_fn()
        row["submitted_answer_snapshot"] = copy.deepcopy(submitted_answer_snapshot or {})
        row["submit_idempotency_key"] = key
        row["result_report_json"] = copy.deepcopy(result_report_json or {})
        row["result_report_hash"] = _report_hash(result_report_json or {})
        row["status"] = "scored"
        row["submitted_at"] = _iso(now)
        row["scored_at"] = _iso(now)
        row["updated_at"] = _iso(now)
        logger.info(
            "assessment_session_scored quiz_id=%s assessment_type=%s blueprint_version=%s form_id=%s answered_count=%s",
            quiz_id,
            row.get("assessment_type"),
            row.get("blueprint_version"),
            row.get("form_id"),
            len(submitted_answer_snapshot or {}),
        )
        return copy.deepcopy(row)

    def attach_writeback_refs(
        self,
        user_id: str,
        quiz_id: str,
        *,
        learning_event_refs: list[dict[str, Any]],
        mistake_book_refs: list[dict[str, Any]],
        mark_scored: bool = False,
    ) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        row["learning_event_refs"] = copy.deepcopy(learning_event_refs or [])
        row["mistake_book_refs"] = copy.deepcopy(mistake_book_refs or [])
        if row.get("result_report_json"):
            report = dict(row["result_report_json"])
            report["attempt_refs"] = copy.deepcopy(learning_event_refs or [])
            report["writeback_status"] = {
                "learning_event_count": len(learning_event_refs or []),
                "mistake_book_count": len(mistake_book_refs or []),
            }
            report["degraded_reason"] = None if mark_scored else row.get("degraded_reason")
            row["result_report_json"] = report
            row["result_report_hash"] = _report_hash(report)
        if mark_scored:
            row["status"] = "scored"
            row["degraded_reason"] = None
        row["updated_at"] = _iso(self._now_fn())
        return copy.deepcopy(row)

    def expire_stale_sessions(self) -> None:
        for row in self._rows.values():
            self._expire_if_needed(row)

    def rekey_user_sessions(self, *, source_user_id: str, target_user_id: str) -> int:
        """Move every session row owned by ``source_user_id`` to ``target_user_id``.

        Account merge invariant (plan §9.4): the assessment read path is strict
        ``user_id`` equality, so a merged-away account's sessions would be
        stranded unless the merge re-keys them. Idempotent: after the first run
        no row matches the source id, so a repeated merge moves nothing.
        """
        source = str(source_user_id or "").strip()
        target = str(target_user_id or "").strip()
        if not source or not target or source == target:
            return 0
        moved = 0
        for row in self._rows.values():
            if str(row.get("user_id") or "").strip() != source:
                continue
            row["user_id"] = target
            row["updated_at"] = _iso(self._now_fn())
            moved += 1
        return moved

    def renew_lease(self, user_id: str, quiz_id: str, *, device_id: str, heartbeat_seconds: int = 300) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        self._assert_lease(row, device_id=device_id)
        now = self._now_fn()
        row["lease_expires_at"] = _iso(now + DEFAULT_LEASE)
        row["updated_at"] = _iso(now)
        return copy.deepcopy(row)

    def take_over_lease(self, user_id: str, quiz_id: str, *, device_id: str, reason: str = "manual") -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        now = self._now_fn()
        if row.get("lease_history"):
            row["lease_history"][-1]["ended_at"] = _iso(now)
        row["device_id"] = str(device_id or "").strip()
        row["lease_expires_at"] = _iso(now + DEFAULT_LEASE)
        row["lease_history"].append(
            {
                "device_id": row["device_id"],
                "started_at": _iso(now),
                "ended_at": "",
                "reason": str(reason or "manual").strip(),
            }
        )
        row["updated_at"] = _iso(now)
        logger.info("assessment_lease_taken_over quiz_id=%s reason=%s", quiz_id, reason)
        return copy.deepcopy(row)

    def patch_draft_answers(self, user_id: str, quiz_id: str, answers: dict[str, Any], *, device_id: str = "") -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        self._assert_lease(row, device_id=device_id)
        draft = dict(row.get("draft_answer_snapshot") or {})
        for key, value in dict(answers or {}).items():
            if key not in draft:
                draft[str(key)] = value
        row["draft_answer_snapshot"] = draft
        row["updated_at"] = _iso(self._now_fn())
        return copy.deepcopy(row)

    def record_degraded(self, user_id: str, quiz_id: str, *, reason: str) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        row["status"] = "degraded"
        row["degraded_reason"] = str(reason or "unknown").strip() or "unknown"
        if row.get("result_report_json"):
            report = dict(row["result_report_json"])
            report["degraded_reason"] = row["degraded_reason"]
            report["writeback_status"] = {
                **dict(report.get("writeback_status") or {}),
                "status": "degraded",
                "reason": row["degraded_reason"],
            }
            row["result_report_json"] = report
            row["result_report_hash"] = _report_hash(report)
        row["updated_at"] = _iso(self._now_fn())
        logger.warning("assessment_writeback_degraded quiz_id=%s degraded_reason=%s", quiz_id, row["degraded_reason"])
        return copy.deepcopy(row)

    def _owned_row(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        row = self._rows.get(str(quiz_id or ""))
        if not row or str(row.get("user_id")) != str(user_id):
            raise AssessmentSessionNotFound("assessment_session_not_found")
        return row

    def _reuse_active_session_or_raise(
        self,
        reusable: dict[str, Any],
        *,
        device_id: str,
        reason: str,
    ) -> dict[str, Any]:
        row = self._owned_row(str(reusable.get("user_id") or ""), str(reusable.get("quiz_id") or ""))
        self._expire_if_needed(row)
        if row.get("status") == "expired":
            raise AssessmentSessionExpired("assessment_session_expired")
        self._assert_lease(row, device_id=device_id)
        result = copy.deepcopy(row)
        result["reuse_reason"] = reason
        return result

    def _expire_if_needed(self, row: dict[str, Any]) -> None:
        if row.get("status") == "in_progress" and _parse_iso(str(row.get("expires_at"))) <= self._now_fn():
            row["status"] = "expired"
            row["updated_at"] = _iso(self._now_fn())

    def _claim_if_lease_expired(self, row: dict[str, Any], *, device_id: str) -> None:
        normalized = str(device_id or "").strip()
        if not normalized:
            return
        if str(row.get("device_id") or "") == normalized:
            return
        if _parse_iso(str(row.get("lease_expires_at"))) <= self._now_fn():
            self.take_over_lease(str(row.get("user_id")), str(row.get("quiz_id")), device_id=normalized, reason="idle_expired")

    def _assert_lease(self, row: dict[str, Any], *, device_id: str) -> None:
        normalized = str(device_id or "").strip()
        holder = str(row.get("device_id") or "").strip()
        if not normalized or not holder or normalized == holder:
            return
        if _parse_iso(str(row.get("lease_expires_at"))) <= self._now_fn():
            self.take_over_lease(str(row.get("user_id")), str(row.get("quiz_id")), device_id=normalized, reason="idle_expired")
            return
        raise AssessmentLeaseConflict("lease_conflict")


class SupabaseAssessmentSessionRepository:
    """Supabase-backed P0A session authority.

    This class intentionally mirrors ``InMemoryAssessmentSessionRepository`` so
    MemberConsoleService can stay a thin coordinator while tests use the local
    adapter. It uses the service-role REST API; client-facing authorization is
    still enforced by the mobile auth layer and the table RLS in the migration.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.Client | None = None,
        timeout_s: float = 10.0,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip().rstrip("/")
        self._service_key = str(
            service_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
            or ""
        ).strip()
        self._client = client
        self._timeout_s = float(timeout_s)
        self._now_fn = now_fn or _utc_now

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    def create_session(
        self,
        *,
        user_id: str,
        assessment_type: str,
        subject_id: str,
        topic_ids: list[str],
        blueprint_version: str,
        form_id: str,
        client_questions_public: list[dict[str, Any]],
        session_questions_private: list[dict[str, Any]],
        device_id: str = "",
        trace_id: str = "",
    ) -> dict[str, Any]:
        self._ensure_configured()
        self.expire_stale_sessions(user_id=user_id)
        reusable = self.find_active_session(
            user_id=user_id,
            assessment_type=assessment_type,
            subject_id=subject_id,
            blueprint_version=blueprint_version,
            topic_ids=topic_ids,
        )
        if reusable is not None:
            return self._reuse_active_session_or_raise(
                reusable,
                device_id=device_id,
                reason="active_session_exists",
            )
        now = self._now_fn()
        row = {
            "quiz_id": f"quiz_{uuid.uuid4().hex[:12]}",
            "user_id": str(user_id or "").strip(),
            "assessment_type": str(assessment_type or "").strip(),
            "subject_id": str(subject_id or "").strip(),
            "topic_ids": [str(item).strip() for item in list(topic_ids or []) if str(item).strip()],
            "blueprint_version": str(blueprint_version or "").strip(),
            "form_id": str(form_id or "").strip(),
            "status": "in_progress",
            "schema_version": SESSION_SCHEMA_VERSION,
            "client_questions_public": copy.deepcopy(client_questions_public or []),
            "session_questions_private": copy.deepcopy(session_questions_private or []),
            "draft_answer_snapshot": {},
            "submitted_answer_snapshot": None,
            "submit_idempotency_key": None,
            "result_report_json": None,
            "result_report_hash": None,
            "learning_event_refs": [],
            "mistake_book_refs": [],
            "degraded_reason": None,
            "device_id": str(device_id or "").strip(),
            "lease_expires_at": _iso(now + DEFAULT_LEASE),
            "lease_history": [
                {
                    "device_id": str(device_id or "").strip(),
                    "started_at": _iso(now),
                    "ended_at": "",
                    "reason": "create",
                }
            ],
            "created_trace_id": str(trace_id or "").strip(),
            "expires_at": _iso(now + DEFAULT_TTL),
            "updated_at": _iso(now),
        }
        try:
            inserted = self._insert(row)
        except AssessmentSessionConflict as exc:
            if str(exc) != "assessment_session_insert_conflict":
                raise
            reusable = self.find_active_session(
                user_id=user_id,
                assessment_type=assessment_type,
                subject_id=subject_id,
                blueprint_version=blueprint_version,
                topic_ids=topic_ids,
            )
            if reusable is None:
                raise
            inserted = self._reuse_active_session_or_raise(
                reusable,
                device_id=device_id,
                reason="active_session_insert_conflict",
            )
        logger.info(
            "assessment_session_started quiz_id=%s assessment_type=%s blueprint_version=%s form_id=%s topic_ids=%s trace_id=%s",
            inserted.get("quiz_id"),
            inserted.get("assessment_type"),
            inserted.get("blueprint_version"),
            inserted.get("form_id"),
            ",".join(list(inserted.get("topic_ids") or [])),
            inserted.get("created_trace_id"),
        )
        return inserted

    def find_active_session(
        self,
        *,
        user_id: str,
        assessment_type: str,
        subject_id: str,
        blueprint_version: str,
        topic_ids: list[str],
    ) -> dict[str, Any] | None:
        normalized_topics = sorted(str(item).strip() for item in list(topic_ids or []) if str(item).strip())
        rows = self._select(
            {
                "user_id": f"eq.{user_id}",
                "assessment_type": f"eq.{assessment_type}",
                "subject_id": f"eq.{subject_id}",
                "blueprint_version": f"eq.{blueprint_version}",
                "status": "eq.in_progress",
            },
            limit=20,
        )
        for row in rows:
            if sorted(list(row.get("topic_ids") or [])) == normalized_topics:
                return copy.deepcopy(row)
        return None

    def latest_scored_session(self, user_id: str, assessment_type: str) -> dict[str, Any] | None:
        """Latest scored session of one type — read-only canonical evidence probe."""

        rows = self._select(
            {
                "user_id": f"eq.{user_id}",
                "assessment_type": f"eq.{assessment_type}",
                "status": "eq.scored",
                "order": "scored_at.desc.nullslast",
            },
            limit=1,
        )
        if not rows:
            return None
        return copy.deepcopy(rows[0])

    def get_session_for_resume(self, user_id: str, quiz_id: str, *, device_id: str = "") -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        row = self._expire_if_needed(row)
        if row.get("status") == "expired":
            raise AssessmentSessionExpired("assessment_session_expired")
        row = self._claim_if_lease_expired(row, device_id=device_id)
        logger.info("assessment_session_resumed quiz_id=%s assessment_type=%s", quiz_id, row.get("assessment_type"))
        return _redacted_session(row)

    def private_session(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        return self._owned_row(user_id, quiz_id)

    def mark_submitted_once(
        self,
        user_id: str,
        quiz_id: str,
        *,
        submitted_answer_snapshot: dict[str, Any],
        result_report_json: dict[str, Any],
        device_id: str = "",
    ) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        row = self._expire_if_needed(row)
        if row.get("status") == "expired":
            raise AssessmentSessionExpired("assessment_session_expired")
        self._assert_lease(row, device_id=device_id)
        key = _submit_key(user_id, quiz_id, submitted_answer_snapshot)
        if row.get("submitted_answer_snapshot") is not None:
            if row.get("submit_idempotency_key") == key:
                return copy.deepcopy(row)
            raise AssessmentSessionConflict("assessment_submit_body_conflict")
        if result_report_json.get("schema_version") not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
            raise AssessmentSessionConflict("result_report_schema_version_required")
        now = self._now_fn()
        patch = {
            "submitted_answer_snapshot": copy.deepcopy(submitted_answer_snapshot or {}),
            "submit_idempotency_key": key,
            "result_report_json": copy.deepcopy(result_report_json or {}),
            "result_report_hash": _report_hash(result_report_json or {}),
            "status": "scored",
            "submitted_at": _iso(now),
            "scored_at": _iso(now),
            "updated_at": _iso(now),
        }
        try:
            updated = self._patch_owned(
                user_id,
                quiz_id,
                patch,
                filters={
                    "status": "eq.in_progress",
                    "submitted_answer_snapshot": "is.null",
                    "expires_at": f"gt.{_iso(self._now_fn())}",
                },
            )
        except AssessmentSessionNotFound as exc:
            latest = self._owned_row(user_id, quiz_id)
            if latest.get("submitted_answer_snapshot") is not None and latest.get("submit_idempotency_key") == key:
                return copy.deepcopy(latest)
            raise AssessmentSessionConflict("assessment_submit_body_conflict") from exc
        logger.info(
            "assessment_session_scored quiz_id=%s assessment_type=%s blueprint_version=%s form_id=%s answered_count=%s",
            quiz_id,
            updated.get("assessment_type"),
            updated.get("blueprint_version"),
            updated.get("form_id"),
            len(submitted_answer_snapshot or {}),
        )
        return updated

    def attach_writeback_refs(
        self,
        user_id: str,
        quiz_id: str,
        *,
        learning_event_refs: list[dict[str, Any]],
        mistake_book_refs: list[dict[str, Any]],
        mark_scored: bool = False,
    ) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        report = dict(row.get("result_report_json") or {})
        if report:
            report["attempt_refs"] = copy.deepcopy(learning_event_refs or [])
            report["writeback_status"] = {
                "status": "ok",
                "learning_event_count": len(learning_event_refs or []),
                "mistake_book_count": len(mistake_book_refs or []),
            }
            report["degraded_reason"] = None if mark_scored else row.get("degraded_reason")
        patch = {
            "learning_event_refs": copy.deepcopy(learning_event_refs or []),
            "mistake_book_refs": copy.deepcopy(mistake_book_refs or []),
            "result_report_json": report or row.get("result_report_json"),
            "result_report_hash": _report_hash(report) if report else row.get("result_report_hash"),
            "updated_at": _iso(self._now_fn()),
        }
        if mark_scored:
            patch["status"] = "scored"
            patch["degraded_reason"] = None
        return self._patch_owned(user_id, quiz_id, patch)

    def rekey_user_sessions(self, *, source_user_id: str, target_user_id: str) -> int:
        """Re-key merged-away sessions to the surviving uid (plan §9.4).

        One PATCH over ``user_id=eq.<source>``; PostgREST returns the moved rows
        so the caller can audit the count. Idempotent by construction — the
        second call matches nothing.
        """
        source = str(source_user_id or "").strip()
        target = str(target_user_id or "").strip()
        if not source or not target or source == target:
            return 0
        self._ensure_configured()
        try:
            response = self._client_or_create().patch(
                f"{self._base_url}/rest/v1/assessment_sessions",
                headers=self._headers(prefer="return=representation"),
                params={"user_id": f"eq.{source}"},
                json={"user_id": target, "updated_at": _iso(self._now_fn())},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AssessmentSessionError("assessment_sessions_unavailable") from exc
        payload = response.json()
        return len(payload) if isinstance(payload, list) else 0

    def expire_stale_sessions(self, *, user_id: str = "") -> None:
        filters = {"status": "eq.in_progress", "expires_at": f"lt.{_iso(self._now_fn())}"}
        if str(user_id or "").strip():
            filters["user_id"] = f"eq.{user_id}"
        rows = self._select(filters, limit=100)
        for row in rows:
            self._patch_owned(str(row.get("user_id") or ""), str(row.get("quiz_id") or ""), {"status": "expired"})

    def renew_lease(self, user_id: str, quiz_id: str, *, device_id: str, heartbeat_seconds: int = 300) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        self._assert_lease(row, device_id=device_id)
        return self._patch_owned(
            user_id,
            quiz_id,
            {"lease_expires_at": _iso(self._now_fn() + DEFAULT_LEASE), "updated_at": _iso(self._now_fn())},
        )

    def take_over_lease(self, user_id: str, quiz_id: str, *, device_id: str, reason: str = "manual") -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        now = self._now_fn()
        history = list(row.get("lease_history") or [])
        if history:
            history[-1] = {**dict(history[-1]), "ended_at": _iso(now)}
        history.append(
            {
                "device_id": str(device_id or "").strip(),
                "started_at": _iso(now),
                "ended_at": "",
                "reason": str(reason or "manual").strip(),
            }
        )
        updated = self._patch_owned(
            user_id,
            quiz_id,
            {
                "device_id": str(device_id or "").strip(),
                "lease_expires_at": _iso(now + DEFAULT_LEASE),
                "lease_history": history,
                "updated_at": _iso(now),
            },
        )
        logger.info("assessment_lease_taken_over quiz_id=%s reason=%s", quiz_id, reason)
        return updated

    def patch_draft_answers(self, user_id: str, quiz_id: str, answers: dict[str, Any], *, device_id: str = "") -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        self._assert_lease(row, device_id=device_id)
        draft = dict(row.get("draft_answer_snapshot") or {})
        for key, value in dict(answers or {}).items():
            if key not in draft:
                draft[str(key)] = value
        return self._patch_owned(
            user_id,
            quiz_id,
            {"draft_answer_snapshot": draft, "updated_at": _iso(self._now_fn())},
        )

    def record_degraded(self, user_id: str, quiz_id: str, *, reason: str) -> dict[str, Any]:
        row = self._owned_row(user_id, quiz_id)
        normalized_reason = str(reason or "unknown").strip() or "unknown"
        report = dict(row.get("result_report_json") or {})
        if report:
            report["degraded_reason"] = normalized_reason
            report["writeback_status"] = {
                **dict(report.get("writeback_status") or {}),
                "status": "degraded",
                "reason": normalized_reason,
            }
        updated = self._patch_owned(
            user_id,
            quiz_id,
            {
                "status": "degraded",
                "degraded_reason": normalized_reason,
                "result_report_json": report or row.get("result_report_json"),
                "result_report_hash": _report_hash(report) if report else row.get("result_report_hash"),
                "updated_at": _iso(self._now_fn()),
            },
        )
        logger.warning("assessment_writeback_degraded quiz_id=%s degraded_reason=%s", quiz_id, normalized_reason)
        return updated

    def _owned_row(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        rows = self._select({"user_id": f"eq.{user_id}", "quiz_id": f"eq.{quiz_id}"}, limit=1)
        if not rows:
            raise AssessmentSessionNotFound("assessment_session_not_found")
        return copy.deepcopy(rows[0])

    def _reuse_active_session_or_raise(
        self,
        reusable: dict[str, Any],
        *,
        device_id: str,
        reason: str,
    ) -> dict[str, Any]:
        row = self._claim_if_lease_expired(copy.deepcopy(reusable), device_id=device_id)
        if row.get("lease_holder_other_device"):
            raise AssessmentLeaseConflict("lease_conflict")
        result = copy.deepcopy(row)
        result["reuse_reason"] = reason
        return result

    def _expire_if_needed(self, row: dict[str, Any]) -> dict[str, Any]:
        if row.get("status") == "in_progress" and _parse_iso(str(row.get("expires_at"))) <= self._now_fn():
            return self._patch_owned(str(row.get("user_id") or ""), str(row.get("quiz_id") or ""), {"status": "expired"})
        return row

    def _claim_if_lease_expired(self, row: dict[str, Any], *, device_id: str) -> dict[str, Any]:
        normalized = str(device_id or "").strip()
        if not normalized or str(row.get("device_id") or "") == normalized:
            return row
        if _parse_iso(str(row.get("lease_expires_at"))) <= self._now_fn():
            return self.take_over_lease(str(row.get("user_id")), str(row.get("quiz_id")), device_id=normalized, reason="idle_expired")
        row = copy.deepcopy(row)
        row["lease_holder_other_device"] = True
        return row

    def _assert_lease(self, row: dict[str, Any], *, device_id: str) -> None:
        normalized = str(device_id or "").strip()
        holder = str(row.get("device_id") or "").strip()
        if not normalized or not holder or normalized == holder:
            return
        if _parse_iso(str(row.get("lease_expires_at"))) <= self._now_fn():
            self.take_over_lease(str(row.get("user_id")), str(row.get("quiz_id")), device_id=normalized, reason="idle_expired")
            return
        raise AssessmentLeaseConflict("lease_conflict")

    def _insert(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client_or_create().post(
                f"{self._base_url}/rest/v1/assessment_sessions",
                headers=self._headers(prefer="return=representation"),
                json=[row],
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                raise AssessmentSessionConflict("assessment_session_insert_conflict") from exc
            raise AssessmentSessionError("assessment_sessions_unavailable") from exc
        except httpx.HTTPError as exc:
            raise AssessmentSessionError("assessment_sessions_unavailable") from exc
        payload = response.json()
        return dict(payload[0]) if isinstance(payload, list) and payload else dict(row)

    def _patch_owned(
        self,
        user_id: str,
        quiz_id: str,
        patch: dict[str, Any],
        *,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        params = {"user_id": f"eq.{user_id}", "quiz_id": f"eq.{quiz_id}", **dict(filters or {})}
        try:
            response = self._client_or_create().patch(
                f"{self._base_url}/rest/v1/assessment_sessions",
                headers=self._headers(prefer="return=representation"),
                params=params,
                json=dict(patch or {}),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AssessmentSessionError("assessment_sessions_unavailable") from exc
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise AssessmentSessionNotFound("assessment_session_not_found")
        return dict(payload[0])

    def _select(self, filters: dict[str, str], *, limit: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": "*", **dict(filters or {})}
        if limit is not None:
            params["limit"] = int(limit)
        try:
            response = self._client_or_create().get(
                f"{self._base_url}/rest/v1/assessment_sessions",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AssessmentSessionError("assessment_sessions_unavailable") from exc
        payload = response.json()
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise AssessmentSessionError("assessment_sessions_supabase_not_configured")

    def _client_or_create(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client
