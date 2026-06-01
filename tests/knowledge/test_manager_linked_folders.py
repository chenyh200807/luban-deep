from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from deeptutor.knowledge import manager as manager_module
from deeptutor.knowledge.manager import KnowledgeBaseManager


def _write_kb_config(base_dir: Path, kb_name: str) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "kb_config.json").write_text(
        json.dumps(
            {
                "knowledge_bases": {
                    kb_name: {
                        "path": kb_name,
                        "description": f"Knowledge base: {kb_name}",
                        "rag_provider": "llamaindex",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _write_metadata(base_dir: Path, kb_name: str, metadata: dict) -> Path:
    kb_dir = base_dir / kb_name
    kb_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = kb_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    return metadata_file


def test_update_folder_sync_state_persists_metadata(tmp_path: Path) -> None:
    kb_name = "demo"
    synced_file = tmp_path / "source.txt"
    synced_file.write_text("content", encoding="utf-8")
    _write_kb_config(tmp_path, kb_name)
    metadata_file = _write_metadata(
        tmp_path,
        kb_name,
        {"linked_folders": [{"id": "folder-1", "path": str(tmp_path)}]},
    )
    manager = KnowledgeBaseManager(base_dir=str(tmp_path))

    manager.update_folder_sync_state(kb_name, "folder-1", [str(synced_file)])

    persisted = json.loads(metadata_file.read_text(encoding="utf-8"))
    folder = persisted["linked_folders"][0]
    assert folder["last_sync"]
    assert folder["synced_files"][str(synced_file)]
    assert folder["file_count"] == 1


def test_unlink_folder_ignores_malformed_linked_folder_entries(tmp_path: Path) -> None:
    kb_name = "demo"
    _write_kb_config(tmp_path, kb_name)
    metadata_file = _write_metadata(
        tmp_path,
        kb_name,
        {"linked_folders": [{"path": "/bad"}, {"id": "keep"}, {"id": "remove"}]},
    )
    manager = KnowledgeBaseManager(base_dir=str(tmp_path))

    assert manager.unlink_folder(kb_name, "remove") is True

    persisted = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert persisted["linked_folders"] == [{"path": "/bad"}, {"id": "keep"}]


def test_detect_folder_changes_ignores_malformed_linked_folder_entries(tmp_path: Path) -> None:
    kb_name = "demo"
    folder = tmp_path / "linked"
    folder.mkdir()
    document = folder / "note.txt"
    document.write_text("new", encoding="utf-8")
    _write_kb_config(tmp_path, kb_name)
    _write_metadata(
        tmp_path,
        kb_name,
        {"linked_folders": [{"path": "/bad"}, {"id": "folder-1", "path": str(folder)}]},
    )
    manager = KnowledgeBaseManager(base_dir=str(tmp_path))

    changes = manager.detect_folder_changes(kb_name, "folder-1")

    assert changes["new_files"] == [str(document)]
    assert changes["modified_files"] == []


def test_windows_file_lock_uses_blocking_lock(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[int, int, int]] = []

    fake_msvcrt = SimpleNamespace(
        LK_LOCK=1,
        LK_NBLCK=2,
        LK_UNLCK=3,
        locking=lambda fileno, mode, size: calls.append((fileno, mode, size)),
    )
    monkeypatch.setattr(manager_module.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    lock_file = tmp_path / "kb_config.json"
    lock_file.write_text("{}", encoding="utf-8")
    with lock_file.open("r+", encoding="utf-8") as handle:
        with manager_module.file_lock_exclusive(handle):
            pass

    assert [call[1] for call in calls] == [fake_msvcrt.LK_LOCK, fake_msvcrt.LK_UNLCK]
