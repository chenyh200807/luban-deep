"""Integration guards for the M9 beta-shadow positive auto-path pressure test.

The dangerous failure is a false-positive auto-certification. M9 must prove: the
production default never auto-certifies a beta_shadow point (status != published), the
test-only dry-run exercises hit/miss/partial/contradiction, false_positive == 0, and
legacy construction grading is untouched.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_v1_beta_shadow_source_assault_m9 as m9

pytestmark = pytest.mark.skipif(
    not (m9.M8_DIR / "verified_source_candidates.jsonl").exists(),
    reason="M8 source-backed supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="session", autouse=True)
def _run_m9():
    subprocess.run([sys.executable, str(m9.REPO / "scripts/run_luban_v1_beta_shadow_source_assault_m9.py")],
                   cwd=m9.REPO, check=True, capture_output=True)
    return m9.OUT_DIR


def test_auto_path_covers_hit_miss_partial_contradiction():
    summary = _j(m9.OUT_DIR / "beta_shadow_auto_path_results.json")["summary"]
    assert {"hit", "miss", "partial", "contradiction"}.issubset(set(summary["kinds_covered"]))


def test_false_positive_is_zero():
    summary = _j(m9.OUT_DIR / "beta_shadow_auto_path_results.json")["summary"]
    assert summary["false_positive"] == 0  # the only dangerous direction


def test_partial_and_contradiction_are_rejected():
    res = _j(m9.OUT_DIR / "beta_shadow_auto_path_results.json")
    for r in res["results"]:
        if r["kind"] in ("partial", "contradiction", "miss", "irrelevant"):
            assert r["test_flag_auto"] is False


def test_production_default_never_auto_certifies_beta_shadow():
    summary = _j(m9.OUT_DIR / "beta_shadow_auto_path_results.json")["summary"]
    assert summary["production_default_auto_count"] == 0
    assert summary["production_default_flag"] is False


def test_real_runtime_gate_downgrades_beta_shadow_to_zero_production_auto():
    """Independent, strongest check: feed the REAL gate a draft that CLAIMS auto on a
    beta_shadow point. Because the artifact status is never 'published', the gate must
    downgrade it -> auto_certified False, auto_certified_score 0. This is the production
    fail-closed proof, not just a capability-flag read."""
    from deeptutor.services.construction_grading.question_grading_registry import load_registry_from_jsonl
    from deeptutor.services.construction_grading import artifact_runtime_gate as gate

    reg_path = m9.OUT_DIR / "beta_shadow_registry_preview.jsonl"
    assert reg_path.exists()
    reg = load_registry_from_jsonl(reg_path)
    report = reg.to_report()
    assert report["questions"], "beta_shadow registry preview is empty"

    total_prod_auto_score = 0.0
    for q in report["questions"]:
        qid = q["question_id"]
        g = gate.resolve_runtime_artifact_gate(qid, registry=reg)
        assert g.artifact_status != "published"  # beta_shadow is never published
        art = reg.get_artifact(qid)
        pid = (art.get("scoring_points") or [{}])[0].get("point_id", "P1")
        draft = {"point_results": [{"point_id": pid, "score": 2, "auto_certified": True,
                                    "high_risk_review": False, "unsupported": False}]}
        out = gate.apply_runtime_artifact_gate(draft, g)
        assert out["point_results"][0]["auto_certified"] is False
        total_prod_auto_score += out.get("auto_certified_score", 0.0)
    assert total_prod_auto_score == 0.0  # no beta_shadow point auto-certifies in production


def test_legacy_unchanged_and_no_production_db_write():
    summary = _j(m9.OUT_DIR / "beta_shadow_auto_path_results.json")["summary"]
    assert summary["legacy_construction_grading_result_unchanged"] is True
    assert summary["production_db_written"] is False
