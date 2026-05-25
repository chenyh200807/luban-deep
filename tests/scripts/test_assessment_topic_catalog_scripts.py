from __future__ import annotations

import subprocess
from pathlib import Path


def test_seed_topic_catalog_forms_supports_dry_run_help() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/seed_assessment_topic_catalog_forms.py",
            "--help",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--persist" in result.stdout
    assert "--topic-id" in result.stdout
    assert "--out-json" in result.stdout
    assert "--out-md" in result.stdout
    assert "--reviewed-json" in result.stdout
    assert "--require-target-main" in result.stdout
    assert "--idempotency-key" in result.stdout


def test_seed_topic_catalog_forms_persist_requires_reviewed_guard_and_idempotency() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/seed_assessment_topic_catalog_forms.py",
            "--persist",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "reviewed_json_required_for_persist" in combined


def test_seed_topic_catalog_forms_dry_run_writes_requested_artifacts(tmp_path: Path) -> None:
    out_json = tmp_path / "catalog.json"
    out_md = tmp_path / "catalog.md"

    result = subprocess.run(
        [
            "python",
            "scripts/seed_assessment_topic_catalog_forms.py",
            "--dry-run",
            "--topic-id",
            "waterproof",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--json",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert out_json.exists()
    assert out_md.exists()
    assert "waterproof" in out_json.read_text(encoding="utf-8")
    assert "| waterproof |" in out_md.read_text(encoding="utf-8")
