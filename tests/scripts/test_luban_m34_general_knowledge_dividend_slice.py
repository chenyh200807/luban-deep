"""M34 slice runner tests: coverage, safety invariants, and honest go/no-go artifacts."""
from __future__ import annotations

import importlib.util
import inspect
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


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_runner_writes_required_artifacts_and_go_when_live_ws_passes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)
    gate_calls = 0

    def fake_live_ws_gate() -> dict:
        nonlocal gate_calls
        gate_calls += 1
        return {
            "live_ws_status": "pass",
            "live_ws_command": m34_runner.LIVE_WS_GATE_COMMAND_TEXT,
            "live_ws_exit_code": 0,
            "live_ws_evidence": (
                "python -m pytest tests/integration/"
                "test_luban_m34_general_knowledge_dividend_ws.py -q => exit_code=0\n"
                "2 passed"
            ),
        }

    monkeypatch.setattr(m34_runner, "_run_live_ws_gate", fake_live_ws_gate)

    result = m34_runner.run_slice(output_dir=tmp_path)

    coverage = _load(tmp_path / "coverage_report_m34.json")
    safety = _load(tmp_path / "safety_invariant_report_m34.json")
    verdict = _load(tmp_path / "go_no_go_m34.json")
    work_orders = _jsonl(tmp_path / "compiler_source_work_orders_m34.jsonl")
    assert gate_calls == 1
    assert result["verdict"] == "GO"
    assert coverage["teaching_context_hit_rate"] >= coverage["threshold"]
    assert coverage["low_confidence_on_syllabus_fall_open_rate"] == 1.0
    assert coverage["calibration_total"] >= 20
    assert coverage["calibration_pass_rate"] == 1.0
    assert coverage["off_syllabus_fall_open_rate"] == 1.0
    assert safety["production_write_count"] == 0
    assert safety["canonical_truth_written"] is False
    assert safety["answer_key_minted"] == 0
    assert verdict["verdict"] == "GO"
    assert verdict["live_ws_status"] == "pass"
    assert "test_luban_m34_general_knowledge_dividend_ws.py" in verdict["live_ws_evidence"]
    assert verdict["live_ws_exit_code"] == 0
    assert verdict["production_default"] == "disabled_pending_online_shadow_evidence"
    assert verdict["default_cohort_scope"] == "shadow_only"
    assert (
        verdict["system_wide_default_gate"]
        == "requires_50_case_online_shadow_compiled_hit_source_validity_and_no_wrong_path_regression"
    )
    assert verdict["optional_cohort_env"] == "LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT"
    assert verdict["kill_switch"] == "LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED=false"
    assert any(
        row["question"] == "双代号网络计划总时差怎么算？"
        and row["work_order_type"] == "source_path_conflict"
        for row in work_orders
    )


def test_runner_rejects_forged_live_ws_attestation_without_exit_code(
    tmp_path: Path,
) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)

    signature = inspect.signature(m34_runner.run_slice)
    assert "live_ws_status" not in signature.parameters
    assert "live_ws_command" not in signature.parameters
    assert "live_ws_exit_code" not in signature.parameters
    assert "live_ws_evidence" not in signature.parameters

    result = m34_runner.run_slice(output_dir=tmp_path, run_live_ws_gate=False)

    verdict = _load(tmp_path / "go_no_go_m34.json")
    assert result["verdict"] == "WEAK-GO"
    assert verdict["verdict"] == "WEAK-GO"
    assert "live_ws_gate_not_executed" in verdict["blockers"]


def test_runner_stays_weak_go_without_live_ws_attestation(tmp_path: Path) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)

    result = m34_runner.run_slice(output_dir=tmp_path, run_live_ws_gate=False)

    verdict = _load(tmp_path / "go_no_go_m34.json")
    assert result["verdict"] == "WEAK-GO"
    assert verdict["verdict"] == "WEAK-GO"
    assert "live_ws_status_not_pass" in verdict["blockers"]


def test_runner_stays_weak_go_when_live_ws_gate_is_skipped(tmp_path: Path) -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(m34_runner)

    result = m34_runner.run_slice(output_dir=tmp_path, run_live_ws_gate=False)

    verdict = _load(tmp_path / "go_no_go_m34.json")
    assert result["verdict"] == "WEAK-GO"
    assert verdict["verdict"] == "WEAK-GO"
    assert "live_ws_gate_not_executed" in verdict["blockers"]
