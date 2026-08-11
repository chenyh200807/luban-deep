"""TDD for the additive semantic-router decision telemetry tuple.

Closes the 3 instrumentation breakpoints from the 2026-05-30 baseline:
  1. raw input captured in-place (not post-join)
  2. final executed capability + drove_route (decision vs lifecycle override)
  3. non-discriminative default/fallback decisions explicitly flagged

The function is pure (no IO) so it is behavior-preserving by construction —
it only reads metadata that the orchestrator already set and never changes any
routing decision.
"""
from __future__ import annotations

from deeptutor.services.semantic_router_telemetry import build_semantic_router_telemetry


def test_primary_mode_marks_decision_as_having_driven_route() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
                "confidence": 0.92,
                "reason": "用户消息是'我选B'，提交当前题目答案。",
                "relation_to_active_object": "answer_active_object",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="我选B",
    )

    assert telemetry["drove_route"] is True
    assert telemetry["mode"] == "primary"
    assert telemetry["final_executed_capability"] == "deep_question"
    assert telemetry["captured_raw_input"] == "我选B"
    assert telemetry["semantic_decision"]["next_action"] == "route_to_grading"
    assert telemetry["semantic_decision"]["confidence"] == 0.92
    assert telemetry["is_default_template"] is False
    assert telemetry["decision_writer_chain"] == ["semantic_router"]
    assert telemetry["decision_writer_chain_source"] == "inferred"
    assert telemetry["final_decision_writer"] == "semantic_router"
    assert telemetry["decision_authority_count"] == 1
    assert telemetry["decision_overwrite_count"] == 0
    assert telemetry["legacy_selector_used"] is False
    assert telemetry["preselected_bypass_used"] is False


def test_lifecycle_override_marks_decision_as_not_driving_route() -> None:
    # Lifecycle decided deep_question before the semantic router; the recorded
    # turn_semantic_decision was bookkeeping only.
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "question_lifecycle",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.7,
                "reason": "active-object bookkeeping",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="出道题",
    )

    assert telemetry["drove_route"] is False
    assert telemetry["mode"] == "question_lifecycle"


def test_decision_capability_mismatch_with_chat_is_not_driving() -> None:
    # Decision said generation but the turn actually ran as chat (the 18% bucket).
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "disabled",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.7,
                "reason": "当前 session 仍在开放对话，但输入明显转入新练题对象。",
            },
        },
        final_executed_capability="chat",
        captured_raw_input="建筑构造是什么？",
    )

    assert telemetry["drove_route"] is False
    assert telemetry["final_executed_capability"] == "chat"


def test_default_template_reason_is_flagged() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.7,
                "reason": "当前 session 仍在开放对话，但输入明显转入新练题对象。",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="",
    )

    assert telemetry["is_default_template"] is True
    assert telemetry["fallback_decision_reason_prefix"].startswith("当前 session 仍在开放对话")


def test_deterministic_fallback_reason_is_flagged() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
                "confidence": 0.55,
                "reason": "deterministic fallback 命中题目追问特征，作为语义降级保底。",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="我选C",
    )

    assert telemetry["is_default_template"] is True


def test_hold_and_wait_zero_confidence_is_flagged_non_discriminative() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "hold_and_wait",
                "confidence": 0.0,
                "reason": "uncertain",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="为什么",
    )

    assert telemetry["is_default_template"] is True


def test_missing_decision_is_safe() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={},
        final_executed_capability="chat",
        captured_raw_input="你好",
    )

    assert telemetry["drove_route"] is False
    assert telemetry["mode"] == ""
    assert telemetry["semantic_decision"] == {}
    assert telemetry["is_default_template"] is False
    assert telemetry["captured_raw_input"] == "你好"
    assert telemetry["decision_writer_chain"] == []
    assert telemetry["decision_writer_chain_source"] == "none"
    assert telemetry["decision_schema_valid"] is False


def test_preselected_and_legacy_modes_surface_competing_authority() -> None:
    preselected = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "preselected",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.5,
                "reason": "request hint selected capability",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="出题",
    )
    assert preselected["preselected_bypass_used"] is True
    assert preselected["decision_writer_chain"] == ["preselected_capability"]
    assert preselected["decision_writer_chain_source"] == "inferred"
    assert preselected["deep_question_canonical_decision_missing"] is True

    legacy = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "disabled",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
                "confidence": 0.55,
                "reason": "deterministic fallback 命中题目追问特征，作为语义降级保底。",
            },
        },
        final_executed_capability="chat",
        captured_raw_input="为什么",
    )
    assert legacy["legacy_selector_used"] is True
    assert legacy["decision_writer_chain"] == ["legacy_selector"]
    assert legacy["fallback_decision_reason_prefix"].startswith("deterministic fallback")


def test_explicit_writer_chain_reports_overwrites_without_deciding_route() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision_writer_chain": [
                "turn_runtime_question_domain_adapter",
                "semantic_router",
            ],
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
                "confidence": 0.92,
                "reason": "canonical",
                "relation_to_active_object": "answer_active_object",
                "allowed_patch": "update_answer_slot",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="B",
    )

    assert telemetry["decision_writer_chain"] == [
        "turn_runtime_question_domain_adapter",
        "semantic_router",
    ]
    assert telemetry["decision_writer_chain_source"] == "recorded"
    assert telemetry["decision_authority_count"] == 2
    assert telemetry["decision_overwrite_count"] == 1
    assert telemetry["decision_schema_valid"] is True
    assert telemetry["deep_question_canonical_decision_missing"] is False


def test_build_telemetry_event_payload_is_internal_turn_event() -> None:
    from deeptutor.services.semantic_router_telemetry import (
        build_semantic_router_telemetry_event,
    )

    event = build_semantic_router_telemetry_event(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
                "confidence": 0.92,
                "reason": "用户消息是'我选B'。",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="我选B",
    )

    assert event["type"] == "observation"
    assert event["source"] == "turn_runtime"
    assert event["stage"] == "semantic_router_telemetry"
    assert event["visibility"] == "internal"
    tele = event["metadata"]["semantic_router_telemetry"]
    assert tele["drove_route"] is True
    assert tele["captured_raw_input"] == "我选B"
    assert tele["final_executed_capability"] == "deep_question"


# ---------------------------------------------------------------------------
# 路由收权 shadow 度量(2026-08-11,observe-only,contracts/capability.md 条款 32
# 追加三键):_classify_scene_divergence 纯分类函数 + payload 三键装配。
# ---------------------------------------------------------------------------


def test_scene_divergence_t1_llm_verdict_gate_vetoed() -> None:
    """T1(F2 形态):LLM 判了 scene、业务闸整案否决(blocked_*)。"""
    from deeptutor.services.semantic_router_telemetry import _classify_scene_divergence

    assert (
        _classify_scene_divergence(
            llm_candidate={"scene": "mcq_grading", "confidence": 0.95, "reason": "作答"},
            final_scene=None,
            decision_source="deterministic",
            business_gate_result="blocked_low_information_exam_query",
        )
        == "llm_verdict_gate_vetoed"
    )


def test_scene_divergence_t2_llm_none_or_threshold_drop() -> None:
    """T2:candidate 非 None 但 scene 为空(自判 none 或 0.72 阈值砍掉)。"""
    from deeptutor.services.semantic_router_telemetry import _classify_scene_divergence

    assert (
        _classify_scene_divergence(
            llm_candidate={"scene": None, "confidence": 0.6, "reason": "不确定"},
            final_scene=None,
            decision_source="none",
            business_gate_result="no_candidate",
        )
        == "llm_none_or_threshold_drop"
    )


def test_scene_divergence_threshold_dropped_candidate_still_classified_as_gate_vetoed() -> None:
    """PR3-R4(F6):0.72 阈值把 candidate["scene"] 置空后,gate 否决整类曾被误分到 T2。
    原始判定留档在 raw_scene,判 gate 否决时优先用它 → 仍是 T1。"""
    from deeptutor.services.semantic_router_telemetry import _classify_scene_divergence

    assert (
        _classify_scene_divergence(
            llm_candidate={
                "scene": None,
                "confidence": 0.55,
                "reason": "像是要真题答案",
                "raw_scene": "question_review",
                "raw_confidence": 0.55,
            },
            final_scene=None,
            decision_source="deterministic",
            business_gate_result="blocked_low_information_exam_query",
        )
        == "llm_verdict_gate_vetoed"
    )
    # 闸未 block 时语义不变:阈值砍除仍归 T2(不因 raw_scene 在场就改判)。
    assert (
        _classify_scene_divergence(
            llm_candidate={
                "scene": None,
                "confidence": 0.55,
                "reason": "不确定",
                "raw_scene": "question_review",
                "raw_confidence": 0.55,
            },
            final_scene=None,
            decision_source="none",
            business_gate_result="no_candidate",
        )
        == "llm_none_or_threshold_drop"
    )


def test_scene_divergence_t3_deterministic_preempt_no_llm() -> None:
    """T3(覆盖率盲区,非分歧):确定性抢答,LLM 未被咨询。"""
    from deeptutor.services.semantic_router_telemetry import _classify_scene_divergence

    assert (
        _classify_scene_divergence(
            llm_candidate=None,
            final_scene="practice_generation",
            decision_source="deterministic",
            business_gate_result="passed",
        )
        == "deterministic_preempt_no_llm"
    )


def test_scene_divergence_t4_gate_blocked_llm_unavailable() -> None:
    """T4:闸 block 且 LLM 调用失败/超时(candidate=None),或 llm_unavailable。"""
    from deeptutor.services.semantic_router_telemetry import _classify_scene_divergence

    assert (
        _classify_scene_divergence(
            llm_candidate=None,
            final_scene=None,
            decision_source="deterministic",
            business_gate_result="blocked_unanchored_answer_submission",
        )
        == "gate_blocked_llm_unavailable"
    )
    assert (
        _classify_scene_divergence(
            llm_candidate=None,
            final_scene=None,
            decision_source="llm",
            business_gate_result="llm_unavailable",
        )
        == "gate_blocked_llm_unavailable"
    )


def test_scene_divergence_agreement_and_conflict_and_defensive_buckets() -> None:
    """agreement / llm_scene_conflicts_final / 防御桶(scene_without_source 预期恒 0,
    仅在 source 缺失异常态出现)/ 无 scene 开放聊天桶。"""
    from deeptutor.services.semantic_router_telemetry import _classify_scene_divergence

    assert (
        _classify_scene_divergence(
            llm_candidate={"scene": "practice_generation", "confidence": 0.9, "reason": "出题"},
            final_scene="practice_generation",
            decision_source="llm",
            business_gate_result="passed",
        )
        == "agreement"
    )
    assert (
        _classify_scene_divergence(
            llm_candidate={"scene": "mcq_grading", "confidence": 0.9, "reason": "作答"},
            final_scene="practice_generation",
            decision_source="deterministic",
            business_gate_result="passed",
        )
        == "llm_scene_conflicts_final"
    )
    # 防御桶:正常轮次不可能出现(scene 有值必有 source);机械可构造以证桶存在。
    assert (
        _classify_scene_divergence(
            llm_candidate=None,
            final_scene="mcq_grading",
            decision_source="",
            business_gate_result="",
        )
        == "scene_without_source"
    )
    assert (
        _classify_scene_divergence(
            llm_candidate=None,
            final_scene=None,
            decision_source="",
            business_gate_result="",
        )
        == "no_llm_no_scene"
    )


def test_telemetry_payload_carries_shadow_divergence_keys() -> None:
    """payload 三键(lifecycle_final / llm_scene_candidate / scene_divergence)
    + schema version 2;observe-only:装配为纯只读,不改任何路由 metadata。"""
    context_metadata = {
        "semantic_router_mode": "question_lifecycle",
        "semantic_router_mode_reason": "blocked_low_information_exam_query",
        "llm_scene_candidate": {"scene": "mcq_grading", "confidence": 0.95, "reason": "作答"},
        "question_lifecycle_scene": None,
        "question_lifecycle_scene_source": "deterministic",
        "business_gate_result": "blocked_low_information_exam_query",
    }
    telemetry = build_semantic_router_telemetry(
        context_metadata=context_metadata,
        final_executed_capability="tutorbot",
        captured_raw_input="2025真题",
    )

    assert telemetry["authority_probe_schema_version"] == 2
    assert telemetry["scene_divergence"] == "llm_verdict_gate_vetoed"
    assert telemetry["llm_scene_candidate"] == {
        "scene": "mcq_grading",
        "confidence": 0.95,
        "reason": "作答",
    }
    assert telemetry["lifecycle_final"] == {
        "scene": None,
        "source": "deterministic",
        "business_gate_result": "blocked_low_information_exam_query",
        "mode_reason": "blocked_low_information_exam_query",
    }
