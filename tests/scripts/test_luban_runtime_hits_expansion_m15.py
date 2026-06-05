"""M15 hit-expansion guards (read the emitted canonical artifacts)."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "artifacts/luban_grading_artifacts/runtime_hits_expansion_and_retest_entry_m15_20260604"


def _j(n):
    return json.loads((OUT / n).read_text("utf-8"))


def _jl(n):
    return [json.loads(l) for l in (OUT / n).read_text("utf-8").splitlines() if l.strip()]


def test_counted_hits_reach_50_from_43():
    g = _j("m15_go_no_go.json")
    m = g["metrics"]
    assert m["m13r_counted_hits_input"] == 43
    assert m["counted_authority_backed_total"] == 70
    assert m["counted_authority_backed_runtime_hits"] >= 50
    assert m["new_runtime_hits_vs_m13r"] >= 1
    assert g["go_threshold_50_met"] is True


def test_no_question_stem_counted():
    g = _j("m15_go_no_go.json")
    assert g["metrics"]["question_stem_fact_counted_hits"] == 0
    assert "question_stem_fact" not in g["metrics"]["hits_by_authority_kind"]


def test_hits_from_legit_authority_kinds():
    kinds = set(_j("m15_go_no_go.json")["metrics"]["hits_by_authority_kind"])
    assert kinds <= {"textbook_verbatim", "machine_checkable_logic", "machine_checkable_calc", "list_rule_full_coverage"}


def test_misses_fully_classified():
    s = _j("miss_classification_summary_m15.json")
    assert s["all_classified"] is True
    led = _jl("m13r_runtime_miss_ledger_m15.jsonl")
    assert all(m["miss_class"] for m in led)


def test_matcher_not_relaxed():
    led = _j("workflow_ledger_m15.json")
    assert led["generate_and_filter"]["matcher_relaxed"] is False
    assert led["tournament"]["chosen_fix"].startswith("sample generation")
    assert _j("m15_manifest.json")["production_code_changed"] is False


def test_adversarial_false_positive_zero():
    g = _j("m15_go_no_go.json")["metrics"]
    assert g["false_positive"] == 0
    assert g["bad_certified"] == 0
    assert g["source_mismatch"] == 0
    adv = _jl("adversarial_negative_matrix_m15.jsonl")
    assert len(adv) >= 40
    assert sum(a["false_positive"] for a in adv) == 0
