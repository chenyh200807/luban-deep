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


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
    problem_type: str = "",
    symptom_tags: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    context_snapshot: dict[str, Any] | None = None,
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
    normalized_problem_type = str(problem_type or "").strip()
    if normalized_problem_type:
        metadata["problem_type"] = normalized_problem_type[:80]
    normalized_symptoms = normalize_feedback_reason_tags(symptom_tags)
    if normalized_symptoms:
        metadata["symptom_tags"] = normalized_symptoms
    normalized_attachments: list[dict[str, Any]] = []
    for item in attachments or []:
        if not isinstance(item, dict):
            continue
        normalized_attachments.append(
            {
                "id": str(item.get("id") or item.get("attachment_id") or "").strip()[:80],
                "kind": str(item.get("kind") or item.get("fileType") or "image").strip()[:24],
                "filename": str(item.get("filename") or item.get("name") or "").strip()[:160],
                "mime_type": str(item.get("mime_type") or item.get("content_type") or "").strip()[:80],
                "size": _nonnegative_int(item.get("size")),
                "url": str(item.get("url") or "").strip()[:500],
                "temp_path": str(item.get("temp_path") or item.get("tempFilePath") or "").strip()[
                    :240
                ],
            }
        )
    if normalized_attachments:
        metadata["attachments"] = [
            {
                key: value
                for key, value in item.items()
                if not (isinstance(value, str) and value == "")
            }
            for item in normalized_attachments[:3]
        ]
        metadata["attachment_count"] = len(metadata["attachments"])
    if isinstance(context_snapshot, dict) and context_snapshot:
        metadata["context_snapshot"] = {
            "route": str(context_snapshot.get("route") or "").strip()[:160],
            "network_type": str(context_snapshot.get("network_type") or "").strip()[:40],
            "device_model": str(context_snapshot.get("device_model") or "").strip()[:120],
            "platform": str(context_snapshot.get("platform") or "").strip()[:40],
            "system": str(context_snapshot.get("system") or "").strip()[:80],
            "wechat_version": str(context_snapshot.get("wechat_version") or "").strip()[:40],
        }
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


def _metadata_mapping(metadata: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = metadata.get(key)
    return dict(value) if isinstance(value, dict) else {}


def normalize_feedback_attachments(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url") or "").strip()
        temp_path = str(item.get("temp_path") or item.get("tempFilePath") or "").strip()
        record = {
            "id": str(item.get("id") or item.get("attachment_id") or "").strip()[:80],
            "kind": str(item.get("kind") or item.get("fileType") or "image").strip()[:24],
            "filename": str(item.get("filename") or item.get("name") or "").strip()[:160],
            "mime_type": str(item.get("mime_type") or item.get("content_type") or "").strip()[:80],
            "size": _nonnegative_int(item.get("size")),
            "url": url[:500],
            "temp_path": temp_path[:240],
        }
        normalized.append(
            {
                key: value
                for key, value in record.items()
                if not (isinstance(value, str) and value == "")
            }
        )
    return normalized[:3]


def normalize_feedback_record(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    triage = _metadata_mapping(normalized_metadata, "bi_triage")
    attachments = normalize_feedback_attachments(normalized_metadata.get("attachments"))
    context_snapshot = _metadata_mapping(normalized_metadata, "context_snapshot")
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
        "triage_status": _metadata_str(triage, "status"),
        "triage_operator": _metadata_str(triage, "operator"),
        "triage_note": _metadata_str(triage, "note"),
        "triage_updated_at": _metadata_str(triage, "updated_at"),
        "problem_type": _metadata_str(normalized_metadata, "problem_type"),
        "symptom_tags": normalize_feedback_reason_tags(normalized_metadata.get("symptom_tags")),
        "attachment_count": _metadata_int(normalized_metadata, "attachment_count")
        or len(attachments),
        "attachments": attachments,
        "context_snapshot": context_snapshot,
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

    async def get_feedback_by_id(self, feedback_id: str) -> dict[str, Any] | None:
        normalized_id = str(feedback_id or "").strip()
        if not normalized_id:
            return None
        client = await self._get_client()
        response = await client.get(
            f"{self._base_url.rstrip('/')}/rest/v1/ai_feedback",
            headers=_supabase_rest_headers(self._service_key),
            params={
                "select": "id,created_at,user_id,conversation_id,message_id,rating,reason_tags,comment,metadata",
                "id": f"eq.{normalized_id}",
                "limit": "1",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return dict(payload[0])
        return None

    async def update_feedback_triage(
        self,
        feedback_id: str,
        *,
        status: str,
        operator: str,
        note: str = "",
    ) -> dict[str, dict[str, Any]]:
        normalized_id = str(feedback_id or "").strip()
        if not normalized_id:
            raise ValueError("feedback_id is required")
        before = await self.get_feedback_by_id(normalized_id)
        if before is None:
            raise KeyError(normalized_id)

        metadata = before.get("metadata")
        updated_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        updated_metadata["bi_triage"] = {
            "status": str(status or "").strip(),
            "operator": str(operator or "").strip() or "admin",
            "note": str(note or "").strip()[:500],
            "updated_at": datetime.now().astimezone().isoformat(),
        }

        client = await self._get_client()
        response = await client.patch(
            f"{self._base_url.rstrip('/')}/rest/v1/ai_feedback",
            headers=_supabase_rest_headers(
                self._service_key,
                prefer="return=representation",
            ),
            params={
                "id": f"eq.{normalized_id}",
                "select": "id,created_at,user_id,conversation_id,message_id,rating,reason_tags,comment,metadata",
            },
            json={"metadata": updated_metadata},
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            after = dict(payload[0])
        else:
            after = dict(before)
            after["metadata"] = updated_metadata
        return {"before": dict(before), "after": after}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        self._owns_client = True
        return self._client
