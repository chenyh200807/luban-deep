#!/usr/bin/env python3
"""Create a runtime backup archive for ``data/user``."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import tarfile
import sys
from typing import Iterable, List, Optional, Tuple, Union

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


PathLike = Union[str, Path]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def resolve_project_root(project_root: Optional[PathLike] = None) -> Path:
    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def resolve_user_data_dir(project_root: Optional[PathLike] = None) -> Path:
    return resolve_project_root(project_root) / "data" / "user"


def resolve_backup_dir(project_root: Optional[PathLike] = None) -> Path:
    return resolve_project_root(project_root) / "data" / "backups"


def build_archive_name(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"deeptutor-data-user-{current.strftime('%Y%m%d-%H%M%SZ')}.tar.gz"


def list_backup_archives(backup_dir: Path) -> List[Path]:
    backup_dir = backup_dir.resolve()
    if not backup_dir.exists():
        return []
    return sorted(path for path in backup_dir.glob("deeptutor-data-user-*.tar.gz") if path.is_file())


def prune_backup_archives(backup_dir: Path, keep: int) -> List[Path]:
    if keep <= 0:
        return []

    archives = list_backup_archives(backup_dir)
    if len(archives) <= keep:
        return []

    to_remove = archives[:-keep]
    for archive_path in to_remove:
        _unlink_if_exists(archive_path)
    return to_remove


def iter_runtime_files(user_data_dir: Path) -> Iterable[Path]:
    for path in user_data_dir.rglob("*"):
        if path.is_file():
            yield path


def summarize_runtime_tree(user_data_dir: Path) -> Tuple[int, int]:
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
    archive_name: Optional[str] = None,
) -> Path:
    user_data_dir = user_data_dir.resolve()
    project_root = project_root.resolve()
    backup_dir = backup_dir.resolve()

    if not user_data_dir.exists():
        raise FileNotFoundError(f"user data dir does not exist: {user_data_dir}")
    if not user_data_dir.is_dir():
        raise NotADirectoryError(f"user data dir is not a directory: {user_data_dir}")
    if not _is_relative_to(user_data_dir, project_root):
        raise ValueError(f"user data dir must live under project root: {user_data_dir}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_archive_name = Path(archive_name).name if archive_name else build_archive_name()
    archive_path = backup_dir / safe_archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(user_data_dir, arcname=str(user_data_dir.relative_to(project_root)))

    return archive_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Back up data/user into a tar.gz archive")
    parser.add_argument("--project-root", type=Path, help="Override project root")
    parser.add_argument("--backup-dir", type=Path, help="Override backup output directory")
    parser.add_argument("--archive-name", help="Override backup archive filename")
    parser.add_argument(
        "--keep",
        type=int,
        default=0,
        help="Keep only the newest N archives after creating a backup (0 disables pruning)",
    )
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    user_data_dir = resolve_user_data_dir(project_root)
    backup_dir = args.backup_dir or resolve_backup_dir(project_root)

    if args.keep < 0:
        parser.error("--keep must be greater than or equal to 0")

    archive_path = create_backup_archive(
        user_data_dir=user_data_dir,
        project_root=project_root,
        backup_dir=backup_dir,
        archive_name=args.archive_name,
    )
    pruned_archives = prune_backup_archives(backup_dir, args.keep)
    file_count, total_bytes = summarize_runtime_tree(user_data_dir)

    print(f"backed up: {user_data_dir}")
    print(f"archive: {archive_path}")
    print(f"files: {file_count}")
    print(f"bytes: {total_bytes}")
    if args.keep > 0:
        print(f"keep: {args.keep}")
        print(f"pruned: {len(pruned_archives)}")
        for path in pruned_archives:
            print(f"removed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
