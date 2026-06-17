"""M13 integration — real /api/v1/ws cohort gate, kill switch, fail-closed artifact.

Drives the production wire (not the hook) to prove the limited-release safety net: only the
named internal cohort gets beta, the env kill switch force-disables it, and a malformed supply
fails closed without ever touching the legacy grade.
"""
from __future__ import annotations

import os

import pytest

import scripts.run_luban_formal_release_candidate_gate_m13 as m13

pytestmark = pytest.mark.skipif(
    not (m13.REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py").exists(),
    reason="ws smoke harness absent",
)

_ANS = "工期为 25 个月，合理，专用开关箱，符合规范要求，编制说明齐全。"


@pytest.fixture(scope="module")
def rt():
    targets = m13._supply_targets()
    qid = next(iter(targets["by_question"]))
    runtime = m13.ReleaseRuntime()
    yield runtime, qid
    runtime.close()


def test_non_cohort_user_is_blocked(rt):
    runtime, qid = rt
    meta = runtime.submit(qid, _ANS, user="real_student_88", flag=True)
    assert "luban_grading_engine_v1_beta_shadow" not in meta  # production / real student -> legacy only
    assert "construction_grading_result" in meta


def test_cohort_user_gets_beta(rt):
    runtime, qid = rt
    meta = runtime.submit(qid, _ANS, user=m13.INTERNAL_COHORT, flag=True)
    assert "luban_grading_engine_v1_beta_shadow" in meta


def test_kill_switch_force_disables_beta(rt):
    runtime, qid = rt
    os.environ[m13.KILL_ENV] = "false"
    try:
        beta = runtime.submit(qid, _ANS, user=m13.INTERNAL_COHORT, flag=True).get(
            "luban_grading_engine_v1_beta_shadow") or {}
    finally:
        os.environ.pop(m13.KILL_ENV, None)
    assert beta.get("shadow_status") == "killed_by_switch"
    assert "point_results" not in beta


def test_malformed_supply_fails_closed_without_touching_legacy(rt):
    runtime, qid = rt
    import deeptutor.services.construction_grading.beta_shadow_loader as bsl
    orig = bsl.load_beta_supply

    def _boom(*_a, **_k):
        raise bsl.BetaSupplyUnavailable("m13_test_drill")

    bsl.load_beta_supply = _boom
    bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = _boom
    try:
        meta = runtime.submit(qid, _ANS, user=m13.INTERNAL_COHORT, flag=True)
    finally:
        bsl.load_beta_supply = orig
        bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = orig
    beta = meta.get("luban_grading_engine_v1_beta_shadow") or {}
    assert beta.get("shadow_status") == "beta_supply_unavailable"
    legacy = meta.get("construction_grading_result") or {}
    assert "luban" not in str(legacy.get("authority") or "")  # legacy never carries beta authority
