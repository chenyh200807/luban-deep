"""Tests for M6 Registry v1 Candidate Compile Dry-Run.

M6 can package M5's deterministic authority adjudication into a sealed candidate
dry-run bundle. It must not emit a formal Registry v1, connect production
runtime, or let weak / rewrite points become auto-certifiable.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from scripts import build_luban_registry_v1_candidate_dry_run as m6


REPO = Path(__file__).resolve().parents[2]
M5_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_authority_adjudication_m5_20260604"
V0_DIR = REPO / "artifacts/luban_grading_artifacts/registry_v0_20260604"

EXPECTED_FILES = {
    "m5_input_audit.json",
    "candidate_registry_schema.md",
    "question_grading_registry_v1_candidate.json",
    "question_grading_artifacts_v1_candidate.jsonl",
    "candidate_publish_report.json",
    "v0_vs_v1_candidate_diff.json",
    "runtime_gate_dry_run_results.json",
    "blocked_from_auto_certification.json",
    "po_review_carryover_queue.json",
    "m5r_overlay_audit.json",
    "FINDING_registry_v1_candidate_dry_run_m6_20260604.md",
}

FORBIDDEN_FORMAL_FILES = {
    "registry_v1.json",
    "question_grading_registry_v1.json",
    "question_grading_artifacts_v1.jsonl",
    "question_grading_registry.json",
    "question_grading_artifacts.jsonl",
}


def _read_json(path: Path):
    return json.loads(path.read_text("utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _dir_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(file.relative_to(path)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


@pytest.fixture()
def built_out(tmp_path: Path) -> Path:
    m6.build_registry_v1_candidate_dry_run(out_dir=tmp_path, m5_dir=M5_DIR, v0_dir=V0_DIR)
    return tmp_path


def test_candidate_package_emits_required_files_only(built_out: Path):
    names = {p.name for p in built_out.iterdir() if p.is_file()}

    assert EXPECTED_FILES <= names
    assert not (FORBIDDEN_FORMAL_FILES & names)
    assert not (built_out / "registry_v1").exists()

    report = _read_json(built_out / "candidate_publish_report.json")
    assert report["package_status"] == "candidate_dry_run"
    assert report["simulation_only"] is True
    assert report["formal_registry_emitted"] is False
    assert report["production_runtime_connected"] is False
    assert report["case_grading_skill_kernel_touched"] is False
    assert report["rag_used_as_authority"] is False
    assert report["database_touched"] is False


def test_m5_counts_match_exactly_and_candidate_counts_are_sealed(built_out: Path):
    audit = _read_json(built_out / "m5_input_audit.json")
    registry = _read_json(built_out / "question_grading_registry_v1_candidate.json")
    artifacts = _read_jsonl(built_out / "question_grading_artifacts_v1_candidate.jsonl")

    assert audit["input_gate_status"] == "pass"
    assert audit["exact_expected_counts_match"] is True
    assert audit["m5_counts"] == {
        "question_count": 34,
        "point_count": 150,
        "auto_certifiable_point_count": 25,
        "review_required_official_weak_point_count": 112,
        "rewrite_needed_point_count": 13,
        "publish_ready_candidate_question_count": 2,
        "draft_review_candidate_question_count": 5,
        "po_review_required_question_count": 27,
        "blocked_candidate_question_count": 0,
        "llm_jury_covered_point_count": 0,
    }

    assert registry["package_status"] == "candidate_dry_run"
    assert registry["version_id"] == m6.VERSION_ID
    assert registry["summary"]["total_questions"] == 34
    assert registry["summary"]["total_scoring_points"] == 150
    assert registry["summary"]["auto_certifiable_point_count"] == 25
    assert registry["summary"]["question_status_counts"] == {
        "candidate_dry_run": 1,
        "draft_review": 5,
        "po_review_required": 28,
    }

    assert len(artifacts) == 34
    assert sum(len(a["scoring_points"]) for a in artifacts) == 150
    assert sum(
        1
        for artifact in artifacts
        for point in artifact["scoring_points"]
        if point["auto_certifiable"]
    ) == 25
    assert Counter(a["status"] for a in artifacts) == {
        "candidate_dry_run": 1,
        "draft_review": 5,
        "po_review_required": 28,
    }


def test_weak_and_rewrite_points_are_blocked_from_auto_certification(built_out: Path):
    blocked = _read_json(built_out / "blocked_from_auto_certification.json")

    assert blocked["summary"]["blocked_point_count"] == 125
    assert blocked["summary"]["decision_counts"] == {
        "review_required_official_weak": 112,
        "rewrite_needed": 13,
    }
    assert len(blocked["points"]) == 125
    assert all(point["auto_certifiable"] is False for point in blocked["points"])
    assert all(point["runtime_auto_certification_allowed"] is False for point in blocked["points"])
    assert not any(point["decision"] == "auto_certifiable" for point in blocked["points"])


def test_runtime_gate_dry_run_fails_closed_for_candidate_statuses(built_out: Path):
    results = _read_json(built_out / "runtime_gate_dry_run_results.json")

    assert results["mode"] == "dry_run_only"
    assert results["formal_runtime_connected"] is False
    assert results["production_runtime_connected"] is False
    assert results["candidate_registry_loaded_in_memory"] is True
    assert results["summary"]["question_count"] == 34
    assert results["summary"]["artifact_auto_certification_allowed_count"] == 0
    assert results["summary"]["point_auto_certified_after_gate_count"] == 0
    assert results["summary"]["blocked_or_pending_after_gate_count"] == 150
    assert set(results["summary"]["artifact_status_counts"]) == {
        "candidate_dry_run",
        "draft_review",
        "po_review_required",
    }
    assert all(row["gate_auto_certification_allowed"] is False for row in results["questions"])


def test_v0_is_read_only_reference_and_not_overwritten(tmp_path: Path):
    before = _dir_digest(V0_DIR)

    m6.build_registry_v1_candidate_dry_run(out_dir=tmp_path, m5_dir=M5_DIR, v0_dir=V0_DIR)

    assert _dir_digest(V0_DIR) == before
    diff = _read_json(tmp_path / "v0_vs_v1_candidate_diff.json")
    assert diff["v0_read_only_reference"] is True
    assert diff["v0_overwritten"] is False
    assert diff["v0"]["total_questions"] == 20
    assert diff["v1_candidate"]["total_questions"] == 34
    assert diff["v1_candidate"]["total_scoring_points"] == 150
    assert diff["v1_candidate"]["auto_certifiable_point_count"] == 25


def test_po_review_carryover_preserves_point_and_question_granularity(built_out: Path):
    carryover = _read_json(built_out / "po_review_carryover_queue.json")

    # 27 M5 po_review_required + 1 M5R-overlay downgrade (M2-2016-31-02) = 28
    assert carryover["summary"]["po_review_required_question_count"] == 28
    assert carryover["summary"]["non_auto_certifiable_point_count"] == 125
    assert carryover["summary"]["point_decision_counts"] == {
        "review_required_official_weak": 112,
        "rewrite_needed": 13,
    }
    assert len(carryover["questions"]) == 28
    assert len(carryover["points"]) == 125
    # the downgraded question keeps its M5 authority status (publish_ready_candidate) but carries
    # an m5r downgrade reason; the rest are M5 po_review_required.
    assert any(q.get("carryover_reason") == "m5r_jury_not_cleared_downgraded_to_po_review"
               for q in carryover["questions"])


def test_m5r_overlay_only_jury_cleared_question_is_candidate_and_no_source_upgrade(built_out: Path):
    overlay = _read_json(built_out / "m5r_overlay_audit.json")
    assert overlay["m5r_jury_cleared_question_ids"] == ["M2-2015-32-00"]
    assert overlay["candidate_dry_run_after_overlay_question_ids"] == ["M2-2015-32-00"]
    assert overlay["downgraded_to_po_review_question_ids"] == ["M2-2016-31-02"]
    # the LLM jury overlay must NEVER upgrade a weak source to verified
    assert overlay["source_status_upgraded_by_jury"] is False
    # exactly one candidate_dry_run question in the registry, and it is the jury-cleared one
    registry = _read_json(built_out / "question_grading_registry_v1_candidate.json")
    cdr = [q for q, v in registry["questions"].items() if v["status"] == "candidate_dry_run"]
    assert cdr == ["M2-2015-32-00"]


def test_finding_answers_required_m6_questions(built_out: Path):
    content = (built_out / "FINDING_registry_v1_candidate_dry_run_m6_20260604.md").read_text("utf-8")

    for idx in range(1, 12):
        assert f"{idx}." in content
    assert "M5 counts match exactly: YES" in content
    assert "Formal Registry v1 generated: NO" in content
    assert "M7 verdict: WEAK-GO" in content
    assert "NO-GO for formal Registry v1 publish/runtime connection" in content
    assert "M5R jury overlay" in content
    assert "M2-2015-32-00" in content


def test_m5_input_mismatch_blocks_compile_and_emits_only_audit(tmp_path: Path):
    bad_m5 = tmp_path / "bad_m5"
    shutil.copytree(M5_DIR, bad_m5)
    adjudication_path = bad_m5 / "authority_adjudication.json"
    adjudication = _read_json(adjudication_path)
    adjudication["points"] = adjudication["points"][:-1]
    adjudication_path.write_text(json.dumps(adjudication, ensure_ascii=False, indent=2) + "\n", "utf-8")

    out = tmp_path / "out"
    with pytest.raises(m6.RegistryCandidateCompileBlocked):
        m6.build_registry_v1_candidate_dry_run(out_dir=out, m5_dir=bad_m5, v0_dir=V0_DIR)

    audit = _read_json(out / "m5_input_audit.json")
    assert audit["input_gate_status"] == "blocked"
    assert audit["exact_expected_counts_match"] is False
    assert not (out / "question_grading_registry_v1_candidate.json").exists()
    assert not (out / "question_grading_artifacts_v1_candidate.jsonl").exists()
