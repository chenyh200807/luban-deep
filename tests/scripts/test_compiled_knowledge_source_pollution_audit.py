from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "pollution_audit",
    REPO / "scripts" / "run_compiled_knowledge_source_pollution_audit.py",
)
pollution_audit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pollution_audit


def test_audit_writes_compiler_feedback_for_network_plan_pollution(tmp_path: Path) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(pollution_audit)

    summary = pollution_audit.run_audit(
        queries=["双代号网络计划总时差怎么算？"],
        output_dir=tmp_path,
    )

    assert summary["query_count"] == 1
    assert summary["work_order_count"] >= 1
    assert summary["release_truth_written"] is False
    ledger = (tmp_path / "compiler_feedback_ledger.jsonl").read_text(encoding="utf-8")
    assert "repair_compiled_source_path_alignment" in ledger
    assert "水泥" in ledger
    report = (tmp_path / "FINDING_compiled_source_pollution.md").read_text(encoding="utf-8")
    assert "双代号网络计划总时差怎么算？" in report
    assert "source_path_conflict" in report


def test_audit_cli_runs_from_repo_root(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "run_compiled_knowledge_source_pollution_audit.py"),
            "--out",
            str(tmp_path),
            "--query",
            "双代号网络计划总时差怎么算？",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "summary.json").exists()
