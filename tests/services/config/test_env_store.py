from __future__ import annotations

from pathlib import Path

from deeptutor.services.config import env_store as env_store_module


def _write_gitfile(worktree_root: Path, gitdir: Path) -> None:
    (worktree_root / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")


def test_env_store_reads_from_main_repo_env_when_worktree_env_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parent = tmp_path / "repos"
    main_repo = parent / "deeptutor"
    worktree = parent / "deeptutor-worktrees" / "observability-m0-m1"
    main_repo.mkdir(parents=True)
    worktree.mkdir(parents=True)

    main_env = main_repo / ".env"
    main_env.write_text(
        "\n".join(
            [
                "LLM_MODEL=gpt-main",
                "LLM_API_KEY=main-key",
                "LLM_HOST=https://example.com/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_gitfile(worktree, main_repo / ".git" / "worktrees" / "observability-m0-m1")

    monkeypatch.setattr(env_store_module, "PROJECT_ROOT", worktree)
    monkeypatch.setattr(env_store_module, "ENV_PATH", worktree / ".env")

    store = env_store_module.EnvStore()

    assert store.path == worktree / ".env"
    assert store.get("LLM_API_KEY") == "main-key"
    assert store.resolve_source_path() == main_env


def test_env_store_backfills_missing_local_values_from_main_repo_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parent = tmp_path / "repos"
    main_repo = parent / "deeptutor"
    worktree = parent / "deeptutor-worktrees" / "observability-m0-m1"
    main_repo.mkdir(parents=True)
    worktree.mkdir(parents=True)

    main_env = main_repo / ".env"
    main_env.write_text(
        "\n".join(
            [
                "LLM_BINDING=openai",
                "LLM_MODEL=gpt-main",
                "LLM_API_KEY=main-key",
                "LLM_HOST=https://example.com/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (worktree / ".env").write_text(
        "\n".join(
            [
                "LLM_MODEL=gpt-worktree",
                "LLM_API_KEY=",
                "LLM_HOST=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_gitfile(worktree, main_repo / ".git" / "worktrees" / "observability-m0-m1")

    monkeypatch.setattr(env_store_module, "PROJECT_ROOT", worktree)
    monkeypatch.setattr(env_store_module, "ENV_PATH", worktree / ".env")

    store = env_store_module.EnvStore()
    values = store.load()

    assert values["LLM_MODEL"] == "gpt-worktree"
    assert values["LLM_API_KEY"] == "main-key"
    assert values["LLM_HOST"] == "https://example.com/v1"
    assert store.resolve_source_path() == worktree / ".env"


def test_env_store_reads_from_legacy_repo_env_when_no_deeptutor_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parent = tmp_path / "repos"
    main_repo = parent / "deeptutor"
    legacy_repo = parent / "FastAPI20251222"
    worktree = parent / "deeptutor-worktrees" / "observability-m0-m1"
    main_repo.mkdir(parents=True)
    legacy_repo.mkdir(parents=True)
    worktree.mkdir(parents=True)

    legacy_env = legacy_repo / ".env"
    legacy_env.write_text(
        "\n".join(
            [
                "LLM_MODEL=qwen-max",
                "LLM_API_KEY=legacy-key",
                "LLM_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_gitfile(worktree, main_repo / ".git" / "worktrees" / "observability-m0-m1")

    monkeypatch.setattr(env_store_module, "PROJECT_ROOT", worktree)
    monkeypatch.setattr(env_store_module, "ENV_PATH", worktree / ".env")

    store = env_store_module.EnvStore()

    assert store.get("LLM_API_KEY") == "legacy-key"
    assert store.resolve_source_path() == legacy_env


def test_env_store_write_keeps_local_worktree_as_write_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parent = tmp_path / "repos"
    main_repo = parent / "deeptutor"
    worktree = parent / "deeptutor-worktrees" / "observability-m0-m1"
    main_repo.mkdir(parents=True)
    worktree.mkdir(parents=True)

    main_env = main_repo / ".env"
    main_env.write_text(
        "\n".join(
            [
                "LLM_MODEL=gpt-main",
                "LLM_API_KEY=main-key",
                "LLM_HOST=https://example.com/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_gitfile(worktree, main_repo / ".git" / "worktrees" / "observability-m0-m1")

    monkeypatch.setattr(env_store_module, "PROJECT_ROOT", worktree)
    monkeypatch.setattr(env_store_module, "ENV_PATH", worktree / ".env")

    store = env_store_module.EnvStore()
    store.write({"LLM_MODEL": "gpt-worktree"})

    assert (worktree / ".env").exists()
    assert "LLM_MODEL=gpt-worktree" in (worktree / ".env").read_text(encoding="utf-8")
    assert "LLM_MODEL=gpt-main" in main_env.read_text(encoding="utf-8")
