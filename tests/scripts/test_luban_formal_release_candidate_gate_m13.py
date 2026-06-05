"""M13 formal release candidate gate — real /api/v1/ws slice + canonical gate invariants.

Drives the REAL ``/api/v1/ws`` wire (not the hook) for a small slice and asserts the
release-safety contract; also validates the canonical M13 go/no-go artifact when present.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_formal_release_candidate_gate_m13 as m13

pytestmark = pytest.mark.skipif(
    not (m13.REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py").exists(),
    reason="ws smoke harness absent",
)

_ANS = "工期为 25 个月，合理，专用开关箱，符合规范要求，编制说明齐全。"
_NEUTRAL = "本次作答与所问知识点无关，仅为占位文本，未给出任何具体技术结论或数值。"


@pytest.fixture(scope="module")
def rt():
    targets = m13._supply_targets()
    qid = next(iter(targets["by_question"]))
    runtime = m13.ReleaseRuntime()
    yield runtime, qid
    runtime.close()


def test_real_ws_flag_off_is_legacy_only(rt):
    runtime, qid = rt
    meta = runtime.submit(qid, _ANS, user=m13.INTERNAL_COHORT, flag=False)
    assert "construction_grading_result" in meta
    assert "luban_grading_engine_v1_beta_shadow" not in meta


def test_real_ws_flag_on_appends_beta_without_overwriting_legacy(rt):
    runtime, qid = rt
    off = runtime.submit(qid, _ANS, user=m13.INTERNAL_COHORT, flag=False)
    on = runtime.submit(qid, _ANS, user=m13.INTERNAL_COHORT, flag=True)
    legacy_off = off.get("construction_grading_result") or {}
    legacy_on = on.get("construction_grading_result") or {}
    assert legacy_off == legacy_on  # append-only: beta never overwrites legacy
    beta = on.get("luban_grading_engine_v1_beta_shadow")
    assert beta is not None
    assert beta["authority"] == "luban_grading_engine_v1_beta_shadow"
    assert beta["not_production_grade"] is True
    assert beta["writeback_performed"] is False
    assert beta["production_runtime_connected"] is False
    assert "luban" not in str(legacy_on.get("authority") or "")


def test_real_ws_wrong_answer_never_auto_certifies(rt):
    runtime, qid = rt
    beta = runtime.submit(qid, _NEUTRAL, user=m13.INTERNAL_COHORT, flag=True).get(
        "luban_grading_engine_v1_beta_shadow") or {}
    # a token-free wrong answer must auto-certify nothing (fail-closed loader)
    assert (beta.get("auto_shadow_count") or 0) == 0
    for p in beta.get("point_results") or []:
        if p.get("auto_shadow"):
            pytest.fail(f"false positive: wrong answer auto-certified {p}")


def test_canonical_m13_gate_artifact_is_go_and_safe():
    go_path = m13.OUT_DEFAULT / "production_v1_go_no_go_m13.json"
    if not go_path.exists():
        pytest.skip("canonical M13 artifact not generated in this environment")
    go = json.loads(go_path.read_text("utf-8"))
    inv = go["invariants"]
    assert go["m13_verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert go["production_v1"] == "NO-GO"
    assert go["formal_registry_emitted"] is False
    assert go["production_default"] == "OFF"
    # safety invariants must hold for any non-NO-GO release candidate
    if go["m13_verdict"] != "NO-GO":
        assert inv["false_positive"] == 0
        assert inv["bad_certified"] == 0
        assert inv["source_mismatch"] == 0
        assert inv["legacy_equal_rate"] == 1.0
        assert inv["production_write_count"] == 0
        assert inv["learning_brain_writeback"] == 0
        assert inv["non_cohort_blocked"] is True
        assert inv["kill_switch_works"] is True
        assert inv["artifact_fail_closed"] is True
        assert inv["ws_submissions"] >= 120


def test_canonical_required_artifacts_exist():
    out = m13.OUT_DEFAULT
    if not (out / "formal_release_manifest_m13.json").exists():
        pytest.skip("canonical M13 artifacts not generated in this environment")
    for name in (
        "formal_release_manifest_m13.json", "runtime_release_candidate_results_m13.jsonl",
        "authority_backed_runtime_coverage_m13.json", "adversarial_release_attacks_m13.jsonl",
        "teacher_review_release_queue_m13.jsonl", "learning_brain_release_preview_m13.jsonl",
        "case_event_text_backfill_queue_m13.jsonl", "limited_release_switch_design_m13.md",
        "rollback_and_killswitch_plan_m13.md", "production_v1_go_no_go_m13.json",
        "FINDING_formal_release_candidate_gate_m13_20260604.md",
    ):
        assert (out / name).exists(), name
