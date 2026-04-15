"""
Shared notebook manager.

This module keeps the notebook storage format unchanged so Web and CLI
can operate on the same files under ``data/user``.
"""

from __future__ import annotations

import asyncio
from enum import Enum
import json
from datetime import datetime
from pathlib import Path
import time
from typing import Any
import uuid

from pydantic import BaseModel

from deeptutor.services.path_service import get_path_service
from deeptutor.services.tutor_state.service import UserTutorStateService


class RecordType(str, Enum):
    """Notebook record type."""

    SOLVE = "solve"
    QUESTION = "question"
    RESEARCH = "research"
    CO_WRITER = "co_writer"
    CHAT = "chat"
    GUIDED_LEARNING = "guided_learning"


class NotebookRecord(BaseModel):
    """Single record stored in a notebook."""

    id: str
    type: RecordType
    title: str
    summary: str = ""
    user_query: str
    output: str
    metadata: dict = {}
    created_at: float
    kb_name: str | None = None


class Notebook(BaseModel):
    """Notebook model."""

    id: str
    name: str
    description: str = ""
    created_at: float
    updated_at: float
    records: list[NotebookRecord] = []
    color: str = "#3B82F6"
    icon: str = "book"


_UNSET = object()


class NotebookManager:
    """Manage notebook files stored under ``data/user/workspace/notebook``."""

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            path_service = get_path_service()
            base_dir_path = path_service.get_notebook_dir()
        else:
            base_dir_path = Path(base_dir)

        self.base_dir = base_dir_path
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.base_dir / "notebooks_index.json"
        self._ensure_index()

    def _ensure_index(self) -> None:
        if not self.index_file.exists():
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump({"notebooks": []}, f, indent=2, ensure_ascii=False)

    def _load_index(self) -> dict:
        try:
            with open(self.index_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"notebooks": []}

    def _save_index(self, index: dict) -> None:
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _get_notebook_file(self, notebook_id: str) -> Path:
        return self.base_dir / f"{notebook_id}.json"

    def _load_notebook(self, notebook_id: str) -> dict | None:
        filepath = self._get_notebook_file(notebook_id)
        if not filepath.exists():
            return None
        try:
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_notebook(self, notebook: dict) -> None:
        filepath = self._get_notebook_file(notebook["id"])
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=2, ensure_ascii=False)

    def _touch_index_entry(self, notebook_id: str, notebook: dict) -> None:
        index = self._load_index()
        for nb_info in index.get("notebooks", []):
            if nb_info["id"] != notebook_id:
                continue
            nb_info["name"] = notebook.get("name", nb_info.get("name", ""))
            nb_info["description"] = notebook.get("description", nb_info.get("description", ""))
            nb_info["updated_at"] = notebook["updated_at"]
            nb_info["record_count"] = len(notebook.get("records", []))
            nb_info["color"] = notebook.get("color", nb_info.get("color", "#3B82F6"))
            nb_info["icon"] = notebook.get("icon", nb_info.get("icon", "book"))
            break
        self._save_index(index)

    def _resolve_learner_context(
        self,
        metadata: dict | None,
        *,
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> tuple[str, str]:
        meta = metadata or {}
        resolved_user_id = ""
        for candidate in (
            user_id,
            meta.get("user_id"),
            meta.get("learner_user_id"),
            meta.get("source_user_id"),
            meta.get("owner_user_id"),
        ):
            value = str(candidate or "").strip()
            if value:
                resolved_user_id = value
                break

        resolved_source_bot_id = ""
        for candidate in (source_bot_id, meta.get("source_bot_id"), meta.get("bot_id")):
            value = str(candidate or "").strip()
            if value:
                resolved_source_bot_id = value
                break

        return resolved_user_id, resolved_source_bot_id

    def _dispatch_writeback(self, coro: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return

        task = loop.create_task(coro)

        def _consume_exception(completed: asyncio.Task[Any]) -> None:
            try:
                completed.result()
            except Exception:
                pass

        task.add_done_callback(_consume_exception)

    async def _writeback_learner_state(
        self,
        *,
        user_id: str,
        source_bot_id: str,
        notebook_id: str,
        title: str,
        user_query: str,
        summary: str,
        output: str,
        metadata: dict | None,
    ) -> bool:
        normalized_user_id = str(user_id or "").strip()
        normalized_summary = str(summary or "").strip()
        normalized_output = str(output or "").strip()
        normalized_title = str(title or "").strip()
        normalized_user_query = str(user_query or "").strip()
        if not normalized_user_id:
            return False

        assistant_message = (
            normalized_summary
            or normalized_output
            or normalized_user_query
            or normalized_title
        )
        if not assistant_message:
            return False

        learner_state_service = UserTutorStateService()
        await learner_state_service.record_notebook_writeback(
            user_id=normalized_user_id,
            notebook_id=notebook_id,
            record_id=str((metadata or {}).get("record_id", "") or ""),
            operation=str((metadata or {}).get("operation", "upsert") or "upsert"),
            title=normalized_title,
            summary=normalized_summary,
            user_query=normalized_user_query,
            record_type=str((metadata or {}).get("record_type", "") or ""),
            kb_name=str((metadata or {}).get("kb_name", "") or "") or None,
            metadata=dict(metadata or {}),
            source_bot_id=source_bot_id or None,
        )
        await learner_state_service.refresh_from_turn(
            user_id=normalized_user_id,
            user_message=normalized_title or normalized_user_query or f"Notebook {notebook_id}",
            assistant_message=assistant_message,
            session_id=str(notebook_id),
            capability="notebook" if not source_bot_id else f"notebook:{source_bot_id}",
            language=str((metadata or {}).get("ui_language", "en") or "en"),
            timestamp=datetime.now().isoformat(),
            source_bot_id=source_bot_id or None,
        )
        return True

    # === Notebook Operations ===

    def create_notebook(
        self, name: str, description: str = "", color: str = "#3B82F6", icon: str = "book"
    ) -> dict:
        notebook_id = str(uuid.uuid4())[:8]
        now = time.time()

        notebook = {
            "id": notebook_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "records": [],
            "color": color,
            "icon": icon,
        }

        self._save_notebook(notebook)

        index = self._load_index()
        index["notebooks"].append(
            {
                "id": notebook_id,
                "name": name,
                "description": description,
                "created_at": now,
                "updated_at": now,
                "record_count": 0,
                "color": color,
                "icon": icon,
            }
        )
        self._save_index(index)
        return notebook

    def list_notebooks(self) -> list[dict]:
        index = self._load_index()
        notebooks: list[dict] = []

        for nb_info in index.get("notebooks", []):
            notebook = self._load_notebook(nb_info["id"])
            if notebook:
                notebooks.append(
                    {
                        "id": notebook["id"],
                        "name": notebook["name"],
                        "description": notebook.get("description", ""),
                        "created_at": notebook["created_at"],
                        "updated_at": notebook["updated_at"],
                        "record_count": len(notebook.get("records", [])),
                        "color": notebook.get("color", "#3B82F6"),
                        "icon": notebook.get("icon", "book"),
                    }
                )

        notebooks.sort(key=lambda x: x["updated_at"], reverse=True)
        return notebooks

    def get_notebook(self, notebook_id: str) -> dict | None:
        return self._load_notebook(notebook_id)

    def update_notebook(
        self,
        notebook_id: str,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        icon: str | None = None,
    ) -> dict | None:
        notebook = self._load_notebook(notebook_id)
        if not notebook:
            return None

        if name is not None:
            notebook["name"] = name
        if description is not None:
            notebook["description"] = description
        if color is not None:
            notebook["color"] = color
        if icon is not None:
            notebook["icon"] = icon

        notebook["updated_at"] = time.time()
        self._save_notebook(notebook)
        self._touch_index_entry(notebook_id, notebook)
        return notebook

    def delete_notebook(self, notebook_id: str) -> bool:
        filepath = self._get_notebook_file(notebook_id)
        if not filepath.exists():
            return False

        filepath.unlink()
        index = self._load_index()
        index["notebooks"] = [nb for nb in index["notebooks"] if nb["id"] != notebook_id]
        self._save_index(index)
        return True

    # === Record Operations ===

    def add_record(
        self,
        notebook_ids: list[str],
        record_type: RecordType | str,
        title: str,
        user_query: str,
        output: str,
        summary: str = "",
        metadata: dict | None = None,
        kb_name: str | None = None,
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> dict:
        record_id = str(uuid.uuid4())[:8]
        now = time.time()
        # Accept both enum instances and plain string values from callers.
        resolved_type = record_type if isinstance(record_type, RecordType) else RecordType(str(record_type))
        resolved_user_id, resolved_source_bot_id = self._resolve_learner_context(
            metadata,
            user_id=user_id,
            source_bot_id=source_bot_id,
        )
        record_metadata = dict(metadata or {})
        if resolved_user_id:
            record_metadata.setdefault("user_id", resolved_user_id)
        if resolved_source_bot_id:
            record_metadata.setdefault("source_bot_id", resolved_source_bot_id)

        record = {
            "id": record_id,
            "type": resolved_type,
            "title": title,
            "summary": summary,
            "user_query": user_query,
            "output": output,
            "metadata": record_metadata,
            "created_at": now,
            "kb_name": kb_name,
        }

        added_to: list[str] = []
        for notebook_id in notebook_ids:
            notebook = self._load_notebook(notebook_id)
            if not notebook:
                continue
            notebook["records"].append(record)
            notebook["updated_at"] = now
            self._save_notebook(notebook)
            self._touch_index_entry(notebook_id, notebook)
            added_to.append(notebook_id)

        if resolved_user_id and added_to:
            self._dispatch_writeback(
                self._writeback_learner_state(
                    user_id=resolved_user_id,
                    source_bot_id=resolved_source_bot_id,
                    notebook_id=added_to[0],
                    title=title,
                    user_query=user_query,
                    summary=summary,
                    output=output,
                    metadata={
                        **record_metadata,
                        "record_id": record_id,
                        "operation": "add",
                        "record_type": str(resolved_type),
                        "kb_name": kb_name,
                    },
                )
            )

        return {"record": record, "added_to_notebooks": added_to}

    def get_records(self, notebook_id: str, record_ids: list[str] | None = None) -> list[dict]:
        notebook = self._load_notebook(notebook_id)
        if not notebook:
            return []

        records = list(notebook.get("records", []))
        if not record_ids:
            return records

        wanted = set(record_ids)
        return [record for record in records if str(record.get("id", "")) in wanted]

    def get_record(self, notebook_id: str, record_id: str) -> dict | None:
        records = self.get_records(notebook_id, [record_id])
        return records[0] if records else None

    def update_record(
        self,
        notebook_id: str,
        record_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        user_query: str | None = None,
        output: str | None = None,
        metadata: dict | None = None,
        kb_name: str | None | object = _UNSET,
        user_id: str | None = None,
        source_bot_id: str | None = None,
    ) -> dict | None:
        notebook = self._load_notebook(notebook_id)
        if not notebook:
            return None

        resolved_user_id, resolved_source_bot_id = self._resolve_learner_context(
            metadata,
            user_id=user_id,
            source_bot_id=source_bot_id,
        )
        updated_record: dict | None = None
        for record in notebook.get("records", []):
            if str(record.get("id", "")) != str(record_id):
                continue
            current_metadata = dict(record.get("metadata", {}) or {})
            current_user_id, current_source_bot_id = self._resolve_learner_context(
                current_metadata,
                user_id=resolved_user_id or None,
                source_bot_id=resolved_source_bot_id or None,
            )
            resolved_user_id = current_user_id or resolved_user_id
            resolved_source_bot_id = current_source_bot_id or resolved_source_bot_id
            if title is not None:
                record["title"] = title
            if summary is not None:
                record["summary"] = summary
            if user_query is not None:
                record["user_query"] = user_query
            if output is not None:
                record["output"] = output
            if metadata is not None:
                record["metadata"] = {**current_metadata, **metadata}
            else:
                record["metadata"] = current_metadata
            if kb_name is not _UNSET:
                record["kb_name"] = kb_name
            if resolved_user_id:
                record.setdefault("metadata", {})
                record["metadata"]["user_id"] = resolved_user_id
            if resolved_source_bot_id:
                record.setdefault("metadata", {})
                record["metadata"]["source_bot_id"] = resolved_source_bot_id
            updated_record = record
            break

        if updated_record is None:
            return None

        notebook["updated_at"] = time.time()
        self._save_notebook(notebook)
        self._touch_index_entry(notebook_id, notebook)

        if resolved_user_id:
            self._dispatch_writeback(
                self._writeback_learner_state(
                    user_id=resolved_user_id,
                    source_bot_id=resolved_source_bot_id,
                    notebook_id=notebook_id,
                    title=str(updated_record.get("title", "") or title or ""),
                    user_query=str(updated_record.get("user_query", "") or user_query or ""),
                    summary=str(updated_record.get("summary", "") or summary or ""),
                    output=str(updated_record.get("output", "") or output or ""),
                    metadata={
                        **(updated_record.get("metadata", {}) or metadata or {}),
                        "record_id": record_id,
                        "operation": "update",
                        "record_type": str(updated_record.get("type", "") or ""),
                        "kb_name": None if kb_name is _UNSET else kb_name,
                    },
                )
            )
        return updated_record

    def get_records_by_references(self, notebook_references: list[dict]) -> list[dict]:
        resolved: list[dict] = []

        for ref in notebook_references:
            notebook_id = str(ref.get("notebook_id", "") or "").strip()
            if not notebook_id:
                continue
            record_ids = [
                str(record_id).strip()
                for record_id in (ref.get("record_ids") or [])
                if str(record_id).strip()
            ]
            notebook = self._load_notebook(notebook_id)
            if not notebook:
                continue

            notebook_name = str(notebook.get("name", "") or notebook_id)
            for record in self.get_records(notebook_id, record_ids):
                resolved.append(
                    {
                        **record,
                        "notebook_id": notebook_id,
                        "notebook_name": notebook_name,
                    }
                )

        return resolved

    def remove_record(self, notebook_id: str, record_id: str) -> bool:
        notebook = self._load_notebook(notebook_id)
        if not notebook:
            return False

        original_count = len(notebook["records"])
        notebook["records"] = [r for r in notebook["records"] if r["id"] != record_id]

        if len(notebook["records"]) == original_count:
            return False

        notebook["updated_at"] = time.time()
        self._save_notebook(notebook)
        self._touch_index_entry(notebook_id, notebook)
        return True

    def get_statistics(self) -> dict:
        notebooks = self.list_notebooks()

        total_records = 0
        type_counts = {
            "solve": 0,
            "question": 0,
            "research": 0,
            "co_writer": 0,
            "chat": 0,
            "guided_learning": 0,
        }

        for nb_info in notebooks:
            notebook = self._load_notebook(nb_info["id"])
            if notebook:
                for record in notebook.get("records", []):
                    total_records += 1
                    record_type = record.get("type", "")
                    if record_type in type_counts:
                        type_counts[record_type] += 1

        return {
            "total_notebooks": len(notebooks),
            "total_records": total_records,
            "records_by_type": type_counts,
            "recent_notebooks": notebooks[:5],
        }


_instance: NotebookManager | None = None


def get_notebook_manager() -> NotebookManager:
    global _instance
    if _instance is None:
        _instance = NotebookManager()
    return _instance


notebook_manager = get_notebook_manager()
