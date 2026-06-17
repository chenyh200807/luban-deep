"""artifact_first_llm_judge — 受 compiled artifact 约束的单次低成本 LLM judge runtime arm。

约束矩阵（与 M35 计划 §4.5 deterministic vs LLM boundary 对齐）：
- LLM 只判语义命中，不得改 rubric、不得新增 answer key、不得给未知 point 发分。
- 无 evidence_span（或 span 不在学生作答原文中）不得给 hit/partial。
- exact_required / calculation / list 必须受 deterministic validator 约束。
- confidence 低或与 deterministic 冲突时 high_risk_review=True，不 fail-open（不发分）。
- 只对 deterministic prescreen 判定为 uncertain 的点触发 LLM（成本策略）。
"""
from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.construction_grading.artifact_first_llm_judge import (
    PRESCREEN_CONFIDENT_HIT,
    PRESCREEN_CONFIDENT_MISS,
    PRESCREEN_UNCERTAIN,
    adjudicate_with_artifact_judge,
    constrain_verdict,
    deterministic_prescreen,
)


def _point(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "point_id": "Q1::SP01",
        "criterion": "指出需要组织专家论证",
        "max_score": 2.0,
        "policy_type": "qualitative",
        "required_terms": [],
        "negative_evidence": [],
        "source_refs": [{"source_type": "exam_reference_answer", "source_id": "S1"}],
    }
    base.update(overrides)
    return base


def _no_llm_judge(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
    raise AssertionError("judge_fn must not be called for deterministic-resolved points")


# ---------------------------------------------------------------------------
# deterministic prescreen（成本策略：confident 点不触发 LLM）
# ---------------------------------------------------------------------------

def test_prescreen_empty_answer_is_confident_miss():
    out = deterministic_prescreen(_point(), "")
    assert out["decision"] == PRESCREEN_CONFIDENT_MISS


def test_prescreen_exact_required_all_terms_present_is_confident_hit():
    point = _point(policy_type="exact_required", required_terms=["专家论证"])
    out = deterministic_prescreen(point, "本工程需组织专家论证后方可实施。")
    assert out["decision"] == PRESCREEN_CONFIDENT_HIT
    assert out["matched_terms"] == ["专家论证"]


def test_prescreen_exact_required_missing_term_is_uncertain_not_auto_miss():
    # 术语缺失仍可能是近义表达，交 LLM 判 near_synonym_not_exact 与 evidence —— 但不会得分（见 constrain）
    point = _point(policy_type="exact_required", required_terms=["专家论证"])
    out = deterministic_prescreen(point, "应该请专家开会讨论一下。")
    assert out["decision"] == PRESCREEN_UNCERTAIN


def test_prescreen_qualitative_is_uncertain_even_with_terms_present():
    # 定性点不能只靠词面命中直接发分（防止否定句/抄题面误判），必须 LLM 语义裁决
    point = _point(required_terms=["专家论证"])
    out = deterministic_prescreen(point, "不需要组织专家论证。")
    assert out["decision"] == PRESCREEN_UNCERTAIN


def test_prescreen_negative_evidence_match_blocks_confident_hit():
    point = _point(
        policy_type="exact_required",
        required_terms=["专家论证"],
        negative_evidence=["仅写专项方案但未写专家论证"],
    )
    out = deterministic_prescreen(point, "编制专项方案。专家论证。")
    # negative evidence 存在时不允许 deterministic 直接发分，必须走 LLM + 约束
    assert out["decision"] == PRESCREEN_UNCERTAIN


# ---------------------------------------------------------------------------
# constrain_verdict（deterministic validator 收权）
# ---------------------------------------------------------------------------

def test_hit_without_evidence_span_is_not_credited():
    point = _point()
    out = constrain_verdict(point, {"status": "hit", "confidence": 0.95, "evidence_span": ""},
                            "需要组织专家论证")
    assert out["status"] == "miss"
    assert out["awarded_score"] == 0.0
    assert out["high_risk_review"] is True
    assert "evidence_span" in out["reason"]


def test_hit_with_fabricated_evidence_span_is_not_credited():
    point = _point()
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.95, "evidence_span": "学生从未写过的句子"},
        "需要组织专家论证",
    )
    assert out["status"] == "miss"
    assert out["awarded_score"] == 0.0
    assert out["high_risk_review"] is True


def test_exact_required_llm_hit_without_term_is_demoted():
    point = _point(policy_type="exact_required", required_terms=["专家论证"])
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.9, "evidence_span": "请专家开会讨论"},
        "应该请专家开会讨论一下。",
    )
    assert out["status"] == "miss"
    assert out["awarded_score"] == 0.0
    assert out["mistake_type"] == "near_synonym_not_exact"


def test_calculation_expected_value_absent_is_demoted():
    point = _point(
        policy_type="calculation",
        calculation_spec={"expected_value": "31.5"},
    )
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.9, "evidence_span": "工期为30天"},
        "工期为30天",
    )
    assert out["status"] == "miss"
    assert out["awarded_score"] == 0.0
    assert out["high_risk_review"] is True


def test_calculation_expected_value_present_is_credited():
    point = _point(
        policy_type="calculation",
        max_score=3.0,
        calculation_spec={"expected_value": "31.5"},
    )
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.9, "evidence_span": "总工期为31.5天"},
        "经计算，总工期为31.5天。",
    )
    assert out["status"] == "hit"
    assert out["awarded_score"] == 3.0


def test_list_rule_partial_ratio_is_deterministic_from_validated_items():
    point = _point(
        policy_type="list_rule",
        max_score=4.0,
        required_terms=["排水沟", "集水井", "降水井", "截水帷幕"],
        list_spec={"denominator": 4},
    )
    out = constrain_verdict(
        point,
        {
            "status": "partial",
            "confidence": 0.9,
            "evidence_span": "设置排水沟和集水井",
            "matched_items": ["排水沟", "集水井", "降水井"],  # 降水井是 LLM 虚报，作答里没有
        },
        "基坑周边设置排水沟和集水井。",
    )
    assert out["status"] == "partial"
    # 只有 2 项能在作答原文中验证：4.0 * 2/4 = 2.0；LLM 虚报的第 3 项不得计入
    assert out["awarded_score"] == 2.0


def test_low_confidence_is_high_risk_and_not_fail_open():
    point = _point()
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.3, "evidence_span": "需要组织专家论证"},
        "需要组织专家论证",
    )
    assert out["high_risk_review"] is True
    assert out["awarded_score"] == 0.0


def test_negative_evidence_matched_span_is_not_credited():
    point = _point(negative_evidence=["仅编制专项方案"])
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.9, "evidence_span": "仅编制专项方案"},
        "我们仅编制专项方案。",
    )
    assert out["status"] == "miss"
    assert out["awarded_score"] == 0.0
    assert out["high_risk_review"] is True


# ---------------------------------------------------------------------------
# adjudicate_with_artifact_judge（整卷编排 + 成本策略 + 安全不变量）
# ---------------------------------------------------------------------------

def test_confident_points_do_not_trigger_llm():
    points = [
        _point(point_id="Q1::SP01", policy_type="exact_required", required_terms=["专家论证"]),
    ]
    result = adjudicate_with_artifact_judge(
        question_id="Q1",
        artifact_version="m35_test_v1",
        scoring_points=points,
        student_answer="需组织专家论证。",
        judge_fn=_no_llm_judge,
    )
    assert result["awarded_score"] == 2.0
    assert result["judge_called_point_ids"] == []
    match = result["point_matches"][0]
    assert match["status"] == "hit"
    assert match["evidence_span"]  # deterministic 命中也必须带 span
    assert match["adjudication_route"] == "deterministic_prescreen"


def test_uncertain_points_trigger_llm_and_are_constrained():
    captured: dict[str, Any] = {}

    def judge(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
        captured["point_ids"] = [p["point_id"] for p in points]
        return {
            "Q1::SP02": {
                "status": "hit",
                "confidence": 0.92,
                "evidence_span": "做好防水保护层",
                "mistake_type": "",
            },
        }

    points = [
        _point(point_id="Q1::SP01", policy_type="exact_required", required_terms=["专家论证"]),
        _point(point_id="Q1::SP02", criterion="说明需做防水保护层", max_score=3.0),
    ]
    result = adjudicate_with_artifact_judge(
        question_id="Q1",
        artifact_version="m35_test_v1",
        scoring_points=points,
        student_answer="需组织专家论证。施工时做好防水保护层。",
        judge_fn=judge,
    )
    assert captured["point_ids"] == ["Q1::SP02"]   # 只送 uncertain 点
    assert result["awarded_score"] == 5.0
    assert result["judge_called_point_ids"] == ["Q1::SP02"]


def test_llm_cannot_mint_points_outside_artifact():
    def judge(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
        return {
            "Q1::SP02": {"status": "hit", "confidence": 0.9, "evidence_span": "防水保护层"},
            "Q1::FAKE": {"status": "hit", "confidence": 0.99, "evidence_span": "防水保护层"},
        }

    points = [_point(point_id="Q1::SP02", criterion="防水保护层", max_score=3.0)]
    result = adjudicate_with_artifact_judge(
        question_id="Q1",
        artifact_version="m35_test_v1",
        scoring_points=points,
        student_answer="做好防水保护层。",
        judge_fn=judge,
    )
    assert [m["point_id"] for m in result["point_matches"]] == ["Q1::SP02"]
    assert result["awarded_score"] == 3.0
    assert result["max_score"] == 3.0


def test_missing_llm_verdict_is_miss_with_high_risk_not_silent_credit():
    def judge(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
        return {}

    points = [_point(point_id="Q1::SP02", max_score=3.0)]
    result = adjudicate_with_artifact_judge(
        question_id="Q1",
        artifact_version="m35_test_v1",
        scoring_points=points,
        student_answer="做好防水保护层。",
        judge_fn=judge,
    )
    match = result["point_matches"][0]
    assert match["status"] == "miss"
    assert match["high_risk_review"] is True
    assert result["high_risk_review"] is True


def test_result_safety_invariants():
    result = adjudicate_with_artifact_judge(
        question_id="Q1",
        artifact_version="m35_test_v1",
        scoring_points=[_point()],
        student_answer="",
        judge_fn=_no_llm_judge,   # 空作答 → confident_miss，不触发 LLM
    )
    assert result["official_score_allowed"] is False
    assert result["is_release_truth"] is False
    assert result["quality_claim_allowed"] is False
    assert result["artifact_version"] == "m35_test_v1"
    assert result["awarded_score"] == 0.0
    # 每个 point match 必须带齐输出契约字段
    match = result["point_matches"][0]
    for key in ("point_id", "status", "awarded_score", "max_score", "evidence_span",
                "mistake_type", "confidence", "high_risk_review", "reason",
                "adjudication_route"):
        assert key in match


def test_deterministic_sum_matches_point_awards():
    def judge(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
        return {
            p["point_id"]: {"status": "hit", "confidence": 0.9,
                            "evidence_span": "排水沟"}
            for p in points
        }

    points = [
        _point(point_id="P1", criterion="排水沟", max_score=1.5),
        _point(point_id="P2", criterion="集水井", max_score=2.5),
    ]
    result = adjudicate_with_artifact_judge(
        question_id="Q1",
        artifact_version="v",
        scoring_points=points,
        student_answer="设置排水沟。",
        judge_fn=judge,
    )
    assert result["awarded_score"] == pytest.approx(
        sum(m["awarded_score"] for m in result["point_matches"])
    )


# ---------------------------------------------------------------------------
# make_retrying_batch_judge（missing-verdict 一次重试，仍然 fail-closed）
# ---------------------------------------------------------------------------

def test_retrying_judge_retries_only_missing_points():
    from deeptutor.services.construction_grading.artifact_first_llm_judge import (
        make_retrying_batch_judge,
    )
    calls: list[list[str]] = []

    def flaky(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
        calls.append([p["point_id"] for p in points])
        if len(calls) == 1:
            return {"P1": {"status": "hit", "confidence": 0.9, "evidence_span": "排水沟"}}
        return {"P2": {"status": "miss", "confidence": 0.9, "evidence_span": ""}}

    judge = make_retrying_batch_judge(flaky, max_retries=1)
    out = judge([_point(point_id="P1"), _point(point_id="P2")], "设置排水沟")
    assert calls == [["P1", "P2"], ["P2"]]      # 第二次只重试缺失点
    assert set(out) == {"P1", "P2"}


def test_retrying_judge_fail_closed_after_budget():
    from deeptutor.services.construction_grading.artifact_first_llm_judge import (
        make_retrying_batch_judge,
    )

    def always_empty(points: list[dict[str, Any]], answer: str) -> dict[str, dict[str, Any]]:
        return {}

    judge = make_retrying_batch_judge(always_empty, max_retries=1)
    out = judge([_point(point_id="P1")], "作答")
    assert out == {}                             # 重试用尽仍缺 → 交回模块按 miss+high_risk fail-closed


# ---------------------------------------------------------------------------
# to_rubric_grading_event（Phase 2 桥：judge 结果 → rubric_grader_v1 GradingEvent 形状）
# ---------------------------------------------------------------------------

def test_to_rubric_grading_event_maps_point_matches():
    from deeptutor.services.construction_grading.artifact_first_llm_judge import (
        to_rubric_grading_event,
    )
    judge_result = {
        "question_id": "Q1",
        "student_id": "S01",
        "artifact_version": "m35_v1",
        "awarded_score": 2.0,
        "max_score": 5.0,
        "high_risk_review": True,
        "point_matches": [
            {"point_id": "P1", "criterion": "排水沟", "status": "hit", "awarded_score": 2.0,
             "max_score": 2.0, "policy_type": "qualitative", "evidence_span": "设置排水沟",
             "mistake_type": "", "confidence": 0.9, "high_risk_review": False, "reason": "llm_hit",
             "adjudication_route": "llm_constrained"},
            {"point_id": "P2", "criterion": "集水井", "status": "miss", "awarded_score": 0.0,
             "max_score": 3.0, "policy_type": "qualitative", "evidence_span": "",
             "mistake_type": "omitted", "confidence": 0.8, "high_risk_review": True,
             "reason": "llm_miss", "adjudication_route": "llm_constrained"},
        ],
    }
    event = to_rubric_grading_event(judge_result)
    assert event["event_type"] == "case_grading_completed"
    assert event["question_id"] == "Q1"
    assert event["awarded_score"] == 2.0
    assert event["official_score_allowed"] is False
    sps = event["scoring_points"]
    assert sps[0]["hit"] == "hit" and sps[0]["score"] == 2.0
    assert sps[1]["hit"] == "miss" and sps[1]["mistake_type"] == "omitted"
    assert sps[1]["knowledge_point"] == "集水井"
    # 必须能被 rubric_grader_v1.to_learning_evidence 直接消费
    from deeptutor.services.construction_grading.rubric_grader_v1 import to_learning_evidence
    payload = to_learning_evidence(event, node_code="1A420000")
    assert payload["learning_signal_type"] == "case_grading"
    assert payload["weak_points"] and payload["weak_points"][0]["concept_label"] == "集水井"
    assert payload["writeback_performed"] is False


def test_derived_calculation_spec_is_advisory_not_hard_gate():
    # criterion_number_parse 派生的 expected_value 是低置信猜测（如把"三星级85分"门槛当结果），
    # 不得作为硬闸清零 LLM 裁决；只允许 advisory：保留得分 + high_risk 进人审。
    point = _point(
        policy_type="calc",
        max_score=6.0,
        calculation_spec={
            "expected_value": "85",
            "provenance": {"source": "criterion_number_parse", "confidence": 0.6,
                           "field_hash": "sha256:x"},
        },
    )
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.9, "evidence_span": "空缺评分项：安全耐久"},
        "空缺评分项：安全耐久、健康舒适、生活便利、环境宜居。",
    )
    assert out["status"] == "hit"
    assert out["awarded_score"] == 6.0
    assert out["high_risk_review"] is True
    assert "unverified" in out["reason"]


def test_artifact_supplied_calculation_spec_remains_hard_gate():
    point = _point(
        policy_type="calculation",
        max_score=3.0,
        calculation_spec={
            "expected_value": "31.5",
            "provenance": {"source": "artifact_calculation_spec", "confidence": 1.0,
                           "field_hash": "sha256:x"},
        },
    )
    out = constrain_verdict(
        point,
        {"status": "hit", "confidence": 0.9, "evidence_span": "工期为30天"},
        "工期为30天",
    )
    assert out["status"] == "miss"
    assert out["awarded_score"] == 0.0


# ---------------------------------------------------------------------------
# Codex 对抗审查修复（2026-06-11）：刷分/NaN/否定句/advisory丢失/重试异常
# ---------------------------------------------------------------------------

def test_list_matched_items_deduped_and_restricted_to_official_items():
    point = _point(
        policy_type="list_rule", max_score=4.0,
        required_terms=["排水沟", "集水井", "降水井", "截水帷幕"],
        list_spec={"denominator": 4},
    )
    out = constrain_verdict(
        point,
        {"status": "partial", "confidence": 0.9, "evidence_span": "设置排水沟",
         "matched_items": ["排水沟", "排水沟", "排水沟", "排水沟"]},   # 重复虚报
        "基坑周边设置排水沟。",
    )
    assert out["awarded_score"] == 1.0     # 去重后只有 1 项：4.0 * 1/4


def test_list_matched_items_outside_official_set_rejected():
    point = _point(
        policy_type="list_rule", max_score=4.0,
        required_terms=["排水沟", "集水井"],
        list_spec={"denominator": 2},
    )
    out = constrain_verdict(
        point,
        {"status": "partial", "confidence": 0.9, "evidence_span": "设置排水沟",
         "matched_items": ["排水沟", "基坑"]},   # "基坑"不在官方项集但在作答原文中
        "基坑周边设置排水沟。",
    )
    assert out["awarded_score"] == 2.0     # 只认官方项：2/2 中的 1 项 → 4.0*1/2


def test_nan_confidence_is_demoted_not_full_credit():
    out = constrain_verdict(
        _point(),
        {"status": "hit", "confidence": float("nan"), "evidence_span": "需要组织专家论证"},
        "需要组织专家论证",
    )
    assert out["awarded_score"] == 0.0
    assert out["high_risk_review"] is True


def test_inf_partial_ratio_does_not_award_above_max():
    out = constrain_verdict(
        _point(max_score=2.0),
        {"status": "partial", "confidence": 0.9, "partial_ratio": float("inf"),
         "evidence_span": "需要组织专家论证"},
        "需要组织专家论证",
    )
    assert out["awarded_score"] == 0.0
    assert out["high_risk_review"] is True


def test_prescreen_negation_near_term_routes_to_llm():
    point = _point(policy_type="exact_required", required_terms=["专家论证"])
    out = deterministic_prescreen(point, "本工程不需要组织专家论证。")
    assert out["decision"] == PRESCREEN_UNCERTAIN   # 否定线索 → 交 LLM，不得自动发分


def test_derived_calc_advisory_survives_partial_branch():
    point = _point(
        policy_type="calc", max_score=6.0,
        calculation_spec={"expected_value": "85",
                          "provenance": {"source": "criterion_number_parse",
                                         "confidence": 0.6, "field_hash": "sha256:x"}},
    )
    out = constrain_verdict(
        point,
        {"status": "partial", "confidence": 0.9, "partial_ratio": 0.5,
         "evidence_span": "空缺评分项：安全耐久"},
        "空缺评分项：安全耐久、健康舒适。",
    )
    assert out["awarded_score"] == 3.0
    assert out["high_risk_review"] is True          # advisory 不得在 partial 分支丢失


def test_retrying_judge_swallows_base_exception_fail_closed():
    from deeptutor.services.construction_grading.artifact_first_llm_judge import (
        make_retrying_batch_judge,
    )

    def explode(points, answer):
        raise RuntimeError("provider down")

    judge = make_retrying_batch_judge(explode, max_retries=1)
    assert judge([_point(point_id="P1")], "作答") == {}   # 异常 → 空 verdict → miss+high_risk
