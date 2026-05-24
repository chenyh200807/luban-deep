from __future__ import annotations

import json
from pathlib import Path

from scripts.check_hermes_upstream import check_versions, main


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_check_versions_reports_match(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    source = tmp_path / "hermes"
    _write_json(inventory, {"source": "zhongweiv/hermes-edu-skills", "version": "0.18.6"})
    _write_json(source / "package.json", {"name": "hermes-edu-skills", "version": "0.18.6"})

    result = check_versions(inventory_path=inventory, source_path=source)

    assert result.inventory_version == "0.18.6"
    assert result.upstream_version == "0.18.6"
    assert result.status == "ok"


def test_check_versions_detects_drift_without_runtime_side_effects(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    source = tmp_path / "hermes"
    _write_json(inventory, {"source": "zhongweiv/hermes-edu-skills", "version": "0.18.6"})
    _write_json(source / "package.json", {"name": "hermes-edu-skills", "version": "0.19.0"})

    result = check_versions(inventory_path=inventory, source_path=source)

    assert result.status == "drift"
    assert "0.18.6" in result.message
    assert "0.19.0" in result.message


def test_main_can_fail_on_drift_for_weekly_ci(tmp_path: Path, capsys) -> None:
    inventory = tmp_path / "inventory.json"
    source = tmp_path / "hermes"
    _write_json(inventory, {"source": "zhongweiv/hermes-edu-skills", "version": "0.18.6"})
    _write_json(source / "catalog.json", {"name": "hermes-edu-skills", "version": "0.19.0", "skills": []})

    exit_code = main(
        [
            "--inventory",
            str(inventory),
            "--source",
            str(source),
            "--fail-on-drift",
        ]
    )

    assert exit_code == 1
    assert "WARN hermes upstream drift" in capsys.readouterr().out
