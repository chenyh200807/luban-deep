"""Stable notebook-card entrypoint for production mini-program saves.

The legacy notebook router is disabled in production, but the mini-program
save-card action still uses the existing /api/v1/notebook/add_record path with
metadata.card_type. This thin router keeps that card path available without
reopening the full legacy notebook surface.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.routers.notebook import AddRecordRequest
from deeptutor.services.notebook_card.service import get_notebook_card_service
from deeptutor.utils.error_utils import public_error_detail

router = secure_router(tags=["notebook"])


@router.post("/add_record")
async def add_record(
    request: AddRecordRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """Save a durable notebook card through the existing add_record payload."""
    try:
        metadata = dict(request.metadata or {})
        metadata["user_id"] = current_user.user_id
        card_type = str(metadata.get("card_type") or "").strip()
        if not card_type:
            raise HTTPException(status_code=422, detail="notebook_card_type_required")

        card = await get_notebook_card_service().save_card(
            user_id=current_user.user_id,
            subject_id=str(metadata.get("subject_id") or ""),
            source_bot_id=str(metadata.get("source_bot_id") or ""),
            card_type=card_type,
            source_type=str(metadata.get("source_type") or "manual"),
            source_ref=dict(metadata.get("source_ref") or {}),
            evidence_event_ids=list(metadata.get("evidence_event_ids") or []),
            title=request.title,
            raw_user_content=request.user_query or request.output,
            ai_enhanced_content=dict(metadata.get("ai_enhanced_content") or {}),
        )
        return {"success": True, "card": card, "note_id": card["note_id"]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=public_error_detail("Notebook operation"),
        )
