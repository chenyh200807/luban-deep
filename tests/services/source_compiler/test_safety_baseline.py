from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from deeptutor.services.source_compiler.metadata import with_compiler_metadata
from deeptutor.services.source_compiler.platform import (
    RunDirectoryLock,
    actually_open_and_read,
    require_darwin_for_dataless_detection,
)
from deeptutor.services.source_compiler.psql import assert_target_database_is_main
from deeptutor.services.source_compiler.source_inventory import build_source_inventory


def test_non_darwin_dataless_scan_requires_explicit_ci_override() -> None:
    with pytest.raises(EnvironmentError, match="dataless detection requires macOS"):
        require_darwin_for_dataless_detection("linux")

    require_darwin_for_dataless_detection("linux", allow_disabled=True)


def test_actual_read_probe_distinguishes_empty_and_non_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    non_empty = tmp_path / "non_empty.json"
    empty.write_bytes(b"")
    non_empty.write_bytes(b'{"ok": true}')

    assert actually_open_and_read(empty) == (False, 0)
    assert actually_open_and_read(non_empty) == (True, len(b'{"ok": true}'))


def test_run_directory_reuse_requires_force(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "existing.jsonl").write_text("x\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="--force"):
        RunDirectoryLock(run_dir, force=False).prepare()

    lock = RunDirectoryLock(run_dir, force=True)
    lock.prepare()
    assert (run_dir / ".compile.lock").exists()
    lock.release()
    assert not (run_dir / ".compile.lock").exists()


def test_metadata_envelope_adds_required_fields() -> None:
    payload = with_compiler_metadata(
        {"stable_source_id": "src_a"},
        run_id="run1",
        source_path="标准文件/a.json",
        compiled_at="2026-05-24T12:00:00Z",
    )

    assert payload["compiler_version"] == "2026-source-compiler-v0.2"
    assert payload["run_id"] == "run1"
    assert payload["source_path"] == "标准文件/a.json"
    assert payload["compiled_at"] == "2026-05-24T12:00:00Z"


def test_target_database_guard_rejects_suspicious_database() -> None:
    class FakeRunner:
        def scalar(self, sql: str) -> str:
            if "to_regclass" in sql:
                return "questions_bank"
            return "42"

    with pytest.raises(RuntimeError, match="suspicious"):
        assert_target_database_is_main(FakeRunner())


def test_source_inventory_records_unknown_shape_and_lecture_page_skip(tmp_path: Path) -> None:
    source_root = tmp_path / "2026"
    lecture_pages = source_root / "讲义" / "section" / "pages"
    lecture_pages.mkdir(parents=True)
    unknown = source_root / "标准文件"
    unknown.mkdir(parents=True)
    (source_root / "taxonomy").mkdir()
    (source_root / "题库").mkdir()
    (unknown / "unknown.json").write_text(json.dumps({"a": {"b": 1}}), encoding="utf-8")
    (lecture_pages / "p1.json").write_text(json.dumps([{"node_code": "1A"}]), encoding="utf-8")

    records = build_source_inventory(
        source_root,
        run_id="run1",
        compiled_at="2026-05-24T12:00:00Z",
        require_platform="darwin",
        platform_name="darwin",
    )

    by_path = {record["source_path"]: record for record in records}
    assert by_path["标准文件/unknown.json"]["record_count"] is None
    assert by_path["标准文件/unknown.json"]["record_count_error"] == "unknown_record_shape"
    assert by_path["讲义/section/pages/p1.json"]["compile_eligibility"] == "redundant_skipped"


def test_git_ls_files_artifacts_guard_is_empty() -> None:
    result = subprocess.run(
        ["git", "ls-files", "artifacts/"],
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.stdout == ""
