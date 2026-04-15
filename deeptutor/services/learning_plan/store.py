from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _normalize_session_id(session_id: str) -> str:
    cleaned = str(session_id or "").strip()
    if not cleaned:
        raise ValueError("session_id is required")
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in cleaned)[:120]


class LearningPlanStore:
    """File-backed store for learning plan records and pages."""

    def __init__(self, guide_root: Path) -> None:
        self._guide_root = guide_root
        self._plans_dir = self._guide_root / "learning_plans"
        self._pages_dir = self._guide_root / "learning_plan_pages"
        self._plans_dir.mkdir(parents=True, exist_ok=True)
        self._pages_dir.mkdir(parents=True, exist_ok=True)

    def _plan_path(self, session_id: str) -> Path:
        return self._plans_dir / f"{_normalize_session_id(session_id)}.json"

    def _pages_path(self, session_id: str) -> Path:
        return self._pages_dir / f"{_normalize_session_id(session_id)}.json"

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return default
            return json.loads(content)
        except Exception:
            return default

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_plan(self, session_id: str) -> dict[str, Any]:
        payload = self._read_json(self._plan_path(session_id), {})
        return dict(payload) if isinstance(payload, dict) else {}

    def write_plan(self, session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        payload = dict(plan)
        payload["session_id"] = _normalize_session_id(session_id)
        self._write_json(self._plan_path(session_id), payload)
        return self.read_plan(session_id)

    def delete_plan(self, session_id: str) -> bool:
        removed = False
        plan_path = self._plan_path(session_id)
        pages_path = self._pages_path(session_id)
        for path in (plan_path, pages_path):
            if path.exists():
                path.unlink()
                removed = True
        return removed

    def list_plan_ids(self) -> list[str]:
        plan_ids = [path.stem for path in self._plans_dir.glob("*.json") if path.is_file()]
        return sorted(plan_ids)

    def read_pages(self, session_id: str) -> list[dict[str, Any]]:
        payload = self._read_json(self._pages_path(session_id), [])
        if not isinstance(payload, list):
            return []
        pages = [dict(item) for item in payload if isinstance(item, dict)]
        pages.sort(key=lambda item: int(item.get("page_index", 0)))
        return pages

    def write_pages(self, session_id: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in pages:
            if not isinstance(item, dict):
                continue
            page = dict(item)
            page["session_id"] = _normalize_session_id(session_id)
            page["page_index"] = int(page.get("page_index", 0))
            normalized.append(page)
        normalized.sort(key=lambda item: int(item.get("page_index", 0)))
        self._write_json(self._pages_path(session_id), normalized)
        return self.read_pages(session_id)
