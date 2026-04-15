"""
Question Notebook API — persists quiz questions, bookmarks, and categories.
"""

from __future__ import annotations

import sqlite3
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.session import get_sqlite_session_store
from deeptutor.services.session.sqlite_store import build_user_owner_key

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


def _raise_internal_error(operation: str) -> None:
    logger.exception(f"Question notebook {operation} failed")
    raise HTTPException(status_code=500, detail=f"Failed to {operation}. Please try again later.")


# ── Models ────────────────────────────────────────────────────────

class NotebookEntryItem(BaseModel):
    id: int
    session_id: str
    session_title: str = ""
    question_id: str = ""
    question: str
    question_type: str = ""
    options: dict[str, str] = {}
    correct_answer: str = ""
    explanation: str = ""
    difficulty: str = ""
    user_answer: str = ""
    is_correct: bool = False
    bookmarked: bool = False
    followup_session_id: str = ""
    created_at: float
    updated_at: float
    categories: list[CategoryItem] | None = None


class NotebookEntryListCursor(BaseModel):
    before_created_at: float
    before_entry_id: int


class NotebookEntryListResponse(BaseModel):
    items: list[NotebookEntryItem]
    total: int
    next_cursor: NotebookEntryListCursor | None = None


class EntryUpdateRequest(BaseModel):
    bookmarked: bool | None = None
    followup_session_id: str | None = None


class CategoryItem(BaseModel):
    id: int
    name: str
    created_at: float = 0
    entry_count: int = 0


class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CategoryRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CategoryAddRequest(BaseModel):
    category_id: int


class UpsertEntryRequest(BaseModel):
    session_id: str
    question_id: str
    question: str
    question_type: str = ""
    options: dict[str, str] | None = None
    correct_answer: str = ""
    explanation: str = ""
    difficulty: str = ""
    user_answer: str = ""
    is_correct: bool = False


def _owner_key(current_user: AuthContext) -> str:
    return build_user_owner_key(current_user.user_id)


async def _assert_session_access(session_id: str, current_user: AuthContext) -> None:
    if current_user.is_admin:
        return
    store = get_sqlite_session_store()
    session_owner_key = await store.get_session_owner_key(session_id)
    if session_owner_key != _owner_key(current_user):
        raise HTTPException(status_code=404, detail="Session not found")


# ── Entry endpoints ──────────────────────────────────────────────

@router.post("/entries/upsert")
async def upsert_single_entry(
    payload: UpsertEntryRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    try:
        await _assert_session_access(payload.session_id, current_user)
        await store.upsert_notebook_entries(payload.session_id, [payload.model_dump()])
        entry = await store.find_notebook_entry(
            payload.session_id,
            payload.question_id,
            owner_key=None if current_user.is_admin else _owner_key(current_user),
        )
        if entry is None:
            _raise_internal_error("persist the notebook entry")
        return entry
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Session not found") from e
    except HTTPException:
        raise
    except Exception:
        _raise_internal_error("upsert the notebook entry")

@router.get("/entries", response_model=NotebookEntryListResponse)
async def list_entries(
    category_id: int | None = Query(default=None),
    bookmarked: bool | None = Query(default=None),
    is_correct: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before_created_at: float | None = Query(default=None),
    before_entry_id: int | None = Query(default=None),
    current_user: AuthContext = Depends(get_current_user),
) -> NotebookEntryListResponse:
    if before_entry_id is not None and before_created_at is None:
        raise HTTPException(status_code=400, detail="before_created_at is required with before_entry_id")
    if before_created_at is not None and offset > 0:
        raise HTTPException(status_code=400, detail="offset cannot be combined with keyset cursor")
    store = get_sqlite_session_store()
    owner_key = None if current_user.is_admin else _owner_key(current_user)
    result = await store.list_notebook_entries(
        category_id=category_id,
        bookmarked=bookmarked,
        is_correct=is_correct,
        limit=limit,
        offset=offset,
        owner_key=owner_key,
        before_created_at=before_created_at,
        before_entry_id=before_entry_id,
    )
    next_cursor = None
    if len(result["items"]) >= limit and result["items"]:
        last = result["items"][-1]
        next_cursor = NotebookEntryListCursor(
            before_created_at=float(last["created_at"]),
            before_entry_id=int(last["id"]),
        )
    return NotebookEntryListResponse(
        items=[NotebookEntryItem(**item) for item in result["items"]],
        total=result["total"],
        next_cursor=next_cursor,
    )


@router.get("/entries/lookup/by-question")
async def lookup_entry(
    session_id: str = Query(...),
    question_id: str = Query(...),
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    entry = await store.find_notebook_entry(
        session_id,
        question_id,
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@router.get("/entries/{entry_id}", response_model=NotebookEntryItem)
async def get_entry(
    entry_id: int,
    current_user: AuthContext = Depends(get_current_user),
) -> NotebookEntryItem:
    store = get_sqlite_session_store()
    entry = await store.get_notebook_entry(
        entry_id,
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return NotebookEntryItem(**entry)


@router.patch("/entries/{entry_id}")
async def update_entry(
    entry_id: int,
    payload: EntryUpdateRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = await store.update_notebook_entry(
        entry_id,
        updates,
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"updated": True, "id": entry_id}


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: int,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    deleted = await store.delete_notebook_entry(
        entry_id,
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True, "id": entry_id}


# ── Entry ↔ Category linking ────────────────────────────────────

@router.post("/entries/{entry_id}/categories")
async def add_entry_to_category(
    entry_id: int,
    payload: CategoryAddRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    owner_key = None if current_user.is_admin else _owner_key(current_user)
    entry = await store.get_notebook_entry(entry_id, owner_key=owner_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    ok = await store.add_entry_to_category(
        entry_id,
        payload.category_id,
        owner_key=owner_key,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to add to category")
    return {"added": True, "entry_id": entry_id, "category_id": payload.category_id}


@router.delete("/entries/{entry_id}/categories/{category_id}")
async def remove_entry_from_category(
    entry_id: int,
    category_id: int,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    owner_key = None if current_user.is_admin else _owner_key(current_user)
    entry = await store.get_notebook_entry(entry_id, owner_key=owner_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    removed = await store.remove_entry_from_category(
        entry_id,
        category_id,
        owner_key=owner_key,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"removed": True, "entry_id": entry_id, "category_id": category_id}


# ── Category CRUD ────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryItem])
async def list_categories(current_user: AuthContext = Depends(get_current_user)):
    store = get_sqlite_session_store()
    return await store.list_categories(
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )


@router.post("/categories", response_model=CategoryItem, status_code=201)
async def create_category(
    payload: CategoryCreateRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    try:
        return await store.create_category(
            payload.name,
            owner_key=None if current_user.is_admin else _owner_key(current_user),
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="Category name already exists") from e
    except HTTPException:
        raise
    except Exception:
        _raise_internal_error("create the notebook category")


@router.patch("/categories/{category_id}")
async def rename_category(
    category_id: int,
    payload: CategoryRenameRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    updated = await store.rename_category(
        category_id,
        payload.name,
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"updated": True, "id": category_id, "name": payload.name}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    deleted = await store.delete_category(
        category_id,
        owner_key=None if current_user.is_admin else _owner_key(current_user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"deleted": True, "id": category_id}
