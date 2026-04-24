from __future__ import annotations

from datetime import datetime


def test_prune_legacy_text_logs_keeps_90_day_window_and_ignores_other_files(tmp_path) -> None:
    from deeptutor.logging.logger import _prune_legacy_text_logs

    old_log = tmp_path / "deeptutor_20251231.log"
    boundary_log = tmp_path / "deeptutor_20260124.log"
    current_log = tmp_path / "deeptutor_20260424.log"
    malformed_log = tmp_path / "deeptutor_latest.log"
    unrelated_log = tmp_path / "other_20251231.log"
    for path in (old_log, boundary_log, current_log, malformed_log, unrelated_log):
        path.write_text("log\n", encoding="utf-8")

    removed = _prune_legacy_text_logs(
        tmp_path,
        now=datetime(2026, 4, 24, 12, 0, 0),
        retention_days=90,
    )

    assert removed == [old_log]
    assert not old_log.exists()
    assert boundary_log.exists()
    assert current_log.exists()
    assert malformed_log.exists()
    assert unrelated_log.exists()
