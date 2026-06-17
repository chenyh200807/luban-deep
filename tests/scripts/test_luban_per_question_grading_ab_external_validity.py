import json
from pathlib import Path

from scripts import run_luban_per_question_grading_ab as ab
from scripts.run_luban_per_question_grading_object_compile import (
    DEFAULT_BOOK_DIR,
    DEFAULT_EXAM_ROOT,
    _load_textbook_chunks,
    compile_selected,
)
from deeptutor.services.construction_grading.per_question_grading_object import build_grading_contract


FIXTURE = Path(
    "deeptutor/services/construction_grading/fixtures/"
    "per_question_grading_external_validity_fixtures.json"
)


def _contracts_by_qid():
    chunks = _load_textbook_chunks(DEFAULT_BOOK_DIR)
    return {
        obj["question_id"]: build_grading_contract(obj)
        for obj in compile_selected(exam_root=DEFAULT_EXAM_ROOT, textbook_chunks=chunks)
    }


def test_external_validity_fixture_is_12_to_20_labeled_student_answers_without_exact_slice_leakage():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixtures = data["fixtures"]
    contracts = _contracts_by_qid()
    answers = [(qid, answer) for qid, group in fixtures.items() for answer in group]

    assert 12 <= len(answers) <= 20
    assert data["review_only"] is True
    assert data["source_corpus"].endswith("近三年案例题_按学生答卷排版.docx")

    for qid, answer in answers:
        contract = contracts[qid]
        ab._validate_fixture(answer, contract)
        student_answer = answer["student_answer"]
        assert answer["student_answer_source_id"]
        assert answer["student_answer_source_id"] in student_answer
        for scoring_point in contract["scoring_points"]:
            official_slice = (scoring_point.get("official_slice") or "").strip()
            if official_slice:
                assert official_slice not in student_answer


def test_external_validity_fixture_keeps_q2024_skip_subquestion5_counterexample():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    q2024 = data["fixtures"]["Q2024-1A432000-P0015-01"]
    labels = {answer["label"]: answer for answer in q2024}

    trap = labels["Q2024-03__S05_skip_subq5"]
    assert trap["answer_type"] == "over_credit_trap"
    q5_point_ids = {
        "sp_5139a59d787cce84d925",
        "sp_6b0a2974cbf485b092c0",
        "sp_bc5f8534f08fa5e6083b",
        "sp_70ca1de6f9008d5c356e",
        "sp_266dd732cdaf03b142cd",
        "sp_58053d9473c5a641bead",
    }
    assert q5_point_ids <= set(trap["missing_point_ids"])
    assert set(trap["covered_point_ids"]).isdisjoint(q5_point_ids)


def test_summary_reports_trial_mean_std_parse_error_and_cost_metrics():
    rows = []
    for trial, scores in enumerate(([0.75, 1.0], [0.8, 1.0], [0.7, 1.0])):
        for arm, score in zip((ab.ARM_B, ab.ARM_RAG_REF), scores):
            rows.append(
                {
                    "trial": trial,
                    "question_id": "Q",
                    "answer_label": "trap",
                    "answer_type": "over_credit_trap",
                    "arm": arm,
                    "score_pct": score,
                    "true_coverage": 0.75,
                    "score_coverage_gap": round(score - 0.75, 4),
                    "ground_truth_over_credit": score - 0.75 > 0.1,
                    "calibration_abs_error": abs(score - 0.75),
                    "false_hit_rate": 0.0 if arm == ab.ARM_B else None,
                    "verdict_self_inconsistency": False,
                    "oracle": False,
                    "parse_error": False,
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "latency_ms": 1000,
                    "ttft_ms": 200,
                }
            )

    summary = ab._summarize(rows, gap_margin=0.1, trials=3)

    assert summary["schema"] == "luban_per_question_grading_ab.v3"
    assert summary["trials"] == 3
    assert summary["by_arm"][ab.ARM_B]["calibration_mae"] == {"mean": 0.0333, "std": 0.0289}
    assert summary["by_arm"][ab.ARM_RAG_REF]["over_credit_rate"] == {"mean": 1.0, "std": 0.0}
    assert summary["by_arm"][ab.ARM_B]["parse_error_rate"] == 0.0
    assert summary["by_arm"][ab.ARM_B]["cost"]["total_tokens"]["mean"] == 120.0
