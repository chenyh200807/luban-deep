from __future__ import annotations

import json
from pathlib import Path

from deeptutor.knowledge.manager import KnowledgeBaseManager


def _write_config(base_dir: Path, kb_name: str, status: str, progress: dict | None) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "knowledge_bases": {
            kb_name: {
                "path": kb_name,
                "description": f"Knowledge base: {kb_name}",
                "rag_provider": "llamaindex",
                "status": status,
                "progress": progress,
            }
        }
    }
    (base_dir / "kb_config.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _create_ready_llamaindex_storage(base_dir: Path, kb_name: str) -> None:
    storage_dir = base_dir / kb_name / "llamaindex_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "docstore.json").write_text("{}", encoding="utf-8")


def test_processing_status_promotes_to_ready_when_llamaindex_storage_exists(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        "demo",
        "processing",
        {"stage": "processing_documents", "percent": 70},
    )
    _create_ready_llamaindex_storage(tmp_path, "demo")

    manager = KnowledgeBaseManager(base_dir=str(tmp_path))
    info = manager.get_info("demo")

    assert info["status"] == "ready"
    assert info["progress"] is None
    assert info["statistics"]["status"] == "ready"
    assert info["statistics"]["progress"] is None
    assert info["statistics"]["rag_initialized"] is True

    persisted = json.loads((tmp_path / "kb_config.json").read_text(encoding="utf-8"))
    persisted_entry = persisted["knowledge_bases"]["demo"]
    assert persisted_entry["status"] == "ready"
    assert "progress" not in persisted_entry


def test_initializing_status_promotes_to_ready_when_llamaindex_storage_exists(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path, "demo", "initializing", {"stage": "initializing"})
    _create_ready_llamaindex_storage(tmp_path, "demo")

    manager = KnowledgeBaseManager(base_dir=str(tmp_path))
    info = manager.get_info("demo")

    assert info["status"] == "ready"
    assert info["progress"] is None


def test_processing_error_stage_is_not_promoted(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "demo",
        "processing",
        {"stage": "error", "error": "embedding API down"},
    )
    _create_ready_llamaindex_storage(tmp_path, "demo")

    manager = KnowledgeBaseManager(base_dir=str(tmp_path))
    info = manager.get_info("demo")

    assert info["status"] == "processing"
    assert info["progress"] == {"stage": "error", "error": "embedding API down"}


def test_empty_llamaindex_storage_does_not_promote_processing(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "demo",
        "processing",
        {"stage": "processing_documents", "percent": 20},
    )
    (tmp_path / "demo" / "llamaindex_storage").mkdir(parents=True, exist_ok=True)

    manager = KnowledgeBaseManager(base_dir=str(tmp_path))
    info = manager.get_info("demo")

    assert info["status"] == "processing"
    assert info["progress"] == {"stage": "processing_documents", "percent": 20}
    assert info["statistics"]["rag_initialized"] is False
