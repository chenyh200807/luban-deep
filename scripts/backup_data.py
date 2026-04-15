#!/usr/bin/env python
"""Create a runtime backup archive for ``data/user``."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import tarfile
import sys
from typing import Iterable

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from deeptutor.services.path_service import PathService


def resolve_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    return PathService.get_instance().project_root


def resolve_user_data_dir(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return resolve_project_root(project_root) / "data" / "user"
    return PathService.get_instance().user_data_dir


def resolve_backup_dir(project_root: str | Path | None = None) -> Path:
    return resolve_project_root(project_root) / "data" / "backups"


def build_archive_name(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"deeptutor-data-user-{current.strftime('%Y%m%d-%H%M%SZ')}.tar.gz"


def iter_runtime_files(user_data_dir: Path) -> Iterable[Path]:
    for path in user_data_dir.rglob("*"):
        if path.is_file():
            yield path


def summarize_runtime_tree(user_data_dir: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for path in iter_runtime_files(user_data_dir):
        file_count += 1
        total_bytes += path.stat().st_size
    return file_count, total_bytes


def create_backup_archive(
    user_data_dir: Path,
    project_root: Path,
    backup_dir: Path,
    archive_name: str | None = None,
) -> Path:
    user_data_dir = user_data_dir.resolve()
    project_root = project_root.resolve()
    backup_dir = backup_dir.resolve()

    if not user_data_dir.exists():
        raise FileNotFoundError(f"user data dir does not exist: {user_data_dir}")
    if not user_data_dir.is_dir():
        raise NotADirectoryError(f"user data dir is not a directory: {user_data_dir}")
    if not user_data_dir.is_relative_to(project_root):
        raise ValueError(f"user data dir must live under project root: {user_data_dir}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_archive_name = Path(archive_name).name if archive_name else build_archive_name()
    archive_path = backup_dir / safe_archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(user_data_dir, arcname=str(user_data_dir.relative_to(project_root)))

    return archive_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up data/user into a tar.gz archive")
    parser.add_argument("--project-root", type=Path, help="Override project root")
    parser.add_argument("--backup-dir", type=Path, help="Override backup output directory")
    parser.add_argument("--archive-name", help="Override backup archive filename")
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    user_data_dir = resolve_user_data_dir(project_root)
    backup_dir = args.backup_dir or resolve_backup_dir(project_root)

    archive_path = create_backup_archive(
        user_data_dir=user_data_dir,
        project_root=project_root,
        backup_dir=backup_dir,
        archive_name=args.archive_name,
    )
    file_count, total_bytes = summarize_runtime_tree(user_data_dir)

    print(f"backed up: {user_data_dir}")
    print(f"archive: {archive_path}")
    print(f"files: {file_count}")
    print(f"bytes: {total_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
