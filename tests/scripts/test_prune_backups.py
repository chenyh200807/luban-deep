from __future__ import annotations

from pathlib import Path

from scripts.prune_backups import iter_backup_archives, prune_backup_archives, select_archives_to_keep


def _touch_archive(backup_dir: Path, stamp: str) -> Path:
    path = backup_dir / f"deeptutor-data-user-{stamp}.tar.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("backup", encoding="utf-8")
    return path


def test_select_archives_to_keep_prefers_latest_per_day_week_month(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    _touch_archive(backup_dir, "20240101-000000Z")
    keep_daily = _touch_archive(backup_dir, "20240101-120000Z")
    keep_weekly = _touch_archive(backup_dir, "20231225-120000Z")
    keep_monthly = _touch_archive(backup_dir, "20231115-120000Z")
    _touch_archive(backup_dir, "20231001-120000Z")

    keep = select_archives_to_keep(
        iter_backup_archives(backup_dir),
        keep_daily=1,
        keep_weekly=1,
        keep_monthly=1,
    )

    assert keep_daily in keep
    assert keep_weekly in keep
    assert keep_monthly in keep
    assert len(keep) == 3


def test_prune_backup_archives_deletes_only_unretained_files(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    kept = _touch_archive(backup_dir, "20240103-120000Z")
    removed = _touch_archive(backup_dir, "20240102-120000Z")

    pruned = prune_backup_archives(
        backup_dir,
        keep_daily=1,
        keep_weekly=0,
        keep_monthly=0,
    )

    assert pruned == [removed.resolve()]
    assert kept.exists()
    assert not removed.exists()


def test_prune_backup_archives_dry_run_preserves_files(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    removed = _touch_archive(backup_dir, "20240101-120000Z")
    _touch_archive(backup_dir, "20240102-120000Z")

    pruned = prune_backup_archives(
        backup_dir,
        keep_daily=1,
        keep_weekly=0,
        keep_monthly=0,
        dry_run=True,
    )

    assert pruned == [removed.resolve()]
    assert removed.exists()
