#!/usr/bin/env python
"""Prune ``data/backups`` archives with simple day/week/month retention."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Iterable

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.backup_data import resolve_backup_dir, resolve_project_root

ARCHIVE_RE = re.compile(r"^deeptutor-data-user-(\d{8}-\d{6}Z)\.tar\.gz$")


@dataclass(frozen=True, slots=True)
class BackupArchive:
    path: Path
    created_at: datetime


def iter_backup_archives(backup_dir: Path) -> list[BackupArchive]:
    archives: list[BackupArchive] = []
    for path in sorted(backup_dir.glob("deeptutor-data-user-*.tar.gz")):
        match = ARCHIVE_RE.match(path.name)
        if not match:
            continue
        created_at = datetime.strptime(match.group(1), "%Y%m%d-%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
        archives.append(BackupArchive(path=path.resolve(), created_at=created_at))
    return archives


def select_archives_to_keep(
    archives: Iterable[BackupArchive],
    *,
    keep_daily: int,
    keep_weekly: int,
    keep_monthly: int,
) -> set[Path]:
    ordered = sorted(archives, key=lambda item: item.created_at, reverse=True)
    keep: set[Path] = set()
    kept_daily_days: set[tuple[int, int, int]] = set()
    covered_weeks: set[tuple[int, int]] = set()
    covered_months: set[tuple[int, int]] = set()

    if keep_daily > 0:
        for archive in ordered:
            day_key = (archive.created_at.year, archive.created_at.month, archive.created_at.day)
            if day_key in kept_daily_days:
                continue
            keep.add(archive.path)
            kept_daily_days.add(day_key)
            covered_weeks.add(archive.created_at.isocalendar()[:2])
            covered_months.add((archive.created_at.year, archive.created_at.month))
            if len(kept_daily_days) >= keep_daily:
                break

    kept_weeks: set[tuple[int, int]] = set()
    if keep_weekly > 0:
        for archive in ordered:
            week_key = archive.created_at.isocalendar()[:2]
            if week_key in covered_weeks or week_key in kept_weeks:
                continue
            keep.add(archive.path)
            kept_weeks.add(week_key)
            covered_months.add((archive.created_at.year, archive.created_at.month))
            if len(kept_weeks) >= keep_weekly:
                break

    kept_months: set[tuple[int, int]] = set()
    if keep_monthly > 0:
        for archive in ordered:
            month_key = (archive.created_at.year, archive.created_at.month)
            if month_key in covered_months or month_key in kept_months:
                continue
            keep.add(archive.path)
            kept_months.add(month_key)
            if len(kept_months) >= keep_monthly:
                break

    return keep


def prune_backup_archives(
    backup_dir: Path,
    *,
    keep_daily: int,
    keep_weekly: int,
    keep_monthly: int,
    dry_run: bool = False,
) -> list[Path]:
    backup_dir = backup_dir.resolve()
    archives = iter_backup_archives(backup_dir)
    keep = select_archives_to_keep(
        archives,
        keep_daily=max(0, int(keep_daily)),
        keep_weekly=max(0, int(keep_weekly)),
        keep_monthly=max(0, int(keep_monthly)),
    )
    removed: list[Path] = []
    for archive in archives:
        if archive.path in keep:
            continue
        removed.append(archive.path)
        if not dry_run:
            archive.path.unlink(missing_ok=True)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune DeepTutor runtime backup archives")
    parser.add_argument("--project-root", type=Path, help="Override project root")
    parser.add_argument("--backup-dir", type=Path, help="Override backup directory")
    parser.add_argument("--keep-daily", type=int, default=7, help="Number of daily backups to retain")
    parser.add_argument("--keep-weekly", type=int, default=2, help="Number of weekly backups to retain")
    parser.add_argument("--keep-monthly", type=int, default=1, help="Number of monthly backups to retain")
    parser.add_argument("--dry-run", action="store_true", help="Print candidates without deleting")
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    backup_dir = args.backup_dir or resolve_backup_dir(project_root)
    removed = prune_backup_archives(
        backup_dir,
        keep_daily=args.keep_daily,
        keep_weekly=args.keep_weekly,
        keep_monthly=args.keep_monthly,
        dry_run=args.dry_run,
    )

    print(f"backup_dir: {backup_dir}")
    print(f"removed: {len(removed)}")
    for path in removed:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
