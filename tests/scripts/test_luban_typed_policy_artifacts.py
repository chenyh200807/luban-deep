from __future__ import annotations

from scripts.build_luban_typed_policy_artifacts import (
    build_typed_policies,
    validate_typed_policy,
)


def _point(
    *,
    point_id: str = "P1",
    point_type: str = "text_term",
    label: str = "必须写出'见证人员'原文术语",
    list_rule: str = "",
    penalty_rule: str | None = None,
    required_terms: list[str] | None = None,
    anchor_source: str = "textbook",
) -> dict:
    return {
        "point_id": point_id,
        "label": label,
        "official_basis": label,
        "max_score": 2,
        "point_type": point_type,
        "list_rule": list_rule,
        "penalty_rule": penalty_rule,
        "required_terms_v1_5": required_terms if required_terms is not None else ["见证人员"],
        "anchor_source": anchor_source,
        "chunk_id": "chunk-1" if anchor_source == "textbook" else "",
        "textbook_quote": "见证人员" if anchor_source == "textbook" else "",
        "term_anchor_map": {
            "见证人员": {
                "anchor_source": "textbook",
                "chunk_id": "chunk-1",
                "textbook_quote": "见证人员",
                "verified": True,
            }
        },
    }


def _case(*, penalty_rule: str = "", points: list[dict] | None = None) -> dict:
    return {
        "case_id": "Q4-1A434000-罚则",
        "question_node": "1A434000",
        "penalty_rule": penalty_rule,
        "gold_scoring_points": points or [_point(point_id="P1")],
    }


def test_penalty_rule_takes_precedence_over_exact_required() -> None:
    policies = build_typed_policies(
        {
            "cases": [
                _case(
                    penalty_rule=(
                        "题干明确多答不得分:仅针对不妥之处+正确做法部分(P1、P2)。"
                        "若考生答出多于2项不妥之处,则P1、P2两个采分点全部清零。"
                    ),
                    points=[_point(point_id="P1")],
                )
            ]
        }
    )

    policy = policies[0]
    assert policy["policy_type"] == "penalty_rule"
    assert policy["base_policy"] == "exact_required"
    assert policy["penalty_spec"]["applies_to_points"] == ["P1", "P2"]
    assert policy["auto_certify"] is False


def test_penalty_rule_excludes_explicit_non_implicated_points() -> None:
    policies = build_typed_policies(
        {
            "cases": [
                _case(
                    penalty_rule=(
                        "题干明确多答不得分:仅针对不妥之处+正确做法部分(P1、P2)。"
                        "若考生答出多于2项不妥之处,则P1、P2两个采分点全部清零。"
                        "本罚则不牵连记录内容列举点P3。"
                    ),
                    points=[_point(point_id="P3", list_rule="列举型", required_terms=["取样", "制样"])],
                )
            ]
        }
    )

    policy = policies[0]
    assert policy["policy_type"] == "list_rule"
    assert policy["penalty_spec"] is None


def test_policy_classifies_calculation_figure_list_and_high_risk() -> None:
    fixture = {
        "cases": [
            _case(
                points=[
                    _point(point_id="P1", point_type="calculation", required_terms=[], anchor_source="calculation"),
                    _point(point_id="P2", point_type="figure_label", required_terms=["A-B-C"], anchor_source="exam_figure"),
                    _point(
                        point_id="P3",
                        list_rule="列举型:写出五牌一图中5项满分",
                        required_terms=["工程概况牌", "安全生产牌", "文明施工牌"],
                    ),
                    _point(point_id="P4", point_type="non_textbook", required_terms=[], anchor_source="non_textbook"),
                ]
            )
        ]
    }

    by_id = {p["point_id"]: p for p in build_typed_policies(fixture)}

    assert by_id["P1"]["policy_type"] == "calculation"
    assert by_id["P2"]["policy_type"] == "figure_label"
    assert by_id["P3"]["policy_type"] == "list_rule"
    assert by_id["P3"]["list_spec"]["denominator"] == 3
    assert by_id["P4"]["policy_type"] == "high_risk_review"
    assert by_id["P4"]["policy_readiness"] == "needs_human_or_source_curation"


def test_exact_required_candidate_is_not_promoted_to_global_hard_guardrail() -> None:
    policy = build_typed_policies({"cases": [_case(points=[_point(point_id="P1")])]})[0]

    assert policy["policy_type"] == "exact_required"
    assert policy["auto_certify"] is False
    assert "not_runtime_guardrail" in policy["safety_notes"]
    assert validate_typed_policy(policy)["valid"] is True


def test_exact_required_without_required_terms_fails_validation() -> None:
    policy = build_typed_policies({"cases": [_case(points=[_point(point_id="P1", required_terms=[])])]})[0]

    validation = validate_typed_policy(policy)

    assert policy["policy_type"] == "semantic_allowed"
    assert validation["valid"] is True
    assert policy["policy_readiness"] == "ready_for_llm_adjudication"


def test_list_rule_filters_non_scoring_junk_terms() -> None:
    policy = build_typed_policies(
        {
            "cases": [
                _case(
                    points=[
                        _point(
                            point_id="P1",
                            list_rule="列举型：汽油、柴油、燃气；折算不是采分项",
                            required_terms=["折算", "汽油", "柴油", "燃气"],
                        )
                    ]
                )
            ]
        }
    )[0]

    assert policy["policy_type"] == "list_rule"
    assert policy["required_terms"] == ["汽油", "柴油", "燃气"]
    assert policy["list_spec"]["denominator"] == 3
