"""Invite-test application router.

SR3 PR-3: switched from per-process private rate-limit dict to the project-wide
``route_rate_limit`` (SQLite/Redis backend). The original private bucket
implementation was multi-worker-broken (each uvicorn worker had its own dict)
and trusted unverified ``X-Forwarded-For`` first hop — both fixed by reusing
the authoritative limiter at ``deeptutor/api/dependencies/rate_limit.py``.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from deeptutor.api._secure_router import public_router
from deeptutor.api.dependencies.rate_limit import route_rate_limit
from deeptutor.services.invite_test_applications import (
    InviteTestApplicationStore,
    InviteTestApplicationValidationError,
)


router = public_router(
    reason="anonymous invite-test registration form (rate-limited)",
)


@router.post(
    "/applications",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            route_rate_limit(
                "invite_test_applications",
                default_max_requests=8,
                default_window_seconds=60.0,
            )
        )
    ],
)
async def submit_invite_test_application(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求内容不是有效 JSON。",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求内容不是有效 JSON。",
        )

    store = InviteTestApplicationStore()
    try:
        result = await store.submit_application(payload)
    except InviteTestApplicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="申请提交失败，请稍后再试。",
        ) from exc
    finally:
        await store.aclose()
    return result
