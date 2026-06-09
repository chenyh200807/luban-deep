from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


LEVELS = {
    "teacher_validated": ("POC_GO_ALLOWED", True),
    "po_directional_single_reviewer": ("WEAK_GO_MAX", True),
    "ai_council_directional": ("DIRECTIONAL_SHADOW", False),
    "generated_self_label": ("SHAPE_ONLY", False),
}

BUCKET_MINIMUMS = {
    "hit": 20,
    "partial": 10,
    "miss": 10,
    "wrong_content": 10,
    "near_synonym_not_exact": 5,
    "list_incomplete": 5,
    "calculation": 5,
    "stem_fact": 5,
    "external_source_required": 3,
    "off_path": 3,
}

VALID_DIRECTIONALITY = {
    "human_validated",
    "po_directional",
    "ai_council_directional",
    "generated_self_label",
}

EXPECTED_DIRECTIONALITY_BY_AUTHORITY = {
    "teacher_validated": "human_validated",
    "po_directional_single_reviewer": "po_directional",
    "ai_council_directional": "ai_council_directional",
    "generated_self_label": "generated_self_label",
}

VALID_LABEL_SCOPE = {"point_and_score"}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit(path: Path) -> dict[str, Any]:
    rows = _rows(path)
    question_count = len({str(row.get("question_id") or "") for row in rows if row.get("question_id")})
    label_authority_counts = Counter(
        str(row.get("label_authority") or "missing") for row in rows
    )
    sample_bucket_counts = Counter(str(row.get("sample_bucket") or "missing") for row in rows)
    missing_contract_answer_ids = [
        row.get("answer_id")
        for row in rows
        if not row.get("label_authority")
        or str(row.get("label_authority") or "") not in LEVELS
        or not row.get("label_scope")
        or str(row.get("label_scope") or "") not in VALID_LABEL_SCOPE
        or not row.get("directionality_flag")
        or str(row.get("directionality_flag") or "") not in VALID_DIRECTIONALITY
        or not _directionality_matches_authority(row)
        or "gold_score" not in row
        or not _has_numeric_gold_score(row)
        or not row.get("gold_point_matches")
        or not row.get("point_label_provenance")
        or not _point_provenance_covers_gold_matches(row)
        or _point_provenance_has_duplicate_points(row)
        or not _point_provenance_authority_matches(row)
        or not row.get("sample_bucket")
    ]
    missing_bucket_minimums = {
        bucket: required - sample_bucket_counts.get(bucket, 0)
        for bucket, required in BUCKET_MINIMUMS.items()
        if sample_bucket_counts.get(bucket, 0) < required
    }

    if missing_contract_answer_ids:
        verdict_ceiling, quality_claim_allowed = "NO_GO_LABEL_CONTRACT", False
    elif label_authority_counts.get("generated_self_label"):
        verdict_ceiling, quality_claim_allowed = LEVELS["generated_self_label"]
    elif not rows or len(rows) < 100 or question_count < 20:
        verdict_ceiling, quality_claim_allowed = "NO_GO_LABEL_VOLUME", False
    elif missing_bucket_minimums:
        verdict_ceiling, quality_claim_allowed = "NO_GO_BUCKET_COVERAGE", False
    elif label_authority_counts.get("ai_council_directional"):
        verdict_ceiling, quality_claim_allowed = LEVELS["ai_council_directional"]
    elif label_authority_counts.get("teacher_validated"):
        if set(label_authority_counts) == {"teacher_validated"}:
            verdict_ceiling, quality_claim_allowed = LEVELS["teacher_validated"]
        elif label_authority_counts.get("po_directional_single_reviewer"):
            verdict_ceiling, quality_claim_allowed = LEVELS["po_directional_single_reviewer"]
        elif label_authority_counts.get("ai_council_directional"):
            verdict_ceiling, quality_claim_allowed = LEVELS["ai_council_directional"]
        else:
            verdict_ceiling, quality_claim_allowed = "NO_GO_LABEL_CONTRACT", False
    elif label_authority_counts.get("po_directional_single_reviewer"):
        verdict_ceiling, quality_claim_allowed = LEVELS["po_directional_single_reviewer"]
    elif label_authority_counts.get("ai_council_directional"):
        verdict_ceiling, quality_claim_allowed = LEVELS["ai_council_directional"]
    else:
        verdict_ceiling, quality_claim_allowed = LEVELS["generated_self_label"]

    return {
        "answer_count": len(rows),
        "question_count": question_count,
        "label_authority_counts": dict(label_authority_counts),
        "sample_bucket_counts": dict(sample_bucket_counts),
        "missing_bucket_minimums": missing_bucket_minimums,
        "missing_contract_answer_ids": missing_contract_answer_ids,
        "verdict_ceiling": verdict_ceiling,
        "quality_claim_allowed": quality_claim_allowed,
        "poc_go_allowed": verdict_ceiling == "POC_GO_ALLOWED",
        "weak_go_allowed": verdict_ceiling in {"POC_GO_ALLOWED", "WEAK_GO_MAX"},
        "spot_check_required": verdict_ceiling == "WEAK_GO_MAX",
    }


def _point_provenance_covers_gold_matches(row: dict[str, Any]) -> bool:
    gold_point_ids = {
        str(point.get("point_id") or "")
        for point in (row.get("gold_point_matches") or [])
        if point.get("point_id")
    }
    provenance_point_ids = {
        str(point.get("point_id") or "")
        for point in (row.get("point_label_provenance") or [])
        if point.get("point_id")
    }
    return bool(gold_point_ids) and gold_point_ids <= provenance_point_ids


def _point_provenance_authority_matches(row: dict[str, Any]) -> bool:
    label_authority = str(row.get("label_authority") or "")
    gold_point_ids = {
        str(point.get("point_id") or "")
        for point in (row.get("gold_point_matches") or [])
        if point.get("point_id")
    }
    provenance_by_point = {
        str(point.get("point_id") or ""): str(point.get("authority") or "")
        for point in (row.get("point_label_provenance") or [])
        if point.get("point_id")
    }
    return all(provenance_by_point.get(point_id) == label_authority for point_id in gold_point_ids)


def _point_provenance_has_duplicate_points(row: dict[str, Any]) -> bool:
    provenance_point_ids = [
        str(point.get("point_id") or "")
        for point in (row.get("point_label_provenance") or [])
        if point.get("point_id")
    ]
    return len(provenance_point_ids) != len(set(provenance_point_ids))


def _directionality_matches_authority(row: dict[str, Any]) -> bool:
    label_authority = str(row.get("label_authority") or "")
    expected = EXPECTED_DIRECTIONALITY_BY_AUTHORITY.get(label_authority)
    return expected is not None and str(row.get("directionality_flag") or "") == expected


def _has_numeric_gold_score(row: dict[str, Any]) -> bool:
    if isinstance(row.get("gold_score"), bool):
        return False
    try:
        score = float(row.get("gold_score"))
    except (TypeError, ValueError):
        return False
    return math.isfinite(score)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit(Path(args.answers)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
