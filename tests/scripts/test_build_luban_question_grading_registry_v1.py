"""Tests for the v1 registry compiler skeleton — it must FAIL CLOSED (data_blocked),
never emit a same-coverage registry pretending to be a full bank."""
from __future__ import annotations

import json

from scripts import build_luban_question_grading_registry_v1 as v1


def test_no_new_source_is_data_blocked():
    result = v1.compile_registry_v1()
    assert result["status"] == v1.DATA_BLOCKED
    assert result["new_question_count"] == 0
    assert result["fabricated"] is False
    assert result["v0_coverage_unchanged"] is True


def test_golden_fixture_is_not_counted_as_new():
    # the golden 20 are already v0; pointing the compiler at them adds 0 NEW questions.
    golden = "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
    result = v1.compile_registry_v1([golden])
    assert result["status"] == v1.DATA_BLOCKED
    assert result["new_question_count"] == 0


def test_mcq_bank_is_not_a_gradeable_case_source():
    # exam_quality_bank is MCQ -> 0 new gradeable case questions.
    mcq = "deeptutor/services/benchmark/fixtures/exam_quality_bank.json"
    result = v1.compile_registry_v1([mcq])
    assert result["status"] == v1.DATA_BLOCKED


def test_missing_source_does_not_crash_and_stays_blocked():
    result = v1.compile_registry_v1(["/no/such/source.json"])
    assert result["status"] == v1.DATA_BLOCKED
    assert result["new_question_count"] == 0


def test_main_writes_status_and_no_fake_registry(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["build_v1", "--out-dir", str(tmp_path)])
    v1.main()
    status = json.loads((tmp_path / "registry_v1_status.json").read_text("utf-8"))
    assert status["status"] == v1.DATA_BLOCKED
    # crucially: it must NOT have emitted a registry artifacts file (no fake coverage).
    assert not (tmp_path / "question_grading_artifacts.jsonl").exists()
    assert not (tmp_path / "question_grading_registry.json").exists()


def test_synthetic_new_case_source_would_compile(tmp_path):
    # a genuinely NEW gradeable case question (not in golden) flips status to compiled.
    src = tmp_path / "new_cases.json"
    src.write_text(json.dumps({"cases": [{
        "case_id": "Q-NEW-EXPANSION-001", "question_type": "case",
        "gold_scoring_points": [{"point_id": "P1", "max_score": 2}],
    }]}, ensure_ascii=False), encoding="utf-8")
    result = v1.compile_registry_v1([str(src)])
    assert result["status"] == v1.COMPILED
    assert result["new_question_count"] == 1
