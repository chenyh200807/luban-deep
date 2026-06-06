from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "run_luban_m26_ab_and_real_chain_qa.py"


def _load():
    spec = importlib.util.spec_from_file_location("m26_ab", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["m26_ab"] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()


def test_seven_scenario_matrix() -> None:
    assert len(M.SCENARIO_MATRIX) == 7
    ids = {s["id"] for s in M.SCENARIO_MATRIX}
    assert "open_construction_concept" in ids
    assert "user_pasted_unknown" in ids


def test_ab_report_has_four_configs_and_safety() -> None:
    report = M.build_report()
    configs = {c["config"] for c in report["ab"]["configs"]}
    assert configs == {
        "v0_registry_only",
        "old_rag_kbv5_context",
        "v1_official_mode",
        "v1_open_world_diagnostic",
    }
    v0 = next(c for c in report["ab"]["configs"] if c["config"] == "v0_registry_only")
    v1ow = next(c for c in report["ab"]["configs"] if c["config"] == "v1_open_world_diagnostic")
    assert v0["refusal_rate"] == 1.0  # registry-only refuses not-in-bank
    assert v1ow["refusal_rate"] == 0.0  # open-world never refuses construction


def test_live_blocker_present_without_creds() -> None:
    report = M.build_report(run_live=True)
    assert report["live_blocker"]  # precise blocker, not faked live data


def test_main_writes_report(tmp_path) -> None:
    out = tmp_path / "ab.json"
    argv = sys.argv
    sys.argv = ["m26ab", "--out", str(out)]
    try:
        assert M.main() == 0
    finally:
        sys.argv = argv
    assert out.exists()
