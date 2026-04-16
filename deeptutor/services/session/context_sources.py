from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Literal

from deeptutor.services.learning_plan import get_learning_plan_service
from deeptutor.services.notebook import get_notebook_manager
from deeptutor.services.session.sqlite_store import build_user_owner_key

ContextAuthority = Literal["anchor", "primary", "supporting", "fallback"]
ContextFragmentKind = Literal["summary", "excerpt", "page"]
ContextSourceKind = Literal["notebook", "history", "active_plan"]


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _clip_text(value: str, limit: int) -> str:
    text = _coerce_str(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())
        if token
    ]


def _score_text(question: str, *fields: str) -> float:
    question_tokens = _tokenize(question)
    if not question_tokens:
        return 0.0
    haystack = " ".join(_coerce_str(field).lower() for field in fields if _coerce_str(field))
    if not haystack:
        return 0.0
    score = 0.0
    for token in question_tokens:
        if token in haystack:
            score += 1.0
    return score


def _estimate_cost_tokens(*parts: str) -> int:
    size = sum(len(_coerce_str(part)) for part in parts if _coerce_str(part))
    return max(1, math.ceil(size / 4))


def _build_history_excerpt(messages: list[dict[str, Any]], *, max_messages: int = 2, max_chars: int = 600) -> str:
    selected = [
        message
        for message in messages[-max_messages:]
        if _coerce_str(message.get("content"))
    ]
    if not selected:
        return ""

    lines = []
    for message in selected:
        role = _coerce_str(message.get("role")) or "message"
        content = _clip_text(_coerce_str(message.get("content")), max_chars)
        lines.append(f"{role.title()}: {content}")
    return "\n".join(lines).strip()


_CROSS_SESSION_MARKERS = (
    "上次",
    "之前",
    "前几天",
    "刚刚那次",
    "上回",
    "回顾",
    "记得",
    "建议",
    "偏好",
    "怎么学",
    "怎么做",
    "我当时",
    "历史",
)


def _looks_like_cross_session_recall(user_question: str) -> bool:
    text = _coerce_str(user_question).lower()
    if not text:
        return False
    return any(marker in text for marker in _CROSS_SESSION_MARKERS)


def _build_session_history_content(
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    max_excerpt_chars: int,
) -> tuple[str, ContextFragmentKind, ContextAuthority]:
    title = _coerce_str(session.get("title")) or "Untitled session"
    summary = _coerce_str(session.get("compressed_summary")) or _coerce_str(session.get("summary"))
    excerpt = _build_history_excerpt(messages, max_messages=2, max_chars=max_excerpt_chars)

    parts: list[str] = [f"Title: {title}"]
    fragment_kind: ContextFragmentKind = "excerpt"
    authority: ContextAuthority = "fallback"

    if summary:
        parts.append(f"Summary: {summary}")
        fragment_kind = "summary"
        authority = "supporting"

    if excerpt:
        parts.append(f"Recent content:\n{excerpt}")
        if not summary:
            authority = "fallback"

    content = "\n\n".join(part for part in parts if part).strip()
    if not content:
        content = f"Title: {title}"
    return content, fragment_kind, authority


@dataclass(slots=True)
class ContextSourceCandidate:
    source_kind: ContextSourceKind
    source_id: str
    fragment_id: str
    fragment_kind: ContextFragmentKind
    title: str
    content: str
    authority: ContextAuthority
    cost_tokens: int
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextSourceLoadRequest:
    user_question: str = ""
    language: str = "en"
    notebook_references: list[dict[str, Any]] = field(default_factory=list)
    history_references: list[str] = field(default_factory=list)
    active_plan_id: str = ""
    user_id: str = ""
    current_session_id: str = ""
    notebook_limit: int = 5
    history_limit: int = 3
    plan_limit: int = 4
    notebook_excerpt_chars: int = 360
    history_excerpt_chars: int = 600
    plan_excerpt_chars: int = 360


class ContextSourceLoader:
    """Build candidate context fragments without deciding final injection."""

    def __init__(
        self,
        *,
        notebook_manager: Any | None = None,
        session_store: Any | None = None,
        learning_plan_service: Any | None = None,
    ) -> None:
        self._notebook_manager = notebook_manager or get_notebook_manager()
        self._session_store = session_store
        self._learning_plan_service = learning_plan_service or get_learning_plan_service()

    async def load(self, request: ContextSourceLoadRequest) -> list[ContextSourceCandidate]:
        candidates: list[ContextSourceCandidate] = []
        candidates.extend(
            self.load_notebook_candidates(
                user_question=request.user_question,
                notebook_references=request.notebook_references,
                max_candidates=request.notebook_limit,
                max_excerpt_chars=request.notebook_excerpt_chars,
            )
        )
        candidates.extend(
            await self.load_history_candidates(
                user_question=request.user_question,
                user_id=request.user_id,
                current_session_id=request.current_session_id,
                history_references=request.history_references,
                max_candidates=request.history_limit,
                max_excerpt_chars=request.history_excerpt_chars,
            )
        )
        candidates.extend(
            self.load_active_plan_page_candidates(
                user_question=request.user_question,
                user_id=request.user_id,
                plan_id=request.active_plan_id,
                max_candidates=request.plan_limit,
                max_excerpt_chars=request.plan_excerpt_chars,
            )
        )
        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                _authority_rank(candidate.authority),
                candidate.cost_tokens,
                candidate.title,
                candidate.fragment_id,
            ),
        )

    def load_notebook_candidates(
        self,
        *,
        user_question: str = "",
        notebook_references: list[dict[str, Any]] | None = None,
        max_candidates: int = 5,
        max_excerpt_chars: int = 360,
    ) -> list[ContextSourceCandidate]:
        references = list(notebook_references or [])
        if not references:
            return []

        records = self._notebook_manager.get_records_by_references(references)
        if not records:
            return []

        scored_records = sorted(
            enumerate(records),
            key=lambda item: (
                -_score_text(user_question, item[1].get("title", ""), item[1].get("summary", ""), item[1].get("output", "")),
                item[0],
            ),
        )

        candidates: list[ContextSourceCandidate] = []
        seen_fragment_ids: set[str] = set()
        for rank, (_, record) in enumerate(scored_records[: max_candidates]):
            title = _coerce_str(record.get("title")) or _coerce_str(record.get("notebook_name")) or "Notebook record"
            summary = _coerce_str(record.get("summary"))
            output = _coerce_str(record.get("output"))
            fragment_id = _coerce_str(record.get("id")) or f"notebook-{rank}"
            if fragment_id in seen_fragment_ids:
                continue
            seen_fragment_ids.add(fragment_id)
            content = summary or _clip_text(output, max_excerpt_chars)
            fragment_kind: ContextFragmentKind = "summary" if summary else "excerpt"
            authority: ContextAuthority = "primary" if summary else "supporting"
            candidates.append(
                ContextSourceCandidate(
                    source_kind="notebook",
                    source_id=_coerce_str(record.get("notebook_id")) or "notebook",
                    fragment_id=fragment_id,
                    fragment_kind=fragment_kind,
                    title=title,
                    content=content,
                    authority=authority,
                    cost_tokens=_estimate_cost_tokens(title, content),
                    score=_score_text(user_question, title, summary, output),
                    metadata={
                        "notebook_id": _coerce_str(record.get("notebook_id")),
                        "notebook_name": _coerce_str(record.get("notebook_name")),
                        "record_type": _coerce_str(record.get("type")),
                        "user_query": _coerce_str(record.get("user_query")),
                        "created_at": record.get("created_at"),
                        "kb_name": record.get("kb_name"),
                        "selected_rank": rank,
                    },
                )
            )
        return candidates

    async def load_history_candidates(
        self,
        *,
        user_question: str = "",
        user_id: str = "",
        current_session_id: str = "",
        history_references: list[str] | None = None,
        max_candidates: int = 3,
        max_excerpt_chars: int = 600,
    ) -> list[ContextSourceCandidate]:
        if self._session_store is None:
            return []

        references = [str(item or "").strip() for item in (history_references or []) if str(item or "").strip()]
        if not references:
            if not _coerce_str(user_id) or not _looks_like_cross_session_recall(user_question):
                return []

            owner_key = build_user_owner_key(user_id)
            if not owner_key:
                return []

            owned_sessions = await self._session_store.list_sessions_by_owner(owner_key, limit=50)
            if len(owned_sessions) <= 1:
                return []

            excluded_session_id = _coerce_str(current_session_id)
            if not excluded_session_id:
                excluded_session_id = _coerce_str((owned_sessions[0] or {}).get("id"))
            owned_sessions = [
                session
                for session in owned_sessions
                if _coerce_str(session.get("id")) != excluded_session_id
            ]
            if not owned_sessions:
                return []
            scored_sessions = sorted(
                enumerate(owned_sessions),
                key=lambda item: (
                    -_score_text(
                        user_question,
                        item[1].get("title", ""),
                        item[1].get("compressed_summary", ""),
                        item[1].get("summary", ""),
                        item[1].get("last_message", ""),
                    ),
                    item[0],
                ),
            )

            candidates: list[ContextSourceCandidate] = []
            seen_session_ids: set[str] = set()
            for rank, (_, session) in enumerate(scored_sessions[: max_candidates]):
                session_id = _coerce_str(session.get("id"))
                if not session_id or session_id in seen_session_ids:
                    continue
                seen_session_ids.add(session_id)

                messages = await self._session_store.get_messages_for_context(session_id)
                content, fragment_kind, authority = _build_session_history_content(
                    session,
                    messages,
                    max_excerpt_chars=max_excerpt_chars,
                )
                if not _coerce_str(content):
                    continue

                candidates.append(
                    ContextSourceCandidate(
                        source_kind="history",
                        source_id=session_id,
                        fragment_id=session_id,
                        fragment_kind=fragment_kind,
                        title=_coerce_str(session.get("title")) or session_id,
                        content=_clip_text(content, max_excerpt_chars),
                        authority=authority,
                        cost_tokens=_estimate_cost_tokens(session_id, content),
                        score=_score_text(
                            user_question,
                            session.get("title", ""),
                            session.get("compressed_summary", ""),
                            session.get("summary", ""),
                            session.get("last_message", ""),
                            content,
                        )
                        + max(0.0, 0.3 * (len(owned_sessions) - rank)),
                        metadata={
                            "session_id": session_id,
                            "owner_key": owner_key,
                            "message_count": len(messages),
                            "has_compressed_summary": bool(
                                _coerce_str(session.get("compressed_summary"))
                            ),
                            "updated_at": session.get("updated_at"),
                            "selected_rank": rank,
                            "load_mode": "implicit_cross_session_recall",
                            "excluded_current_session": bool(excluded_session_id),
                        },
                    )
                )
            return candidates

        candidates: list[ContextSourceCandidate] = []
        seen_sessions: set[str] = set()
        for session_id in references[: max_candidates]:
            if session_id in seen_sessions:
                continue
            seen_sessions.add(session_id)
            session = await self._session_store.get_session(session_id)
            if not session:
                continue

            messages = await self._session_store.get_messages_for_context(session_id)
            summary = _coerce_str(session.get("compressed_summary")) or _coerce_str(session.get("summary"))
            title = _coerce_str(session.get("title")) or session_id
            if summary:
                content = _clip_text(summary, max_excerpt_chars)
                fragment_kind: ContextFragmentKind = "summary"
                authority: ContextAuthority = "supporting"
            else:
                content = _build_history_excerpt(messages, max_messages=2, max_chars=max_excerpt_chars)
                fragment_kind = "excerpt"
                authority = "fallback"
                if not content:
                    content = f"{len(messages)} messages"

            candidates.append(
                ContextSourceCandidate(
                    source_kind="history",
                    source_id=session_id,
                    fragment_id=session_id,
                    fragment_kind=fragment_kind,
                    title=title,
                    content=content,
                    authority=authority,
                    cost_tokens=_estimate_cost_tokens(title, content),
                    score=_score_text(user_question, title, summary, content),
                    metadata={
                        "session_id": session_id,
                        "message_count": len(messages),
                        "has_compressed_summary": bool(summary),
                        "updated_at": session.get("updated_at"),
                    },
                )
            )

        return candidates

    def load_active_plan_page_candidates(
        self,
        *,
        user_question: str = "",
        user_id: str = "",
        plan_id: str = "",
        max_candidates: int = 4,
        max_excerpt_chars: int = 360,
    ) -> list[ContextSourceCandidate]:
        normalized_plan_id = _coerce_str(plan_id)
        if not normalized_plan_id:
            return []

        plan_view = self._learning_plan_service.read_guided_session_view(normalized_plan_id)
        if not plan_view:
            return []
        if _coerce_str(user_id) and _coerce_str(plan_view.get("user_id")) and _coerce_str(plan_view.get("user_id")) != _coerce_str(user_id):
            return []

        pages = [page for page in list(plan_view.get("pages") or []) if isinstance(page, dict)]
        if not pages:
            return []

        current_index = int(plan_view.get("current_index") or -1)
        if current_index < 0:
            current_index = int(pages[0].get("page_index", 0) or 0)

        candidate_pages: list[tuple[int, dict[str, Any], ContextAuthority]] = []
        seen_indices: set[int] = set()

        plan_summary = _coerce_str(plan_view.get("summary"))
        if plan_summary:
            candidate_pages.append((-1, {"fragment_id": "plan-summary", "title": plan_view.get("notebook_name", "") or plan_id, "content": plan_summary}, "anchor"))

        for offset, authority in ((0, "primary"), (-1, "supporting"), (1, "supporting")):
            page_index = current_index + offset
            page = next(
                (
                    item
                    for item in pages
                    if int(item.get("page_index", -1) or -1) == page_index
                ),
                None,
            )
            if page is None or page_index in seen_indices:
                continue
            seen_indices.add(page_index)
            candidate_pages.append(
                (
                    page_index,
                    {
                        "fragment_id": str(page_index),
                        "title": _coerce_str(page.get("knowledge_title")) or f"Page {page_index}",
                        "content": self._build_plan_page_text(page, max_excerpt_chars=max_excerpt_chars),
                    },
                    authority,
                )
            )

        scored_candidates: list[ContextSourceCandidate] = []
        for rank, (page_index, fragment, authority) in enumerate(candidate_pages[: max_candidates]):
            content = _coerce_str(fragment.get("content"))
            title = _coerce_str(fragment.get("title"))
            scored_candidates.append(
                ContextSourceCandidate(
                    source_kind="active_plan",
                    source_id=normalized_plan_id,
                    fragment_id=_coerce_str(fragment.get("fragment_id")) or str(page_index),
                    fragment_kind="summary" if page_index == -1 else "page",
                    title=title,
                    content=content,
                    authority=authority,
                    cost_tokens=_estimate_cost_tokens(title, content),
                    score=_score_text(user_question, title, content) + (1.5 if page_index == current_index else 0.0),
                    metadata={
                        "plan_id": normalized_plan_id,
                        "page_index": page_index,
                        "current_index": current_index,
                        "status": _coerce_str(plan_view.get("status")),
                        "progress": plan_view.get("progress"),
                        "ready_count": plan_view.get("ready_count"),
                        "page_count": plan_view.get("page_count"),
                        "selected_rank": rank,
                    },
                )
            )

        return sorted(
            scored_candidates,
            key=lambda candidate: (
                -candidate.score,
                _authority_rank(candidate.authority),
                candidate.cost_tokens,
                candidate.fragment_id,
            ),
        )[: max_candidates]

    @staticmethod
    def _build_plan_page_text(page: dict[str, Any], *, max_excerpt_chars: int) -> str:
        title = _coerce_str(page.get("knowledge_title")) or "Learning page"
        summary = _coerce_str(page.get("knowledge_summary"))
        difficulty = _coerce_str(page.get("user_difficulty"))
        html = _coerce_str(page.get("html"))
        lines = [title]
        if summary:
            lines.append(summary)
        if difficulty:
            lines.append(f"Difficulty: {difficulty}")
        if html and not summary:
            lines.append(_clip_text(html, max_excerpt_chars))
        return "\n".join(line for line in lines if line).strip()


def _authority_rank(authority: ContextAuthority) -> int:
    return {
        "anchor": 0,
        "primary": 1,
        "supporting": 2,
        "fallback": 3,
    }.get(authority, 3)


__all__ = [
    "ContextAuthority",
    "ContextFragmentKind",
    "ContextSourceCandidate",
    "ContextSourceKind",
    "ContextSourceLoadRequest",
    "ContextSourceLoader",
]
