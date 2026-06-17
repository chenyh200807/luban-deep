"""M16 controlled-runtime guards: release_candidate registry + loader + artifact verdict."""
from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading import beta_shadow_loader as bsl

OUT = Path(__file__).resolve().parents[2] / "artifacts/luban_grading_artifacts/controlled_production_runtime_flip_m16_20260604"


def _j(n):
    return json.loads((OUT / n).read_text("utf-8"))


def test_registry_is_release_candidate_not_published():
    reg = _j("registry_v1_release_candidate.json")
    assert reg["status"] == "release_candidate"
    assert reg["published"] is False
    assert reg["production_default"] == "off"
    assert reg["registry_content_hash"] and reg["rollback_pointer"]


def test_registry_loads_and_validates_hash():
    loaded = bsl.load_release_candidate_registry()
    assert loaded["status"] == "release_candidate"
    assert loaded["registry_content_hash"]


def test_registry_only_legit_authority_no_question_stem():
    reg = _j("registry_v1_release_candidate.json")
    kinds = set(reg["by_authority_kind"])
    assert kinds <= {"textbook_verbatim", "machine_checkable_logic", "machine_checkable_calc", "list_rule_full_coverage"}
    assert "question_stem_fact" not in kinds
    assert reg["question_stem_fact_excluded"] is True


def test_no_official_answer_or_vote_as_source():
    aud = _j("registry_release_candidate_audit_m16.json")
    assert aud["official_answer_as_textbook"] is False
    assert aud["model_vote_as_source"] is False
    assert aud["council_vote_as_source"] is False
    assert aud["v0_overwritten"] is False
    assert aud["v0_present_untouched"] is True


def test_malformed_registry_fails_closed(tmp_path: Path):
    bad = tmp_path / "controlled_production_runtime_flip_m16_bad"
    bad.mkdir()
    (bad / "registry_v1_release_candidate.json").write_text('{"status": "published"}', "utf-8")
    try:
        bsl.load_release_candidate_registry(root=tmp_path)
        assert False, "expected ReleaseCandidateUnavailable"
    except bsl.ReleaseCandidateUnavailable:
        pass


def test_verdict_and_production_default_off():
    g = _j("m16_go_no_go.json")
    assert g["controlled_production_runtime"] in {"GO", "WEAK-GO", "NO-GO"}
    assert g["production_default_enable"] == "NO-GO"
    assert g["production_v1"] == "NO-GO"
    assert g["production_default"] == "OFF"
    m = g["metrics"]
    assert m["false_positive"] == 0 and m["bad_certified"] == 0 and m["source_mismatch"] == 0
    assert m["production_write_count"] == 0
    if g["controlled_production_runtime"] == "GO":
        assert m["registry_loadable"] and m["controlled_cohort_hit"] and m["non_cohort_blocked"]
        assert m["kill_switch_works"] and m["malformed_registry_fail_closed"] and m["rollback_to_legacy"]
