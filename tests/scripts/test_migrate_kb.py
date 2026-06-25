from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_kb.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("migrate_kb", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_valid_kb(tmp_path: Path) -> Path:
    kb_dir = tmp_path / "source-kb"
    storage_dir = kb_dir / "llamaindex_storage"
    storage_dir.mkdir(parents=True)
    for filename in ("docstore.json", "index_store.json", "default__vector_store.json"):
        (storage_dir / filename).write_text("{}", encoding="utf-8")
    return kb_dir


def test_migrate_kb_defaults_to_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_script()
    source = _create_valid_kb(tmp_path)
    target_base = tmp_path / "target"
    target_base.mkdir()

    calls: list[str] = []

    def _copy(*_args, **_kwargs):
        calls.append("copy")
        return True

    def _register(*_args, **_kwargs):
        calls.append("register")
        return True

    async def _fake_test_kb_search(*_args, **_kwargs):
        calls.append("test")
        return True

    monkeypatch.setattr(module, "copy_kb_directory", _copy)
    monkeypatch.setattr(module, "register_kb", _register)
    monkeypatch.setattr(module, "test_kb_search", _fake_test_kb_search)

    success = asyncio.run(
        module.migrate_kb(
            source_path=str(source),
            target_base_dir=str(target_base),
            kb_name="preview-kb",
            run_test=True,
            force=True,
        )
    )

    assert success is True
    assert calls == []
    assert not (target_base / "preview-kb").exists()


def test_migrate_kb_apply_executes_copy_and_register(tmp_path: Path) -> None:
    module = _load_script()
    source = _create_valid_kb(tmp_path)
    target_base = tmp_path / "target"
    target_base.mkdir()

    success = asyncio.run(
        module.migrate_kb(
            source_path=str(source),
            target_base_dir=str(target_base),
            kb_name="applied-kb",
            apply=True,
        )
    )

    target_dir = target_base / "applied-kb"
    assert success is True
    assert target_dir.exists()
    assert (target_dir / "metadata.json").exists()
    assert (target_base / "kb_config.json").exists()


def test_main_rejects_apply_with_validate_only(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script()
    monkeypatch.setattr(sys, "argv", ["migrate_kb.py", "/tmp/kb", "--apply", "--validate-only"])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 2
