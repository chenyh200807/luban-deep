from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.services.config.loader import (
    PROJECT_ROOT,
    get_runtime_settings_dir,
    load_config_with_main,
    resolve_config_path,
)


def test_resolve_config_path_returns_existing_config(tmp_path: Path) -> None:
    settings_dir = tmp_path / "data" / "user" / "settings"
    settings_dir.mkdir(parents=True)
    (settings_dir / "custom.yaml").write_text("system:\n  language: en\n", encoding="utf-8")

    resolved, used_alias = resolve_config_path("custom.yaml", tmp_path)

    assert resolved == settings_dir / "custom.yaml"
    assert used_alias is False


def test_load_config_with_main_merges_main_and_module_config(tmp_path: Path) -> None:
    settings_dir = tmp_path / "data" / "user" / "settings"
    settings_dir.mkdir(parents=True)
    (settings_dir / "main.yaml").write_text(
        "system:\n  language: en\nsolve:\n  max_replans: 2\n",
        encoding="utf-8",
    )
    (settings_dir / "custom.yaml").write_text(
        "solve:\n  max_replans: 5\nlogging:\n  level: INFO\n",
        encoding="utf-8",
    )

    config = load_config_with_main("custom.yaml", tmp_path)

    assert config["system"]["language"] == "en"
    assert config["solve"]["max_replans"] == 5
    assert config["logging"]["level"] == "INFO"


def test_load_config_with_main_raises_for_unknown_missing_config(tmp_path: Path) -> None:
    settings_dir = tmp_path / "data" / "user" / "settings"
    settings_dir.mkdir(parents=True)
    (settings_dir / "main.yaml").write_text("system:\n  language: en\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        load_config_with_main("nonexistent_module.yaml", tmp_path)


def test_load_config_with_main_uses_explicit_project_root() -> None:
    config = load_config_with_main("main.yaml", PROJECT_ROOT)

    assert "system" in config
    assert config["paths"]["solve_output_dir"].endswith("data/user/workspace/chat/deep_solve")


def test_runtime_settings_dir_honors_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override_dir = tmp_path / "custom-runtime"
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(override_dir))

    assert get_runtime_settings_dir(tmp_path) == override_dir.resolve() / "settings"
