"""M34 slice runner tests: coverage, safety invariants, and honest go/no-go artifacts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m34_runner",
    REPO / "scripts" / "run_luban_m34_general_knowledge_dividend_slice.py",
)
m34_runner = importlib.util.module_from_spec(_spec)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runner_writes_required_artifacts_and_go_when_live_ws_passes(tmp_path: Path) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)

    result = m34_runner.run_slice(
        output_dir=tmp_path,
        live_ws_status="pass",
        live_ws_evidence="python -m pytest tests/integration/test_luban_m34_general_knowledge_dividend_ws.py -q => 2 passed",
    )

    coverage = _load(tmp_path / "coverage_report_m34.json")
    safety = _load(tmp_path / "safety_invariant_report_m34.json")
    verdict = _load(tmp_path / "go_no_go_m34.json")
    assert result["verdict"] == "GO"
    assert coverage["teaching_context_hit_rate"] >= coverage["threshold"]
    assert coverage["off_syllabus_fall_open_rate"] == 1.0
    assert safety["production_write_count"] == 0
    assert safety["canonical_truth_written"] is False
    assert safety["answer_key_minted"] == 0
    assert verdict["verdict"] == "GO"
    assert verdict["live_ws_status"] == "pass"
    assert "test_luban_m34_general_knowledge_dividend_ws.py" in verdict["live_ws_evidence"]


def test_runner_stays_weak_go_without_live_ws_attestation(tmp_path: Path) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)

    result = m34_runner.run_slice(output_dir=tmp_path, live_ws_status="unchecked")

    verdict = _load(tmp_path / "go_no_go_m34.json")
    assert result["verdict"] == "WEAK-GO"
    assert verdict["verdict"] == "WEAK-GO"
    assert "live_ws_status_not_pass" in verdict["blockers"]


def test_runner_stays_weak_go_when_live_ws_pass_lacks_evidence(tmp_path: Path) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)

    result = m34_runner.run_slice(output_dir=tmp_path, live_ws_status="pass")

    verdict = _load(tmp_path / "go_no_go_m34.json")
    assert result["verdict"] == "WEAK-GO"
    assert verdict["verdict"] == "WEAK-GO"
    assert "live_ws_evidence_missing_or_invalid" in verdict["blockers"]
