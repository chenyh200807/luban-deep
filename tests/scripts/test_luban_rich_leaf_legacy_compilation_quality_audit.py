from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_legacy_compilation_quality_audit_flags_direct_reuse_gaps(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_legacy_compilation_quality_audit import (
        run_legacy_compilation_quality_audit,
    )

    old_dir = tmp_path / "textbook_knowledge_full_20260606"
    _write_json(
        old_dir / "go_no_go.json",
        {
            "verdict": "GO",
            "safety": {"canonical_truth_written": False, "production_write_count": 0},
            "records": [{"leaf_id": "L1", "text": "source text without span hash"}],
        },
    )
    _write_json(
        old_dir / "signed_release_candidate_bundle.json",
        {
            "release_candidate": True,
            "production_default": False,
            "items": [{"source_refs": [{"path": "a.md", "span": "abc"}]}],
        },
    )

    report = run_legacy_compilation_quality_audit(artifact_dirs=[old_dir])

    assert report["schema"] == "luban_rich_leaf_legacy_compilation_quality_audit.v1"
    assert report["verdict"] == "REVIEW_REQUIRED"
    assert report["summary"]["artifact_dir_count"] == 1
    assert report["summary"]["quality_gap_count"] >= 1
    assert report["summary"]["direct_reuse_allowed_count"] == 0
    finding = report["artifact_findings"][0]
    assert finding["direct_rich_leaf_reuse_allowed"] is False
    assert "missing_modern_candidate_boundary" in finding["quality_gaps"]
    assert "release_or_default_claim_present" in finding["quality_gaps"]


def test_legacy_compilation_quality_audit_blocks_safety_violations(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_legacy_compilation_quality_audit import (
        run_legacy_compilation_quality_audit,
    )

    old_dir = tmp_path / "bad_compiler"
    _write_json(
        old_dir / "unsafe.json",
        {
            "classification": {"runtime_install_allowed": True},
            "safety": {"production_write_count": 1},
        },
    )

    report = run_legacy_compilation_quality_audit(artifact_dirs=[old_dir])

    assert report["verdict"] == "NO_GO_FOR_DIRECT_REUSE"
    assert report["summary"]["safety_violation_count"] == 2
    assert any("unsafe_runtime_install_allowed" in gap for gap in report["artifact_findings"][0]["quality_gaps"])
    assert any("unsafe_production_write_count" in gap for gap in report["artifact_findings"][0]["quality_gaps"])


def test_legacy_compilation_quality_audit_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_legacy_compilation_quality_audit import main

    old_dir = tmp_path / "canonical_unified_knowledge_20260606"
    _write_json(old_dir / "coverage_report.json", {"coverage": 0.125})
    output = tmp_path / "legacy_quality_audit.json"

    exit_code = main(["--artifact-dir", str(old_dir), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["artifact_dir_count"] == 1
    assert payload["artifact_findings"][0]["artifact_dir"].endswith("canonical_unified_knowledge_20260606")
