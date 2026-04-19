"""
Shared notebook manager.

This module keeps the notebook storage format unchanged so Web and CLI
can operate on the same files under ``data/user``.
"""

from __future__ import annotations

import asyncio
import hashlib
from enum import Enum
import json
from datetime import datetime
from pathlib import Path
import time
from typing import Any
import uuid

from pydantic import BaseModel

from deeptutor.services.learner_state.service import get_learner_state_service
from deeptutor.services.path_service import get_path_service


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
        self._ensure_index()

    @staticmethod
    def _empty_index() -> dict[str, list[dict[str, Any]]]:
        return {"notebooks": []}

    @staticmethod
    def _owner_scope_name(owner_key: str | None) -> str:
        normalized = str(owner_key or "").strip()
        if not normalized:
            return ""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _scope_dir(self, owner_key: str | None = None) -> Path:
        scope_name = self._owner_scope_name(owner_key)
        if not scope_name:
            return self.base_dir
        return self.base_dir / "owners" / scope_name

    def _index_file_for(self, owner_key: str | None = None) -> Path:
        return self._scope_dir(owner_key) / "notebooks_index.json"

    def _ensure_index(self, owner_key: str | None = None) -> None:
        index_file = self._index_file_for(owner_key)
        index_file.parent.mkdir(parents=True, exist_ok=True)
        if not index_file.exists():
            self._write_json_file(index_file, self._empty_index())

    def _write_json_file(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        temp_path.replace(path)

    def _rebuild_index(self, owner_key: str | None = None) -> dict[str, Any]:
        scope_dir = self._scope_dir(owner_key)
        notebooks: list[dict[str, Any]] = []
        if scope_dir.exists():
            for notebook_file in sorted(scope_dir.glob("*.json")):
                if notebook_file.name == "notebooks_index.json":
                    continue
                notebook = self._read_json_file(notebook_file)
                if not isinstance(notebook, dict) or not notebook.get("id"):
                    continue
                notebooks.append(
                    {
                        "id": notebook["id"],
                        "name": notebook.get("name", ""),
                        "description": notebook.get("description", ""),
                        "created_at": notebook.get("created_at", 0),
                        "updated_at": notebook.get("updated_at", 0),
                        "record_count": len(notebook.get("records", [])),
                        "color": notebook.get("color", "#3B82F6"),
                        "icon": notebook.get("icon", "book"),
                        "owner_key": str(notebook.get("owner_key") or str(owner_key or "").strip()),
                    }
                )
        index = {"notebooks": notebooks}
        self._write_json_file(self._index_file_for(owner_key), index)
        return index

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any] | None:
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        if not isinstance(loaded, dict):
            return None
        return loaded

    def _load_index(self, owner_key: str | None = None) -> dict:
        index_file = self._index_file_for(owner_key)
        loaded = self._read_json_file(index_file)
        if loaded is None:
            return self._rebuild_index(owner_key)
        notebooks = loaded.get("notebooks")
        if not isinstance(notebooks, list):
            return self._rebuild_index(owner_key)
        return loaded

    def _save_index(self, index: dict, owner_key: str | None = None) -> None:
        self._write_json_file(self._index_file_for(owner_key), index)

    def _get_notebook_file(self, notebook_id: str, owner_key: str | None = None) -> Path:
        return self._scope_dir(owner_key) / f"{notebook_id}.json"

    def _load_notebook(self, notebook_id: str, owner_key: str | None = None) -> dict | None:
        filepath = self._get_notebook_file(notebook_id, owner_key=owner_key)
        if not filepath.exists():
            return None
        return self._read_json_file(filepath)

    def _save_notebook(self, notebook: dict, owner_key: str | None = None) -> None:
        filepath = self._get_notebook_file(notebook["id"], owner_key=owner_key)
        self._write_json_file(filepath, notebook)

    def _touch_index_entry(self, notebook_id: str, notebook: dict, owner_key: str | None = None) -> None:
        index = self._load_index(owner_key)
        for nb_info in index.get("notebooks", []):
            if nb_info["id"] != notebook_id:
                continue
            nb_info["name"] = notebook.get("name", nb_info.get("name", ""))
            nb_info["description"] = notebook.get("description", nb_info.get("description", ""))
            nb_info["updated_at"] = notebook["updated_at"]
            nb_info["record_count"] = len(notebook.get("records", []))
            nb_info["color"] = notebook.get("color", nb_info.get("color", "#3B82F6"))
            nb_info["icon"] = notebook.get("icon", nb_info.get("icon", "book"))
            nb_info["owner_key"] = str(notebook.get("owner_key") or str(owner_key or "").strip())
            break
        self._save_index(index, owner_key)

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

        learner_state_service = get_learner_state_service()
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
        if source_bot_id:
            try:
                from deeptutor.services.learner_state import get_bot_learner_overlay_service

                operations: list[dict[str, Any]] = [
                    {
                        "op": "set",
                        "field": "local_notebook_scope_refs",
                        "value": [str(notebook_id).strip()],
                    }
                ]
                if normalized_summary or normalized_title:
                    operations.append(
                        {
                            "op": "set",
                            "field": "working_memory_projection",
                            "value": normalized_summary or normalized_title,
                        }
                    )
                get_bot_learner_overlay_service().patch_overlay(
                    source_bot_id,
                    normalized_user_id,
                    {"operations": operations},
                    source_feature="notebook",
                    source_id=str((metadata or {}).get("record_id", "") or notebook_id),
                )
            except Exception:
                pass
        return True

    # === Notebook Operations ===

    def create_notebook(
        self,
        name: str,
        description: str = "",
        color: str = "#3B82F6",
        icon: str = "book",
        owner_key: str | None = None,
    ) -> dict:
        notebook_id = str(uuid.uuid4())[:8]
        now = time.time()
        normalized_owner_key = str(owner_key or "").strip()

        notebook = {
            "id": notebook_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "records": [],
            "color": color,
            "icon": icon,
            "owner_key": normalized_owner_key,
        }

        self._ensure_index(normalized_owner_key)
        self._save_notebook(notebook, owner_key=normalized_owner_key)

        index = self._load_index(normalized_owner_key)
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
                "owner_key": normalized_owner_key,
            }
        )
        self._save_index(index, normalized_owner_key)
        return notebook

    def list_notebooks(self, owner_key: str | None = None) -> list[dict]:
        normalized_owner_key = str(owner_key or "").strip()
        index = self._load_index(normalized_owner_key)
        notebooks: list[dict] = []

        for nb_info in index.get("notebooks", []):
            notebook = self._load_notebook(nb_info["id"], owner_key=normalized_owner_key)
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

    def get_notebook(self, notebook_id: str, owner_key: str | None = None) -> dict | None:
        return self._load_notebook(notebook_id, owner_key=owner_key)

    def update_notebook(
        self,
        notebook_id: str,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        owner_key: str | None = None,
    ) -> dict | None:
        normalized_owner_key = str(owner_key or "").strip()
        notebook = self._load_notebook(notebook_id, owner_key=normalized_owner_key)
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
        self._save_notebook(notebook, owner_key=normalized_owner_key)
        self._touch_index_entry(notebook_id, notebook, owner_key=normalized_owner_key)
        return notebook

    def delete_notebook(self, notebook_id: str, owner_key: str | None = None) -> bool:
        normalized_owner_key = str(owner_key or "").strip()
        filepath = self._get_notebook_file(notebook_id, owner_key=normalized_owner_key)
        if not filepath.exists():
            return False

        filepath.unlink()
        index = self._load_index(normalized_owner_key)
        index["notebooks"] = [nb for nb in index["notebooks"] if nb["id"] != notebook_id]
        self._save_index(index, normalized_owner_key)
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
        owner_key: str | None = None,
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
            notebook = self._load_notebook(notebook_id, owner_key=owner_key)
            if not notebook:
                continue
            notebook["records"].append(record)
            notebook["updated_at"] = now
            self._save_notebook(notebook, owner_key=owner_key)
            self._touch_index_entry(notebook_id, notebook, owner_key=owner_key)
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

    def get_records(
        self,
        notebook_id: str,
        record_ids: list[str] | None = None,
        owner_key: str | None = None,
    ) -> list[dict]:
        notebook = self._load_notebook(notebook_id, owner_key=owner_key)
        if not notebook:
            return []

        records = list(notebook.get("records", []))
        if not record_ids:
            return records

        wanted = set(record_ids)
        return [record for record in records if str(record.get("id", "")) in wanted]

    def get_record(
        self,
        notebook_id: str,
        record_id: str,
        owner_key: str | None = None,
    ) -> dict | None:
        records = self.get_records(notebook_id, [record_id], owner_key=owner_key)
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
        owner_key: str | None = None,
    ) -> dict | None:
        normalized_owner_key = str(owner_key or "").strip()
        notebook = self._load_notebook(notebook_id, owner_key=normalized_owner_key)
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
        self._save_notebook(notebook, owner_key=normalized_owner_key)
        self._touch_index_entry(notebook_id, notebook, owner_key=normalized_owner_key)

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

    def get_records_by_references(
        self,
        notebook_references: list[dict],
        owner_key: str | None = None,
    ) -> list[dict]:
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
            notebook = self._load_notebook(notebook_id, owner_key=owner_key)
            if not notebook:
                continue

            notebook_name = str(notebook.get("name", "") or notebook_id)
            for record in self.get_records(notebook_id, record_ids, owner_key=owner_key):
                resolved.append(
                    {
                        **record,
                        "notebook_id": notebook_id,
                        "notebook_name": notebook_name,
                    }
                )

        return resolved

    def remove_record(self, notebook_id: str, record_id: str, owner_key: str | None = None) -> bool:
        normalized_owner_key = str(owner_key or "").strip()
        notebook = self._load_notebook(notebook_id, owner_key=normalized_owner_key)
        if not notebook:
            return False

        original_count = len(notebook["records"])
        notebook["records"] = [r for r in notebook["records"] if r["id"] != record_id]

        if len(notebook["records"]) == original_count:
            return False

        notebook["updated_at"] = time.time()
        self._save_notebook(notebook, owner_key=normalized_owner_key)
        self._touch_index_entry(notebook_id, notebook, owner_key=normalized_owner_key)
        return True

    def get_statistics(self, owner_key: str | None = None) -> dict:
        notebooks = self.list_notebooks(owner_key=owner_key)

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
            notebook = self._load_notebook(nb_info["id"], owner_key=owner_key)
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
