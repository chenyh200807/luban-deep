"""Hermetic guards for M9 canonical WEAK-GO reconciliation + beta-shadow source assault.

M9 must (0) make the M8 verdict canonical WEAK-GO without deleting the script's
superseded GO, and (1) recover textbook source ONLY via deterministic verbatim
exact-match. Case-answer judgment phrases must never become a textbook source, and the
canonical override must be readable BEFORE the stale release_risk_matrix GO.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_v1_beta_shadow_source_assault_m9 as m9

pytestmark = pytest.mark.skipif(
    not (m9.M8_DIR / "source_gap_candidates.jsonl").exists(),
    reason="M8 source_gap supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _run_m9():
    subprocess.run([sys.executable, str(m9.REPO / "scripts/run_luban_v1_beta_shadow_source_assault_m9.py")],
                   cwd=m9.REPO, check=True, capture_output=True)
    return m9.OUT_DIR


def test_phase0_canonical_verdict_is_weak_go_and_preserves_superseded_go():
    override = _j(m9.M8_DIR / "canonical_m8_verdict_override.json")
    assert override["canonical_verdict"] == "WEAK-GO"
    assert override["superseded_script_verdict"] == "GO"  # evidence preserved, not deleted
    assert override["constraints_reasserted"]["alpha_shadow_is_not_gated_beta"] is True
    assert override["constraints_reasserted"]["formal_registry_emitted"] is False


def test_release_risk_matrix_canonical_overrides_old_go():
    rm = _j(m9.M8_DIR / "release_risk_matrix.json")
    # the canonical verdict must be WEAK-GO; the old GO must survive only as superseded evidence
    assert rm["v1_alpha_verdict_canonical"] == "WEAK-GO"
    assert rm["superseded_script_verdict"] == "GO"
    # readers must be told canonical override wins over the stale field
    assert "canonical_m8_verdict_override.json" in rm["read_order"]


def test_m8_finding_has_canonical_override_banner():
    finding = (m9.M8_DIR / "FINDING_v1_alpha_grand_sprint_m8_20260604.md").read_text("utf-8")
    assert "CANONICAL VERDICT OVERRIDE (M9)" in finding
    assert "WEAK-GO" in finding


def test_source_authority_invariants_all_zero():
    delta = _j(m9.OUT_DIR / "source_coverage_delta_m9.json")
    inv = delta["source_authority_invariants"]
    assert inv["official_answer_as_textbook"] == 0
    assert inv["model_vote_as_source"] == 0
    assert inv["source_mismatch"] == 0
    assert inv["case_answer_laundering"] == 0
    assert inv["list_rule_partial_anchor_auto"] == 0
    assert delta["all_invariants_zero"] is True


def test_every_recovered_anchor_is_verbatim_textbook_and_not_case_number():
    import re

    corpus, _blocks = m9.load_textbook()
    verified = _jsonl(m9.OUT_DIR / "verified_source_candidates_m9.jsonl")
    for v in verified:
        ref = v["verified_source_ref"]
        # independent recheck: the recovered anchor MUST be verbatim in the textbook
        assert ref["variant_norm"] in corpus, f"non-textbook anchor leaked: {ref}"
        # a recovered anchor must never be a numeric case-answer judgment
        assert not re.search(r"\d", ref["variant"]), f"numeric case-answer laundering: {ref}"
        assert v["source_authority"] == "textbook_exact_match"
        assert v["runtime_auto_certifiable_in_production"] is False


def test_auto_preview_after_equals_baseline_plus_new():
    delta = _j(m9.OUT_DIR / "source_coverage_delta_m9.json")
    assert delta["auto_preview_before"] == m9.M8_SOURCE_BACKED_TOTAL
    assert delta["auto_preview_after"] == delta["auto_preview_before"] + delta["m9_new_verified_source_recovered"]


def test_case_judgment_gaps_routed_out_not_anchored():
    inv = _j(m9.OUT_DIR / "source_gap_inventory_m9.json")
    # at least some gaps must be honestly routed to external/keep_draft (not forced anchors)
    counts = inv["gap_class_counts"]
    assert counts.get("external_source_required", 0) >= 1
    assert sum(counts.values()) == inv["gap_total"]
