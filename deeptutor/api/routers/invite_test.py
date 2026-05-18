from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from deeptutor.services.invite_test_applications import (
    InviteTestApplicationStore,
    InviteTestApplicationValidationError,
)


router = APIRouter()

_RATE_LIMIT_BUCKETS: dict[str, dict[str, float]] = {}
_RATE_LIMIT_WINDOW_S = 60.0
_RATE_LIMIT_MAX = 8


def _extract_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    current = _RATE_LIMIT_BUCKETS.get(ip)
    if not current or current["reset_at"] <= now:
        _RATE_LIMIT_BUCKETS[ip] = {"count": 1.0, "reset_at": now + _RATE_LIMIT_WINDOW_S}
        return False
    current["count"] += 1
    return current["count"] > _RATE_LIMIT_MAX


@router.post("/applications", status_code=status.HTTP_201_CREATED)
async def submit_invite_test_application(request: Request) -> dict[str, Any]:
    ip = _extract_ip(request)
    if _is_rate_limited(ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="提交过于频繁，请稍后再试。")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请求内容不是有效 JSON。") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请求内容不是有效 JSON。")

    store = InviteTestApplicationStore()
    try:
        result = await store.submit_application(payload)
    except InviteTestApplicationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="申请提交失败，请稍后再试。") from exc
    finally:
        await store.aclose()
    return result
