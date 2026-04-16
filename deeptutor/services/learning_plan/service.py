from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Any

from deeptutor.services.path_service import PathService, get_path_service

from .store import LearningPlanStore, _normalize_session_id


def _now() -> float:
    return time.time()


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _coerce_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value if value is not None else fallback)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(value: Any, fallback: float) -> float:
    try:
        return float(value if value is not None else fallback)
    except (TypeError, ValueError):
        return fallback


def _timestamp_from_value(value: Any, fallback: float) -> float:
    if value is None or value == "":
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return fallback


@dataclass
class LearningPlanView:
    session_id: str
    notebook_id: str
    notebook_name: str
    created_at: float
    user_id: str
    source_bot_id: str
    knowledge_points: list[dict[str, Any]]
    current_index: int
    chat_history: list[dict[str, Any]]
    status: str
    html_pages: dict[str, str]
    page_statuses: dict[str, str]
    page_errors: dict[str, str]
    summary: str
    notebook_context: str
    pages: list[dict[str, Any]]
    page_count: int
    ready_count: int
    progress: int
    updated_at: float


class LearningPlanService:
    """File-backed learning plan domain using guide-dir storage."""

    def __init__(self, path_service: PathService | None = None) -> None:
        self._path_service = path_service or get_path_service()
        self._store = LearningPlanStore(self._path_service.get_guide_dir())

    def _plan_defaults(self, session_id: str) -> dict[str, Any]:
        normalized = _normalize_session_id(session_id)
        return {
            "session_id": normalized,
            "user_id": "",
            "source_bot_id": "",
            "source_material_refs_json": [],
            "notebook_id": "",
            "notebook_name": "",
            "notebook_context": "",
            "status": "initialized",
            "current_index": -1,
            "chat_history": [],
            "summary": "",
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _normalize_plan(self, session_id: str, plan: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
        normalized_session_id = _normalize_session_id(session_id)
        normalized = dict(self._plan_defaults(normalized_session_id))
        normalized.update({key: value for key, value in plan.items() if key not in {"session_id"}})
        normalized["session_id"] = normalized_session_id
        normalized["user_id"] = _coerce_str(normalized.get("user_id"))
        normalized["source_bot_id"] = _coerce_str(normalized.get("source_bot_id"))
        normalized["source_material_refs_json"] = [
            dict(item) for item in list(normalized.get("source_material_refs_json") or []) if isinstance(item, dict)
        ]
        normalized["notebook_id"] = _coerce_str(normalized.get("notebook_id"))
        normalized["notebook_name"] = _coerce_str(normalized.get("notebook_name"))
        normalized["notebook_context"] = _coerce_str(normalized.get("notebook_context"))
        normalized["status"] = _coerce_str(normalized.get("status")) or "initialized"
        normalized["current_index"] = _coerce_int(normalized.get("current_index"), -1)
        normalized["summary"] = _coerce_str(normalized.get("summary"))
        normalized["chat_history"] = list(normalized.get("chat_history") or [])
        normalized["created_at"] = _coerce_float(normalized.get("created_at"), _now())
        normalized["updated_at"] = _coerce_float(normalized.get("updated_at"), normalized["created_at"])
        normalized["page_count"] = len(pages)
        normalized["ready_count"] = sum(1 for page in pages if _coerce_str(page.get("page_status")) == "ready")
        normalized["progress"] = int(
            (normalized["ready_count"] / normalized["page_count"]) * 100 if normalized["page_count"] else 0
        )
        return normalized

    def _normalize_page(self, session_id: str, page_index: int, page: dict[str, Any], *, created_at: float | None = None) -> dict[str, Any]:
        timestamp = created_at if created_at is not None else _now()
        normalized = dict(page)
        normalized["session_id"] = _normalize_session_id(session_id)
        normalized["page_index"] = int(page_index)
        normalized["knowledge_title"] = _coerce_str(normalized.get("knowledge_title"))
        normalized["knowledge_summary"] = _coerce_str(normalized.get("knowledge_summary"))
        normalized["user_difficulty"] = _coerce_str(normalized.get("user_difficulty"))
        normalized["html"] = _coerce_str(normalized.get("html"))
        page_status = _coerce_str(normalized.get("page_status")) or "pending"
        if normalized["html"] and page_status == "pending":
            page_status = "ready"
        normalized["page_status"] = page_status
        normalized["page_error"] = _coerce_str(normalized.get("page_error"))
        normalized["created_at"] = _coerce_float(normalized.get("created_at"), timestamp)
        normalized["updated_at"] = _coerce_float(normalized.get("updated_at"), timestamp)
        return normalized

    @staticmethod
    def _page_projection(page: dict[str, Any]) -> dict[str, Any]:
        projection = {
            "page_index": _coerce_int(page.get("page_index"), 0),
            "knowledge_title": _coerce_str(page.get("knowledge_title")),
            "knowledge_summary": _coerce_str(page.get("knowledge_summary")),
            "user_difficulty": _coerce_str(page.get("user_difficulty")),
        }
        return projection

    @staticmethod
    def _current_knowledge(pages: list[dict[str, Any]], current_index: int) -> dict[str, Any] | None:
        for page in pages:
            if _coerce_int(page.get("page_index"), -1) == current_index:
                return LearningPlanService._page_projection(page)
        return None

    @staticmethod
    def _page_maps(pages: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        html_pages: dict[str, str] = {}
        page_statuses: dict[str, str] = {}
        page_errors: dict[str, str] = {}
        for page in pages:
            key = str(_coerce_int(page.get("page_index"), 0))
            html_pages[key] = _coerce_str(page.get("html"))
            page_statuses[key] = _coerce_str(page.get("page_status")) or "pending"
            page_errors[key] = _coerce_str(page.get("page_error"))
        return html_pages, page_statuses, page_errors

    def create_plan(self, *, session_id: str, pages: list[dict[str, Any]] | None = None, **fields: Any) -> dict[str, Any]:
        normalized_session_id = _normalize_session_id(session_id)
        now = _now()
        plan = self._plan_defaults(normalized_session_id)
        plan.update(fields)
        plan["session_id"] = normalized_session_id
        plan["created_at"] = _timestamp_from_value(plan.get("created_at"), now)
        plan["updated_at"] = _timestamp_from_value(plan.get("updated_at"), plan["created_at"])

        normalized_pages: list[dict[str, Any]] = []
        for index, item in enumerate(pages or []):
            if not isinstance(item, dict):
                continue
            page_index = _coerce_int(item.get("page_index"), index)
            normalized_pages.append(self._normalize_page(normalized_session_id, page_index, item, created_at=now))

        persisted_plan = self._store.write_plan(normalized_session_id, self._normalize_plan(normalized_session_id, plan, normalized_pages))
        self._store.write_pages(normalized_session_id, normalized_pages)
        return self.read_plan(normalized_session_id) or persisted_plan

    def read_plan(self, session_id: str) -> dict[str, Any] | None:
        normalized_session_id = _normalize_session_id(session_id)
        plan = self._store.read_plan(normalized_session_id)
        if not plan:
            return None
        pages = self._store.read_pages(normalized_session_id)
        return self._normalize_plan(normalized_session_id, plan, pages)

    def update_plan(self, session_id: str, **fields: Any) -> dict[str, Any] | None:
        current = self.read_plan(session_id)
        if current is None:
            return None
        current.update(fields)
        current["updated_at"] = _now()
        pages = self._store.read_pages(session_id)
        persisted = self._store.write_plan(session_id, self._normalize_plan(session_id, current, pages))
        return persisted

    def upsert_page(self, session_id: str, page_index: int, **fields: Any) -> dict[str, Any]:
        normalized_session_id = _normalize_session_id(session_id)
        pages = self._store.read_pages(normalized_session_id)
        now = _now()
        target_index = int(page_index)
        existing = next((page for page in pages if _coerce_int(page.get("page_index"), -1) == target_index), None)
        if existing is None:
            page = self._normalize_page(normalized_session_id, target_index, fields, created_at=now)
            pages.append(page)
        else:
            merged = dict(existing)
            merged.update(fields)
            merged["updated_at"] = now
            page = self._normalize_page(
                normalized_session_id,
                target_index,
                merged,
                created_at=_coerce_float(existing.get("created_at"), now),
            )
            pages = [page if _coerce_int(item.get("page_index"), -1) == target_index else item for item in pages]
        pages.sort(key=lambda item: _coerce_int(item.get("page_index"), 0))
        self._store.write_pages(normalized_session_id, pages)
        plan = self.read_plan(normalized_session_id)
        if plan is not None:
            plan["updated_at"] = now
            self._store.write_plan(normalized_session_id, self._normalize_plan(normalized_session_id, plan, pages))
        return self._normalize_page(normalized_session_id, target_index, page, created_at=_coerce_float(page.get("created_at"), now))

    def list_plans(self) -> list[dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        for session_id in self._store.list_plan_ids():
            plan = self.read_plan(session_id)
            if plan is not None:
                plans.append(
                    {
                        "session_id": plan["session_id"],
                        "notebook_name": plan.get("notebook_name", ""),
                        "status": plan.get("status", "initialized"),
                        "created_at": plan.get("created_at", 0.0),
                        "updated_at": plan.get("updated_at", 0.0),
                        "current_index": _coerce_int(plan.get("current_index"), -1),
                        "page_count": plan.get("page_count", 0),
                        "ready_count": plan.get("ready_count", 0),
                        "progress": plan.get("progress", 0),
                        "user_id": plan.get("user_id", ""),
                        "source_bot_id": plan.get("source_bot_id", ""),
                    }
                )
        plans.sort(key=lambda item: float(item.get("updated_at", item.get("created_at", 0.0)) or 0.0), reverse=True)
        return plans

    def delete_plan(self, session_id: str) -> bool:
        normalized_session_id = _normalize_session_id(session_id)
        return self._store.delete_plan(normalized_session_id)

    def read_guided_session_view(self, session_id: str) -> dict[str, Any] | None:
        plan = self.read_plan(session_id)
        if plan is None:
            return None
        pages = self._store.read_pages(session_id)
        html_pages, page_statuses, page_errors = self._page_maps(pages)
        current_index = _coerce_int(plan.get("current_index"), -1)
        return {
            "session_id": plan["session_id"],
            "notebook_id": plan.get("notebook_id", ""),
            "notebook_name": plan.get("notebook_name", ""),
            "created_at": plan.get("created_at", 0.0),
            "user_id": plan.get("user_id", ""),
            "source_bot_id": plan.get("source_bot_id", ""),
            "source_material_refs_json": list(plan.get("source_material_refs_json") or []),
            "knowledge_points": [self._page_projection(page) for page in pages],
            "current_index": current_index,
            "current_knowledge": self._current_knowledge(pages, current_index),
            "chat_history": list(plan.get("chat_history") or []),
            "status": plan.get("status", "initialized"),
            "html_pages": html_pages,
            "page_statuses": page_statuses,
            "page_errors": page_errors,
            "summary": plan.get("summary", ""),
            "notebook_context": plan.get("notebook_context", ""),
            "pages": pages,
            "page_count": plan.get("page_count", len(pages)),
            "ready_count": plan.get("ready_count", 0),
            "progress": plan.get("progress", 0),
            "updated_at": plan.get("updated_at", plan.get("created_at", 0.0)),
        }


_learning_plan_service: LearningPlanService | None = None


def get_learning_plan_service() -> LearningPlanService:
    global _learning_plan_service
    if _learning_plan_service is None:
        _learning_plan_service = LearningPlanService()
    return _learning_plan_service


__all__ = [
    "LearningPlanService",
    "LearningPlanView",
    "get_learning_plan_service",
]
