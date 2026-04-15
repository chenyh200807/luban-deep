from __future__ import annotations

from pathlib import Path
import shutil
import tarfile

import pytest

from deeptutor.services.path_service import PathService
from scripts.backup_data import create_backup_archive, prune_backup_archives, resolve_backup_dir
from scripts.restore_data import find_latest_backup, restore_backup_archive


def _use_project_root(tmp_path: Path) -> tuple[PathService, Path, Path]:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    project_root = tmp_path
    user_data_dir = project_root / "data" / "user"

    service._project_root = project_root
    service._user_data_dir = user_data_dir
    return service, original_root, original_user_dir


def _restore_project_root(service: PathService, original_root: Path, original_user_dir: Path) -> None:
    service._project_root = original_root
    service._user_data_dir = original_user_dir


def _write_sample_user_data(user_data_dir: Path) -> None:
    (user_data_dir / "settings").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "workspace" / "chat" / "chat").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "tutor_state").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "logs").mkdir(parents=True, exist_ok=True)

    (user_data_dir / "chat_history.db").write_text("sqlite", encoding="utf-8")
    (user_data_dir / "settings" / "config.json").write_text('{"llm":"openai"}', encoding="utf-8")
    (user_data_dir / "workspace" / "chat" / "chat" / "sessions.json").write_text(
        '{"sessions":[]}', encoding="utf-8"
    )
    (user_data_dir / "tutor_state" / "state.json").write_text('{"turn":1}', encoding="utf-8")
    (user_data_dir / "logs" / "runtime.log").write_text("ok", encoding="utf-8")


def test_backup_archive_contains_data_user_tree(tmp_path: Path) -> None:
    service, original_root, original_user_dir = _use_project_root(tmp_path)
    try:
        user_data_dir = service.user_data_dir
        _write_sample_user_data(user_data_dir)

        archive_path = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=resolve_backup_dir(service.project_root),
        )

        assert archive_path.exists()
        assert archive_path.parent == service.project_root / "data" / "backups"

        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()

        assert "data/user/chat_history.db" in names
        assert "data/user/settings/config.json" in names
        assert "data/user/workspace/chat/chat/sessions.json" in names
        assert all(not name.startswith("data/backups") for name in names)
    finally:
        _restore_project_root(service, original_root, original_user_dir)


def test_restore_archive_recreates_user_data_tree(tmp_path: Path) -> None:
    service, original_root, original_user_dir = _use_project_root(tmp_path)
    try:
        user_data_dir = service.user_data_dir
        _write_sample_user_data(user_data_dir)

        archive_path = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=resolve_backup_dir(service.project_root),
        )

        shutil.rmtree(user_data_dir)

        restored = restore_backup_archive(
            archive_path=archive_path,
            project_root=service.project_root,
            user_data_dir=user_data_dir,
            replace=False,
        )

        assert restored == user_data_dir
        assert (user_data_dir / "chat_history.db").read_text(encoding="utf-8") == "sqlite"
        assert (user_data_dir / "settings" / "config.json").exists()
        assert (user_data_dir / "workspace" / "chat" / "chat" / "sessions.json").exists()
    finally:
        _restore_project_root(service, original_root, original_user_dir)


def test_restore_requires_replace_for_existing_data(tmp_path: Path) -> None:
    service, original_root, original_user_dir = _use_project_root(tmp_path)
    try:
        user_data_dir = service.user_data_dir
        _write_sample_user_data(user_data_dir)

        archive_path = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=resolve_backup_dir(service.project_root),
        )

        with pytest.raises(FileExistsError):
            restore_backup_archive(
                archive_path=archive_path,
                project_root=service.project_root,
                user_data_dir=user_data_dir,
                replace=False,
            )
    finally:
        _restore_project_root(service, original_root, original_user_dir)


def test_restore_allows_existing_empty_directory(tmp_path: Path) -> None:
    service, original_root, original_user_dir = _use_project_root(tmp_path)
    try:
        user_data_dir = service.user_data_dir
        user_data_dir.mkdir(parents=True, exist_ok=True)
        _write_sample_user_data(user_data_dir)

        archive_path = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=resolve_backup_dir(service.project_root),
        )

        shutil.rmtree(user_data_dir)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        restored = restore_backup_archive(
            archive_path=archive_path,
            project_root=service.project_root,
            user_data_dir=user_data_dir,
            replace=False,
        )

        assert restored == user_data_dir
        assert (user_data_dir / "chat_history.db").exists()
    finally:
        _restore_project_root(service, original_root, original_user_dir)


def test_find_latest_backup_prefers_newest_name(tmp_path: Path) -> None:
    service, original_root, original_user_dir = _use_project_root(tmp_path)
    try:
        user_data_dir = service.user_data_dir
        _write_sample_user_data(user_data_dir)
        backup_dir = resolve_backup_dir(service.project_root)

        older = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=backup_dir,
            archive_name="deeptutor-data-user-20240101-000000Z.tar.gz",
        )
        newer = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=backup_dir,
            archive_name="deeptutor-data-user-20240102-000000Z.tar.gz",
        )

        latest = find_latest_backup(backup_dir)

        assert latest == newer
        assert older.exists()
    finally:
        _restore_project_root(service, original_root, original_user_dir)


def test_prune_backup_archives_keeps_newest_requested_count(tmp_path: Path) -> None:
    service, original_root, original_user_dir = _use_project_root(tmp_path)
    try:
        user_data_dir = service.user_data_dir
        _write_sample_user_data(user_data_dir)
        backup_dir = resolve_backup_dir(service.project_root)

        oldest = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=backup_dir,
            archive_name="deeptutor-data-user-20240101-000000Z.tar.gz",
        )
        middle = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=backup_dir,
            archive_name="deeptutor-data-user-20240102-000000Z.tar.gz",
        )
        newest = create_backup_archive(
            user_data_dir=user_data_dir,
            project_root=service.project_root,
            backup_dir=backup_dir,
            archive_name="deeptutor-data-user-20240103-000000Z.tar.gz",
        )

        removed = prune_backup_archives(backup_dir, keep=2)

        assert removed == [oldest]
        assert not oldest.exists()
        assert middle.exists()
        assert newest.exists()
        assert prune_backup_archives(backup_dir, keep=5) == []
    finally:
        _restore_project_root(service, original_root, original_user_dir)
