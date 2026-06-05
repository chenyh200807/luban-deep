"""Tests for the registry v0 build script.

Deterministic: builds the registry in-memory and writes to a tmp dir. No DB, no
provider key, no fabrication.
"""
from __future__ import annotations

import json

from scripts import build_luban_question_grading_registry_v0 as build


def test_build_artifacts_returns_twenty():
    artifacts = build.build_artifacts()
    assert len(artifacts) == 20
    assert all(a.get("question_id") for a in artifacts)


def test_publish_report_is_complete():
    artifacts = build.build_artifacts()
    report = build.build_publish_report(artifacts)
    for key in (
        "total_questions",
        "published_count",
        "draft_count",
        "blocked_count",
        "total_scoring_points",
        "policy_type_counts",
        "source_type_counts",
        "auto_certifiable_point_count",
        "weak_source_point_count",
        "missing_policy_count",
        "missing_source_count",
        "blocked_reasons",
        "top_risks",
    ):
        assert key in report, f"publish_report missing {key}"
    assert report["total_questions"] == 20
    assert (
        report["published_count"]
        + report["draft_count"]
        + report["blocked_count"]
        == 20
    )
    assert report["total_scoring_points"] == 97


def test_report_does_not_fabricate_textbook_source():
    # textbook source_refs must never exceed the count of points with a verified
    # (strong) source -> no fabrication inflates the published count.
    artifacts = build.build_artifacts()
    report = build.build_publish_report(artifacts)
    strong_points = sum(
        1
        for a in artifacts
        for sp in a["scoring_points"]
        if sp.get("source_status") == "ok"
    )
    assert report["source_type_counts"].get("textbook", 0) == strong_points


def test_main_writes_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["build", "--out-dir", str(tmp_path)])
    build.main()
    for name in (
        "question_grading_artifacts.jsonl",
        "question_grading_registry.json",
        "publish_report.json",
        "FINDING_question_grading_registry_v0_20260604.md",
    ):
        assert (tmp_path / name).exists(), f"missing output {name}"

    # jsonl is one artifact per line and round-trips
    lines = (tmp_path / "question_grading_artifacts.jsonl").read_text(
        encoding="utf-8"
    ).strip().splitlines()
    assert len(lines) == 20
    first = json.loads(lines[0])
    assert first["schema_version"] == "question_grading_artifact.v0"

    index = json.loads((tmp_path / "question_grading_registry.json").read_text("utf-8"))
    assert index["summary"]["published"] + index["summary"]["draft"] + index[
        "summary"
    ]["blocked"] == 20


def test_serialized_registry_round_trips_to_lookup(tmp_path, monkeypatch):
    from deeptutor.services.construction_grading import question_grading_registry as reg

    monkeypatch.setattr("sys.argv", ["build", "--out-dir", str(tmp_path)])
    build.main()
    loaded = reg.load_registry_from_jsonl(
        tmp_path / "question_grading_artifacts.jsonl"
    )
    assert len(loaded.question_ids()) == 20
    # unknown still blocks auto-cert through the serialized registry
    assert loaded.lookup("DOES-NOT-EXIST").status == reg.ARTIFACT_MISSING
