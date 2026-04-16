from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx


def _service_key_from_env(explicit: str | None = None) -> str:
    return str(
        explicit
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.getenv("SUPABASE_KEY", "")
        or ""
    ).strip()


def _rest_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def _select_params(
    *,
    filters: dict[str, str] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"select": "*"}
    for key, value in dict(filters or {}).items():
        params[key] = value
    if order_by:
        params["order"] = order_by
    if limit is not None:
        params["limit"] = max(int(limit), 0)
    return params


def _nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goal_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or "").strip(),
        "user_id": str(row.get("user_id") or "").strip(),
        "goal_type": str(row.get("goal_type") or "").strip(),
        "title": str(row.get("title") or "").strip(),
        "target_node_codes": list(row.get("target_node_codes") or []),
        "target_question_count": int(row.get("target_question_count") or 0),
        "progress": row.get("progress", 0),
        "deadline": _nullable_text(row.get("deadline")),
        "created_at": _nullable_text(row.get("created_at")),
        "completed_at": _nullable_text(row.get("completed_at")),
    }


def _progress_from_row(row: dict[str, Any]) -> dict[str, Any]:
    knowledge_map = dict(row.get("knowledge_map") or {})
    progress = {
        "user_id": str(row.get("user_id") or "").strip(),
        "mastery_level": row.get("mastery_level", 0),
        "knowledge_map": knowledge_map,
        "current_question_context": dict(row.get("current_question_context") or {}),
        "radar_history": list(row.get("radar_history") or []),
        "total_attempts": int(row.get("total_attempts") or 0),
        "error_count": int(row.get("error_count") or 0),
        "last_practiced_at": _nullable_text(row.get("last_practiced_at")),
        "last_updated": _nullable_text(row.get("last_updated")),
        "tag": _nullable_text(row.get("tag")),
    }
    if isinstance(knowledge_map.get("today"), dict):
        progress["today"] = dict(knowledge_map["today"])
    if isinstance(knowledge_map.get("chapters"), list):
        progress["chapters"] = list(knowledge_map["chapters"])
    return progress


def _progress_to_row(user_id: str, progress: dict[str, Any]) -> dict[str, Any]:
    knowledge_map = dict(progress.get("knowledge_map") or {})
    if isinstance(progress.get("today"), dict):
        knowledge_map["today"] = dict(progress["today"])
    if isinstance(progress.get("chapters"), list):
        knowledge_map["chapters"] = list(progress["chapters"])
    return {
        "user_id": user_id,
        "mastery_level": progress.get("mastery_level", 0),
        "knowledge_map": knowledge_map,
        "current_question_context": dict(progress.get("current_question_context") or {}),
        "radar_history": list(progress.get("radar_history") or []),
        "total_attempts": int(progress.get("total_attempts") or 0),
        "error_count": int(progress.get("error_count") or 0),
        "last_practiced_at": _nullable_text(progress.get("last_practiced_at")),
        "last_updated": str(progress.get("last_updated") or _iso_now()).strip(),
        "tag": str(progress.get("tag") or "").strip(),
    }


class LearnerStateSupabaseClient:
    """Minimal async PostgREST client for learner-state tables."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip()
        self._service_key = _service_key_from_env(service_key)
        self._client = client
        self._timeout_s = float(timeout_s)
        self._owns_client = client is None

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def select_rows(
        self,
        table: str,
        *,
        filters: dict[str, str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            table,
            params=_select_params(filters=filters, order_by=order_by, limit=limit),
        )
        data = response.json()
        if not isinstance(data, list):
            return []
        return [dict(item) for item in data if isinstance(item, dict)]

    async def upsert_rows(
        self,
        table: str,
        *,
        rows: list[dict[str, Any]],
        on_conflict: str,
    ) -> list[dict[str, Any]]:
        response = await self._request(
            "POST",
            table,
            params={"on_conflict": on_conflict},
            json=rows,
        )
        data = response.json()
        if not isinstance(data, list):
            return []
        return [dict(item) for item in data if isinstance(item, dict)]

    async def upsert_row(
        self,
        table: str,
        *,
        row: dict[str, Any],
        on_conflict: str,
    ) -> dict[str, Any]:
        rows = await self.upsert_rows(table, rows=[row], on_conflict=on_conflict)
        return rows[0] if rows else dict(row)

    async def delete_rows(self, table: str, *, filters: dict[str, str]) -> None:
        await self._request("DELETE", table, params=dict(filters))

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        if not self._base_url:
            raise ValueError("SUPABASE_URL is missing")
        if not self._service_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY is missing")
        client = await self._get_client()
        response = await client.request(
            method,
            f"{self._base_url.rstrip('/')}/rest/v1/{table}",
            headers=_rest_headers(self._service_key),
            params=params,
            json=json,
        )
        response.raise_for_status()
        return response

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        self._owns_client = True
        return self._client


class LearnerStateSupabaseCoreStore:
    """Async Supabase-backed store for reused learner core tables."""

    def __init__(self, client: LearnerStateSupabaseClient | None = None, **client_kwargs: Any) -> None:
        self._client = client or LearnerStateSupabaseClient(**client_kwargs)

    @property
    def client(self) -> LearnerStateSupabaseClient:
        return self._client

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    async def aclose(self) -> None:
        await self._client.aclose()

    async def read_profile(self, user_id: str) -> dict[str, Any]:
        rows = await self._client.select_rows("user_profiles", filters={"user_id": f"eq.{user_id}"}, limit=1)
        return rows[0] if rows else {}

    async def upsert_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        row = dict(profile or {})
        row["user_id"] = str(user_id).strip()
        rows = await self._client.upsert_rows("user_profiles", rows=[row], on_conflict="user_id")
        return rows[0] if rows else row

    async def merge_profile(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = await self.read_profile(user_id)
        current.update(dict(patch or {}))
        return await self.upsert_profile(user_id, current)

    async def read_stats(self, user_id: str) -> dict[str, Any]:
        rows = await self._client.select_rows("user_stats", filters={"user_id": f"eq.{user_id}"}, limit=1)
        return _progress_from_row(rows[0]) if rows else {}

    async def upsert_stats(self, user_id: str, stats: dict[str, Any]) -> dict[str, Any]:
        row = _progress_to_row(str(user_id).strip(), stats)
        rows = await self._client.upsert_rows("user_stats", rows=[row], on_conflict="user_id")
        saved = rows[0] if rows else row
        return _progress_from_row(saved)

    async def merge_stats(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = await self.read_stats(user_id)
        current.update(dict(patch or {}))
        return await self.upsert_stats(user_id, current)

    async def read_goals(self, user_id: str) -> list[dict[str, Any]]:
        return await self._client.select_rows(
            "user_goals",
            filters={"user_id": f"eq.{user_id}"},
            order_by="created_at.desc",
        )

    async def upsert_goal(self, goal: dict[str, Any]) -> dict[str, Any]:
        row = dict(goal or {})
        if row.get("id") is None:
            row.pop("id", None)
        row["user_id"] = str(row.get("user_id") or "").strip()
        if not row["user_id"]:
            raise ValueError("user_id is required for user_goals")
        rows = await self._client.upsert_rows("user_goals", rows=[row], on_conflict="id")
        return rows[0] if rows else row

    async def delete_goal(self, goal_id: str) -> None:
        await self._client.delete_rows("user_goals", filters={"id": f"eq.{str(goal_id).strip()}"} )


class LearnerStateSupabaseSyncCoreStore:
    """Sync adapter used by LearnerStateService for reused learner core tables."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.Client | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip()
        self._service_key = _service_key_from_env(service_key)
        self._client = client
        self._timeout_s = float(timeout_s)
        self._owns_client = client is None

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._service_key)

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def read_profile(self, user_id: str) -> dict[str, Any] | None:
        row = self._select_one("user_profiles", {"user_id": user_id})
        if row is None:
            return None
        attributes = dict(row.get("attributes") or {})
        profile = {
            **attributes,
            "user_id": str(row.get("user_id") or user_id).strip(),
            "summary": str(row.get("summary") or "").strip(),
            "last_updated": _nullable_text(row.get("last_updated")),
        }
        profile.setdefault("display_name", profile["user_id"])
        return profile

    def write_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        attributes = dict(profile.get("attributes") or {})
        for key, value in dict(profile or {}).items():
            if key in {"user_id", "id", "summary", "last_updated", "attributes"}:
                continue
            attributes[key] = value
        row = {
            "user_id": normalized_user_id,
            "summary": str(profile.get("summary") or "").strip(),
            "attributes": attributes,
            "last_updated": str(profile.get("last_updated") or _iso_now()).strip(),
        }
        rows = self._upsert("user_profiles", [row], on_conflict="user_id")
        saved = rows[0] if rows else row
        return {
            **dict(saved.get("attributes") or {}),
            "user_id": normalized_user_id,
            "summary": str(saved.get("summary") or "").strip(),
            "last_updated": str(saved.get("last_updated") or row["last_updated"]).strip(),
        }

    def read_progress(self, user_id: str) -> dict[str, Any] | None:
        row = self._select_one("user_stats", {"user_id": user_id})
        if row is None:
            return None
        return _progress_from_row(row)

    def write_progress(self, user_id: str, progress: dict[str, Any]) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        row = _progress_to_row(normalized_user_id, progress)
        rows = self._upsert("user_stats", [row], on_conflict="user_id")
        saved = rows[0] if rows else row
        return _progress_from_row(saved)

    def read_goals(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._select_many("user_goals", {"user_id": user_id}, order="created_at.desc")
        return [_goal_from_row(row) for row in rows]

    def upsert_goal(self, user_id: str, goal: dict[str, Any]) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        raw_goal_id = goal.get("id")
        row = {
            "user_id": normalized_user_id,
            "goal_type": str(goal.get("goal_type") or "study_goal").strip() or "study_goal",
            "title": str(goal.get("title") or "").strip(),
            "target_node_codes": list(goal.get("target_node_codes") or []),
            "target_question_count": int(goal.get("target_question_count") or 0),
            "progress": goal.get("progress", 0),
            "deadline": _nullable_text(goal.get("deadline")),
            "created_at": str(goal.get("created_at") or _iso_now()).strip(),
            "completed_at": _nullable_text(goal.get("completed_at")),
        }
        if raw_goal_id is not None:
            row["id"] = raw_goal_id if isinstance(raw_goal_id, int) else str(raw_goal_id).strip()
        rows = self._upsert("user_goals", [row], on_conflict="id")
        saved = rows[0] if rows else row
        return _goal_from_row(saved)

    def delete_goal(self, goal_id: str) -> None:
        normalized_goal_id = str(goal_id or "").strip()
        if not normalized_goal_id:
            return
        if not self.is_configured:
            raise RuntimeError("Supabase core store is not configured")
        client = self._client_or_create()
        response = client.delete(
            f"{self._base_url.rstrip('/')}/rest/v1/user_goals",
            headers=_rest_headers(self._service_key),
            params={"id": f"eq.{normalized_goal_id}"},
        )
        response.raise_for_status()

    def _client_or_create(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(timeout=self._timeout_s)
        self._owns_client = True
        return self._client

    def _select_one(self, table: str, filters: dict[str, Any]) -> dict[str, Any] | None:
        rows = self._select_many(table, filters, limit=1)
        return rows[0] if rows else None

    def _select_many(
        self,
        table: str,
        filters: dict[str, Any],
        *,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []
        client = self._client_or_create()
        response = client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/{table}",
            headers=_rest_headers(self._service_key),
            params=_select_params(
                filters={str(key): f"eq.{value}" for key, value in dict(filters or {}).items()},
                order_by=order,
                limit=limit,
            ),
        )
        response.raise_for_status()
        payload = response.json()
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _upsert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> list[dict[str, Any]]:
        if not self.is_configured:
            raise RuntimeError("Supabase core store is not configured")
        client = self._client_or_create()
        response = client.post(
            f"{self._base_url.rstrip('/')}/rest/v1/{table}",
            headers=_rest_headers(self._service_key),
            params={"on_conflict": on_conflict},
            json=rows,
        )
        response.raise_for_status()
        payload = response.json()
        return [dict(item) for item in payload if isinstance(item, dict)]


__all__ = [
    "LearnerStateSupabaseClient",
    "LearnerStateSupabaseCoreStore",
    "LearnerStateSupabaseSyncCoreStore",
]
