from __future__ import annotations

import subprocess


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
