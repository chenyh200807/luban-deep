"""Stage 5 PGO canary gate report tests."""

from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
    build_grading_contracts_from_factory_candidate,
    build_pgo_runtime_supply,
    write_pgo_runtime_supply,
)
from deeptutor.services.construction_grading.per_question_grading_object import (
    A_OFFICIAL,
    PENDING_SCORE_AUTHORITY,
    SCHEMA_ID,
)


def _write_slot(tmp_path: Path) -> Path:
    obj = {
        "schema_id": SCHEMA_ID,
        "question_id": "Q-CANARY",
        "stem": "案例题",
        "official_total_score": 5.0,
        "official_total_score_authority": A_OFFICIAL,
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "per_point_score_authority": PENDING_SCORE_AUTHORITY,
        "sub_questions": [
            {
                "sub_no": 1,
                "official_sub_answer_verbatim": "施工总进度计划表( 图)",
                "scoring_points": [],
            }
        ],
    }
    factory = {
        "summary": {
            "schema": "luban_full_factory_candidate.v1",
            "classification": {"candidate_only": True, "review_only": True},
        },
        "cases": [
            {
                "question_id": "Q-CANARY",
                "case_file": "Q-CANARY.json",
                "point_type": "list",
                "resolution": "consensus",
                "resolution_lane": "A_consensus",
                "final_mnm_ok": True,
                "segments": [{"text": "施工总进度计划表( 图)", "is_list_item": True}],
            }
        ],
    }
    result = build_grading_contracts_from_factory_candidate(factory, [obj])
    bundle = build_pgo_runtime_supply(result["contracts"])
    out_dir = tmp_path / "v_case_rubric_scored_pgo"
    write_pgo_runtime_supply(bundle, out_dir)
    return out_dir


def _write_scaled_gate(tmp_path: Path) -> Path:
    payload = {
        "summary": {
            "schema": "luban_scaled_double_gate.v1",
            "n_pairs": 2,
            "MAE_new": 0.1,
            "MAE_legacy": 0.4,
            "over_credit": {"new": 0, "legacy": 1},
            "gate_MAE_new_le_legacy": True,
            "gate_overcredit_new_le_legacy": True,
            "double_gate_pass": True,
        },
        "records": [
            {"case": "Q1", "student": "S1", "official_total": 5.0, "new": 5.0, "legacy": 5.0, "gold": 5.0},
            {"case": "Q1", "student": "S2", "official_total": 5.0, "new": 2.5, "legacy": 4.5, "gold": 2.5},
        ],
    }
    path = tmp_path / "scaled_double_gate.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_human_boundary_gate(tmp_path: Path, *, new_over: int = 2, legacy_over: int = 0) -> Path:
    payload = {
        "summary": {
            "schema": "luban_legacy_arm_regression.v1",
            "gold": "po_slice 131 HUMAN labels (non-circular)",
            "n_pairs": 24,
            "over_credit_pairs": {"new": new_over, "legacy": legacy_over},
            "honest_boundary": "12 cases/24 pairs directional; human boundary blocker must not be ignored.",
        },
        "records": [
            {
                "case": "Q4-1A434000-罚则",
                "student": "S4",
                "legacy_awarded": 0.0,
                "new_uniform": 7.0,
                "human_awarded": 3.0,
                "official_total": 7.0,
            },
            {
                "case": "Q4-1A434000-罚则",
                "student": "S5",
                "legacy_awarded": 0.0,
                "new_uniform": 1.167,
                "human_awarded": 0.0,
                "official_total": 7.0,
            },
        ],
    }
    path = tmp_path / "human_boundary_gate.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_resolved_human_boundary_repair(tmp_path: Path) -> Path:
    payload = {
        "schema": "luban_pgo_stage5_human_boundary_repair.v1",
        "status": "resolved",
        "resolved_blockers": ["stage5_human_gold_over_credit_blocker"],
        "human_boundary_after_repair": {
            "gold": "po_slice 131 HUMAN labels (non-circular)",
            "n_pairs": 24,
            "over_credit_pairs": {"new": 0, "legacy": 0},
            "covered_over_credit_pairs": [
                {"case": "Q4-1A434000-罚则", "student": "S4"},
                {"case": "Q4-1A434000-罚则", "student": "S5"},
            ],
        },
        "safety": {
            "production_default_flip_allowed": False,
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "remote_write_allowed": False,
        },
    }
    path = tmp_path / "human_boundary_repair.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_pgo_stage5_canary_gate_allows_only_qa_operator_canary_and_reports_distribution(
    tmp_path: Path,
) -> None:
    from scripts.run_luban_pgo_stage5_canary_gate import build_canary_gate_report

    report = build_canary_gate_report(
        slot_dir=_write_slot(tmp_path),
        scaled_double_gate_path=_write_scaled_gate(tmp_path),
        cohort_ids=["qa_stage5", "operator_stage5"],
    )

    assert report["status"] == "qa_operator_canary_go"
    assert report["production_default_flip_allowed"] is False
    assert report["cohort_gate"]["allowed"] is True
    assert report["cohort_gate"]["cohort_ids"] == ["qa_stage5", "operator_stage5"]
    assert report["worker_restart_probe"]["fresh_process_verifier"]["status"] == "ok"
    assert report["runtime_supply"]["manifest"]["question_count"] == 1
    assert report["shadow_delta"]["sample_count"] == 2
    assert report["shadow_delta"]["mean_abs_new_legacy_delta"] == 1.0
    assert report["over_credit"]["scaled_gate_new"] == 0
    assert report["over_credit"]["scaled_gate_legacy"] == 1
    assert report["score_distribution"]["new"]["mean"] == 3.75
    assert report["score_distribution"]["legacy"]["mean"] == 4.75


def test_pgo_stage5_canary_gate_blocks_human_boundary_over_credit(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage5_canary_gate import build_canary_gate_report

    report = build_canary_gate_report(
        slot_dir=_write_slot(tmp_path),
        scaled_double_gate_path=_write_scaled_gate(tmp_path),
        human_boundary_path=_write_human_boundary_gate(tmp_path),
        cohort_ids=["qa_stage5", "operator_stage5"],
    )

    assert report["status"] == "blocked"
    assert "stage5_human_gold_over_credit_blocker" in report["blockers"]
    assert report["over_credit"]["human_boundary"]["broad_flip_blocker"] is True
    assert report["over_credit"]["human_boundary"]["repair_status"] == "missing"


def test_pgo_stage5_canary_gate_accepts_resolved_human_boundary_repair(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage5_canary_gate import build_canary_gate_report

    report = build_canary_gate_report(
        slot_dir=_write_slot(tmp_path),
        scaled_double_gate_path=_write_scaled_gate(tmp_path),
        human_boundary_path=_write_human_boundary_gate(tmp_path),
        human_boundary_repair_path=_write_resolved_human_boundary_repair(tmp_path),
        cohort_ids=["qa_stage5", "operator_stage5"],
    )

    assert report["status"] == "qa_operator_canary_go"
    assert "stage5_human_gold_over_credit_blocker" not in report["blockers"]
    assert report["over_credit"]["human_boundary"]["broad_flip_blocker"] is False
    assert report["over_credit"]["human_boundary"]["repair_status"] == "resolved"
    assert report["over_credit"]["human_boundary"]["original_broad_flip_blocker"] is True


def test_pgo_stage5_human_boundary_repair_evidence_is_built_from_runtime_scorer(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage5_human_boundary_repair import (
        build_human_boundary_repair_evidence,
    )

    repair = build_human_boundary_repair_evidence(
        human_boundary_path=_write_human_boundary_gate(tmp_path),
    )

    assert repair["schema"] == "luban_pgo_stage5_human_boundary_repair.v1"
    assert repair["status"] == "resolved"
    assert repair["resolved_blockers"] == ["stage5_human_gold_over_credit_blocker"]
    assert repair["runtime_consumed"]["pgo_coverage_scorer"] is True
    assert repair["runtime_consumed"]["tracked_runtime_supply"] is True
    assert repair["runtime_consumed"]["multi_answer_no_score"] is True
    assert repair["runtime_consumed"]["list_shape_weights"] is True
    assert repair["human_boundary_after_repair"]["over_credit_pairs"] == {"new": 0, "legacy": 0}
    assert repair["repair_records"]["Q4-1A434000-罚则::S4"]["repaired_new_awarded"] == 3.0
    assert repair["repair_records"]["Q4-1A434000-罚则::S4"]["runtime_supply"]["status"] == "ok"
    assert repair["repair_records"]["Q4-1A434000-罚则::S4"]["runtime_supply"]["runtime_qid"] == (
        "2023::EXAM_1A434000_P0010_02::E0"
    )
    assert repair["repair_records"]["Q4-1A434000-罚则::S5"]["repaired_new_awarded"] == 0.0
    assert repair["safety"]["official_score_allowed"] is False
    assert repair["safety"]["canonical_write_allowed"] is False


def test_pgo_stage5_canary_gate_blocks_non_canary_cohort(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage5_canary_gate import build_canary_gate_report

    report = build_canary_gate_report(
        slot_dir=_write_slot(tmp_path),
        scaled_double_gate_path=_write_scaled_gate(tmp_path),
        cohort_ids=["student_1"],
    )

    assert report["status"] == "blocked"
    assert "cohort_not_limited_to_qa_operator" in report["blockers"]


def test_pgo_stage5_canary_gate_blocks_missing_scaled_gate_without_traceback(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage5_canary_gate import build_canary_gate_report

    report = build_canary_gate_report(
        slot_dir=_write_slot(tmp_path),
        scaled_double_gate_path=tmp_path / "missing_scaled_double_gate.json",
        cohort_ids=["qa_stage5"],
    )

    assert report["status"] == "blocked"
    assert "scaled_double_gate_missing" in report["blockers"]
