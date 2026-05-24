from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.audit_2026_compiler_supabase_coverage import _metrics


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_script(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["PYTHONPATH"] = str(REPO_ROOT)
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_inventory_script_fails_without_source_root() -> None:
    env = os.environ.copy()
    env.pop("LUBAN_2026_SOURCE_ROOT", None)
    result = run_script(
        ["scripts/run_2026_source_inventory.py", "--run-id", "test-missing-root"],
        env=env,
    )

    assert result.returncode != 0
    assert "LUBAN_2026_SOURCE_ROOT is required" in result.stderr


def test_inventory_script_limit_and_force(tmp_path: Path) -> None:
    source_root = tmp_path / "2026"
    (source_root / "taxonomy").mkdir(parents=True)
    (source_root / "标准文件").mkdir()
    (source_root / "题库").mkdir()
    (source_root / "标准文件" / "a.json").write_text('{"records": [{"x": 1}]}', encoding="utf-8")

    env = {"LUBAN_2026_SOURCE_ROOT": str(source_root)}
    run_id = "pytest-inventory"
    first = run_script(
        [
            "scripts/run_2026_source_inventory.py",
            "--run-id",
            run_id,
            "--require-platform",
            "darwin",
            "--limit",
            "1",
            "--force",
        ],
        env=env,
    )
    assert first.returncode == 0, first.stderr
    assert "json_files=1" in first.stdout

    second = run_script(
        [
            "scripts/run_2026_source_inventory.py",
            "--run-id",
            run_id,
            "--require-platform",
            "darwin",
            "--limit",
            "1",
        ],
        env=env,
    )
    assert second.returncode != 0
    assert "--force" in second.stderr


def test_supabase_coverage_script_rejects_missing_db_url() -> None:
    env = os.environ.copy()
    env.pop("DB_URL", None)
    env.pop("DATABASE_URL", None)
    result = run_script(["scripts/audit_2026_compiler_supabase_coverage.py", "--run-id", "pytest"], env=env)

    assert result.returncode != 0
    assert "DB_URL or DATABASE_URL is required" in result.stderr


def test_supabase_coverage_accepts_relation_type_graph_schema() -> None:
    class FakeRunner:
        def scalar(self, sql: str) -> str:
            if "to_regclass" in sql:
                return "questions_bank"
            return "1001"

        def run_csv(self, sql: str) -> list[dict[str, str]]:
            if "information_schema.columns" in sql:
                return [{"column_name": "relation_type"}]
            if "knowledge_graph_edges" in sql:
                assert "relation_type" in sql
                return [{"metric": "knowledge_cards->knowledge_cards:part_of", "count": "538"}]
            return [{"count": "1001"}]

    rows = _metrics(FakeRunner())

    assert {"metric": "knowledge_graph_edges.knowledge_cards->knowledge_cards:part_of", "count": "538"} in rows
