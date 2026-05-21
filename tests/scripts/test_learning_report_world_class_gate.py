from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_learning_report_world_class_e2e.py"


def _load_gate_module() -> Any:
    spec = importlib.util.spec_from_file_location("learning_report_world_class_gate", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_static_local_gates() -> list[dict[str, Any]]:
    return [
        {"name": "v1_v2_dual_emit", "ok": True},
        {"name": "b1_forbidden_positive_usage_scan", "ok": True},
        {"name": "b7_5k_attempt_detail_warm_p95", "ok": True},
        {"name": "payload_size_under_80kb_fixture", "ok": True},
        {"name": "g12_i18n_keys_presence", "ok": True},
    ]


def test_world_class_gate_report_separates_local_external_and_manual(tmp_path, monkeypatch) -> None:
    gate = _load_gate_module()
    monkeypatch.setattr(gate, "_run", lambda command: {"command": " ".join(command), "returncode": 0})
    monkeypatch.setattr(gate, "_static_local_gates", _fake_static_local_gates)

    report = gate.run(tmp_path / "gate.json")

    assert report["ok"] is True
    assert report["rollout_ready"] is False
    assert report["external_proof_required"] is True
    assert isinstance(report["passed_local_gates"], list)
    assert isinstance(report["blocked_external_gates"], list)
    assert isinstance(report["manual_required"], list)
    assert "production_required_but_not_proven_locally" not in report


def test_world_class_gate_records_required_local_plan_assertions(tmp_path, monkeypatch) -> None:
    gate = _load_gate_module()
    monkeypatch.setattr(gate, "_run", lambda command: {"command": " ".join(command), "returncode": 0})
    monkeypatch.setattr(gate, "_static_local_gates", _fake_static_local_gates)

    report = gate.run(tmp_path / "gate.json")
    local_gate_names = {item["name"] for item in report["passed_local_gates"]}

    assert {
        "service_api_pytest",
        "node_view_model_layout",
        "contract_guard",
        "v1_v2_dual_emit",
        "b1_forbidden_positive_usage_scan",
        "b5_prod_secret_fail_closed_ci_simulation",
        "b7_5k_attempt_detail_warm_p95",
        "payload_size_under_80kb_fixture",
        "g12_i18n_keys_presence",
    }.issubset(local_gate_names)


def test_world_class_gate_marks_external_and_manual_proof_as_blocking(tmp_path, monkeypatch) -> None:
    gate = _load_gate_module()
    monkeypatch.setattr(gate, "_run", lambda command: {"command": " ".join(command), "returncode": 0})
    monkeypatch.setattr(gate, "_static_local_gates", _fake_static_local_gates)

    report = gate.run(tmp_path / "gate.json")
    blocked_names = {item["name"] for item in report["blocked_external_gates"]}
    manual_names = {item["name"] for item in report["manual_required"]}
    statuses = {item["status"] for item in report["blocked_external_gates"] + report["manual_required"]}

    assert {"production_14_day_observation", "staging_v1_v2_dual_emit", "langfuse_trace_bundle"}.issubset(
        blocked_names
    )
    assert {"wechat_ios_android_pc_screenshots"}.issubset(manual_names)
    assert statuses <= {"pending", "blocking"}
