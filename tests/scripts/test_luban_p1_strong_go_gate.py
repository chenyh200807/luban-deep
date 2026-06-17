"""P1 Strong GO gate for the M35 Nexus-like scoring artifact engine."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_p1_strong_go_gate import build_p1_strong_go_package


def test_p1_strong_go_uses_governed_subset_without_release_promotion(tmp_path: Path) -> None:
    package = build_p1_strong_go_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_p1_strong_go_gate.v1"
    assert package["p1_governed_subset"]["verdict"] == "STRONG-GO"
    assert package["p1_full_set"]["verdict"] == "WEAK-GO"
    assert package["release_verdict"] == "NO-GO"
    assert package["p1_governed_subset"]["sample_count"] >= 100
    assert package["p1_governed_subset"]["label_authority"] == "ai_governed_gold"
    assert package["p1_governed_subset"]["quality_claim_allowed"] is True

    metrics = package["p1_governed_subset"]["summary"]
    assert metrics["artifact_first_llm_judge"]["score_mae"] < metrics["legacy"]["score_mae"]
    assert metrics["artifact_first_llm_judge"]["fail_open_rate"] <= metrics["legacy"]["fail_open_rate"]
    assert metrics["artifact_first_llm_judge"]["fail_open_rate"] <= 0.01
    assert metrics["artifact_first_llm_judge"]["point_precision"] >= 0.99
    assert metrics["artifact_first_llm_judge"]["point_recall"] >= 0.99

    assert package["safety"]["official_score_allowed"] is False
    assert package["safety"]["canonical_truth_written"] is False
    assert package["safety"]["published_registry_written"] is False

    written = tmp_path / "p1_strong_go_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package


def test_p1_strong_go_blocks_when_governed_sample_is_too_small(tmp_path: Path) -> None:
    gold = tmp_path / "student_answers.jsonl"
    gold.write_text(
        json.dumps(
            {
                "answer_id": "A1",
                "question_id": "Q1",
                "student_id": "S1",
                "label_authority": "ai_governed_gold",
                "score_label_valid": True,
                "gold_score": 1.0,
                "gold_point_matches": [{"point_id": "Q1::P1", "status": "hit"}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    per_row = tmp_path / "per_row.jsonl"
    for arm, score in {
        "legacy": 0.0,
        "current_rag_offline": 0.0,
        "artifact_first_compiled": 1.0,
        "artifact_first_llm_judge": 1.0,
    }.items():
        payload = {
            "arm": arm,
            "question_id": "Q1",
            "student_id": "S1",
            "predicted_score": score,
            "token_total": 1,
            "latency_ms": 1,
            "high_risk_review": False,
        }
        if arm == "artifact_first_llm_judge":
            payload["point_matches"] = [
                {
                    "point_id": "Q1::P1",
                    "status": "hit",
                    "awarded_score": 1.0,
                    "evidence_span": "x",
                }
            ]
        per_row.write_text(
            per_row.read_text(encoding="utf-8") + json.dumps(payload, ensure_ascii=False) + "\n"
            if per_row.exists()
            else json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "provider": {"provider_call_count": 1},
                "safety": {
                    "production_write_count": 0,
                    "db_write_count": 0,
                    "remote_write_count": 0,
                    "canonical_truth_written": False,
                    "published_registry_written": False,
                    "official_score_allowed": False,
                    "is_release_truth": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    package = build_p1_strong_go_package(
        output_dir=tmp_path / "out",
        gold_path=gold,
        per_row_path=per_row,
        ab_report_path=report,
        min_governed_rows=100,
    )

    assert package["p1_governed_subset"]["verdict"] == "NO-GO"
    assert "governed_sample_below_threshold" in package["p1_governed_subset"]["blockers"]
    assert package["release_verdict"] == "NO-GO"
