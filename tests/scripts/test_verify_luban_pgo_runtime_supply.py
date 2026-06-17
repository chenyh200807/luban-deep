"""Verification gate for the tracked PGO runtime-supply slot."""

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


def _pgo_object() -> dict:
    return {
        "schema_id": SCHEMA_ID,
        "question_id": "Q-VERIFY",
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


def _factory_candidate() -> dict:
    return {
        "summary": {
            "schema": "luban_full_factory_candidate.v1",
            "classification": {"candidate_only": True, "review_only": True},
        },
        "cases": [
            {
                "question_id": "Q-VERIFY",
                "case_file": "Q-VERIFY.json",
                "point_type": "list",
                "resolution": "consensus",
                "resolution_lane": "A_consensus",
                "final_mnm_ok": True,
                "segments": [{"text": "施工总进度计划表( 图)", "is_list_item": True}],
            }
        ],
    }


def _write_slot(tmp_path: Path) -> Path:
    result = build_grading_contracts_from_factory_candidate(_factory_candidate(), [_pgo_object()])
    bundle = build_pgo_runtime_supply(result["contracts"])
    out_dir = tmp_path / "v_case_rubric_scored_pgo"
    write_pgo_runtime_supply(bundle, out_dir)
    return out_dir


def test_verify_luban_pgo_runtime_supply_accepts_hash_pinned_default_off_slot(tmp_path: Path) -> None:
    from scripts.verify_luban_pgo_runtime_supply import verify_pgo_runtime_supply

    report = verify_pgo_runtime_supply(_write_slot(tmp_path))

    assert report["status"] == "ok"
    assert report["blockers"] == []
    assert report["checks"]["content_hash_match"] is True
    assert report["checks"]["canonical_pointer_match"] is True
    assert report["checks"]["production_default_off"] is True
    assert report["manifest"]["question_count"] == 1
    assert report["manifest"]["scoring_point_count"] == 1
    assert report["manifest"]["factory_resolution_lanes"] == ["A_consensus"]


def test_verify_luban_pgo_runtime_supply_blocks_pointer_hash_mismatch(tmp_path: Path) -> None:
    from scripts.verify_luban_pgo_runtime_supply import main, verify_pgo_runtime_supply

    slot_dir = _write_slot(tmp_path)
    pointer_path = slot_dir / "canonical_pointer.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["expected_content_hash"] = "tampered"
    pointer_path.write_text(json.dumps(pointer, ensure_ascii=False), encoding="utf-8")

    report = verify_pgo_runtime_supply(slot_dir)

    assert report["status"] == "blocked"
    assert "canonical_pointer_hash_mismatch" in report["blockers"]
    assert main(["--slot-dir", str(slot_dir)]) == 1
