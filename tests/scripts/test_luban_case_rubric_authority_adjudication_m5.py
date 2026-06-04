"""Tests for M5 authority adjudication and promotion simulation.

M5 is the hard authority gate before any Registry v1 candidate compile. It may
simulate promotion, but it must not emit a formal registry or let weak/LLM
signals bypass deterministic source and policy gates.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_case_rubric_authority_adjudication_m5 import (
    build_authority_adjudication_m5,
    decide_point_authority,
    decide_question_status,
)


@pytest.fixture(scope="module")
def built_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("authority_m5")
    build_authority_adjudication_m5(out_dir=out)
    return out


def _read(path: Path):
    return json.loads(path.read_text("utf-8"))


def test_official_weak_never_auto_certifiable():
    fact = {
        "source_status": "official_weak",
        "policy_gaps": [],
        "llm_jury_suggestion": {"consensus": "keep_draft"},
    }

    decision = decide_point_authority(fact)

    assert decision["point_authority_decision"] == "review_required_official_weak"
    assert decision["auto_certifiable_final"] is False


def test_llm_cannot_promote_weak_source_to_verified():
    fact = {
        "source_status": "official_weak",
        "policy_gaps": [],
        "llm_jury_suggestion": {"consensus": "auto_certifiable"},
    }

    decision = decide_point_authority(fact)

    assert decision["point_authority_decision"] != "auto_certifiable"
    assert decision["source_status_final"] == "official_weak"


def test_calculation_without_spec_cannot_auto():
    fact = {
        "source_status": "verified_textbook",
        "policy_type": "calculation",
        "policy_gaps": ["calculation_without_spec"],
        "llm_jury_suggestion": {"consensus": "keep_draft"},
    }

    decision = decide_point_authority(fact)

    assert decision["point_authority_decision"] == "rewrite_needed"
    assert decision["auto_certifiable_final"] is False


def test_list_rule_without_denominator_cannot_auto():
    fact = {
        "source_status": "verified_textbook",
        "policy_type": "list_rule",
        "policy_gaps": ["list_rule_without_denominator"],
        "llm_jury_suggestion": {"consensus": "keep_draft"},
    }

    decision = decide_point_authority(fact)

    assert decision["point_authority_decision"] == "rewrite_needed"
    assert decision["auto_certifiable_final"] is False


def test_source_coverage_below_half_is_not_publish_ready():
    points = [
        {"point_authority_decision": "auto_certifiable"},
        {"point_authority_decision": "review_required_official_weak"},
        {"point_authority_decision": "external_source_required"},
    ]

    status = decide_question_status(points)

    assert status == "po_review_required"


def test_provider_unavailable_is_recorded(built_out: Path):
    jury_votes = sorted((built_out / "model_jury_votes").glob("*.json"))
    assert jury_votes
    first = _read(jury_votes[0])

    assert first["reviewer_type"] == "llm_jury"
    assert first["available_models"] == []
    assert set(first["provider_unavailable"]) == {"gpt55_codex", "opus48_dynamic", "deepseek_v4", "qwen37"}


def test_no_formal_registry_emitted(built_out: Path):
    simulation = _read(built_out / "registry_v1_promotion_candidate_simulation.json")

    assert simulation["formal_registry_emitted"] is False
    assert not (built_out / "registry_v1.json").exists()


def test_po_packets_include_provenance(built_out: Path):
    packets = sorted((built_out / "po_review_packets").glob("*.md"))

    assert packets
    content = packets[0].read_text("utf-8")
    assert "## Provenance" in content
    assert "recommended action" in content


def test_rewrite_recommendations_do_not_overwrite_source_packets(built_out: Path):
    recommendations = _read(built_out / "rewrite_recommendations.json")

    assert isinstance(recommendations, list)
    assert not (built_out / "refined_audit_packets").exists()
