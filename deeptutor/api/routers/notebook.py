"""
Notebook API Router
Provides notebook creation, querying, updating, deletion, and record management functions
"""

import json
from typing import AsyncGenerator, Literal

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.agents.notebook import NotebookSummarizeAgent
from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.notebook import notebook_manager
from deeptutor.services.notebook_card.service import get_notebook_card_service
from deeptutor.services.notebook_card.store import OptimisticConcurrencyError
from deeptutor.services.session import build_user_owner_key
from deeptutor.utils.error_utils import public_error_detail

router = secure_router(tags=["notebook"])


# === Request/Response Models ===


class CreateNotebookRequest(BaseModel):
    """Create notebook request"""

    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "book"


class UpdateNotebookRequest(BaseModel):
    """Update notebook request"""

    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddRecordRequest(BaseModel):
    """Add record request"""

    notebook_ids: list[str]
    record_type: Literal["solve", "question", "research", "co_writer", "chat", "guided_learning"]
    title: str
    summary: str = ""
    user_query: str
    output: str
    metadata: dict = {}
    kb_name: str | None = None


class RemoveRecordRequest(BaseModel):
    """Remove record request"""

    record_id: str


class UpdateRecordRequest(BaseModel):
    """Update an existing notebook record."""

    title: str | None = None
    summary: str | None = None
    user_query: str | None = None
    output: str | None = None
    metadata: dict | None = None
    kb_name: str | None = None


class CardPatchRequest(BaseModel):
    """学习卡片乐观并发编辑请求（expected_version 来自上次读取的 version / If-Match）。"""

    expected_version: int
    patch: dict = {}


# === API Endpoints ===


async def _build_record_summary(request: AddRecordRequest) -> str:
    if request.summary.strip():
        return request.summary.strip()
    agent = NotebookSummarizeAgent(language=str(request.metadata.get("ui_language", "en")))
    return await agent.summarize(
        title=request.title,
        record_type=request.record_type,
        user_query=request.user_query,
        output=request.output,
        metadata=request.metadata,
    )


def _owner_key_for(current_user: AuthContext) -> str:
    return build_user_owner_key(current_user.user_id)


def _request_metadata(request: AddRecordRequest | UpdateRecordRequest, current_user: AuthContext) -> dict:
    metadata = dict(request.metadata or {})
    metadata["user_id"] = current_user.user_id
    return metadata


async def _stream_add_record_with_summary(
    request: AddRecordRequest,
    current_user: AuthContext,
) -> AsyncGenerator[str, None]:
    try:
        metadata = _request_metadata(request, current_user)
        agent = NotebookSummarizeAgent(language=str(request.metadata.get("ui_language", "en")))
        summary_parts: list[str] = []
        if request.summary.strip():
            summary_parts.append(request.summary.strip())
            yield f"data: {json.dumps({'type': 'summary_chunk', 'content': request.summary.strip()}, ensure_ascii=False)}\n\n"
        else:
            async for chunk in agent.stream_summary(
                title=request.title,
                record_type=request.record_type,
                user_query=request.user_query,
                output=request.output,
                metadata=metadata,
            ):
                if not chunk:
                    continue
                summary_parts.append(chunk)
                yield f"data: {json.dumps({'type': 'summary_chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

        summary = "".join(summary_parts).strip()
        result = notebook_manager.add_record(
            notebook_ids=request.notebook_ids,
            record_type=request.record_type,
            title=request.title,
            summary=summary,
            user_query=request.user_query,
            output=request.output,
            metadata=metadata,
            kb_name=request.kb_name,
            user_id=current_user.user_id,
            owner_key=_owner_key_for(current_user),
        )
        payload = {
            "type": "result",
            "success": True,
            "summary": summary,
            "record": result["record"],
            "added_to_notebooks": result["added_to_notebooks"],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    except Exception as exc:
        payload = {"type": "error", "detail": public_error_detail("Notebook operation")}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/list")
async def list_notebooks(current_user: AuthContext = Depends(get_current_user)):
    """
    Get all notebook list

    Returns:
        Notebook list (includes summary information)
    """
    try:
        notebooks = notebook_manager.list_notebooks(owner_key=_owner_key_for(current_user))
        return {"notebooks": notebooks, "total": len(notebooks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.get("/statistics")
async def get_statistics(current_user: AuthContext = Depends(get_current_user)):
    """
    Get notebook statistics

    Returns:
        Statistics information
    """
    try:
        stats = notebook_manager.get_statistics(owner_key=_owner_key_for(current_user))
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.post("/create")
async def create_notebook(
    request: CreateNotebookRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """
    Create new notebook

    Args:
        request: Create request

    Returns:
        Created notebook information
    """
    try:
        notebook = notebook_manager.create_notebook(
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
            owner_key=_owner_key_for(current_user),
        )
        return {"success": True, "notebook": notebook}
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.get("/{notebook_id}")
async def get_notebook(
    notebook_id: str,
    current_user: AuthContext = Depends(get_current_user),
):
    """
    Get notebook details

    Args:
        notebook_id: Notebook ID

    Returns:
        Notebook details (includes all records)
    """
    try:
        notebook = notebook_manager.get_notebook(notebook_id, owner_key=_owner_key_for(current_user))
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return notebook
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.put("/{notebook_id}")
async def update_notebook(
    notebook_id: str,
    request: UpdateNotebookRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """
    Update notebook information

    Args:
        notebook_id: Notebook ID
        request: Update request

    Returns:
        Updated notebook information
    """
    try:
        notebook = notebook_manager.update_notebook(
            notebook_id=notebook_id,
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
            owner_key=_owner_key_for(current_user),
        )
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {"success": True, "notebook": notebook}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.delete("/{notebook_id}")
async def delete_notebook(
    notebook_id: str,
    current_user: AuthContext = Depends(get_current_user),
):
    """
    Delete notebook

    Args:
        notebook_id: Notebook ID

    Returns:
        Deletion result
    """
    try:
        success = notebook_manager.delete_notebook(notebook_id, owner_key=_owner_key_for(current_user))
        if not success:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {"success": True, "message": "Notebook deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.post("/add_record")
async def add_record(
    request: AddRecordRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """
    Add record to notebook

    Args:
        request: Add record request

    Returns:
        Addition result
    """
    try:
        metadata = _request_metadata(request, current_user)
        # Phase 3.1 分流：带 metadata.card_type 的写入走 durable NotebookCardService（轻写回，
        # 零 summary/overlay 污染）；其余维持 legacy notebook_manager 不变。不新增 cards writer。
        card_type = str((metadata or {}).get("card_type") or "").strip()
        if card_type:
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
        normalized_request = request.model_copy(update={"metadata": metadata})
        summary = await _build_record_summary(normalized_request)
        result = notebook_manager.add_record(
            notebook_ids=request.notebook_ids,
            record_type=request.record_type,
            title=request.title,
            summary=summary,
            user_query=request.user_query,
            output=request.output,
            metadata=metadata,
            kb_name=request.kb_name,
            user_id=current_user.user_id,
            owner_key=_owner_key_for(current_user),
        )
        return {
            "success": True,
            "summary": summary,
            "record": result["record"],
            "added_to_notebooks": result["added_to_notebooks"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.post("/add_record_with_summary")
async def add_record_with_summary(
    request: AddRecordRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """Add record to notebook and stream generated summary."""
    return StreamingResponse(
        _stream_add_record_with_summary(request, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{notebook_id}/records/{record_id}")
async def remove_record(
    notebook_id: str,
    record_id: str,
    current_user: AuthContext = Depends(get_current_user),
):
    """
    Remove record from notebook

    Args:
        notebook_id: Notebook ID
        record_id: Record ID

    Returns:
        Deletion result
    """
    try:
        success = notebook_manager.remove_record(
            notebook_id,
            record_id,
            owner_key=_owner_key_for(current_user),
        )
        if not success:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"success": True, "message": "Record removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.put("/{notebook_id}/records/{record_id}")
async def update_record(
    notebook_id: str,
    record_id: str,
    request: UpdateRecordRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """Update an existing notebook record in place."""
    try:
        metadata = _request_metadata(request, current_user) if request.metadata is not None else {"user_id": current_user.user_id}
        updated = notebook_manager.update_record(
            notebook_id=notebook_id,
            record_id=record_id,
            title=request.title,
            summary=request.summary,
            user_query=request.user_query,
            output=request.output,
            metadata=metadata,
            kb_name=request.kb_name,
            user_id=current_user.user_id,
            owner_key=_owner_key_for(current_user),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"success": True, "record": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_detail("Notebook operation"))


@router.patch("/cards/{note_id}")
async def update_notebook_card(
    note_id: str,
    request: CardPatchRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    """编辑学习卡片（乐观并发：stale version → 409）。走 NotebookCardService，不新增 cards writer。"""
    try:
        updated = await get_notebook_card_service().update_card(
            user_id=current_user.user_id,
            note_id=note_id,
            expected_version=int(request.expected_version),
            patch=dict(request.patch or {}),
        )
        return {"success": True, "card": updated}
    except OptimisticConcurrencyError:
        raise HTTPException(status_code=409, detail="card was modified by another device; reload and retry")
    except KeyError:
        raise HTTPException(status_code=404, detail="card not found")


@router.delete("/cards/{note_id}")
async def delete_notebook_card(
    note_id: str,
    expected_version: int,
    current_user: AuthContext = Depends(get_current_user),
):
    """软删学习卡片（archived_at；乐观并发：stale version → 409）。"""
    try:
        deleted = await get_notebook_card_service().delete_card(
            user_id=current_user.user_id,
            note_id=note_id,
            expected_version=int(expected_version),
        )
        return {"success": True, "card": deleted}
    except OptimisticConcurrencyError:
        raise HTTPException(status_code=409, detail="card was modified by another device; reload and retry")
    except KeyError:
        raise HTTPException(status_code=404, detail="card not found")


@router.get("/health")
async def health_check():
    """Health check"""
    return {"status": "healthy", "service": "notebook"}
