"""R5 MCQ official-key quality line: deterministic grading, no LLM, no network.

The runner re-scores every fixture answer against the official MCQ answer key
(single choice = exact match; multiple choice = official yijian rule: any wrong
selection scores zero, underselection earns proportional credit per selected
correct option) and reports agreement with the fixture ``gold_score`` without
silently trusting either side.
"""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_luban_m35_mcq_official_key_quality.py"

FORBIDDEN_NETWORK_MODULES = {
    "aiohttp",
    "anthropic",
    "http",
    "httpx",
    "openai",
    "requests",
    "socket",
    "urllib",
    "urllib3",
    "websocket",
    "websockets",
}


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_luban_m35_mcq_official_key_quality", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _points(*pairs):
    return [
        {"point_id": f"OPT_{key}", "criterion": f"选择正确选项 {key}", "max_score": score}
        for key, score in pairs
    ]


def _row(
    *,
    answer_id,
    question_id,
    student_answer,
    gold_score,
    correct_answer,
    question_type="multiple_choice",
    scoring_points,
):
    return {
        "answer_id": answer_id,
        "question_id": question_id,
        "student_id": "synthetic",
        "student_answer": student_answer,
        "gold_score": gold_score,
        "scoring_points": scoring_points,
        "scoring_protocol": {
            "question_type": question_type,
            "correct_answer": correct_answer,
            "overselect_policy": "zero_score_if_any_wrong_option_selected",
            "missing_correct_option_policy": "partial_credit_without_wrong_options",
        },
        "label_authority": "generated_from_official_mcq_key",
    }


def _write_fixture(tmp_path, rows):
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    question_ids = sorted({row["question_id"] for row in rows})
    manifest = {
        "schema_version": "luban_m35_fastapi_mcq_fixture.v1",
        "label_authority": "generated_from_official_mcq_key",
        "actual_question_count": len(question_ids),
        "actual_answer_count": len(rows),
        "questions": [{"question_id": qid} for qid in question_ids],
    }
    (fixture_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (fixture_dir / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return fixture_dir


def _synthetic_rows():
    multi_points = _points(("B", 1.0), ("E", 1.0))
    single_points = _points(("C", 1.0))
    return [
        _row(
            answer_id="Q1__correct",
            question_id="Q1",
            student_answer="BE",
            gold_score=2.0,
            correct_answer="BE",
            scoring_points=multi_points,
        ),
        _row(
            answer_id="Q1__missing_one",
            question_id="Q1",
            student_answer="B",
            gold_score=1.0,
            correct_answer="BE",
            scoring_points=multi_points,
        ),
        _row(
            answer_id="Q1__overselect",
            question_id="Q1",
            student_answer="ABE",
            gold_score=0.0,
            correct_answer="BE",
            scoring_points=multi_points,
        ),
        _row(
            answer_id="Q1__blank",
            question_id="Q1",
            student_answer="",
            gold_score=0.0,
            correct_answer="BE",
            scoring_points=multi_points,
        ),
        _row(
            answer_id="Q2__correct",
            question_id="Q2",
            student_answer="C",
            gold_score=1.0,
            correct_answer="C",
            question_type="single_choice",
            scoring_points=single_points,
        ),
        _row(
            answer_id="Q2__wrong",
            question_id="Q2",
            student_answer="A",
            gold_score=0.0,
            correct_answer="C",
            question_type="single_choice",
            scoring_points=single_points,
        ),
        # Fixture gold disagrees with the official key on purpose: the official
        # key recomputes 1.0 but the fixture claims 0.5.
        _row(
            answer_id="Q2__gold_mismatch",
            question_id="Q2",
            student_answer="C",
            gold_score=0.5,
            correct_answer="C",
            question_type="single_choice",
            scoring_points=single_points,
        ),
    ]


def _run_runner(fixture_dir, output_path):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture",
            str(fixture_dir),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_report_shape_metrics_and_safety(tmp_path):
    fixture_dir = _write_fixture(tmp_path, _synthetic_rows())
    output = tmp_path / "report.json"
    proc = _run_runner(fixture_dir, output)
    assert proc.returncode == 0, proc.stderr

    raw = output.read_text(encoding="utf-8")
    assert "verdict_ceiling" not in raw
    report = json.loads(raw)

    assert report["schema_version"] == "luban_m35_mcq_official_key_quality.v1"
    assert report["quality_claim_allowed"] is True
    assert report["authority_basis"] == "official_mcq_answer_key"
    assert report["rule_source"] == "fixture_scoring_protocol"

    metrics = report["metrics"]
    assert metrics["answer_count"] == 7
    assert metrics["question_count"] == 2
    assert metrics["accuracy"] == pytest.approx(6 / 7)
    assert metrics["score_mae"] == pytest.approx(0.5 / 7)
    assert metrics["per_question_accuracy"]["Q1"] == pytest.approx(1.0)
    assert metrics["per_question_accuracy"]["Q2"] == pytest.approx(2 / 3)

    assert report["label_authority_counts"] == {
        "generated_from_official_mcq_key": 7
    }

    safety = report["safety"]
    assert safety == {
        "production_write_count": 0,
        "canonical_truth_written": False,
        "rag_chunk_as_answer_key": 0,
        "candidate_used_as_release_truth": 0,
        "client_status_promoted_to_release_truth": 0,
        "shadow_changed_legacy_result": 0,
        "db_write_count": 0,
        "remote_write_count": 0,
        "provider_call_count": 0,
    }


def test_gold_mismatch_is_reported_not_silently_resolved(tmp_path):
    fixture_dir = _write_fixture(tmp_path, _synthetic_rows())
    output = tmp_path / "report.json"
    proc = _run_runner(fixture_dir, output)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(output.read_text(encoding="utf-8"))
    mismatch = report["gold_score_mismatch"]
    assert mismatch["mismatch_count"] == 1
    assert mismatch["mismatched_answer_ids"] == ["Q2__gold_mismatch"]
    (detail,) = mismatch["details"]
    assert detail["answer_id"] == "Q2__gold_mismatch"
    # Both sides reported verbatim — the runner never picks a winner.
    assert detail["official_key_score"] == pytest.approx(1.0)
    assert detail["fixture_gold_score"] == pytest.approx(0.5)


def test_official_mcq_rule_scoring():
    module = _load_module()
    multi_points = _points(("B", 1.0), ("E", 1.0))
    three_points = _points(("A", 2.0 / 3), ("B", 2.0 / 3), ("C", 2.0 / 3))
    single_points = _points(("C", 2.0))

    def score(student, correct, points, qtype="multiple_choice"):
        row = _row(
            answer_id="x",
            question_id="q",
            student_answer=student,
            gold_score=0.0,
            correct_answer=correct,
            question_type=qtype,
            scoring_points=points,
        )
        return module.score_official_mcq(row)

    # Single choice: exact match only.
    assert score("C", "C", single_points, "single_choice") == pytest.approx(2.0)
    assert score("A", "C", single_points, "single_choice") == pytest.approx(0.0)
    assert score("AC", "C", single_points, "single_choice") == pytest.approx(0.0)

    # Multiple choice: full credit on exact set.
    assert score("BE", "BE", multi_points) == pytest.approx(2.0)
    assert score("EB", "BE", multi_points) == pytest.approx(2.0)
    # Underselection: proportional credit per selected correct option.
    assert score("B", "BE", multi_points) == pytest.approx(1.0)
    assert score("AB", "ABC", three_points) == pytest.approx(4.0 / 3)
    # Any wrong selection scores zero, even alongside correct ones.
    assert score("ABE", "BE", multi_points) == pytest.approx(0.0)
    assert score("D", "BE", multi_points) == pytest.approx(0.0)
    # Blank scores zero.
    assert score("", "BE", multi_points) == pytest.approx(0.0)


def test_runner_has_no_network_or_llm_imports():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & FORBIDDEN_NETWORK_MODULES, imported
