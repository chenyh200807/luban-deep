from __future__ import annotations

import json
from pathlib import Path


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v1",
        "status": "candidate_ready_for_streaming_ab",
        "classification": {
            "runtime_token_pack": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
        "summary": {"token_pack_unit_count": 10, "blocker_count": 0},
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
        },
    }


def _runtime_supply_regression() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_supply_regression.v1",
        "verdict": "PASS",
        "summary": {"input_supply_unit_count": 10, "blocker_count": 0},
        "classification": {"runtime_install_allowed": False, "production_default": False, "release_truth_claimed": False},
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
        },
    }


def _streaming_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack_streaming_ab.v1",
        "runtime_exercised": True,
        "summary": {"sample_count": 8, "provider_call_count": 16, "blocker_count": 0},
        "arms": [
            {"arm": "runtime_token_pack_thin", "mean_context_char_count": 500, "mean_ttft_ms": 300},
            {"arm": "runtime_supply_full_span", "mean_context_char_count": 900, "mean_ttft_ms": 420},
        ],
        "classification": {"runtime_install_allowed": False, "production_default": False, "release_truth_claimed": False},
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
        },
    }


def _live_ab() -> dict:
    return {
        "verdict": "PASS_LIVE_RUNTIME_AB_SHADOW",
        "verdict_ceiling": "LIVE_RUNTIME_SHADOW_ONLY",
        "effect_table": [
            {"arm": "rich_leaf_promoted_context", "accuracy_rate": 0.99, "fail_open_rate": 0.0},
            {"arm": "current_rag_runtime", "accuracy_rate": 0.95, "fail_open_rate": 0.0},
        ],
        "not_exercised": ["production_default_decision", "release_truth_governance"],
    }


def test_runtime_default_gate_ready_but_does_not_install_default() -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import run_runtime_default_gate

    report = run_runtime_default_gate(
        runtime_token_pack=_runtime_token_pack(),
        runtime_supply_regression=_runtime_supply_regression(),
        streaming_ab=_streaming_ab(),
        semantic_runtime_live_ab=_live_ab(),
    )

    assert report["schema"] == "luban_rich_leaf_runtime_default_gate.v1"
    assert report["verdict"] == "READY_FOR_CONTROLLED_DEFAULT_REVIEW"
    assert report["runtime_default_decision"]["default_install_allowed"] is False
    assert report["runtime_default_decision"]["canonical_pointer_write_allowed"] is False
    assert report["summary"]["blocker_count"] == 0
    assert report["summary"]["streaming_ttft_delta_ms"] == -120
    assert report["safety"]["production_write_count"] == 0


def test_runtime_default_gate_blocks_on_live_ab_no_go() -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import run_runtime_default_gate

    live_ab = _live_ab()
    live_ab["verdict"] = "NO_GO"
    report = run_runtime_default_gate(
        runtime_token_pack=_runtime_token_pack(),
        runtime_supply_regression=_runtime_supply_regression(),
        streaming_ab=_streaming_ab(),
        semantic_runtime_live_ab=live_ab,
    )

    assert report["verdict"] == "BLOCKED"
    assert "semantic_runtime_live_ab_not_pass:NO_GO" in report["blockers"]


def _frozen_runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "classification": {
            "candidate_only": True,
            "frozen_full_compile": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
        "summary": {"unit_count": 1534, "unresolved_count": 0, "production_write_count": 0},
        "quarantine": {
            "quarantine_candidate_count": 2,
            "quarantine_candidate_unit_ids": ["u1", "u2"],
        },
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
        },
    }


def _frozen_live_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_frozen_v1_live_ab.v1",
        "verdict": "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB",
        "arms": [
            {"arm": "rich_leaf_context_live", "accuracy_rate": 0.94},
            {"arm": "current_rag_projection_live", "accuracy_rate": 0.47},
        ],
        "summary": {"failed_call_count": 0},
    }


def test_runtime_default_gate_accepts_frozen_v1_line_inputs() -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import run_runtime_default_gate

    report = run_runtime_default_gate(
        runtime_token_pack=_frozen_runtime_token_pack(),
        runtime_supply_regression=_runtime_supply_regression(),
        streaming_ab=_streaming_ab(),
        semantic_runtime_live_ab=_frozen_live_ab(),
    )

    assert report["verdict"] == "READY_FOR_CONTROLLED_DEFAULT_REVIEW"
    assert report["blockers"] == []
    assert report["input_line"] == "frozen_v1"
    assert report["input_schemas"]["runtime_token_pack"] == "luban_rich_leaf_runtime_token_pack.v2.3"
    assert report["summary"]["token_pack_unit_count"] == 1534
    # safety invariants must remain untouched by the frozen-line migration
    assert report["runtime_default_decision"]["default_install_allowed"] is False
    assert report["runtime_default_decision"]["canonical_pointer_write_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["classification"]["runtime_install_allowed"] is False


def test_runtime_default_gate_blocks_frozen_pack_with_unresolved_units() -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import run_runtime_default_gate

    pack = _frozen_runtime_token_pack()
    pack["summary"]["unresolved_count"] = 3
    report = run_runtime_default_gate(
        runtime_token_pack=pack,
        runtime_supply_regression=_runtime_supply_regression(),
        streaming_ab=_streaming_ab(),
        semantic_runtime_live_ab=_frozen_live_ab(),
    )

    assert report["verdict"] == "BLOCKED"
    assert "frozen_pack_unresolved_units:3" in report["blockers"]


def test_runtime_default_gate_blocks_frozen_pack_quarantine_accounting_mismatch() -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import run_runtime_default_gate

    pack = _frozen_runtime_token_pack()
    pack["quarantine"]["quarantine_candidate_count"] = 5
    report = run_runtime_default_gate(
        runtime_token_pack=pack,
        runtime_supply_regression=_runtime_supply_regression(),
        streaming_ab=_streaming_ab(),
        semantic_runtime_live_ab=_frozen_live_ab(),
    )

    assert report["verdict"] == "BLOCKED"
    assert "frozen_pack_quarantine_accounting_mismatch" in report["blockers"]


def test_runtime_default_gate_still_blocks_unknown_pack_schema_and_status() -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import run_runtime_default_gate

    pack = _frozen_runtime_token_pack()
    pack["schema"] = "luban_rich_leaf_runtime_token_pack.v9"
    pack["status"] = "something_else"
    report = run_runtime_default_gate(
        runtime_token_pack=pack,
        runtime_supply_regression=_runtime_supply_regression(),
        streaming_ab=_streaming_ab(),
        semantic_runtime_live_ab=_frozen_live_ab(),
    )

    assert report["verdict"] == "BLOCKED"
    assert "runtime_token_pack_schema_mismatch:luban_rich_leaf_runtime_token_pack.v9" in report["blockers"]
    assert "runtime_token_pack_not_ready:something_else" in report["blockers"]


def test_runtime_default_gate_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_runtime_default_gate import main

    token_pack = tmp_path / "runtime_token_pack.json"
    supply_regression = tmp_path / "runtime_supply_regression.json"
    streaming_ab = tmp_path / "streaming_ab.json"
    live_ab = tmp_path / "live_ab.json"
    output = tmp_path / "runtime_default_gate.json"
    token_pack.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")
    supply_regression.write_text(json.dumps(_runtime_supply_regression(), ensure_ascii=False), encoding="utf-8")
    streaming_ab.write_text(json.dumps(_streaming_ab(), ensure_ascii=False), encoding="utf-8")
    live_ab.write_text(json.dumps(_live_ab(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--runtime-token-pack",
            str(token_pack),
            "--runtime-supply-regression",
            str(supply_regression),
            "--streaming-ab",
            str(streaming_ab),
            "--semantic-runtime-live-ab",
            str(live_ab),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["verdict"] == "READY_FOR_CONTROLLED_DEFAULT_REVIEW"
