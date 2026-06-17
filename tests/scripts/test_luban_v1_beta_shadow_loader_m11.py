"""Loader unit tests: read-only load/hash/schema/fail-closed + matcher safety (no false-positive auto)."""
from __future__ import annotations

from deeptutor.services.construction_grading import beta_shadow_loader as L


def test_load_supply_counts_and_hash():
    s = L.load_beta_supply()
    c = s.counts()
    assert c["beta_shadow_scoring_supply"] == c["machine_specs"] + c["list_specs"] + c["source_backed"]
    assert c["machine_specs"] >= 20
    assert c["source_backed"] >= 1
    assert len(s.content_hash) == 64  # sha256


def test_official_answer_never_textbook_source():
    s = L.load_beta_supply()
    for row in s.machine_specs.values():
        assert row["textbook_source"] is False
        assert row["rubric_seed"] == "official_answer_not_textbook"
        assert row["auto_certifiable"] is False


def test_machine_matcher_rejects_off_by_one_and_contradiction():
    s = L.load_beta_supply()
    # find a numeric_judgment / numeric spec with an expected value
    spec = None
    for row in s.machine_specs.values():
        k = row["spec"].get("kind")
        if k in ("numeric_value", "numeric_judgment", "numeric_formula") and row["spec"].get("acceptance_range"):
            spec = row["spec"]
            break
    assert spec is not None
    exp = spec["expected"]
    assert L._machine_accepts(spec, f"{exp}") is True            # exact value present
    assert L._machine_accepts(spec, f"{exp + 1}") is False       # off-by-one rejected
    assert L._machine_accepts(spec, "完全无关的答案") is False     # irrelevant rejected


def test_list_matcher_requires_full_coverage():
    s = L.load_beta_supply()
    row = next(iter(s.list_specs.values()))
    items = [m["item"] for m in row["spec"]["item_matchers"]]
    full_answer = "，".join(items)
    assert L._list_accepts(row["spec"], full_answer) is True
    if len(items) > 1:
        partial = "，".join(items[:-1])
        assert L._list_accepts(row["spec"], partial) is False    # partial list never full-coverage


def test_score_point_never_auto_on_gap():
    s = L.load_beta_supply()
    (qid, pid) = next(iter(s.machine_specs))
    r = L.score_point(s, qid, pid, "我不知道")
    assert r["auto_shadow"] is False
    assert r["disposition"] == "review_required"
    assert r["not_production_grade"] is True


def test_build_payload_is_read_only_and_shadow():
    s = L.load_beta_supply()
    (qid, _pid) = next(iter(s.machine_specs))
    payload = L.build_beta_shadow_payload(qid, "qa_x", "工期 25 个月，合理")
    assert payload["production_runtime_connected"] is False
    assert payload["formal_registry_emitted"] is False
    assert payload["writeback_performed"] is False
    assert payload["learning_brain_preview"]["writeback_performed"] is False
    assert payload["teacher_review_queue_item"]["qa_simulated"] is True
