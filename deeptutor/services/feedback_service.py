from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID, uuid4

import httpx


def _supabase_service_key(explicit: str | None = None) -> str:
    return str(
        explicit
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.getenv("SUPABASE_KEY", "")
        or ""
    ).strip()


def _supabase_rest_headers(service_key: str, *, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def normalize_feedback_reason_tags(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        tag = str(raw or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized


def normalize_feedback_rating(value: int) -> int:
    if int(value or 0) > 0:
        return 1
    if int(value or 0) < 0:
        return -1
    return 0


def normalize_uuid_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return str(UUID(text))
    except (TypeError, ValueError):
        return None


def build_mobile_feedback_row(
    *,
    user_id: str,
    session_id: str | None = None,
    message_id: str | None = None,
    surface_message_id: str | None = None,
    turn_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    rating: int = 0,
    reason_tags: list[str] | None = None,
    comment: str = "",
    answer_mode: str = "AUTO",
    feedback_source: str = "wx_miniprogram_message_actions",
    requested_response_mode: str = "",
    effective_response_mode: str = "",
    response_mode_degrade_reason: str = "",
    actual_tool_rounds: int | None = None,
) -> dict[str, Any]:
    normalized_conversation_id = str(session_id or "").strip()
    normalized_message_id = str(message_id or "").strip()
    normalized_surface_message_id = str(surface_message_id or "").strip()
    normalized_turn_id = str(turn_id or "").strip()
    normalized_trace_id = str(trace_id or "").strip()
    normalized_request_id = str(request_id or "").strip()
    normalized_tags = normalize_feedback_reason_tags(reason_tags)
    normalized_rating = normalize_feedback_rating(rating)
    normalized_answer_mode = str(answer_mode or "AUTO").strip().upper() or "AUTO"
    normalized_feedback_source = str(feedback_source or "").strip() or "wx_miniprogram_message_actions"
    normalized_user_uuid = normalize_uuid_or_none(user_id)
    normalized_conversation_uuid = normalize_uuid_or_none(normalized_conversation_id)
    normalized_message_uuid = normalize_uuid_or_none(normalized_message_id)
    metadata = {
        "answer_mode": normalized_answer_mode,
        "requested_response_mode": str(requested_response_mode or "").strip().upper(),
        "effective_response_mode": str(effective_response_mode or "").strip().upper(),
        "response_mode_degrade_reason": str(response_mode_degrade_reason or "").strip(),
        "feedback_source": normalized_feedback_source[:80],
        "surface": "wx_miniprogram",
        "platform": "wechat_miniprogram",
        "source": "wx_miniprogram",
    }
    if actual_tool_rounds is not None:
        try:
            metadata["actual_tool_rounds"] = max(0, int(actual_tool_rounds))
        except (TypeError, ValueError):
            pass
    if user_id and normalized_user_uuid != user_id:
        metadata["deeptutor_user_id"] = user_id
    if normalized_conversation_id and normalized_conversation_uuid != normalized_conversation_id:
        metadata["deeptutor_session_id"] = normalized_conversation_id
    if normalized_message_id and normalized_message_uuid != normalized_message_id:
        metadata["deeptutor_message_id"] = normalized_message_id
    if normalized_surface_message_id and normalized_surface_message_id != normalized_message_id:
        metadata["surface_message_id"] = normalized_surface_message_id
    if normalized_turn_id:
        metadata["turn_id"] = normalized_turn_id
    if normalized_trace_id:
        metadata["trace_id"] = normalized_trace_id
    if normalized_request_id:
        metadata["request_id"] = normalized_request_id
    return {
        "id": str(uuid4()),
        "created_at": datetime.now().astimezone().isoformat(),
        "user_id": normalized_user_uuid,
        "conversation_id": normalized_conversation_uuid,
        "message_id": normalized_message_uuid,
        "rating": normalized_rating,
        "reason_tags": normalized_tags,
        "comment": str(comment or "").strip(),
        "metadata": metadata,
    }


def _metadata_str(metadata: Mapping[str, Any], key: str) -> str:
    return str(metadata.get(key) or "").strip()


def _metadata_int(metadata: Mapping[str, Any], key: str) -> int:
    try:
        return int(metadata.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def normalize_feedback_record(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    return {
        "id": str(row.get("id") or "").strip(),
        "created_at": str(row.get("created_at") or "").strip(),
        "user_id": str(row.get("user_id") or "").strip()
        or _metadata_str(normalized_metadata, "deeptutor_user_id"),
        "session_id": str(row.get("conversation_id") or "").strip()
        or _metadata_str(normalized_metadata, "deeptutor_session_id"),
        "message_id": str(row.get("message_id") or "").strip()
        or _metadata_str(normalized_metadata, "deeptutor_message_id"),
        "rating": normalize_feedback_rating(int(row.get("rating") or 0)),
        "reason_tags": normalize_feedback_reason_tags(row.get("reason_tags")),
        "comment": str(row.get("comment") or "").strip(),
        "answer_mode": _metadata_str(normalized_metadata, "answer_mode"),
        "requested_response_mode": _metadata_str(normalized_metadata, "requested_response_mode"),
        "effective_response_mode": _metadata_str(normalized_metadata, "effective_response_mode"),
        "response_mode_degrade_reason": _metadata_str(
            normalized_metadata, "response_mode_degrade_reason"
        ),
        "actual_tool_rounds": _metadata_int(normalized_metadata, "actual_tool_rounds"),
        "turn_id": _metadata_str(normalized_metadata, "turn_id"),
        "trace_id": _metadata_str(normalized_metadata, "trace_id"),
        "request_id": _metadata_str(normalized_metadata, "request_id"),
        "surface_message_id": _metadata_str(normalized_metadata, "surface_message_id"),
        "feedback_source": _metadata_str(normalized_metadata, "feedback_source"),
        "surface": _metadata_str(normalized_metadata, "surface"),
        "platform": _metadata_str(normalized_metadata, "platform"),
        "source": _metadata_str(normalized_metadata, "source"),
        "metadata": normalized_metadata,
    }


def is_deeptutor_feedback_record(row: Mapping[str, Any]) -> bool:
    normalized = normalize_feedback_record(row)
    if normalized["session_id"] or normalized["message_id"]:
        return True
    return normalized["source"] == "wx_miniprogram" or normalized["surface"] == "wx_miniprogram"


class SupabaseFeedbackStore:
    """Minimal PostgREST client for message feedback persistence and BI reads."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = str(base_url or os.getenv("SUPABASE_URL", "") or "").strip()
        self._service_key = _supabase_service_key(service_key)
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

    async def insert_feedback(self, row: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.post(
            f"{self._base_url.rstrip('/')}/rest/v1/ai_feedback",
            headers=_supabase_rest_headers(
                self._service_key,
                prefer="return=representation",
            ),
            json=[row],
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return dict(payload[0])
        return dict(row)

    async def list_feedback(
        self,
        *,
        created_after: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        client = await self._get_client()
        response = await client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/ai_feedback",
            headers=_supabase_rest_headers(self._service_key),
            params={
                "select": "id,created_at,user_id,conversation_id,message_id,rating,reason_tags,comment,metadata",
                "created_at": f"gte.{created_after}",
                "order": "created_at.desc",
                "limit": str(max(1, min(limit, 1000))),
                "offset": str(max(0, offset)),
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        self._owns_client = True
        return self._client
