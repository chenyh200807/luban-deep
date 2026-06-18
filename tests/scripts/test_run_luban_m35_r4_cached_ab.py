"""R4 cached A/B replay: artifact-first grading vs ai-governed gold.

The R4 runner re-grades every gold row artifact-first (the fixture scoring
points are the compiled artifact under test) with a cached judge, then scores
the prediction against the gold point matches and gold score:

  - point_precision / point_recall over hit predictions
  - score_mae against ``gold_score``
  - the historical failure line (0.5267 point-hit agreement / 4.6091 MAE)

The judge is injected (hermetic in tests, a cached deepseek-chat replay live)
so the math is verified without provider calls. Safety must stay all-zero and
the tier is ``cached_judge_replay``.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_m35_r4_cached_ab import (
    HISTORICAL_POINT_HIT_AGREEMENT,
    HISTORICAL_SCORE_MAE,
    POINT_PRECISION_THRESHOLD,
    POINT_RECALL_THRESHOLD,
    SCORE_MAE_THRESHOLD,
    build_report,
)


def _gold_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Two gold rows over one question: one perfect, one half-credit."""
    manifest = {
        "fixture_id": "r4_test",
        "questions": [
            {
                "question_id": "Q1",
                "stem": "案例题题干",
                "total_score": 4.0,
                "scoring_points": [
                    {
                        "point_id": "Q1::SP01",
                        "criterion": "应组织专家论证",
                        "max_score": 2.0,
                        "policy_type": "qualitative",
                        "required_terms": [],
                        "source_refs": [
                            {"source_type": "exam_reference_answer", "source_id": "X1"}
                        ],
                    },
                    {
                        "point_id": "Q1::SP02",
                        "criterion": "应编制专项施工方案",
                        "max_score": 2.0,
                        "policy_type": "qualitative",
                        "required_terms": [],
                        "source_refs": [
                            {"source_type": "exam_reference_answer", "source_id": "X2"}
                        ],
                    },
                ],
            }
        ],
    }
    rows = [
        {
            "answer_id": "A1",
            "question_id": "Q1",
            "student_answer": "组织专家论证并编制专项施工方案",
            "label_authority": "ai_governed_gold",
            "gold_score": 4.0,
            "gold_point_matches": [
                {"point_id": "Q1::SP01", "status": "hit", "max_score": 2.0, "awarded_score": 2.0},
                {"point_id": "Q1::SP02", "status": "hit", "max_score": 2.0, "awarded_score": 2.0},
            ],
        },
        {
            "answer_id": "A2",
            "question_id": "Q1",
            "student_answer": "组织专家论证",
            "label_authority": "ai_governed_gold",
            "gold_score": 2.0,
            "gold_point_matches": [
                {"point_id": "Q1::SP01", "status": "hit", "max_score": 2.0, "awarded_score": 2.0},
                {"point_id": "Q1::SP02", "status": "miss", "max_score": 2.0, "awarded_score": 0.0},
            ],
        },
    ]
    manifest_path = tmp_path / "manifest.json"
    answers_path = tmp_path / "student_answers.jsonl"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    answers_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return answers_path, manifest_path


def _oracle_judge(point: dict, answer: str) -> dict:
    """A judge that reproduces the gold verdicts exactly (perfect prediction)."""
    pid = str(point.get("point_id") or "")
    if "组织专家论证并编制专项施工方案" in answer:
        return {"status": "hit", "evidence_span": answer}
    if pid.endswith("SP01"):
        return {"status": "hit", "evidence_span": answer}
    return {"status": "miss", "evidence_span": ""}


def test_oracle_judge_hits_perfect_thresholds(tmp_path):
    answers_path, manifest_path = _gold_fixture(tmp_path)
    report = build_report(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fn=_oracle_judge,
        judge_model="deepseek-chat",
        cache_path=tmp_path / "cache.json",
        cache_provenance="hermetic_oracle",
    )

    assert report["tier"] == "cached_judge_replay"
    metrics = report["metrics"]
    assert metrics["point_precision"] == 1.0
    assert metrics["point_recall"] == 1.0
    assert metrics["score_mae"] == 0.0
    gates = report["gate_results"]
    assert gates["point_precision_pass"] is True
    assert gates["point_recall_pass"] is True
    assert gates["score_mae_pass"] is True
    assert gates["all_thresholds_pass"] is True
    hist = report["historical_comparison"]
    assert hist["historical_point_hit_agreement"] == HISTORICAL_POINT_HIT_AGREEMENT
    assert hist["historical_score_mae"] == HISTORICAL_SCORE_MAE
    assert hist["point_hit_agreement_beats_historical"] is True
    assert hist["score_mae_beats_historical"] is True


def test_thresholds_are_the_plan_values():
    assert POINT_PRECISION_THRESHOLD == 0.90
    assert POINT_RECALL_THRESHOLD == 0.90
    assert SCORE_MAE_THRESHOLD == 1.0
    assert HISTORICAL_POINT_HIT_AGREEMENT == 0.5267
    assert HISTORICAL_SCORE_MAE == 4.6091


def test_safety_block_is_all_zero_and_label_audit_present(tmp_path):
    answers_path, manifest_path = _gold_fixture(tmp_path)
    report = build_report(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fn=_oracle_judge,
        judge_model="deepseek-chat",
        cache_path=tmp_path / "cache.json",
        cache_provenance="hermetic_oracle",
    )
    safety = report["safety"]
    assert safety["db_write_count"] == 0
    assert safety["remote_write_count"] == 0
    assert safety["production_write_count"] == 0
    assert safety["canonical_truth_written"] is False
    assert safety["rag_chunk_as_answer_key"] == 0
    assert report["tier"] == "cached_judge_replay"
    assert report["official_score_allowed"] is False
    assert "label_audit" in report
    assert report["label_audit"]["answer_count"] == 2
    assert report["judge"]["cache_provenance"] == "hermetic_oracle"
    assert report["judge"]["model"] == "deepseek-chat"


def test_wrong_judge_drops_below_thresholds(tmp_path):
    """A judge that misses everything must fail the recall gate (no fake-green)."""
    answers_path, manifest_path = _gold_fixture(tmp_path)

    def all_miss_judge(point: dict, answer: str) -> dict:
        return {"status": "miss", "evidence_span": ""}

    report = build_report(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fn=all_miss_judge,
        judge_model="deepseek-chat",
        cache_path=tmp_path / "cache.json",
        cache_provenance="hermetic_all_miss",
    )
    assert report["metrics"]["point_recall"] == 0.0
    assert report["gate_results"]["point_recall_pass"] is False
    assert report["gate_results"]["all_thresholds_pass"] is False
    assert report["metrics"]["score_mae"] == 3.0
    assert report["gate_results"]["score_mae_pass"] is False
