from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.services.rag.embedding_signature import signature_from_config


def _write_versioned_index(kb_dir: Path) -> str:
    config = SimpleNamespace(
        binding="openai",
        model="embed-a",
        dim=1024,
        effective_url="https://example.test/v1",
        base_url="https://example.test/v1",
        api_version="",
    )
    signature = signature_from_config(config)
    version_dir = kb_dir / "version-1"
    version_dir.mkdir(parents=True)
    (version_dir / "docstore.json").write_text("{}", encoding="utf-8")
    (version_dir / "meta.json").write_text(
        json.dumps({"signature": signature.hash(), "version": "version-1"}),
        encoding="utf-8",
    )
    return signature.hash()


def test_manager_auto_registers_versioned_kb(tmp_path: Path) -> None:
    kb_dir = tmp_path / "versioned-kb"
    _write_versioned_index(kb_dir)

    manager = KnowledgeBaseManager(base_dir=str(tmp_path))

    assert "versioned-kb" in manager.list_knowledge_bases()
    assert manager.config["knowledge_bases"]["versioned-kb"]["rag_provider"] == "llamaindex"


def test_manager_info_reports_versioned_index_state(monkeypatch, tmp_path: Path) -> None:
    kb_dir = tmp_path / "versioned-kb"
    signature_hash = _write_versioned_index(kb_dir)
    manager = KnowledgeBaseManager(base_dir=str(tmp_path))

    signature_module = __import__(
        "deeptutor.services.rag.embedding_signature",
        fromlist=["signature_from_embedding_config"],
    )
    monkeypatch.setattr(
        signature_module,
        "signature_from_embedding_config",
        lambda: signature_from_config(
            SimpleNamespace(
                binding="openai",
                model="embed-a",
                dim=1024,
                effective_url="https://example.test/v1",
                base_url="https://example.test/v1",
                api_version="",
            )
        ),
    )

    info = manager.get_info("versioned-kb")

    assert manager.get_rag_storage_path("versioned-kb") == kb_dir / "version-1"
    assert info["statistics"]["rag_initialized"] is True
    assert info["statistics"]["active_signature"] == signature_hash
    assert info["statistics"]["active_match"] is True
    assert info["statistics"]["index_versions"][0]["layout"] == "flat"
