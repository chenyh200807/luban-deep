"""R6 release decision package tests."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_r6_release_decision_package import build_r6_release_decision_package


def test_r6_package_holds_release_gate_when_remote_ws_is_missing(tmp_path: Path) -> None:
    package = build_r6_release_decision_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_r6_release_decision_package.v1"
    assert package["overall"]["verdict"] == "NO-GO_REMOTE_WS_PENDING"
    assert package["overall"]["release_gate_entry_allowed"] is False
    assert package["overall"]["write_actions_allowed"] is False

    phases = package["evidence"]["p1_to_p5"]
    assert phases["phase1_nexus_like_scoring"] == "STRONG-GO"
    assert phases["phase5_real_wechat_package_readback"] == "STRONG-GO"
    assert package["evidence"]["cached_ab"]["artifact_first_llm_judge"]["score_mae"] < package["evidence"]["cached_ab"]["legacy"]["score_mae"]
    assert package["evidence"]["real_wechat_package"]["real_wechat_package"]["devtools_project_root"] == "yousenwebview"

    assert package["remote_or_production_ws_turn"]["status"] == "PENDING"
    assert "remote_or_production_ws_turn" in package["not_exercised"]

    registry = package["preflights"]["published_registry"]
    assert registry["status"] == "PREFLIGHT_READY_NOT_EXECUTED"
    assert registry["published_registry_executed"] is False
    assert registry["action_allowed_without_authorization"] is False
    assert registry["required_authorization"] == "explicit_registry_publish_authorization"

    canonical = package["preflights"]["canonical_learner_truth_write"]
    assert canonical["status"] == "PREFLIGHT_BLOCKED_NOT_EXECUTED"
    assert canonical["canonical_truth_written"] is False
    assert canonical["action_allowed_without_authorization"] is False
    assert "teacher-final live signoff missing" in canonical["stop_conditions"]

    default_flip = package["preflights"]["system_wide_default_flip"]
    assert default_flip["status"] == "PREFLIGHT_ONLY_NOT_EXECUTED"
    assert default_flip["limited_default"]["verdict"] == "ready_for_user_authorization"
    assert default_flip["broad_default"]["verdict"] == "not_ready_limited_default_not_executed"
    assert default_flip["action_allowed_without_authorization"] is False

    assert package["release_gate"]["can_enter_as_evidence"] == [
        "p1_governed_subset_scoring",
        "p2_local_live_readback",
        "p3_local_api_readback",
        "p4_local_ws_readback",
        "p5_real_wechat_package_readback",
        "cached_ab_directional_effectiveness",
        "published_registry_preflight",
    ]
    assert "canonical_learner_truth_write" in package["release_gate"]["forbidden_actions"]
    assert "system_wide_default_flip" in package["release_gate"]["forbidden_actions"]
    assert all(value in (False, 0) for value in package["safety"].values())

    written = tmp_path / "r6_release_decision_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package


def test_r6_package_absorbs_remote_ws_readback_without_authorizing_writes(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote_ws"
    remote_dir.mkdir()
    (remote_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entry": "remote test2 /api/v1/ws cohort loop soak",
                "api_base_url": "https://test2.example.com",
                "ws_url": "wss://test2.example.com/api/v1/ws",
                "evidence_scope": "remote_test2_ws_cohort_soak",
                "remote_write_performed": True,
                "cohort_user_id": "qa_remote_soak",
                "cohort_identity": "qa_remote_soak",
                "stage_chain": ["remote_api_ws", "grading", "learning_brain_projection_readback"],
            }
        ),
        encoding="utf-8",
    )
    (remote_dir / "go_no_go.json").write_text(
        json.dumps(
            {
                "status": "REMOTE_TEST2_WS_GO",
                "remote_write_performed": True,
                "ws_grading_ok": True,
                "same_projection_hash": True,
                "learning_brain_projection_hash": "sha256:remote",
                "learning_report_projection_hash": "sha256:remote",
                "cohort_user_id": "qa_remote_soak",
                "cohort_identity": "qa_remote_soak",
                "initial_has_construction_grading_result": True,
                "retest_has_construction_grading_result": True,
            }
        ),
        encoding="utf-8",
    )

    package = build_r6_release_decision_package(
        output_dir=tmp_path / "decision",
        remote_ws_artifact_dir=remote_dir,
    )

    assert package["overall"]["verdict"] == "RELEASE_GATE_REVIEW_READY_WRITES_FORBIDDEN"
    assert package["overall"]["release_gate_entry_allowed"] is True
    assert package["overall"]["write_actions_allowed"] is False
    assert package["remote_or_production_ws_turn"]["status"] == "STRONG-GO"
    assert package["remote_or_production_ws_turn"]["remote_runtime_state_observed"] is True
    assert "remote_or_production_ws_turn" not in package["not_exercised"]
    assert "canonical_learner_truth_write" in package["release_gate"]["forbidden_actions"]
    assert package["safety"]["canonical_truth_written"] is False
    assert package["safety"]["published_registry_written"] is False
    assert package["safety"]["system_wide_default_flipped"] is False


def test_r6_package_keeps_remote_ws_not_exercised_for_auth_missing_artifact(tmp_path: Path) -> None:
    remote_dir = tmp_path / "remote_ws_auth_missing"
    remote_dir.mkdir()
    (remote_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entry": "remote/prod-like /api/v1/ws QA-scoped turn",
                "api_base_url": "https://test2.example.com",
                "evidence_scope": "remote_or_production_ws_turn_preflight",
                "remote_or_production_ws_turn_exercised": False,
                "remote_write_performed": False,
                "canonical_truth_written": False,
                "published_registry_written": False,
                "stage_chain": [],
            }
        ),
        encoding="utf-8",
    )
    (remote_dir / "go_no_go.json").write_text(
        json.dumps(
            {
                "status": "REMOTE_WS_AUTH_MATERIAL_MISSING",
                "remote_or_production_ws_turn_exercised": False,
                "remote_write_performed": False,
            }
        ),
        encoding="utf-8",
    )

    package = build_r6_release_decision_package(
        output_dir=tmp_path / "decision",
        remote_ws_artifact_dir=remote_dir,
    )

    assert package["overall"]["verdict"] == "NO-GO_REMOTE_WS_PENDING"
    assert package["remote_or_production_ws_turn"]["status"] == "PENDING"
    assert package["remote_or_production_ws_turn"]["remote_or_production_ws_turn_exercised"] is False
    assert "remote_or_production_ws_turn" in package["not_exercised"]
