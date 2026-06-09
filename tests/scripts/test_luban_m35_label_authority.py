import json
import subprocess
from pathlib import Path


SCRIPT = "scripts/audit_luban_m35_label_authority.py"
_DIRECTIONALITY_BY_AUTHORITY = {
    "teacher_validated": "human_validated",
    "po_directional_single_reviewer": "po_directional",
    "ai_council_directional": "ai_council_directional",
    "ai_governed_gold": "ai_governed_gold",
    "generated_self_label": "generated_self_label",
}


def _write_answers(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _run_audit(tmp_path: Path, rows: list[dict]) -> dict:
    fixture = tmp_path / "student_answers.jsonl"
    _write_answers(fixture, rows)
    out = tmp_path / "label_audit.json"

    subprocess.run(
        ["python", SCRIPT, "--answers", str(fixture), "--output", str(out)],
        check=True,
    )

    return json.loads(out.read_text(encoding="utf-8"))


def _row(
    label_authority: str = "teacher_validated",
    sample_bucket: str = "hit",
    index: int = 0,
) -> dict:
    row = {
        "answer_id": f"A-{index}-{label_authority}-{sample_bucket}",
        "question_id": f"Q{index % 20:02d}-NA",
        "label_authority": label_authority,
        "label_scope": "point_and_score",
        "directionality_flag": _DIRECTIONALITY_BY_AUTHORITY[label_authority],
        "gold_score": 1.0,
        "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
        "point_label_provenance": [{"point_id": "P1", "authority": label_authority}],
        "sample_bucket": sample_bucket,
    }
    if label_authority == "ai_governed_gold":
        row["ai_governed_gold"] = _ai_governed_gold_protocol()
    return row


def _ai_governed_gold_protocol(**overrides) -> dict:
    protocol = {
        "protocol_version": "m35_ai_governed_gold.v1",
        "blind_model_votes": [
            {"model_id": "gpt-5.5", "independent": True, "verdict": "accept"},
            {"model_id": "claude-opus-4.8", "independent": True, "verdict": "accept"},
            {"model_id": "qwen-3.7-plus", "independent": True, "verdict": "accept"},
        ],
        "adversarial_review": {
            "model_id": "deepseek-v4-pro",
            "role": "adversarial_prosecutor",
            "unresolved_objection_count": 0,
        },
        "source_anchor": {
            "source_ref_count": 2,
            "field_level_citations": True,
        },
        "mutation_test": {
            "passed": True,
            "case_count": 8,
        },
        "reproducibility_hash": "sha256:test",
        "deterministic_gate": {
            "passed": True,
        },
    }
    protocol.update(overrides)
    return protocol


def _valid_pack(label_authority: str = "teacher_validated") -> list[dict]:
    buckets = (
        ["hit"] * 44
        + ["partial"] * 10
        + ["miss"] * 10
        + ["wrong_content"] * 10
        + ["near_synonym_not_exact"] * 5
        + ["list_incomplete"] * 5
        + ["calculation"] * 5
        + ["stem_fact"] * 5
        + ["external_source_required"] * 3
        + ["off_path"] * 3
    )
    return [_row(label_authority, buckets[index % len(buckets)], index) for index in range(100)]


def test_generated_self_label_is_shape_only_without_quality_claim(tmp_path):
    payload = _run_audit(tmp_path, _valid_pack("generated_self_label"))

    assert payload["answer_count"] == 100
    assert payload["question_count"] == 20
    assert payload["label_authority_counts"] == {"generated_self_label": 100}
    assert payload["missing_contract_answer_ids"] == []
    assert payload["verdict_ceiling"] == "SHAPE_ONLY"
    assert payload["quality_claim_allowed"] is False


def test_missing_label_contract_blocks_quality_claims(tmp_path):
    payload = _run_audit(
        tmp_path,
        [
            {
                "answer_id": "missing-authority",
                "question_id": "Q1-NA",
                "label_scope": "point_and_score",
                "directionality_flag": "human_validated",
                "gold_score": 1.0,
                "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
                "point_label_provenance": [
                    {"point_id": "P1", "authority": "teacher_validated"}
                ],
                "sample_bucket": "hit",
            },
            {
                "answer_id": "missing-points",
                "question_id": "Q1-NA",
                "label_authority": "teacher_validated",
                "label_scope": "point_and_score",
                "directionality_flag": "human_validated",
                "gold_score": 1.0,
                "point_label_provenance": [
                    {"point_id": "P1", "authority": "teacher_validated"}
                ],
                "sample_bucket": "partial",
            },
            {
                "answer_id": "missing-bucket",
                "question_id": "Q1-NA",
                "label_authority": "teacher_validated",
                "label_scope": "point_and_score",
                "directionality_flag": "human_validated",
                "gold_score": 1.0,
                "gold_point_matches": [{"point_id": "P1", "status": "miss"}],
                "point_label_provenance": [
                    {"point_id": "P1", "authority": "teacher_validated"}
                ],
            },
        ],
    )

    assert payload["answer_count"] == 3
    assert payload["label_authority_counts"] == {"missing": 1, "teacher_validated": 2}
    assert payload["sample_bucket_counts"] == {"hit": 1, "partial": 1, "missing": 1}
    assert payload["missing_contract_answer_ids"] == [
        "missing-authority",
        "missing-points",
        "missing-bucket",
    ]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_teacher_validated_allows_poc_go_ceiling(tmp_path):
    payload = _run_audit(tmp_path, _valid_pack("teacher_validated"))

    assert payload["verdict_ceiling"] == "POC_GO_ALLOWED"
    assert payload["quality_claim_allowed"] is True


def test_po_directional_single_reviewer_allows_weak_go_ceiling(tmp_path):
    payload = _run_audit(tmp_path, _valid_pack("po_directional_single_reviewer"))

    assert payload["verdict_ceiling"] == "WEAK_GO_MAX"
    assert payload["quality_claim_allowed"] is True
    assert payload["poc_go_allowed"] is False
    assert payload["weak_go_allowed"] is True
    assert payload["spot_check_required"] is True


def test_ai_council_directional_is_directional_shadow_without_quality_claim(tmp_path):
    payload = _run_audit(tmp_path, _valid_pack("ai_council_directional"))

    assert payload["verdict_ceiling"] == "DIRECTIONAL_SHADOW"
    assert payload["quality_claim_allowed"] is False


def test_ai_governed_gold_can_replace_human_label_authority_for_poc_ceiling(tmp_path):
    payload = _run_audit(tmp_path, _valid_pack("ai_governed_gold"))

    assert payload["label_authority_counts"] == {"ai_governed_gold": 100}
    assert payload["verdict_ceiling"] == "POC_GO_ALLOWED"
    assert payload["quality_claim_allowed"] is True
    assert payload["poc_go_allowed"] is True
    assert payload["ai_governed_gold_allowed"] is True


def test_ai_governed_gold_unresolved_deepseek_objection_blocks_quality_claim(tmp_path):
    rows = _valid_pack("ai_governed_gold")
    rows[0]["ai_governed_gold"] = _ai_governed_gold_protocol(
        adversarial_review={
            "model_id": "deepseek-v4-pro",
            "role": "adversarial_prosecutor",
            "unresolved_objection_count": 1,
        }
    )

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_missing_scope_directionality_or_point_provenance_blocks_quality_claims(tmp_path):
    payload = _run_audit(
        tmp_path,
        [
            {
                "answer_id": "missing-scope",
                "question_id": "Q1-NA",
                "label_authority": "teacher_validated",
                "directionality_flag": "human_validated",
                "gold_score": 1.0,
                "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
                "point_label_provenance": [
                    {"point_id": "P1", "authority": "teacher_validated"}
                ],
                "sample_bucket": "hit",
            },
            {
                "answer_id": "missing-directionality",
                "question_id": "Q1-NA",
                "label_authority": "teacher_validated",
                "label_scope": "point_and_score",
                "gold_score": 1.0,
                "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
                "point_label_provenance": [
                    {"point_id": "P1", "authority": "teacher_validated"}
                ],
                "sample_bucket": "hit",
            },
            {
                "answer_id": "missing-point-provenance",
                "question_id": "Q1-NA",
                "label_authority": "teacher_validated",
                "label_scope": "point_and_score",
                "directionality_flag": "human_validated",
                "gold_score": 1.0,
                "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
                "sample_bucket": "hit",
            },
        ],
    )

    assert payload["missing_contract_answer_ids"] == [
        "missing-scope",
        "missing-directionality",
        "missing-point-provenance",
    ]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_mixed_generated_labels_keep_entire_pack_shape_only(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["label_authority"] = "generated_self_label"
    rows[0]["directionality_flag"] = "generated_self_label"
    rows[0]["point_label_provenance"] = [
        {"point_id": "P1", "authority": "generated_self_label"}
    ]

    payload = _run_audit(tmp_path, rows)

    assert payload["label_authority_counts"] == {
        "generated_self_label": 1,
        "teacher_validated": 99,
    }
    assert payload["verdict_ceiling"] == "SHAPE_ONLY"
    assert payload["quality_claim_allowed"] is False


def test_less_than_twenty_questions_or_hundred_answers_blocks_quality_claim(tmp_path):
    payload = _run_audit(tmp_path, [_row("teacher_validated", "hit", index) for index in range(99)])

    assert payload["answer_count"] == 99
    assert payload["question_count"] == 20
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_VOLUME"
    assert payload["quality_claim_allowed"] is False


def test_missing_bucket_coverage_blocks_quality_claim(tmp_path):
    rows = [_row("teacher_validated", "hit", index) for index in range(100)]

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_bucket_minimums"]["partial"] == 10
    assert payload["verdict_ceiling"] == "NO_GO_BUCKET_COVERAGE"
    assert payload["quality_claim_allowed"] is False


def test_missing_gold_score_or_point_provenance_coverage_blocks_quality_claim(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0].pop("gold_score")
    rows[1]["point_label_provenance"] = [{"point_id": "different", "authority": "teacher_validated"}]

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"], rows[1]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_point_provenance_authority_must_match_row_label_authority(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["point_label_provenance"] = [
        {"point_id": "P1", "authority": "generated_self_label"}
    ]

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_directionality_must_match_label_authority_tier(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["directionality_flag"] = "generated_self_label"

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_gold_score_must_be_numeric(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["gold_score"] = None
    rows[1]["gold_score"] = "not-a-number"

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [
        rows[0]["answer_id"],
        rows[1]["answer_id"],
    ]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_unknown_label_authority_is_contract_failure(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["label_authority"] = "spreadsheet_unknown"
    rows[0]["point_label_provenance"] = [
        {"point_id": "P1", "authority": "spreadsheet_unknown"}
    ]

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_ai_council_mixed_with_po_directional_keeps_directional_shadow(tmp_path):
    rows = _valid_pack("po_directional_single_reviewer")
    rows[0]["label_authority"] = "ai_council_directional"
    rows[0]["directionality_flag"] = "ai_council_directional"
    rows[0]["point_label_provenance"] = [
        {"point_id": "P1", "authority": "ai_council_directional"}
    ]

    payload = _run_audit(tmp_path, rows)

    assert payload["verdict_ceiling"] == "DIRECTIONAL_SHADOW"
    assert payload["quality_claim_allowed"] is False
    assert payload["weak_go_allowed"] is False


def test_hundred_answers_with_only_nineteen_questions_blocks_quality_claim(tmp_path):
    rows = _valid_pack("teacher_validated")
    for index, row in enumerate(rows):
        row["question_id"] = f"Q{index % 19:02d}-NA"

    payload = _run_audit(tmp_path, rows)

    assert payload["answer_count"] == 100
    assert payload["question_count"] == 19
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_VOLUME"
    assert payload["quality_claim_allowed"] is False


def test_duplicate_or_conflicting_point_provenance_blocks_quality_claim(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["point_label_provenance"] = [
        {"point_id": "P1", "authority": "teacher_validated"},
        {"point_id": "P1", "authority": "generated_self_label"},
    ]

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_duplicate_point_provenance_blocks_even_when_last_authority_matches(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["point_label_provenance"] = [
        {"point_id": "P1", "authority": "generated_self_label"},
        {"point_id": "P1", "authority": "teacher_validated"},
    ]

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_label_scope_must_support_point_and_score_labels(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["label_scope"] = "score_only"

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [rows[0]["answer_id"]]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_gold_score_must_be_finite(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["gold_score"] = "NaN"
    rows[1]["gold_score"] = "Infinity"

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [
        rows[0]["answer_id"],
        rows[1]["answer_id"],
    ]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False


def test_gold_score_must_not_be_boolean(tmp_path):
    rows = _valid_pack("teacher_validated")
    rows[0]["gold_score"] = True
    rows[1]["gold_score"] = False

    payload = _run_audit(tmp_path, rows)

    assert payload["missing_contract_answer_ids"] == [
        rows[0]["answer_id"],
        rows[1]["answer_id"],
    ]
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_CONTRACT"
    assert payload["quality_claim_allowed"] is False
