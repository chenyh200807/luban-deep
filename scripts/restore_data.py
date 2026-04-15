#!/usr/bin/env python
"""Restore a runtime backup archive into ``data/user``."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tarfile
import tempfile
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.backup_data import resolve_backup_dir, resolve_project_root, resolve_user_data_dir


def find_latest_backup(backup_dir: Path) -> Path:
    backup_dir = backup_dir.resolve()
    candidates = sorted(backup_dir.glob("deeptutor-data-user-*.tar.gz"))
    if not candidates:
        raise FileNotFoundError(f"no backup archive found in {backup_dir}")
    return candidates[-1]


def _is_within_directory(root: Path, candidate: Path) -> bool:
    root = root.resolve()
    candidate = candidate.resolve()
    return candidate == root or root in candidate.parents


def _safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"archive contains unsupported link entry: {member.name}")
            member_path = destination / member.name
            if not _is_within_directory(destination, member_path):
                raise ValueError(f"archive member escapes destination: {member.name}")
        tar.extractall(destination)


def restore_backup_archive(
    archive_path: Path,
    project_root: Path,
    user_data_dir: Path,
    replace: bool = False,
) -> Path:
    archive_path = archive_path.resolve()
    project_root = project_root.resolve()
    user_data_dir = user_data_dir.resolve()

    if not archive_path.exists():
        raise FileNotFoundError(f"archive does not exist: {archive_path}")
    if not archive_path.is_file():
        raise FileNotFoundError(f"archive is not a file: {archive_path}")
    if not user_data_dir.is_relative_to(project_root):
        raise ValueError(f"user data dir must live under project root: {user_data_dir}")
    if user_data_dir.exists():
        if any(user_data_dir.iterdir()) and not replace:
            raise FileExistsError(f"user data dir is not empty: {user_data_dir}")
        shutil.rmtree(user_data_dir)

    project_data_dir = project_root / "data"
    project_data_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=project_data_dir) as temp_dir:
        temp_root = Path(temp_dir)
        _safe_extract_tar(archive_path, temp_root)

        restored_user_dir = temp_root / user_data_dir.relative_to(project_root)
        if not restored_user_dir.exists():
            raise FileNotFoundError(
                f"archive does not contain expected path: {user_data_dir.relative_to(project_root)}"
            )

        user_data_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(restored_user_dir), str(user_data_dir))

    return user_data_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore a data/user backup archive")
    parser.add_argument("--project-root", type=Path, help="Override project root")
    parser.add_argument("--backup-dir", type=Path, help="Override backup directory used for latest lookup")
    parser.add_argument("--archive", type=Path, help="Explicit archive path to restore")
    parser.add_argument("--replace", action="store_true", help="Replace existing data/user contents")
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    user_data_dir = resolve_user_data_dir(project_root)
    backup_dir = args.backup_dir or resolve_backup_dir(project_root)
    archive_path = args.archive or find_latest_backup(backup_dir)

    restored_user_dir = restore_backup_archive(
        archive_path=archive_path,
        project_root=project_root,
        user_data_dir=user_data_dir,
        replace=args.replace,
    )

    print(f"restored: {restored_user_dir}")
    print(f"archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
