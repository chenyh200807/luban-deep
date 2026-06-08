"""M17A unit + artifact guards: GradingPacket builder, LLM parser, validator floor, fallback,
fail-closed, and the emitted canonical verdict."""
from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

OUT = Path(__file__).resolve().parents[2] / "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604"


def _packet():
    supply = bsl.load_beta_supply()
    reg = bsl.load_release_candidate_registry()
    qid = next(p["question_id"] for p in reg["points"])
    ans = "工期为 25 个月，合理。"
    return adj.build_grading_packet(qid, ans, supply=supply, registry=reg), supply, reg, qid, ans


def test_packet_has_required_fields():
    packet, *_ = _packet()
    for f in ("schema_version", "question_id", "point_ids", "student_answer",
              "registry_release_candidate", "source_spec_list_policy_slices",
              "personalization_context_pack_readonly", "token_budget", "packet_hash"):
        assert f in packet
    assert packet["registry_release_candidate"]["registry_content_hash"]
    assert packet["personalization_context_pack_readonly"]["read_only"] is True
    assert packet["personalization_context_pack_readonly"]["is_second_learner_memory"] is False


def test_personalization_context_guides_tone_without_becoming_scoring_authority():
    supply = bsl.load_beta_supply()
    reg = bsl.load_release_candidate_registry()
    qid = next(p["question_id"] for p in reg["points"])
    pcp = {
        "source": "PersonalizationContextPack",
        "top_claims": [
            {
                "claim_status": "repeated",
                "label": "exact_required 术语经常用近义词替代",
                "evidence_refs": ["teacher_final_evt", "real_retest_evt"],
            }
        ],
        "next_best_action_candidates": [
            {
                "action_type": "retest_or_targeted_practice",
                "target": "同类 exact_required 术语题",
                "evidence_refs": ["teacher_final_evt"],
            }
        ],
    }

    packet = adj.build_grading_packet(
        qid,
        "我写成了普通钢筋调直机。",
        supply=supply,
        registry=reg,
        personalization_context_pack=pcp,
    )

    pcp_block = packet["personalization_context_pack_readonly"]
    assert pcp_block["read_only"] is True
    assert pcp_block["is_second_learner_memory"] is False
    assert pcp_block["scoring_authority"] == "rubric_policy_and_validator_only"
    assert pcp_block["feedback_guidance"]["grading_tone"] == "advanced_repeat_mistake"
    assert pcp_block["feedback_guidance"]["explanation_depth"] == "reference_prior_pattern"
    assert pcp_block["feedback_guidance"]["next_action_hint"] == "同类 exact_required 术语题"

    _system, user = adj._adjudication_prompt(packet)
    prompt_payload = json.loads(user)
    assert prompt_payload["personalization_feedback_guidance"] == pcp_block["feedback_guidance"]
    assert "personalization_feedback_guidance" not in json.dumps(
        prompt_payload["points"], ensure_ascii=False
    )


def test_validator_floor_blocks_llm_accept_when_deterministic_rejects():
    packet, supply, _reg, _qid, _ans = _packet()
    pid = packet["point_ids"][0]

    def fake(role, system, user, env):
        return json.dumps([{"point_id": pid, "disposition": "accept", "evidence_span": "工期", "confidence": 0.9}], ensure_ascii=False)

    val = adj.validate(packet, adj.adjudicate(packet, provider=fake), supply=supply)
    # "工期为 25 个月" likely does NOT satisfy the first list/source point -> validator downgrades; fp stays 0
    assert val["false_positive"] == 0
    for v in val["validated_points"]:
        if v["llm_disposition"] == "accept" and not v["deterministic_auto"]:
            assert v["auto_shadow_safe"] is False
            assert v["final_disposition"] == "needs_review"


def test_validator_blocks_evidence_span_laundering():
    packet, supply, *_ = _packet()
    pid = packet["point_ids"][0]

    def fake(role, system, user, env):
        return json.dumps([{"point_id": pid, "disposition": "accept", "evidence_span": "这段不在学生作答里", "confidence": 1.0}], ensure_ascii=False)

    val = adj.validate(packet, adj.adjudicate(packet, provider=fake), supply=supply)
    assert val["false_positive"] == 0
    # never auto on a fabricated span
    assert all(not v["auto_shadow_safe"] or v["evidence_span_valid"] for v in val["validated_points"])


def test_fallback_used_when_primary_fails():
    packet, supply, *_ = _packet()

    def fake(role, system, user, env):
        if role == "primary":
            raise RuntimeError("deepseek down")
        return json.dumps([{"point_id": p, "disposition": "reject", "evidence_span": ""} for p in packet["point_ids"]], ensure_ascii=False)

    res = adj.adjudicate(packet, provider=fake)
    assert res["fallback_used"] is True
    assert res["model_used"] == adj.FALLBACK_MODEL
    assert res["failclosed"] is False


def test_failclosed_when_both_providers_fail():
    packet, supply, *_ = _packet()

    def fake(role, system, user, env):
        raise RuntimeError("provider down")

    res = adj.adjudicate(packet, provider=fake)
    assert res["failclosed"] is True
    assert all(o["disposition"] == "needs_review" for o in res["point_outputs"])
    val = adj.validate(packet, res, supply=supply)
    assert val["auto_shadow_count"] == 0  # fail-closed never auto-certifies


def test_lb_draft_is_preview_only():
    packet, supply, *_ = _packet()
    val = adj.validate(packet, adj.adjudicate(packet, provider=lambda *a: "[]"), supply=supply)
    draft = adj.build_lb_event_draft(packet, val, "qa_x")
    assert draft["preview_only"] is True
    assert draft["mastery_raised"] is False
    assert draft["writeback_performed"] is False
    assert draft["canonical_truth_written"] is False
    assert draft["personalization_context_pack_is_second_memory"] is False


def test_emitted_verdict_safety():
    g = json.loads((OUT / "m17a_go_no_go.json").read_text("utf-8"))
    assert g["production_v1"] == "NO-GO"
    assert g["production_default_enable"] == "NO-GO"
    m = g["metrics"]
    assert m["false_positive"] == 0 and m["bad_certified"] == 0 and m["source_mismatch"] == 0
    assert m["legacy_equal_rate"] == 1.0
    assert m["production_write_count"] == 0
    assert m["real_adjudications"] >= 1
