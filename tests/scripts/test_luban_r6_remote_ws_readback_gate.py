"""R6 remote/prod-like WS readback gate tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_r6_remote_ws_readback_gate as gate


@pytest.mark.asyncio
async def test_remote_ws_gate_blocks_locally_when_auth_material_is_missing(tmp_path: Path) -> None:
    result = await gate.run_r6_remote_ws_readback_gate(
        out_dir=tmp_path,
        api_base_url="https://test2.example.com",
    )

    assert result["go_no_go"]["status"] == "REMOTE_WS_AUTH_MATERIAL_MISSING"
    assert result["go_no_go"]["remote_write_performed"] is False
    assert result["manifest"]["remote_or_production_ws_turn_exercised"] is False
    assert result["manifest"]["canonical_truth_written"] is False
    assert result["manifest"]["published_registry_written"] is False
    assert (tmp_path / "manifest.json").exists()
    assert json.loads((tmp_path / "go_no_go.json").read_text(encoding="utf-8")) == result["go_no_go"]


@pytest.mark.asyncio
async def test_remote_ws_gate_delegates_to_remote_soak_without_ssh_synthesis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    async def _fake_remote_soak(**kwargs):
        captured.update(kwargs)
        out = kwargs["out_dir"]
        out.mkdir(parents=True, exist_ok=True)
        manifest = {
            "entry": "remote test2 /api/v1/ws cohort loop soak",
            "api_base_url": kwargs["api_base_url"],
            "ws_url": "wss://test2.example.com/api/v1/ws",
            "evidence_scope": "remote_test2_ws_cohort_soak",
            "remote_write_performed": True,
            "cohort_user_id": "qa_remote_soak",
            "cohort_identity": "qa_remote_soak",
            "stage_chain": ["remote_api_ws", "grading", "learning_brain_projection_readback"],
        }
        go_no_go = {
            "status": "REMOTE_TEST2_WS_GO",
            "remote_write_performed": True,
            "ws_grading_ok": True,
            "same_projection_hash": True,
        }
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (out / "go_no_go.json").write_text(json.dumps(go_no_go), encoding="utf-8")
        return {"out_dir": str(out), "manifest": manifest, "go_no_go": go_no_go}

    monkeypatch.setattr(gate.soak, "run_remote_test2_ws_soak", _fake_remote_soak)

    result = await gate.run_r6_remote_ws_readback_gate(
        out_dir=tmp_path,
        api_base_url="https://test2.example.com",
        auth_token="token-qa",
    )

    assert result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO"
    assert captured["auth_token"] == "token-qa"
    assert captured["remote_synthesis_ssh_host"] == ""
    assert captured["scenario_id"] == "temporary-electricity-smoke"
