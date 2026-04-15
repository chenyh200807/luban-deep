from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from deeptutor.api.dependencies import AuthContext, require_self_or_admin
from deeptutor.services.tutor_state import get_user_tutor_state_service

router = APIRouter()


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "user_id": snapshot.user_id,
        "profile": snapshot.profile,
        "persona": snapshot.persona,
        "memory": snapshot.memory,
        "profile_updated_at": snapshot.profile_updated_at,
        "persona_updated_at": snapshot.persona_updated_at,
        "memory_updated_at": snapshot.memory_updated_at,
    }


@router.get("/{user_id}")
async def get_tutor_state(
    user_id: str,
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    snapshot = get_user_tutor_state_service().read_snapshot(user_id)
    return _snapshot_dict(snapshot)


@router.get("/{user_id}/context")
async def get_tutor_state_context(
    user_id: str,
    language: str = Query(default="zh"),
    max_chars: int = Query(default=5000, ge=500, le=20000),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    service = get_user_tutor_state_service()
    return {
        "user_id": user_id,
        "language": language,
        "max_chars": max_chars,
        "context": service.build_context(user_id, language=language, max_chars=max_chars),
    }
