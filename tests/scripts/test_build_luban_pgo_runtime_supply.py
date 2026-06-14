"""CLI tests for building the PGO runtime supply candidate."""

from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.per_question_grading_object import (
    A_OFFICIAL,
    GRADING_CONTRACT_SCHEMA_ID,
    PENDING_SCORE_AUTHORITY,
    SCHEMA_ID,
)


def _contract() -> dict:
    return {
        "contract_schema": GRADING_CONTRACT_SCHEMA_ID,
        "source_schema": "luban_per_question_grading_object.v1",
        "question_id": "Q-CLI",
        "official_total_score": 6.0,
        "official_total_score_authority": A_OFFICIAL,
        "per_point_score_authority": "pending_calibration_not_official",
        "scoring_points": [
            {
                "point_id": "sp_cli",
                "sub_no": 1,
                "sub_type": "free_text_point",
                "official_slice": "写明验收应由总监理工程师组织",
                "authority_source": A_OFFICIAL,
                "span_hash": "sha256:cli",
            }
        ],
        "supporting_citations": [],
        "official_score_allowed": False,
        "canonical_write_allowed": False,
    }


def _pgo_object() -> dict:
    return {
        "schema_id": SCHEMA_ID,
        "question_id": "Q-FACTORY-CLI",
        "stem": "案例题",
        "official_total_score": 8.0,
        "official_total_score_authority": A_OFFICIAL,
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "per_point_score_authority": PENDING_SCORE_AUTHORITY,
        "sub_questions": [
            {
                "sub_no": 1,
                "sub_type": "free_text_point",
                "official_sub_answer_verbatim": "施工总进度计划表( 图)\n资源需要量及供应平衡表",
                "scoring_points": [],
            }
        ],
    }


def _factory_candidate() -> dict:
    return {
        "summary": {
            "schema": "luban_full_factory_candidate.v1",
            "classification": {"candidate_only": True, "review_only": True},
            "final_must_not_mint_clean": "1/1",
        },
        "cases": [
            {
                "question_id": "Q-FACTORY-CLI",
                "case_file": "Q-FACTORY-CLI.json",
                "point_type": "list",
                "resolution": "consensus",
                "resolution_lane": "A_consensus",
                "final_mnm_ok": True,
                "segments": [
                    {"text": "施工总进度计划表( 图)", "is_list_item": True},
                    {"text": "资源需要量及供应平衡表", "is_list_item": True},
                ],
            }
        ],
    }


def test_build_luban_pgo_runtime_supply_cli_writes_bank_and_pointer(tmp_path: Path) -> None:
    from scripts.build_luban_pgo_runtime_supply import main

    contracts_path = tmp_path / "contracts.json"
    out_dir = tmp_path / "v_case_rubric_scored_pgo"
    contracts_path.write_text(
        json.dumps({"contracts": [_contract()]}, ensure_ascii=False), encoding="utf-8"
    )

    code = main(["--contracts", str(contracts_path), "--out-dir", str(out_dir)])

    assert code == 0
    bank = json.loads((out_dir / "case_rubric_scored_pgo.json").read_text(encoding="utf-8"))
    pointer = json.loads((out_dir / "canonical_pointer.json").read_text(encoding="utf-8"))
    assert bank["manifest"]["namespace"] == "case_rubric_scored_pgo"
    assert bank["manifest"]["production_default"] == "off"
    assert bank["records"][0]["score"] is None
    assert pointer["expected_content_hash"] == bank["manifest"]["content_hash"]


def test_build_luban_pgo_runtime_supply_cli_blocks_empty_supply(tmp_path: Path) -> None:
    from scripts.build_luban_pgo_runtime_supply import main

    contracts_path = tmp_path / "contracts.json"
    out_dir = tmp_path / "out"
    contracts_path.write_text(json.dumps({"contracts": []}, ensure_ascii=False), encoding="utf-8")

    code = main(["--contracts", str(contracts_path), "--out-dir", str(out_dir)])

    assert code == 1
    assert not (out_dir / "case_rubric_scored_pgo.json").exists()


def test_build_luban_pgo_runtime_supply_cli_accepts_factory_candidate(tmp_path: Path) -> None:
    from scripts.build_luban_pgo_runtime_supply import main

    factory_path = tmp_path / "factory.json"
    objects_dir = tmp_path / "objects"
    out_dir = tmp_path / "v_case_rubric_scored_pgo"
    objects_dir.mkdir()
    factory_path.write_text(json.dumps(_factory_candidate(), ensure_ascii=False), encoding="utf-8")
    (objects_dir / "Q_FACTORY_CLI.json").write_text(
        json.dumps(_pgo_object(), ensure_ascii=False), encoding="utf-8"
    )

    code = main(
        [
            "--factory-candidate",
            str(factory_path),
            "--pgo-objects-dir",
            str(objects_dir),
            "--out-dir",
            str(out_dir),
        ]
    )

    assert code == 0
    bank = json.loads((out_dir / "case_rubric_scored_pgo.json").read_text(encoding="utf-8"))
    pointer = json.loads((out_dir / "canonical_pointer.json").read_text(encoding="utf-8"))
    assert bank["manifest"]["question_count"] == 1
    assert bank["manifest"]["scoring_point_count"] == 2
    assert bank["manifest"]["production_default"] == "off"
    assert bank["records"][0]["score"] is None
    assert pointer["expected_content_hash"] == bank["manifest"]["content_hash"]
