from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from deeptutor.api.dependencies import resolve_auth_context
from deeptutor.services.observability import get_control_plane_store, get_surface_event_store

router = APIRouter()


class SurfaceEventIngestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(min_length=1, max_length=128)
    surface: str = Field(min_length=1, max_length=64)
    event_name: str = Field(min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=128)
    turn_id: str | None = Field(default=None, max_length=128)
    collected_at_ms: int | None = Field(default=None, ge=0)
    sent_at_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


@router.post("/surface-events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_surface_event(
    payload: SurfaceEventIngestRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        auth_context = resolve_auth_context(authorization)
        normalized_payload = payload.model_dump(exclude_none=True)
        if auth_context is not None:
            normalized_payload["user_id"] = auth_context.user_id
        result = get_surface_event_store().ingest(normalized_payload)
        return {
            "ok": True,
            **result,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/control-plane/{kind}/latest")
async def get_control_plane_latest(kind: str) -> dict[str, Any]:
    try:
        latest = get_control_plane_store().latest_run(kind)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No control plane run found for {kind}",
        )
    return {
        "ok": True,
        "record": latest,
    }


@router.get("/control-plane/{kind}/history")
async def get_control_plane_history(kind: str, limit: int = 10) -> dict[str, Any]:
    try:
        records = get_control_plane_store().list_runs(kind, limit=max(1, min(limit, 50)))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "ok": True,
        "records": records,
    }
