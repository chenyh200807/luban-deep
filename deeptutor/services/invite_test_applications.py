from __future__ import annotations

import json
import os
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import httpx

from deeptutor.services.feedback_service import _supabase_rest_headers, _supabase_service_key
from deeptutor.services.runtime_env import is_production_environment


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
_REQUIRED_FIELDS = ("name", "phone", "email", "wechat_id", "exam_type", "exam_stage", "pain_point", "weekly_time")
_MAX_LENGTHS = {
    "name": 80,
    "phone": 24,
    "email": 160,
    "province": 80,
    "age_range": 40,
    "education": 80,
    "occupation": 120,
    "exam_type": 80,
    "exam_stage": 80,
    "preparation_years": 80,
    "knowledge_foundation": 80,
    "pain_point": 80,
    "weekly_time": 80,
    "daily_study_time": 80,
    "current_method": 800,
    "study_difficulties": 1000,
    "wechat_id": 120,
    "is_yousen_member": 80,
    "exam_date": 80,
    "latest_wrong_question": 1400,
    "source_page": 120,
    "utm_source": 120,
    "utm_campaign": 120,
}
_CAMEL_KEYS = {
    "source_page": "sourcePage",
    "utm_source": "utmSource",
    "utm_campaign": "utmCampaign",
    "age_range": "ageRange",
    "wechat_id": "wechatId",
    "exam_type": "examType",
    "exam_stage": "examStage",
    "preparation_years": "preparationYears",
    "knowledge_foundation": "knowledgeFoundation",
    "pain_point": "painPoint",
    "weekly_time": "weeklyTime",
    "daily_study_time": "dailyStudyTime",
    "current_method": "currentMethod",
    "study_difficulties": "studyDifficulties",
    "latest_wrong_question": "latestWrongQuestion",
    "is_yousen_member": "isYousenMember",
    "exam_date": "examDate",
    "accept_interview": "acceptInterview",
}


class InviteTestApplicationValidationError(ValueError):
    """Raised when a public invite-test application payload is invalid."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clean_string(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()[:max_length]


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


def _payload_value(payload: Mapping[str, Any], snake_key: str) -> Any:
    return _field(payload, snake_key, _CAMEL_KEYS.get(snake_key))


def _raw_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _field(row, "raw_payload", "rawPayload")
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


def _raw_field(row: Mapping[str, Any], snake_key: str) -> Any:
    raw = _raw_payload(row)
    return _field(row, snake_key, _CAMEL_KEYS.get(snake_key)) or _field(raw, snake_key, _CAMEL_KEYS.get(snake_key))


def build_invite_test_application_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_page": _clean_string(_payload_value(payload, "source_page"), _MAX_LENGTHS["source_page"]),
        "utm_source": _clean_string(_payload_value(payload, "utm_source"), _MAX_LENGTHS["utm_source"]),
        "utm_campaign": _clean_string(_payload_value(payload, "utm_campaign"), _MAX_LENGTHS["utm_campaign"]),
        "name": _clean_string(_payload_value(payload, "name"), _MAX_LENGTHS["name"]),
        "phone": _clean_string(_payload_value(payload, "phone"), _MAX_LENGTHS["phone"]).replace(" ", ""),
        "email": _clean_string(_payload_value(payload, "email"), _MAX_LENGTHS["email"]).lower(),
        "wechat_id": _clean_string(_payload_value(payload, "wechat_id"), _MAX_LENGTHS["wechat_id"]),
        "exam_type": _clean_string(_payload_value(payload, "exam_type"), _MAX_LENGTHS["exam_type"]),
        "exam_stage": _clean_string(_payload_value(payload, "exam_stage"), _MAX_LENGTHS["exam_stage"]),
        "pain_point": _clean_string(_payload_value(payload, "pain_point"), _MAX_LENGTHS["pain_point"]),
        "weekly_time": _clean_string(_payload_value(payload, "weekly_time"), _MAX_LENGTHS["weekly_time"]),
        "current_method": _clean_string(_payload_value(payload, "current_method"), _MAX_LENGTHS["current_method"]),
        "latest_wrong_question": _clean_string(
            _payload_value(payload, "latest_wrong_question"),
            _MAX_LENGTHS["latest_wrong_question"],
        ),
        "is_yousen_member": _clean_string(
            _payload_value(payload, "is_yousen_member"),
            _MAX_LENGTHS["is_yousen_member"],
        ),
        "exam_date": _clean_string(_payload_value(payload, "exam_date"), _MAX_LENGTHS["exam_date"]),
        "accept_interview": _bool(_payload_value(payload, "accept_interview")),
        "consent": _bool(_payload_value(payload, "consent")),
        "status": "submitted",
        "operator_note": "",
        "submit_count": 1,
    }
    record["raw_payload"] = {
        _CAMEL_KEYS.get(key, key): value
        for key, value in record.items()
        if key
        in {
            "source_page",
            "utm_source",
            "utm_campaign",
            "name",
            "phone",
            "email",
            "province",
            "age_range",
            "education",
            "occupation",
            "wechat_id",
            "exam_type",
            "exam_stage",
            "preparation_years",
            "knowledge_foundation",
            "pain_point",
            "weekly_time",
            "daily_study_time",
            "current_method",
            "study_difficulties",
            "latest_wrong_question",
            "is_yousen_member",
            "exam_date",
            "accept_interview",
            "consent",
        }
    }
    for key in (
        "province",
        "age_range",
        "education",
        "occupation",
        "preparation_years",
        "knowledge_foundation",
        "daily_study_time",
        "study_difficulties",
    ):
        record["raw_payload"][_CAMEL_KEYS.get(key, key)] = _clean_string(
            _payload_value(payload, key),
            _MAX_LENGTHS[key],
        )

    missing_field = next((field for field in _REQUIRED_FIELDS if not record[field]), "")
    if missing_field:
        raise InviteTestApplicationValidationError(f"缺少必填字段：{_CAMEL_KEYS.get(missing_field, missing_field)}")
    if not record["phone"].isdigit() or len(record["phone"]) != 11 or not record["phone"].startswith("1"):
        raise InviteTestApplicationValidationError("手机号格式不正确。")
    if "@" not in record["email"] or "." not in record["email"].rsplit("@", 1)[-1]:
        raise InviteTestApplicationValidationError("邮箱格式不正确。")
    if not record["consent"]:
        raise InviteTestApplicationValidationError("请先同意内测筛选与产品改进用途。")
    return record


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
        "province": _text(_raw_field(row, "province")),
        "age_range": _text(_raw_field(row, "age_range")),
        "education": _text(_raw_field(row, "education")),
        "occupation": _text(_raw_field(row, "occupation")),
        "wechat_id": wechat_id if reveal_contact else _mask_optional(wechat_id),
        "exam_type": _text(_field(row, "exam_type", "examType")),
        "exam_stage": _text(_field(row, "exam_stage", "examStage")),
        "preparation_years": _text(_raw_field(row, "preparation_years")),
        "knowledge_foundation": _text(_raw_field(row, "knowledge_foundation")),
        "pain_point": _text(_field(row, "pain_point", "painPoint")),
        "weekly_time": _text(_field(row, "weekly_time", "weeklyTime")),
        "daily_study_time": _text(_raw_field(row, "daily_study_time")),
        "current_method": _text(_field(row, "current_method", "currentMethod")),
        "study_difficulties": _text(_raw_field(row, "study_difficulties")),
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

    async def submit_application(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = build_invite_test_application_record(payload)
        attempted: list[str] = []
        last_error: Exception | None = None
        if self.is_supabase_configured:
            attempted.append("supabase")
            try:
                await self._save_supabase_record(record)
                return {"ok": True, "id": record["id"], "storage_status": "supabase"}
            except Exception as exc:
                last_error = exc
        if self.is_database_configured:
            attempted.append("database")
            try:
                await self._save_database_record(record)
                storage_status = "database"
                if attempted and attempted[0] == "supabase":
                    storage_status = "supabase_error_database_fallback"
                return {"ok": True, "id": record["id"], "storage_status": storage_status}
            except Exception as exc:
                last_error = exc
        if self._save_jsonl_record(record):
            if attempted == ["supabase", "database"]:
                storage_status = "supabase_database_error_jsonl_fallback"
            elif attempted == ["supabase"]:
                storage_status = "supabase_error_jsonl_fallback"
            elif attempted == ["database"]:
                storage_status = "database_error_jsonl_fallback"
            else:
                storage_status = "jsonl_fallback"
            return {"ok": True, "id": record["id"], "storage_status": storage_status}
        if last_error is not None:
            raise RuntimeError("申请提交通道暂时不可用，请稍后再试。") from last_error
        raise RuntimeError("申请提交通道未配置，请稍后再试。")

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

    async def _save_supabase_record(self, record: dict[str, Any]) -> None:
        record["submit_count"] = await self._count_supabase_submissions_by_phone(record["phone"]) + 1
        client = await self._get_client()
        response = await client.post(
            f"{self._base_url.rstrip('/')}/rest/v1/invite_test_applications",
            headers=_supabase_rest_headers(self._service_key, prefer="return=representation"),
            json=record,
        )
        response.raise_for_status()

    async def _count_supabase_submissions_by_phone(self, phone: str) -> int:
        client = await self._get_client()
        response = await client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/invite_test_applications",
            headers=_supabase_rest_headers(self._service_key),
            params={"select": "id", "phone": f"eq.{phone}", "limit": "10000"},
        )
        response.raise_for_status()
        payload = response.json()
        return len(payload) if isinstance(payload, list) else 0

    async def _load_database_rows(self, *, days: int) -> list[dict[str, Any]]:
        created_after = datetime.now(timezone.utc) - timedelta(days=days)
        return await asyncio.to_thread(self._load_database_rows_sync, created_after)

    async def _save_database_record(self, record: dict[str, Any]) -> None:
        await asyncio.to_thread(self._save_database_record_sync, record)

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

    def _save_database_record_sync(self, record: dict[str, Any]) -> None:
        try:
            import psycopg
        except ImportError:
            return self._save_database_record_sync_psycopg2(record)

        with psycopg.connect(self._database_url, connect_timeout=max(1, int(self._timeout_s))) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select count(*)::int from public.invite_test_applications where phone = %s",
                    (record["phone"],),
                )
                row = cursor.fetchone()
                record["submit_count"] = int(row[0] if row else 0) + 1
                cursor.execute(self._insert_sql(), self._insert_values(record))
            conn.commit()

    def _save_database_record_sync_psycopg2(self, record: dict[str, Any]) -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("psycopg is required for invite-test DB URL writes") from exc

        conn = psycopg2.connect(self._database_url, connect_timeout=max(1, int(self._timeout_s)))
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select count(*)::int from public.invite_test_applications where phone = %s",
                    (record["phone"],),
                )
                row = cursor.fetchone()
                record["submit_count"] = int(row[0] if row else 0) + 1
                cursor.execute(self._insert_sql(), self._insert_values(record))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _insert_sql() -> str:
        return """
            insert into public.invite_test_applications (
                id, created_at, source_page, utm_source, utm_campaign, name, phone,
                email, wechat_id, exam_type, exam_stage, pain_point, weekly_time,
                current_method, latest_wrong_question, is_yousen_member, exam_date,
                accept_interview, consent, status, operator_note, submit_count, raw_payload
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
        """

    @staticmethod
    def _insert_values(record: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            record["id"],
            record["created_at"],
            record["source_page"],
            record["utm_source"],
            record["utm_campaign"],
            record["name"],
            record["phone"],
            record["email"],
            record["wechat_id"],
            record["exam_type"],
            record["exam_stage"],
            record["pain_point"],
            record["weekly_time"],
            record["current_method"],
            record["latest_wrong_question"],
            record["is_yousen_member"],
            record["exam_date"],
            record["accept_interview"],
            record["consent"],
            record["status"],
            record["operator_note"],
            record["submit_count"],
            json.dumps(record["raw_payload"], ensure_ascii=False),
        )

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

    def _save_jsonl_record(self, record: Mapping[str, Any]) -> bool:
        if is_production_environment() and not self._jsonl_path:
            return False
        path = self._candidate_jsonl_paths()[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True

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
                        _text(_raw_field(row, "province")),
                        _text(_raw_field(row, "occupation")),
                        _text(_raw_field(row, "knowledge_foundation")),
                        _text(_field(row, "exam_type", "examType")),
                        _text(_field(row, "exam_stage", "examStage")),
                        _text(_field(row, "pain_point", "painPoint")),
                        _text(_raw_field(row, "study_difficulties")),
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
