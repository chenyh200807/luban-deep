"""鲁班内测回访问卷读模型（public.luban_feedback）。

仿 InviteTestApplicationStore：连同一个 Supabase（REST 优先，pg 直连兜底），
为 BI 看板提供统计聚合、回访池列表（联系方式按需脱敏）与运营跟进（status/operator_note）。

本模块只做读 + 跟进；问卷写入由 web/app/api/feedback/responses/route.ts 负责，互不耦合。
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import httpx

from deeptutor.services.feedback_service import _supabase_rest_headers, _supabase_service_key

_TABLE = "public.luban_feedback"
_SELECT_COLUMNS = (
    "id,created_at,source_page,survey_version,nps,overall_satisfaction,"
    "most_valuable,will_continue,pay_willingness,would_recommend,revisit_willingness,"
    "attempt_count,exam_timeframe,top_suggestion,unsolved_pain,"
    "phone,wechat_id,status,operator_note,raw_payload"
)
# REST select 用逗号列表；usage_frequency 列仍在表中但问卷已下线，读模型不暴露。

_STATUS_VALUES = {"submitted", "contacted", "interviewed", "resolved", "archived"}
_MAX_OPERATOR_NOTE = 1000
_PROMOTER_MIN = 9
_PASSIVE_MIN = 7
_REVISIT_WILLING = {"very_willing", "ok"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mask_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{digits[:3]}****{digits[-2:]}"


def _mask_optional(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return value[0] + "*"
    return value[0] + "*" * (len(value) - 2) + value[-1]


def _raw_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("raw_payload")
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, Mapping) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def normalize_luban_feedback(row: Mapping[str, Any], *, reveal_contact: bool = False) -> dict[str, Any]:
    """把一行答卷归一化为 BI 视图，联系方式按 reveal_contact 脱敏。"""
    raw = _raw_payload(row)
    phone = _text(row.get("phone"))
    wechat = _text(row.get("wechat_id"))
    return {
        "id": _text(row.get("id")),
        "created_at": _text(row.get("created_at")),
        "source_page": _text(row.get("source_page")),
        "survey_version": _text(row.get("survey_version")),
        "nps": _int_or_none(row.get("nps")),
        "overall_satisfaction": _int_or_none(row.get("overall_satisfaction")),
        "most_valuable": _text(row.get("most_valuable")),
        "will_continue": _text(row.get("will_continue")),
        "pay_willingness": _text(row.get("pay_willingness")),
        "would_recommend": _text(row.get("would_recommend")),
        "revisit_willingness": _text(row.get("revisit_willingness")),
        "attempt_count": _text(row.get("attempt_count")),
        "exam_timeframe": _text(row.get("exam_timeframe")),
        "one_word": _text(raw.get("one_word")),
        "top_suggestion": _text(row.get("top_suggestion")),
        "unsolved_pain": _text(row.get("unsolved_pain")),
        "phone": phone if reveal_contact else _mask_phone(phone),
        "wechat_id": wechat if reveal_contact else _mask_optional(wechat),
        "status": _text(row.get("status")) or "submitted",
        "operator_note": _text(row.get("operator_note")),
        "contact_revealed": reveal_contact,
    }


def _counter_rows(counter: Counter[str], *, key: str) -> list[dict[str, Any]]:
    return [{key: label, "count": count} for label, count in counter.most_common()]


def compute_luban_feedback_stats(normalized: list[dict[str, Any]]) -> dict[str, Any]:
    """从已归一化（脱敏无关）的答卷列表算 BI 聚合。抽成纯函数便于单测。"""
    total = len(normalized)
    nps_values = [n["nps"] for n in normalized if n["nps"] is not None]
    nps_base = len(nps_values)
    promoters = sum(1 for v in nps_values if v >= _PROMOTER_MIN)
    passives = sum(1 for v in nps_values if _PASSIVE_MIN <= v < _PROMOTER_MIN)
    detractors = sum(1 for v in nps_values if v < _PASSIVE_MIN)
    nps_score = round((promoters - detractors) / nps_base * 100, 1) if nps_base else 0.0

    sat_values = [n["overall_satisfaction"] for n in normalized if n["overall_satisfaction"] is not None]
    avg_satisfaction = round(sum(sat_values) / len(sat_values), 2) if sat_values else 0.0

    revisit_willing = sum(1 for n in normalized if n["revisit_willingness"] in _REVISIT_WILLING)
    with_contact = sum(1 for n in normalized if n["phone"] or n["wechat_id"])

    nps_counter = Counter(str(v) for v in nps_values)
    sat_counter = Counter(str(v) for v in sat_values)
    most_valuable_counter = Counter(n["most_valuable"] or "unknown" for n in normalized)
    will_continue_counter = Counter(n["will_continue"] or "unknown" for n in normalized)
    pay_willingness_counter = Counter(n["pay_willingness"] or "unknown" for n in normalized)
    revisit_counter = Counter(n["revisit_willingness"] or "unknown" for n in normalized)
    attempt_counter = Counter(n["attempt_count"] or "unknown" for n in normalized)
    timeframe_counter = Counter(n["exam_timeframe"] or "unknown" for n in normalized)
    status_counter = Counter(n["status"] or "submitted" for n in normalized)
    source_counter = Counter(n["source_page"] or "unknown" for n in normalized)

    return {
        "summary": {
            "total_responses": total,
            "nps_score": nps_score,
            "nps_base": nps_base,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "avg_satisfaction": avg_satisfaction,
            "satisfaction_base": len(sat_values),
            "revisit_willing_count": revisit_willing,
            "revisit_willing_rate": round(revisit_willing / total, 4) if total else 0,
            "with_contact_count": with_contact,
            "with_contact_rate": round(with_contact / total, 4) if total else 0,
        },
        "nps_breakdown": _counter_rows(nps_counter, key="nps"),
        "satisfaction_breakdown": _counter_rows(sat_counter, key="overall_satisfaction"),
        "most_valuable_breakdown": _counter_rows(most_valuable_counter, key="most_valuable"),
        "will_continue_breakdown": _counter_rows(will_continue_counter, key="will_continue"),
        "pay_willingness_breakdown": _counter_rows(pay_willingness_counter, key="pay_willingness"),
        "revisit_willingness_breakdown": _counter_rows(revisit_counter, key="revisit_willingness"),
        "attempt_count_breakdown": _counter_rows(attempt_counter, key="attempt_count"),
        "exam_timeframe_breakdown": _counter_rows(timeframe_counter, key="exam_timeframe"),
        "status_breakdown": _counter_rows(status_counter, key="status"),
        "source_breakdown": _counter_rows(source_counter, key="source_page"),
    }


def validate_luban_feedback_patch(payload: Mapping[str, Any]) -> dict[str, Any]:
    """跟进只允许改 status / operator_note，其余忽略。"""
    patch: dict[str, Any] = {}
    if "status" in payload:
        status = _text(payload.get("status")).lower()
        if status not in _STATUS_VALUES:
            raise ValueError(f"Unsupported status: {status or '(empty)'}")
        patch["status"] = status
    if "operator_note" in payload:
        patch["operator_note"] = _text(payload.get("operator_note"))[:_MAX_OPERATOR_NOTE]
    if not patch:
        raise ValueError("No editable fields provided (status / operator_note)")
    return patch


class LubanFeedbackStore:
    """内测回访答卷读模型：REST 优先，pg 直连兜底。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        database_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = _text(base_url or os.getenv("SUPABASE_URL"))
        self._service_key = _supabase_service_key(service_key)
        self._database_url = _text(
            database_url
            or os.getenv("FEEDBACK_DATABASE_URL")
            or os.getenv("SUPABASE_DB_URL")
            or os.getenv("DB_URL")
        )
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

    async def list_responses(
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
            normalize_luban_feedback(row, reveal_contact=reveal_contact)
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
        visible_rows = self._filter_rows(rows)
        normalized = [normalize_luban_feedback(row, reveal_contact=False) for row in visible_rows]
        stats = compute_luban_feedback_stats(normalized)
        return {
            "window_days": max(1, min(int(days or 365), 3650)),
            "storage_status": storage_status,
            **stats,
        }

    async def update_response(self, response_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        patch = validate_luban_feedback_patch(payload)
        rid = _text(response_id)
        if not rid:
            raise ValueError("Missing response id")
        if self.is_supabase_configured:
            try:
                return await self._update_supabase_record(rid, patch)
            except KeyError:
                raise
            except Exception:
                if not self.is_database_configured:
                    raise
        if self.is_database_configured:
            return await asyncio.to_thread(self._update_database_record_sync, rid, patch)
        raise RuntimeError("回访跟进通道未配置，请稍后再试。")

    # ---------- 加载 ----------

    async def _load_rows(self, *, days: int) -> tuple[str, list[dict[str, Any]]]:
        safe_days = max(1, min(int(days or 365), 3650))
        if self.is_supabase_configured:
            try:
                return "supabase", await self._load_supabase_rows(days=safe_days)
            except Exception:
                if self.is_database_configured:
                    return "database_fallback", await self._load_database_rows(days=safe_days)
                raise
        if self.is_database_configured:
            return "database", await self._load_database_rows(days=safe_days)
        return "unconfigured", []

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        self._owns_client = True
        return self._client

    async def _load_supabase_rows(self, *, days: int) -> list[dict[str, Any]]:
        created_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        client = await self._get_client()
        response = await client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/luban_feedback",
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
                    from {_TABLE}
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
            raise RuntimeError("psycopg is required for luban-feedback DB URL reads") from exc

        conn = psycopg2.connect(self._database_url, connect_timeout=max(1, int(self._timeout_s)))
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""
                    select {_SELECT_COLUMNS}
                    from {_TABLE}
                    where created_at >= %s
                    order by created_at desc
                    limit %s
                    """,
                    (created_after, 2000),
                )
                return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ---------- 跟进更新 ----------

    async def _update_supabase_record(self, response_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.patch(
            f"{self._base_url.rstrip('/')}/rest/v1/luban_feedback",
            headers=_supabase_rest_headers(self._service_key, prefer="return=representation"),
            params={"id": f"eq.{response_id}", "select": _SELECT_COLUMNS},
            json=dict(patch),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise KeyError(response_id)
        return {"after": normalize_luban_feedback(dict(payload[0]), reveal_contact=True)}

    def _update_database_record_sync(self, response_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            return self._update_database_record_sync_psycopg2(response_id, patch)

        assignments = ", ".join(f"{key} = %s" for key in patch)
        values = list(patch.values())
        with psycopg.connect(
            self._database_url,
            row_factory=dict_row,
            connect_timeout=max(1, int(self._timeout_s)),
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"update {_TABLE} set {assignments} where id = %s returning {_SELECT_COLUMNS}",
                    (*values, response_id),
                )
                after = cursor.fetchone()
            conn.commit()
        if not after:
            raise KeyError(response_id)
        return {"after": normalize_luban_feedback(dict(after), reveal_contact=True)}

    def _update_database_record_sync_psycopg2(self, response_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError("psycopg is required for luban-feedback DB URL writes") from exc

        assignments = ", ".join(f"{key} = %s" for key in patch)
        values = list(patch.values())
        conn = psycopg2.connect(self._database_url, connect_timeout=max(1, int(self._timeout_s)))
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"update {_TABLE} set {assignments} where id = %s returning {_SELECT_COLUMNS}",
                    (*values, response_id),
                )
                after = cursor.fetchone()
            conn.commit()
        finally:
            conn.close()
        if not after:
            raise KeyError(response_id)
        return {"after": normalize_luban_feedback(dict(after), reveal_contact=True)}

    # ---------- 过滤 ----------

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
            row_status = _text(row.get("status")).lower() or "submitted"
            if not status_filter and row_status == "archived":
                continue
            if status_filter and row_status != status_filter:
                continue
            if source_filter and _text(row.get("source_page")).lower() != source_filter:
                continue
            if query:
                raw = _raw_payload(row)
                haystack = " ".join(
                    [
                        _text(row.get("top_suggestion")),
                        _text(row.get("unsolved_pain")),
                        _text(row.get("phone")),
                        _text(row.get("wechat_id")),
                        _text(raw.get("one_word")),
                    ]
                ).lower()
                if query not in haystack:
                    continue
            result.append(row)
        return result
