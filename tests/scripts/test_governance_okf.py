from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "build_governance_okf.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_governance_okf", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fixture_roots(tmp_path: Path) -> dict[str, Path]:
    roots = {
        "plan": tmp_path / "docs" / "plan",
        "runbook": tmp_path / "docs" / "runbook",
        "contracts": tmp_path / "contracts",
        "docs_contracts": tmp_path / "docs" / "contracts",
        "agent_skills": tmp_path / "agent-skills",
    }
    for root in roots.values():
        root.mkdir(parents=True)
    (roots["plan"] / "INDEX.md").write_text("# Plan Index\n", encoding="utf-8")
    (roots["plan"] / "learning-report-plan.md").write_text("# Learning Report Plan\n", encoding="utf-8")
    (roots["runbook"] / "ci-runtime-smoke-guardrails.md").write_text("# CI Runtime Smoke Guardrails\n", encoding="utf-8")
    (roots["contracts"] / "index.yaml").write_text("domains: []\n", encoding="utf-8")
    (roots["docs_contracts"] / "learning-state-inference.md").write_text("# Learning State Inference\n", encoding="utf-8")
    skill_dir = roots["agent_skills"] / "deeptutor-ci-runtime-fix-gate"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# CI Runtime Fix Gate\n", encoding="utf-8")
    (roots["agent_skills"] / "__pycache__").mkdir()
    (roots["agent_skills"] / "__pycache__" / "ignored.pyc").write_bytes(b"ignore")
    return roots


def test_governance_okf_indexes_governance_sources_without_promoting_runtime(tmp_path):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "governance_okf_v1"

    result = builder.build_governance_okf(
        source_roots=_fixture_roots(tmp_path),
        output_root=output_root,
        generated_at="2026-06-20T00:00:00+08:00",
    )

    manifest = result["manifest"]
    assert manifest["schema"] == "deeptutor_governance_okf_manifest.v1"
    assert manifest["authority_status"] == "ai_project_context_only"
    assert manifest["runtime_guard"]["runtime_consumable"] is False
    assert manifest["runtime_guard"]["official_score_allowed"] is False
    assert manifest["runtime_guard"]["production_registry_write_allowed"] is False
    assert manifest["counts"]["files"] == 6
    assert manifest["counts"]["by_domain"]["contracts"] == 1
    assert manifest["counts"]["by_domain"]["agent_skills"] == 1

    records = _read_jsonl(output_root / "governance_files.jsonl")
    by_path = {row["source_path"]: row for row in records}
    assert any(row["authority_role"] == "contract_reference" for row in records)
    assert any(row["authority_role"] == "operational_runbook" for row in records)
    assert any(row["authority_role"] == "agent_behavior_guidance" for row in records)
    assert all(row["runtime_guard"]["canonical_write_allowed"] is False for row in records)
    assert not any("__pycache__" in path for path in by_path)

    summary = (output_root / "summary.md").read_text(encoding="utf-8")
    assert "not a production control plane" in summary
    assert "Contracts and runbooks remain the authority" in summary

    saved_manifest = _read_json(output_root / "manifest.json")
    assert saved_manifest == manifest


def test_governance_okf_rejects_dangerous_output_root_before_reset(tmp_path, monkeypatch):
    builder = _load_builder()

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unsafe path: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="unsafe output root"):
        builder.build_governance_okf(
            source_roots=_fixture_roots(tmp_path),
            output_root=REPO_ROOT,
            generated_at="2026-06-20T00:00:00+08:00",
        )


def test_governance_okf_rejects_unowned_generated_tree(tmp_path, monkeypatch):
    builder = _load_builder()
    output_root = tmp_path / "extractions" / "governance_okf_v1"
    output_root.mkdir(parents=True)
    (output_root / "human_note.md").write_text("do not delete\n", encoding="utf-8")

    def fail_if_reset_called(path):
        raise AssertionError(f"reset_dir should not be called for unowned output: {path}")

    monkeypatch.setattr(builder, "reset_dir", fail_if_reset_called)

    with pytest.raises(ValueError, match="missing generated sentinel"):
        builder.build_governance_okf(
            source_roots=_fixture_roots(tmp_path),
            output_root=output_root,
            generated_at="2026-06-20T00:00:00+08:00",
        )
