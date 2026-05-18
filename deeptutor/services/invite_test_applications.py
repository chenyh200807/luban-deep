from __future__ import annotations

import json
import os
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx

from deeptutor.services.feedback_service import _supabase_rest_headers, _supabase_service_key


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JSONL_PATHS = (
    _REPO_ROOT / "web" / "tmp" / "invite-test-applications.jsonl",
    _REPO_ROOT / "tmp" / "invite-test-applications.jsonl",
)
_SELECT_COLUMNS = (
    "id,created_at,source_page,utm_source,utm_campaign,name,phone,email,wechat_id,"
    "exam_type,exam_stage,pain_point,weekly_time,current_method,latest_wrong_question,"
    "is_yousen_member,exam_date,accept_interview,consent,status,operator_note,"
    "submit_count,raw_payload"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _field(row: Mapping[str, Any], snake_key: str, camel_key: str | None = None) -> Any:
    if snake_key in row:
        return row.get(snake_key)
    if camel_key and camel_key in row:
        return row.get(camel_key)
    return None


def _parse_created_at(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mask_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 11:
        return f"{digits[:3]}****{digits[-4:]}"
    if len(value) <= 4:
        return value
    return f"{value[:2]}****{value[-2:]}"


def _mask_email(value: str) -> str:
    if "@" not in value:
        return value
    prefix, domain = value.split("@", 1)
    if len(prefix) <= 2:
        masked_prefix = f"{prefix[:1]}*"
    else:
        masked_prefix = f"{prefix[:2]}***"
    return f"{masked_prefix}@{domain}"


def _mask_optional(value: str) -> str:
    if len(value) <= 2:
        return value
    return f"{value[:1]}***{value[-1:]}"


def normalize_invite_test_application(row: Mapping[str, Any], *, reveal_contact: bool = False) -> dict[str, Any]:
    phone = _text(_field(row, "phone"))
    email = _text(_field(row, "email"))
    wechat_id = _text(_field(row, "wechat_id", "wechatId"))
    created_at = _text(_field(row, "created_at", "createdAt"))
    normalized = {
        "id": _text(_field(row, "id")),
        "created_at": created_at,
        "source_page": _text(_field(row, "source_page", "sourcePage")),
        "utm_source": _text(_field(row, "utm_source", "utmSource")),
        "utm_campaign": _text(_field(row, "utm_campaign", "utmCampaign")),
        "name": _text(_field(row, "name")),
        "phone": phone if reveal_contact else _mask_phone(phone),
        "email": email if reveal_contact else _mask_email(email),
        "wechat_id": wechat_id if reveal_contact else _mask_optional(wechat_id),
        "exam_type": _text(_field(row, "exam_type", "examType")),
        "exam_stage": _text(_field(row, "exam_stage", "examStage")),
        "pain_point": _text(_field(row, "pain_point", "painPoint")),
        "weekly_time": _text(_field(row, "weekly_time", "weeklyTime")),
        "current_method": _text(_field(row, "current_method", "currentMethod")),
        "latest_wrong_question": _text(_field(row, "latest_wrong_question", "latestWrongQuestion")),
        "is_yousen_member": _text(_field(row, "is_yousen_member", "isYousenMember")),
        "exam_date": _text(_field(row, "exam_date", "examDate")),
        "accept_interview": _bool(_field(row, "accept_interview", "acceptInterview")),
        "consent": _bool(_field(row, "consent")),
        "status": _text(_field(row, "status")) or "submitted",
        "operator_note": _text(_field(row, "operator_note", "operatorNote")),
        "submit_count": _int(_field(row, "submit_count", "submitCount"), 1),
    }
    normalized["contact_revealed"] = reveal_contact
    return normalized


class InviteTestApplicationStore:
    """Read model for invite-test applications submitted by the public Next.js form."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        database_url: str | None = None,
        jsonl_path: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = _text(base_url or os.getenv("SUPABASE_URL"))
        self._service_key = _supabase_service_key(service_key)
        self._database_url = _text(
            database_url
            or os.getenv("INVITE_TEST_DATABASE_URL")
            or os.getenv("SUPABASE_DB_URL")
            or os.getenv("DB_URL")
        )
        self._jsonl_path = _text(jsonl_path or os.getenv("INVITE_TEST_APPLICATIONS_PATH"))
        self._client = client
        self._timeout_s = float(timeout_s)
        self._owns_client = client is None

    @property
    def is_supabase_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    @property
    def is_database_configured(self) -> bool:
        return bool(self._database_url)

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_applications(
        self,
        *,
        days: int = 365,
        limit: int = 100,
        status: str | None = None,
        source_page: str | None = None,
        q: str | None = None,
        reveal_contact: bool = False,
    ) -> dict[str, Any]:
        storage_status, rows = await self._load_rows(days=days)
        filtered = self._filter_rows(rows, status=status, source_page=source_page, q=q)
        normalized = [
            normalize_invite_test_application(row, reveal_contact=reveal_contact)
            for row in filtered[: max(1, min(limit, 500))]
        ]
        return {
            "window_days": max(1, min(int(days or 365), 3650)),
            "storage_status": storage_status,
            "total": len(filtered),
            "contact_revealed": reveal_contact,
            "items": normalized,
        }

    async def get_stats(self, *, days: int = 365) -> dict[str, Any]:
        storage_status, rows = await self._load_rows(days=days)
        normalized = [normalize_invite_test_application(row, reveal_contact=False) for row in rows]
        status_counter = Counter(item["status"] or "submitted" for item in normalized)
        source_counter = Counter(item["source_page"] or "unknown" for item in normalized)
        exam_type_counter = Counter(item["exam_type"] or "unknown" for item in normalized)
        exam_stage_counter = Counter(item["exam_stage"] or "unknown" for item in normalized)
        pain_point_counter = Counter(item["pain_point"] or "unknown" for item in normalized)
        weekly_time_counter = Counter(item["weekly_time"] or "unknown" for item in normalized)
        unique_contacts = {
            (_text(_field(row, "phone")) or _text(_field(row, "email"))).lower()
            for row in rows
            if _text(_field(row, "phone")) or _text(_field(row, "email"))
        }
        total = len(normalized)
        accept_interview_count = sum(1 for item in normalized if item["accept_interview"])
        with_wrong_question_count = sum(1 for item in normalized if item["latest_wrong_question"])
        return {
            "window_days": max(1, min(int(days or 365), 3650)),
            "storage_status": storage_status,
            "summary": {
                "total_applications": total,
                "unique_contacts": len(unique_contacts),
                "accept_interview_count": accept_interview_count,
                "accept_interview_rate": round(accept_interview_count / total, 4) if total else 0,
                "with_wrong_question_count": with_wrong_question_count,
                "with_wrong_question_rate": round(with_wrong_question_count / total, 4) if total else 0,
                "consented_count": sum(1 for item in normalized if item["consent"]),
            },
            "status_breakdown": self._counter_rows(status_counter, key="status"),
            "source_breakdown": self._counter_rows(source_counter, key="source_page"),
            "exam_type_breakdown": self._counter_rows(exam_type_counter, key="exam_type"),
            "exam_stage_breakdown": self._counter_rows(exam_stage_counter, key="exam_stage"),
            "pain_point_breakdown": self._counter_rows(pain_point_counter, key="pain_point"),
            "weekly_time_breakdown": self._counter_rows(weekly_time_counter, key="weekly_time"),
        }

    async def _load_rows(self, *, days: int) -> tuple[str, list[dict[str, Any]]]:
        safe_days = max(1, min(int(days or 365), 3650))
        if self.is_supabase_configured:
            try:
                return "supabase", await self._load_supabase_rows(days=safe_days)
            except Exception:
                if self.is_database_configured:
                    try:
                        return "database_fallback", await self._load_database_rows(days=safe_days)
                    except Exception:
                        fallback = self._load_jsonl_rows(days=safe_days)
                        if fallback:
                            return "supabase_database_error_jsonl_fallback", fallback
                        raise
                fallback = self._load_jsonl_rows(days=safe_days)
                if fallback:
                    return "supabase_error_jsonl_fallback", fallback
                raise
        if self.is_database_configured:
            try:
                return "database", await self._load_database_rows(days=safe_days)
            except Exception:
                fallback = self._load_jsonl_rows(days=safe_days)
                if fallback:
                    return "database_error_jsonl_fallback", fallback
                raise
        fallback = self._load_jsonl_rows(days=safe_days)
        if fallback:
            return "jsonl_fallback", fallback
        return "unconfigured", []

    async def _load_supabase_rows(self, *, days: int) -> list[dict[str, Any]]:
        created_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        client = await self._get_client()
        response = await client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/invite_test_applications",
            headers=_supabase_rest_headers(self._service_key),
            params={
                "select": _SELECT_COLUMNS,
                "created_at": f"gte.{created_after}",
                "order": "created_at.desc",
                "limit": "2000",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]

    async def _load_database_rows(self, *, days: int) -> list[dict[str, Any]]:
        created_after = datetime.now(timezone.utc) - timedelta(days=days)
        return await asyncio.to_thread(self._load_database_rows_sync, created_after)

    def _load_database_rows_sync(self, created_after: datetime) -> list[dict[str, Any]]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            return self._load_database_rows_sync_psycopg2(created_after)

        with psycopg.connect(
            self._database_url,
            row_factory=dict_row,
            connect_timeout=max(1, int(self._timeout_s)),
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    select {_SELECT_COLUMNS}
                    from public.invite_test_applications
                    where created_at >= %s
                    order by created_at desc
                    limit %s
                    """,
                    (created_after, 2000),
                )
                return [dict(row) for row in cursor.fetchall()]

    def _load_database_rows_sync_psycopg2(self, created_after: datetime) -> list[dict[str, Any]]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError("psycopg is required for invite-test DB URL reads") from exc

        conn = psycopg2.connect(self._database_url, connect_timeout=max(1, int(self._timeout_s)))
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
                    select {_SELECT_COLUMNS}
                    from public.invite_test_applications
                    where created_at >= %s
                    order by created_at desc
                    limit %s
                    """,
                    (created_after, 2000),
                )
                return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _load_jsonl_rows(self, *, days: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows: list[dict[str, Any]] = []
        for path in self._candidate_jsonl_paths():
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict):
                    continue
                created_at = _parse_created_at(_field(item, "created_at", "createdAt"))
                if created_at is not None and created_at.astimezone(timezone.utc) < cutoff:
                    continue
                rows.append(item)
        rows.sort(key=lambda item: _text(_field(item, "created_at", "createdAt")), reverse=True)
        return rows

    def _candidate_jsonl_paths(self) -> list[Path]:
        if self._jsonl_path:
            return [Path(self._jsonl_path)]
        return list(_DEFAULT_JSONL_PATHS)

    @staticmethod
    def _filter_rows(
        rows: list[dict[str, Any]],
        *,
        status: str | None = None,
        source_page: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        status_filter = _text(status).lower()
        source_filter = _text(source_page).lower()
        query = _text(q).lower()
        result: list[dict[str, Any]] = []
        for row in rows:
            if status_filter and _text(_field(row, "status")).lower() != status_filter:
                continue
            if source_filter and _text(_field(row, "source_page", "sourcePage")).lower() != source_filter:
                continue
            if query:
                haystack = " ".join(
                    [
                        _text(_field(row, "name")),
                        _text(_field(row, "phone")),
                        _text(_field(row, "email")),
                        _text(_field(row, "wechat_id", "wechatId")),
                        _text(_field(row, "exam_type", "examType")),
                        _text(_field(row, "exam_stage", "examStage")),
                        _text(_field(row, "pain_point", "painPoint")),
                    ]
                ).lower()
                if query not in haystack:
                    continue
            result.append(row)
        return result

    @staticmethod
    def _counter_rows(counter: Counter[str], *, key: str) -> list[dict[str, Any]]:
        return [
            {key: label, "count": count}
            for label, count in counter.most_common()
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        self._owns_client = True
        return self._client
