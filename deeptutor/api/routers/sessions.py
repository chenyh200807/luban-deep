"""
Unified session history API.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Query

from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


class QuizResultItem(BaseModel):
    question_id: str = ""
    question: str = Field(..., min_length=1)
    question_type: str = ""
    options: dict[str, str] | None = None
    user_answer: str = ""
    correct_answer: str = ""
    explanation: str | None = ""
    difficulty: str | None = ""
    is_correct: bool

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_options(cls, v):
        return v if isinstance(v, dict) else {}

    @field_validator("explanation", "difficulty", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return v if isinstance(v, str) else ""


class QuizResultsRequest(BaseModel):
    answers: list[QuizResultItem] = Field(default_factory=list)


def _format_quiz_results_message(answers: list[QuizResultItem]) -> str:
    total = len(answers)
    correct = sum(1 for item in answers if item.is_correct)
    score_pct = round((correct / total) * 100) if total else 0
    lines = ["[Quiz Performance]"]
    for idx, item in enumerate(answers, 1):
        question = item.question.strip().replace("\n", " ")
        user_answer = (item.user_answer or "").strip() or "(blank)"
        status = "Correct" if item.is_correct else "Incorrect"
        suffix = f" ({status})"
        if not item.is_correct and (item.correct_answer or "").strip():
            suffix = f" ({status}, correct: {(item.correct_answer or '').strip()})"
        qid = f"[{item.question_id}] " if item.question_id else ""
        lines.append(f"{idx}. {qid}Q: {question} -> Answered: {user_answer}{suffix}")
    lines.append(f"Score: {correct}/{total} ({score_pct}%)")
    return "\n".join(lines)


def _session_page_cursor(sessions: list[dict[str, object]], limit: int) -> dict[str, object] | None:
    if len(sessions) < limit or not sessions:
        return None
    last = sessions[-1]
    return {
        "before_updated_at": float(last.get("updated_at") or 0.0),
        "before_session_id": str(last.get("session_id") or last.get("id") or ""),
    }


async def _authorize_session_access(
    session_id: str,
    current_user: AuthContext,
) -> None:
    store = get_sqlite_session_store()
    owner_key = await store.get_session_owner_key(session_id)
    if not owner_key:
        if current_user.is_admin:
            return
        raise HTTPException(status_code=404, detail="Session not found")
    if current_user.is_admin:
        return
    if owner_key != build_user_owner_key(current_user.user_id):
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before_updated_at: float | None = Query(default=None),
    before_session_id: str | None = Query(default=None),
    current_user: AuthContext = Depends(get_current_user),
):
    if before_session_id and before_updated_at is None:
        raise HTTPException(status_code=400, detail="before_updated_at is required with before_session_id")
    if before_updated_at is not None and offset > 0:
        raise HTTPException(status_code=400, detail="offset cannot be combined with keyset cursor")
    store = get_sqlite_session_store()
    if current_user.is_admin:
        sessions = await store.list_sessions(
            limit=limit,
            offset=offset,
            before_updated_at=before_updated_at,
            before_session_id=before_session_id,
        )
    else:
        sessions = await store.list_sessions_by_owner(
            build_user_owner_key(current_user.user_id),
            limit=limit,
            offset=offset,
            before_updated_at=before_updated_at,
            before_session_id=before_session_id,
        )
    return {"sessions": sessions, "next_cursor": _session_page_cursor(sessions, limit)}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    await _authorize_session_access(session_id, current_user)
    session = await store.get_session_with_messages(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}")
async def rename_session(
    session_id: str,
    payload: SessionRenameRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    await _authorize_session_access(session_id, current_user)
    updated = await store.update_session_title(session_id, payload.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    session = await store.get_session(session_id)
    return {"session": session}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: AuthContext = Depends(get_current_user),
):
    store = get_sqlite_session_store()
    await _authorize_session_access(session_id, current_user)
    deleted = await store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, "session_id": session_id}


@router.post("/{session_id}/quiz-results")
async def record_quiz_results(
    session_id: str,
    payload: QuizResultsRequest,
    current_user: AuthContext = Depends(get_current_user),
):
    if not payload.answers:
        raise HTTPException(status_code=400, detail="Quiz results are required")
    store = get_sqlite_session_store()
    await _authorize_session_access(session_id, current_user)
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    content = _format_quiz_results_message(payload.answers)
    await store.add_message(
        session_id=session_id,
        role="user",
        content=content,
        capability="deep_question",
    )
    notebook_count = 0
    try:
        notebook_count = await store.upsert_notebook_entries(
            session_id,
            [item.model_dump() for item in payload.answers],
        )
    except Exception:
        logger.warning("Failed to upsert notebook entries for session %s", session_id, exc_info=True)
    return {
        "recorded": True,
        "session_id": session_id,
        "answer_count": len(payload.answers),
        "notebook_count": notebook_count,
        "content": content,
    }
