"""Integration-style alpha shadow guard for M8.

This does not connect production runtime. It proves the M8 shadow payload shape
is append-only and cannot overwrite legacy construction grading results.
"""
from __future__ import annotations

import copy

import scripts.run_luban_v1_alpha_grand_sprint_m8 as m8


def test_alpha_shadow_payload_is_append_only_and_not_a_grade():
    legacy_payload = {
        "event": "RESULT",
        "metadata": {
            "construction_grading_result": {
                "score_awarded": 3,
                "max_score": 5,
                "authority": "CaseGradingSkillKernel",
            }
        },
    }
    before = copy.deepcopy(legacy_payload)
    pack = {
        "alpha_auto_preview_total": 9,
        "components": {
            "m7_reverified_auto_points": 6,
            "m7r_new_source_backed_points": 3,
            "weak_or_source_gap_points_diagnostic_only": 12,
        },
    }

    out = m8.build_alpha_shadow_payload(legacy_payload, pack, qa_sample_id="qa_m8_shadow_sample")

    assert legacy_payload == before  # helper must not mutate caller payload
    assert out["metadata"]["construction_grading_result"] == before["metadata"]["construction_grading_result"]
    shadow = out["metadata"]["luban_grading_engine_v1_alpha_shadow"]
    assert shadow["authority"] == "luban_grading_engine_v1_alpha_shadow"
    assert shadow["not_production_grade"] is True
    assert shadow["writeback_performed"] is False
    assert shadow["production_runtime_connected"] is False
    assert shadow["human_reviewed"] is False
    assert shadow["scores"]["legacy_score_overwritten"] is False


def test_shadow_payload_can_be_disabled_without_legacy_change():
    legacy_payload = {
        "event": "RESULT",
        "metadata": {
            "construction_grading_result": {
                "score_awarded": 0,
                "max_score": 4,
                "authority": "CaseGradingSkillKernel",
            }
        },
    }
    out = m8.build_alpha_shadow_payload(
        legacy_payload,
        {"alpha_auto_preview_total": 0, "components": {}},
        qa_sample_id="qa_m8_shadow_disabled",
        enabled=False,
    )

    assert out == legacy_payload
    assert "luban_grading_engine_v1_alpha_shadow" not in out["metadata"]
