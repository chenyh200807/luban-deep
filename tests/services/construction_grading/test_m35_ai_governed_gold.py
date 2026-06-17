from deeptutor.services.construction_grading.m35_ai_governed_gold import (
    build_deepseek_adversarial_prompt,
    normalize_deepseek_adversarial_report,
    validate_ai_governed_gold_protocol,
)


def _protocol(**overrides):
    protocol = {
        "protocol_version": "m35_ai_governed_gold.v1",
        "blind_model_votes": [
            {"model_id": "gpt-5.5", "independent": True, "verdict": "accept"},
            {"model_id": "claude-opus-4.8", "independent": True, "verdict": "accept"},
            {"model_id": "qwen-3.7-plus", "independent": True, "verdict": "accept"},
        ],
        "adversarial_review": {
            "model_id": "deepseek-v4-pro",
            "role": "adversarial_prosecutor",
            "unresolved_objection_count": 0,
        },
        "source_anchor": {
            "source_ref_count": 2,
            "field_level_citations": True,
        },
        "mutation_test": {
            "passed": True,
            "case_count": 8,
        },
        "reproducibility_hash": "sha256:abc123",
        "deterministic_gate": {
            "passed": True,
        },
    }
    protocol.update(overrides)
    return protocol


def test_ai_governed_gold_protocol_can_replace_human_label_authority_without_release_truth():
    result = validate_ai_governed_gold_protocol(_protocol())

    assert result["valid"] is True
    assert result["label_authority"] == "ai_governed_gold"
    assert result["quality_claim_allowed"] is True
    assert result["official_score_allowed"] is False
    assert result["is_release_truth"] is False
    assert result["blocking_reasons"] == []


def test_ai_governed_gold_blocks_unresolved_deepseek_objections():
    result = validate_ai_governed_gold_protocol(
        _protocol(
            adversarial_review={
                "model_id": "deepseek-v4-pro",
                "role": "adversarial_prosecutor",
                "unresolved_objection_count": 1,
            }
        )
    )

    assert result["valid"] is False
    assert result["quality_claim_allowed"] is False
    assert result["official_score_allowed"] is False
    assert "unresolved_adversarial_objections" in result["blocking_reasons"]


def test_ai_governed_gold_requires_independent_blind_panel_source_anchor_and_mutations():
    result = validate_ai_governed_gold_protocol(
        _protocol(
            blind_model_votes=[{"model_id": "gpt-5.5", "independent": True, "verdict": "accept"}],
            source_anchor={"source_ref_count": 0, "field_level_citations": False},
            mutation_test={"passed": False, "case_count": 2},
            reproducibility_hash="",
        )
    )

    assert result["valid"] is False
    assert result["blocking_reasons"] == [
        "blind_panel_too_small",
        "source_anchor_missing",
        "mutation_test_not_passed",
        "reproducibility_hash_missing",
    ]


def test_deepseek_adversarial_report_is_candidate_not_truth():
    report = normalize_deepseek_adversarial_report(
        {
            "source_challenges": [{"point_id": "P1", "reason": "source quote too broad"}],
            "rubric_attacks": [{"point_id": "P2", "risk": "overaccepts slogan answer"}],
            "suggested_demotions": [{"point_id": "P2", "from": "hit", "to": "partial"}],
            "unresolved_objection_count": 1,
        },
        model_id="deepseek-v4-pro",
    )

    assert report["origin"] == "deepseek_v4_pro_adversarial"
    assert report["role"] == "adversarial_prosecutor"
    assert report["runtime_usable_as_truth"] is False
    assert report["promote_to_release"] is False
    assert report["unresolved_objection_count"] == 1


def test_deepseek_prompt_demands_json_and_forbids_final_judge_role():
    prompt = build_deepseek_adversarial_prompt(
        question={"question_id": "Q1-NA", "stem": "案例题"},
        artifact={"artifact_version": "m35_case_scoring_20260609", "scoring_points": []},
        student_answer="施工总进度计划表。",
    )

    assert "DeepSeek-v4-pro" in prompt
    assert "adversarial prosecutor" in prompt
    assert "You are not the final judge" in prompt
    assert "JSON" in prompt
