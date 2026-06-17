from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from scripts.build_luban_agentic_grading_harness import (
    build_agentic_grading_packet,
    score_agentic_predictions,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    review_packet = {
        "slice_id": "agentic-fixture",
        "grading_guideline": "踩字给分；近义/口号不给分。",
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A400000",
                "stem": "题干",
                "official_answer": "标准答案",
                "official_analysis": "解析",
                "penalty_rule": "",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出防护栏杆",
                        "max_score": 1,
                        "official_basis": "防护栏杆",
                        "list_rule": "",
                        "penalty_rule": None,
                    }
                ],
                "samples": [
                    {"student_id": "S1", "archetype": "半对", "answer_text": "设置防护栏杆。"}
                ],
            }
        ],
    }
    manifest = {
        "slice_id": "agentic-fixture",
        "selected_samples": [
            {
                "case_id": "QX",
                "student_id": "S1",
                "artifact_point_scores": {"P1": 0.0},
                "ledger_point_rows": [
                    {"point_id": "P1", "ledger_hit": "hit", "max_score": 1, "gold_score": 1}
                ],
            }
        ],
    }
    labels = [
        {
            "case_id": "QX",
            "student_id": "S1",
            "point_id": "P1",
            "human_hit": "hit",
            "human_score": "1",
            "human_error_codes": "",
            "human_note": "命中防护栏杆",
        }
    ]
    review_packet_path = tmp_path / "packet.json"
    manifest_path = tmp_path / "manifest.json"
    labels_path = tmp_path / "labels.csv"
    review_packet_path.write_text(json.dumps(review_packet, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    _write_csv(labels_path, labels)
    return review_packet_path, manifest_path, labels_path


def test_build_agentic_grading_packet_is_blind_and_schema_bound(tmp_path: Path) -> None:
    review_packet_path, manifest_path, _labels_path = _fixture_paths(tmp_path)

    paths = build_agentic_grading_packet(
        review_packet_path=review_packet_path,
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
    )

    packet = json.loads(paths["packet"].read_text(encoding="utf-8"))
    serialized = json.dumps(packet, ensure_ascii=False)
    assert packet["slice_id"] == "agentic-fixture"
    assert packet["status"] == "awaiting_model_predictions"
    assert packet["tasks"][0]["case_id"] == "QX"
    assert packet["tasks"][0]["scoring_points"][0]["point_id"] == "P1"
    assert "human_hit" not in serialized
    assert "human_score" not in serialized
    assert "artifact_point_scores" not in serialized
    assert "ledger_hit" not in serialized
    assert "evidence_span" in packet["response_schema"]["per_point_required_fields"]
    assert paths["predictions_template"].exists()


def test_agentic_grading_harness_cli_build_runs_as_script(tmp_path: Path) -> None:
    review_packet_path, manifest_path, _labels_path = _fixture_paths(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_luban_agentic_grading_harness.py",
            "build",
            "--review-packet",
            str(review_packet_path),
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "out" / "agentic_grading_packet.json").exists()


def test_score_agentic_predictions_compares_model_to_human_and_artifact(tmp_path: Path) -> None:
    _review_packet_path, manifest_path, labels_path = _fixture_paths(tmp_path)
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(
        json.dumps(
            {
                "slice_id": "agentic-fixture",
                "prediction_sets": [
                    {
                        "arm": "gpt55_primary",
                        "predictions": [
                            {
                                "case_id": "QX",
                                "student_id": "S1",
                                "point_id": "P1",
                                "hit": "hit",
                                "score": 1,
                                "confidence": 0.9,
                                "evidence_span": "防护栏杆",
                                "rationale": "学生逐字写出防护栏杆。",
                                "unsupported": False,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = score_agentic_predictions(
        manifest_path=manifest_path,
        labels_path=labels_path,
        predictions_path=predictions_path,
    )

    assert result["human_vs_artifact_first"]["mean_abs_score_delta"] == 1.0
    assert result["agentic_arms"]["gpt55_primary"]["mean_abs_score_delta"] == 0.0
    assert result["agentic_arms"]["gpt55_primary"]["point_hit_agreement"] == 1.0
    assert result["agentic_arms"]["gpt55_primary"]["unsupported_judgment_rate"] == 0.0


def test_score_agentic_predictions_flags_missing_evidence_as_unsupported(tmp_path: Path) -> None:
    _review_packet_path, manifest_path, labels_path = _fixture_paths(tmp_path)
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(
        json.dumps(
            {
                "slice_id": "agentic-fixture",
                "prediction_sets": [
                    {
                        "arm": "opus48_reviewer",
                        "predictions": [
                            {
                                "case_id": "QX",
                                "student_id": "S1",
                                "point_id": "P1",
                                "hit": "hit",
                                "score": 1,
                                "confidence": 0.2,
                                "evidence_span": "",
                                "rationale": "感觉命中。",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = score_agentic_predictions(
        manifest_path=manifest_path,
        labels_path=labels_path,
        predictions_path=predictions_path,
    )

    assert result["agentic_arms"]["opus48_reviewer"]["unsupported_judgment_rate"] == 1.0
    assert result["agentic_arms"]["opus48_reviewer"]["unsupported_judgments"][0]["point_id"] == "P1"


def test_score_agentic_predictions_flags_evidence_span_not_from_student_answer(tmp_path: Path) -> None:
    review_packet_path, manifest_path, labels_path = _fixture_paths(tmp_path)
    build_agentic_grading_packet(
        review_packet_path=review_packet_path,
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
    )
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(
        json.dumps(
            {
                "slice_id": "agentic-fixture",
                "prediction_sets": [
                    {
                        "arm": "gpt55_primary",
                        "predictions": [
                            {
                                "case_id": "QX",
                                "student_id": "S1",
                                "point_id": "P1",
                                "hit": "hit",
                                "score": 1,
                                "confidence": 0.9,
                                "evidence_span": "标准答案里的防护栏杆，不是学生原文",
                                "rationale": "模型引用了非学生答案片段。",
                                "unsupported": False,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = score_agentic_predictions(
        manifest_path=manifest_path,
        labels_path=labels_path,
        predictions_path=predictions_path,
        review_packet_path=review_packet_path,
    )

    arm = result["agentic_arms"]["gpt55_primary"]
    assert arm["unsupported_judgment_rate"] == 1.0
    assert arm["unsupported_judgments"][0]["reason"] == "evidence_span_not_in_student_answer"


def test_score_agentic_predictions_recognizes_deepseek_three_role_arms(tmp_path: Path) -> None:
    # The scorer is arm-name agnostic: deepseek_primary / deepseek_strict_reviewer /
    # deepseek_dual_adjudicated must each be scored as their own arm.
    _review_packet_path, manifest_path, labels_path = _fixture_paths(tmp_path)
    pred = {
        "case_id": "QX",
        "student_id": "S1",
        "point_id": "P1",
        "hit": "hit",
        "score": 1,
        "confidence": 0.9,
        "evidence_span": "防护栏杆",
        "rationale": "学生逐字写出防护栏杆。",
        "unsupported": False,
    }
    predictions_path = tmp_path / "deepseek_predictions.json"
    predictions_path.write_text(
        json.dumps(
            {
                "slice_id": "deepseek-fixture",
                "prediction_sets": [
                    {"arm": "deepseek_primary", "predictions": [dict(pred)]},
                    {"arm": "deepseek_strict_reviewer", "predictions": [dict(pred)]},
                    {"arm": "deepseek_dual_adjudicated", "predictions": [dict(pred)]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = score_agentic_predictions(
        manifest_path=manifest_path,
        labels_path=labels_path,
        predictions_path=predictions_path,
    )

    arms = result["agentic_arms"]
    for arm_name in ("deepseek_primary", "deepseek_strict_reviewer", "deepseek_dual_adjudicated"):
        assert arm_name in arms
        assert arms[arm_name]["point_hit_agreement"] == 1.0
        assert arms[arm_name]["unsupported_judgment_rate"] == 0.0
