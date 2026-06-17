from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from scripts import audit_luban_m35_label_authority as label_audit


ROOT = Path("tests/fixtures/luban_m35_case_scoring")
MANIFEST = ROOT / "manifest.json"
ANSWERS = ROOT / "student_answers.jsonl"
REQUIRED_ANSWER_FIELDS = {
    "answer_id",
    "question_id",
    "student_answer",
    "gold_score",
    "gold_point_matches",
    "label_authority",
    "label_scope",
    "directionality_flag",
    "point_label_provenance",
    "sample_bucket",
}
NON_CANONICAL_CLAIM_VALUES = {
    "production",
    "published",
    "canonical",
    "canonical_truth",
    "production_truth",
    "published_truth",
    "release_truth",
    "POC_GO_ALLOWED",
}
ALLOWED_VERDICT_CEILINGS_AT_OR_BELOW_WEAK_GO = {
    "WEAK_GO_OR_BELOW",
    "WEAK_GO_MAX",
    "DIRECTIONAL_SHADOW",
    "SHAPE_ONLY",
    "NO-GO_OR_SHAPE_ONLY",
    "NO_GO_LABEL_CONTRACT",
    "NO_GO_LABEL_VOLUME",
    "NO_GO_BUCKET_COVERAGE",
}


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _load_answers() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in ANSWERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_m35_manifest_has_twenty_questions_and_hundred_answers() -> None:
    manifest = _load_manifest()
    answers = _load_answers()

    question_ids = [str(q.get("question_id") or "") for q in manifest["questions"]]
    assert len(question_ids) == 20
    assert len(set(question_ids)) == 20
    assert len(answers) >= 100

    for question in manifest["questions"]:
        assert question.get("question_id")
        assert question.get("stem")
        assert "total_score" in question
        assert isinstance(question.get("source_refs"), list)
        assert question.get("expected_artifact_lane")

    manifest_question_ids = set(question_ids)
    assert all(str(answer.get("question_id") or "") in manifest_question_ids for answer in answers)


def test_m35_answers_follow_task_0b_label_contract() -> None:
    answers = _load_answers()

    for answer in answers:
        assert REQUIRED_ANSWER_FIELDS <= set(answer), answer.get("answer_id")
        assert answer["label_authority"] in label_audit.LEVELS
        assert answer["label_scope"] in label_audit.VALID_LABEL_SCOPE
        assert answer["directionality_flag"] in label_audit.VALID_DIRECTIONALITY
        assert (
            answer["directionality_flag"]
            == label_audit.EXPECTED_DIRECTIONALITY_BY_AUTHORITY[answer["label_authority"]]
        )
        assert answer["sample_bucket"] in label_audit.BUCKET_MINIMUMS
        assert isinstance(answer["student_answer"], str) and answer["student_answer"].strip()
        assert _is_number(answer["gold_score"])
        assert isinstance(answer["gold_point_matches"], list) and answer["gold_point_matches"]
        assert isinstance(answer["point_label_provenance"], list)
        assert _point_provenance_covers_gold_matches(answer)
        assert _point_provenance_authority_matches(answer)


def test_m35_bucket_minimums_or_manifest_declares_label_gap() -> None:
    manifest = _load_manifest()
    answers = _load_answers()

    counts = Counter(str(answer.get("sample_bucket") or "") for answer in answers)
    missing = {
        bucket: required - counts.get(bucket, 0)
        for bucket, required in label_audit.BUCKET_MINIMUMS.items()
        if counts.get(bucket, 0) < required
    }
    if missing:
        assert manifest.get("known_label_gap") is True
        assert manifest.get("verdict_ceiling") in ALLOWED_VERDICT_CEILINGS_AT_OR_BELOW_WEAK_GO
        assert manifest.get("verdict_ceiling") != "POC_GO_ALLOWED"


def test_m35_manifest_does_not_claim_production_or_canonical_truth() -> None:
    manifest = _load_manifest()

    assert manifest.get("known_label_gap") is True
    assert manifest.get("verdict_ceiling") != "POC_GO_ALLOWED"
    assert not manifest.get("production")
    assert not manifest.get("published")
    assert not manifest.get("canonical_truth")
    assert not manifest.get("production_truth")
    assert not manifest.get("published_truth")
    assert not manifest.get("release_truth")
    assert _contains_forbidden_claim(manifest) is False


def test_m35_manifest_label_ceiling_matches_task_0b_audit() -> None:
    manifest = _load_manifest()
    audit = label_audit.audit(ANSWERS)

    assert manifest["answer_label_authority"] == "generated_self_label"
    assert manifest["verdict_ceiling"] == audit["verdict_ceiling"]
    assert manifest["quality_claim_allowed"] == audit["quality_claim_allowed"]
    assert manifest["poc_go_allowed"] == audit["poc_go_allowed"]
    assert audit["verdict_ceiling"] == "SHAPE_ONLY"
    assert audit["quality_claim_allowed"] is False


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _point_provenance_covers_gold_matches(answer: dict[str, Any]) -> bool:
    gold_point_ids = {
        str(point.get("point_id") or "")
        for point in answer.get("gold_point_matches", [])
        if point.get("point_id")
    }
    provenance_point_ids = {
        str(point.get("point_id") or "")
        for point in answer.get("point_label_provenance", [])
        if point.get("point_id")
    }
    return bool(gold_point_ids) and gold_point_ids <= provenance_point_ids


def _point_provenance_authority_matches(answer: dict[str, Any]) -> bool:
    label_authority = str(answer.get("label_authority") or "")
    gold_point_ids = {
        str(point.get("point_id") or "")
        for point in answer.get("gold_point_matches", [])
        if point.get("point_id")
    }
    provenance_by_point = {
        str(point.get("point_id") or ""): str(point.get("authority") or "")
        for point in answer.get("point_label_provenance", [])
        if point.get("point_id")
    }
    return all(provenance_by_point.get(point_id) == label_authority for point_id in gold_point_ids)


def _contains_forbidden_claim(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key) in NON_CANONICAL_CLAIM_VALUES
            or _contains_forbidden_claim(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_claim(child) for child in value)
    if isinstance(value, str):
        return value in NON_CANONICAL_CLAIM_VALUES
    return False
