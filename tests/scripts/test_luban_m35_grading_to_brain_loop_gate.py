import json
import subprocess

from scripts.run_luban_m35_grading_to_brain_loop_gate import build_m35_loop_trace


def test_m35_hermetic_loop_trace_cannot_claim_convergence():
    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_001",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P1", "status": "hit", "mistake_code": ""},
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        }
    )

    assert trace["artifact_version"] == "m35_case_scoring_20260609"
    assert trace["learning_evidence"]["point_count"] == 2
    assert trace["learner_memory_event"]["event_type"] == "m35_point_grading_evidence"
    assert trace["weakness_projection"]["mistake_codes"] == ["E02"]
    assert trace["next_action"]["action_type"] == "targeted_retest"
    assert trace["retest_condition"]["required"] is True
    assert trace["canonical_truth_written"] is False
    assert trace["mode"] == "hermetic_trace"
    assert trace["convergence_claim_allowed"] is False


def test_m35_live_readback_loop_trace_can_claim_convergence_when_all_readbacks_exist():
    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_002",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        },
        mode="live_readback",
        live_readback={
            "learner_memory_event_id": "evt_m35_001",
            "weakness_projection_id": "weak_m35_001",
            "next_action_id": "nba_m35_001",
            "retest_condition_id": "retest_m35_001",
        },
    )

    assert trace["mode"] == "live_readback"
    assert trace["convergence_claim_allowed"] is True
    assert trace["required_readbacks_present"] is True
    assert trace["canonical_truth_written"] is False


def test_m35_live_readback_without_all_ids_cannot_claim_convergence():
    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_003",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        },
        mode="live_readback",
        live_readback={
            "learner_memory_event_id": "evt_m35_001",
            "weakness_projection_id": "weak_m35_001",
        },
    )

    assert trace["mode"] == "live_readback"
    assert trace["required_readbacks_present"] is False
    assert trace["convergence_claim_allowed"] is False


def test_cli_live_readback_without_external_readback_file_cannot_claim_convergence(tmp_path):
    out = tmp_path / "live_readback.json"

    subprocess.run(
        [
            "python",
            "scripts/run_luban_m35_grading_to_brain_loop_gate.py",
            "--fixture",
            "tests/fixtures/luban_m35_case_scoring",
            "--mode",
            "live_readback",
            "--output",
            str(out),
        ],
        check=True,
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "live_readback"
    assert payload["convergence_claim_allowed"] is False
    assert payload["trace"]["required_readbacks_present"] is False
