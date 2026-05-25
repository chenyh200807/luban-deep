from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user, require_admin
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.observability import get_control_plane_store, get_surface_event_store
from deeptutor.services.observability.launch_readiness import build_launch_readiness_dashboard
from deeptutor.services.observability.run_history import build_observability_run_history

# SR1 PR-1b: surface-events used to accept anonymous writes → A4 P0.
# secure_router enforces auth at router level; admin endpoints stack require_admin on top.
router = secure_router(tags=["observability"])

# Cap metadata blob size — codex review hinted at "刷爆 control_plane 磁盘 / 注入误导事件"
_SURFACE_EVENT_METADATA_MAX_BYTES = 8 * 1024  # 8 KB


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

    @field_validator("metadata")
    @classmethod
    def _metadata_size_cap(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if size > _SURFACE_EVENT_METADATA_MAX_BYTES:
            raise ValueError(
                f"metadata too large ({size} B > {_SURFACE_EVENT_METADATA_MAX_BYTES} B)"
            )
        return v


@router.post(
    "/surface-events",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(
            route_rate_limit(
                "observability_surface_events",
                default_max_requests=120,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def ingest_surface_event(
    payload: SurfaceEventIngestRequest,
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        normalized_payload = payload.model_dump(exclude_none=True)
        # SR1 PR-1b: current_user is non-None now (secure_router 401 if missing).
        normalized_payload["user_id"] = current_user.user_id
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


@router.get("/control-plane/run-history", dependencies=[Depends(require_admin)])
async def get_observability_run_history(
    limit: int = 20,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        **build_observability_run_history(
            store=get_control_plane_store(),
            limit=max(1, min(limit, 100)),
            commit_sha=commit_sha,
        ),
    }


@router.get("/launch-readiness", dependencies=[Depends(require_admin)])
async def get_launch_readiness_dashboard() -> dict[str, Any]:
    return {
        "ok": True,
        **build_launch_readiness_dashboard(store=get_control_plane_store()),
    }


@router.get("/control-plane/{kind}/latest", dependencies=[Depends(require_admin)])
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


@router.get("/control-plane/{kind}/history", dependencies=[Depends(require_admin)])
async def get_control_plane_history(kind: str, limit: int = 10) -> dict[str, Any]:
    try:
        records = get_control_plane_store().list_runs(kind, limit=max(1, min(limit, 50)))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "ok": True,
        "records": records,
    }
