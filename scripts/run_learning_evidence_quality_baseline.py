#!/usr/bin/env python
"""
Learning Evidence Quality Baseline Script
==========================================
Task 0 deliverable: measure quality-gate field completeness against a fixture
dataset and write results to .gstack/qa-reports/learning-evidence-quality-baseline.json.

The script uses fixture events (no Supabase dependency) and can run standalone:

    python scripts/run_learning_evidence_quality_baseline.py

Exit codes:
  0  – baseline meets all minimums
  1  – one or more minimum thresholds violated (use as CI gate trigger)

Thresholds (hardcoded as policy, not configurable per-run):
  detail_ready_min:           0.70
  truth_eligible_min:         0.60
  missing_explanation_max:    0.20
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root without pip install
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from deeptutor.services.construction_grading.learning_evidence import build_learning_evidence_payload

# ─────────────────────────────────────────────────────────────────────────────
# Policy thresholds (CI gate boundaries)
# ─────────────────────────────────────────────────────────────────────────────
_THRESHOLDS = {
    "detail_ready_min": 0.70,
    "truth_eligible_min": 0.60,
    "missing_explanation_max": 0.20,
}

# ─────────────────────────────────────────────────────────────────────────────
# Fixture dataset (20 sample events spanning multiple signal types)
# ─────────────────────────────────────────────────────────────────────────────

def _fixture_events() -> list[dict[str, Any]]:
    """Return a list of grading_result dicts covering a range of quality scenarios."""
    return [
        # ── grading_result with full explanation (12 events) ─────────────────
        {
            "type": "mcq",
            "question_id": f"mcq_{i:03d}",
            "question_stem": f"关于建筑施工管理的说法（第{i}题），正确的是？",
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": {
                "summary": f"正确选项是 B，因为规范第{i}条明确要求。",
                "why_user_wrong": "选项 A 忽略了并列条件。",
            },
            "error_events": [
                {
                    "error_code": "M06",
                    "concept_tag": "工程招标投标与合同管理",
                    "diagnosis": "漏掉关键选项。",
                }
            ],
            "next_training_signal": {
                "concept": "工程招标投标与合同管理",
                "focus": "并列条件判断",
                "mode": "practice",
            },
            "_signal_type": "grading_result",
        }
        for i in range(1, 13)
    ] + [
        # ── answer_explanation events — some have explanation (4 of 6 have) ──
        {
            "type": "mcq",
            "question_id": f"ae_{i:03d}",
            "question_stem": f"关于防火分区规范的说法（第{i}题），正确的是？",
            "user_answer": "C",
            "correct_answer": "D",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": "正确答案是 D，因为防火分区面积上限因建筑类型不同。" if i <= 4 else None,
            "explanation_missing_reason": "" if i <= 4 else "grading_output_missing_explanation",
            "error_events": [
                {
                    "error_code": "M01",
                    "concept_tag": "防火分区",
                    "diagnosis": "基础知识不扎实。",
                }
            ],
            "next_training_signal": {
                "concept": "防火分区",
                "focus": "分区面积限值",
                "mode": "practice",
            },
            "_signal_type": "answer_explanation",
        }
        for i in range(1, 7)
    ] + [
        # ── concept_explain events — missing concept_tag (2 events) ──────────
        {
            "type": "case",
            "question_id": f"ce_{i:03d}",
            "question_stem": f"某项目施工现场安全要求（第{i}题），正确做法是？",
            "user_answer": "应立即停工。",
            "correct_answer": "应立即停工并报告监理。",
            "score_awarded": 0,
            "max_score": 1,
            "explanation": "完整答案需要包括停工后的报告程序。",
            "error_events": [
                # No concept_tag — represents concept_explain type with missing concept
                {
                    "error_code": "E02",
                    "diagnosis": "漏写报告程序。",
                }
            ],
            "next_training_signal": {
                # No concept
                "focus": "安全停工程序",
                "mode": "case_repair",
            },
            "_signal_type": "concept_explain",
        }
        for i in range(1, 3)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation logic
# ─────────────────────────────────────────────────────────────────────────────

def _run_baseline() -> dict[str, Any]:
    fixtures = _fixture_events()
    sample_size = len(fixtures)

    detail_ready_count = 0
    truth_eligible_count = 0
    missing_explanation_count = 0
    missing_concept_count = 0
    missing_question_ref_count = 0
    by_signal_type: dict[str, int] = {}

    for raw in fixtures:
        signal_type = raw.get("_signal_type", "unknown")
        clean_payload = {k: v for k, v in raw.items() if k != "_signal_type"}
        payload = build_learning_evidence_payload(
            grading_result=clean_payload,
            turn_id=f"baseline_turn_{clean_payload['question_id']}",
        )
        quality = payload.get("quality", {})

        if quality.get("detail_ready"):
            detail_ready_count += 1
        if quality.get("truth_eligible"):
            truth_eligible_count += 1
        missing = quality.get("missing_fields", [])
        if "explanation" in missing:
            missing_explanation_count += 1
        if "concept_label" in missing:
            missing_concept_count += 1
        if "question_ref" in missing:
            missing_question_ref_count += 1

        by_signal_type[signal_type] = by_signal_type.get(signal_type, 0) + 1

    detail_ready_rate = detail_ready_count / sample_size
    truth_eligible_rate = truth_eligible_count / sample_size
    missing_explanation_rate = missing_explanation_count / sample_size
    missing_concept_rate = missing_concept_count / sample_size
    missing_question_ref_rate = missing_question_ref_count / sample_size

    violations: list[str] = []
    if detail_ready_rate < _THRESHOLDS["detail_ready_min"]:
        violations.append(
            f"detail_ready={detail_ready_rate:.0%} < threshold {_THRESHOLDS['detail_ready_min']:.0%}"
        )
    if truth_eligible_rate < _THRESHOLDS["truth_eligible_min"]:
        violations.append(
            f"truth_eligible={truth_eligible_rate:.0%} < threshold {_THRESHOLDS['truth_eligible_min']:.0%}"
        )
    if missing_explanation_rate > _THRESHOLDS["missing_explanation_max"]:
        violations.append(
            f"missing_explanation={missing_explanation_rate:.0%} > threshold {_THRESHOLDS['missing_explanation_max']:.0%}"
        )

    return {
        "sample_size": sample_size,
        "detail_ready": f"{detail_ready_rate:.0%}",
        "truth_eligible": f"{truth_eligible_rate:.0%}",
        "missing_explanation": f"{missing_explanation_rate:.0%}",
        "missing_concept": f"{missing_concept_rate:.0%}",
        "missing_question_ref": f"{missing_question_ref_rate:.0%}",
        "by_signal_type": by_signal_type,
        "thresholds": _THRESHOLDS,
        "violations": violations,
        "passed": len(violations) == 0,
        # Numeric values for programmatic use
        "_rates": {
            "detail_ready": detail_ready_rate,
            "truth_eligible": truth_eligible_rate,
            "missing_explanation": missing_explanation_rate,
            "missing_concept": missing_concept_rate,
            "missing_question_ref": missing_question_ref_rate,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    result = _run_baseline()

    # Print human-readable summary
    print(f"sample_size={result['sample_size']}")
    print(f"detail_ready={result['detail_ready']}")
    print(f"truth_eligible={result['truth_eligible']}")
    print(f"missing_explanation={result['missing_explanation']}")
    print(f"missing_concept={result['missing_concept']}")
    print(f"missing_question_ref={result['missing_question_ref']}")
    print(f"by_signal_type={result['by_signal_type']}")

    if result["violations"]:
        print("\nTHRESHOLD VIOLATIONS:")
        for violation in result["violations"]:
            print(f"  - {violation}")
    else:
        print("\nAll thresholds passed.")

    # Write JSON report
    output_dir = _REPO_ROOT / ".gstack" / "qa-reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "learning-evidence-quality-baseline.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nReport written to: {output_path}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
