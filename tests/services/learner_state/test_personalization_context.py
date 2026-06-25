from __future__ import annotations

from deeptutor.services.learner_state.personalization_context import (
    build_personalization_context_pack,
)
from deeptutor.services.learner_state.training_intent import build_learning_training_intent


def test_personalization_context_pack_is_read_only_view_over_claims_and_training_intent() -> None:
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A432000",
        concept_label="工程招标投标与合同管理",
        error_code="M06",
        error_label="多选漏选",
        evidence_refs=["evt_claim_1", "evt_claim_2"],
        training_mode="case_repair",
    )
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "claim_confirmed",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A432000",
                    "label": "工程招标投标与合同管理：多选漏选",
                    "supporting_event_ids": ["evt_claim_1", "evt_claim_2"],
                    "confidence": 0.82,
                },
                {
                    "object_id": "claim_stale",
                    "object_type": "error",
                    "claim_status": "stale",
                    "label": "旧的薄弱点",
                    "evidence_refs": ["evt_old"],
                    "confidence": 0.51,
                },
            ]
        },
        active_training_intent=intent,
        recent_events=[{"event_id": "evt_recent"}],
    )

    assert pack["schema_version"] == 1
    assert pack["source"] == "PersonalizationContextPack"
    assert pack["authority"]["claims"] == "learning_synthesis"
    assert pack["authority"]["prescription"] == "training_intent"
    assert pack["top_claims"][0]["claim_id"] == "claim_confirmed"
    assert pack["top_claims"][0]["evidence_refs"] == ["evt_claim_1", "evt_claim_2"]
    assert pack["recent_evidence_refs"] == ["evt_recent", "evt_claim_1", "evt_claim_2"]
    assert pack["active_training_intent"]["training_intent_id"] == intent["training_intent_id"]
    assert pack["next_best_action_candidates"][0]["training_intent_id"] == intent["training_intent_id"]
    assert pack["next_best_action_candidates"][0]["prescription_authority"] == "training_intent"
    assert pack["gaps"] == [{"claim_id": "claim_stale", "reason": "claim_stale"}]


def test_personalization_context_treats_string_evidence_ref_as_single_ref() -> None:
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "claim_string_ref",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A432000",
                    "label": "防水工程薄弱",
                    "evidence_refs": "evt_string",
                }
            ]
        },
    )

    assert pack["top_claims"][0]["evidence_refs"] == ["evt_string"]


def test_personalization_context_excludes_blocked_conversation_claims_from_prompt_payload() -> None:
    raw_topic = "我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题"
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": f"{raw_topic}:M07",
                    "object_type": "error",
                    "claim_status": "observed",
                    "concept_id": raw_topic,
                    "current_truth": f"长期画像提示：{raw_topic} 上出现 M07 错因",
                    "evidence_refs": ["conv_turn_1"],
                    "evidence_cap_reasons": ["conversation_signal_not_grading_truth"],
                }
            ]
        },
    )

    payload_text = str(pack)
    assert pack["top_claims"] == []
    assert pack["active_training_intent"] == {}
    assert pack["next_best_action_candidates"] == []
    assert "M07" not in payload_text
    assert "长期画像提示" not in payload_text


def test_personalization_context_humanizes_internal_error_codes_for_prompt_payload() -> None:
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "1A432000:M07",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A432000",
                    "current_truth": "1A432000 上出现 M07 错因观察",
                    "evidence_refs": ["grading_evt_1", "grading_evt_2"],
                }
            ]
        },
    )

    assert pack["top_claims"]
    claim = pack["top_claims"][0]
    assert claim["claim_id"] == "1A432000:M07"
    assert claim["error_label"] == "多选错选"
    assert "多选错选" in claim["label"]
    assert "长期画像提示" not in str(pack)


def test_personalization_context_derives_next_action_from_confirmed_long_term_claim() -> None:
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "1A413050:E02",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A413050",
                    "label": "屋面与防水工程施工：采分点遗漏",
                    "supporting_event_ids": ["teacher_final_evt"],
                    "evidence_refs": ["teacher_final_evt"],
                    "confidence": 0.92,
                }
            ]
        },
        active_training_intent=None,
    )

    assert pack["active_training_intent"]["source"] == "PersonalizationContextPack"
    assert pack["active_training_intent"]["concept_id"] == "1A413050"
    assert pack["active_training_intent"]["evidence_refs"] == ["teacher_final_evt"]
    nba = pack["next_best_action_candidates"][0]
    assert nba["prescription_authority"] == "training_intent"
    assert nba["evidence_refs"] == ["teacher_final_evt"]
    assert "防水" in nba["target"]


def test_personalization_context_passes_real_graph_chain_to_next_best_action() -> None:
    """图谱自接线：learning_brain 投影里的 typed_graph 必须作为 graph_chain
    传给 next_best_action，使 why_this_now 基于真实错因图而非泛化的证据计数。"""
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A415000",
        concept_label="屋面与防水工程施工",
        error_code="M06",
        error_label="近义替代原文术语",
        evidence_refs=["evt_2"],
        training_mode="case_repair",
    )
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={
            "compiled_objects": [
                {
                    "object_id": "1A415000:M06",
                    "object_type": "error",
                    "claim_status": "confirmed",
                    "concept_id": "1A415000",
                    "label": "屋面与防水工程施工：近义替代",
                    "supporting_event_ids": ["evt_2"],
                    "confidence": 0.8,
                }
            ],
            "typed_graph": {
                "schema_version": 1,
                "edges": [
                    {
                        "edge_type": "error_points_to_training",
                        "from": {"type": "error", "id": "1A415000:M06"},
                        "to": {"type": "training", "id": "training_waterproof_terms"},
                        "evidence_event_id": "evt_2",
                    }
                ],
            },
        },
        active_training_intent=intent,
    )

    nba = pack["next_best_action_candidates"][0]
    assert nba["why_this_now"] == "真实错因图已把该薄弱点连接到下一轮训练。"


def _claim_with_timeline(observed_at: str) -> dict:
    return {
        "object_id": "1A413050:M06",
        "object_type": "error",
        "claim_status": "confirmed",
        "concept_id": "1A413050",
        "label": "屋面与防水工程施工：采分点遗漏",
        "supporting_event_ids": ["evt_old"],
        "confidence": 0.9,
        "decay_state": "active",
        "occurrence_timeline": [
            {"event_id": "evt_old", "observed_at": observed_at, "question_id": "Q1", "turn_id": "t1"}
        ],
    }


def test_personalization_context_surfaces_review_due_by_time_rule() -> None:
    """时间维度（遗忘曲线第一步）：active claim 末次证据超过阈值天数即进入
    review_due 只读视图，并优先成为无显式 intent 时的下一步动作来源。
    纯时间规则、零 LLM；不改变 claim 本身的任何权威状态。"""
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={"compiled_objects": [_claim_with_timeline("2026-05-01T10:00:00+08:00")]},
        active_training_intent=None,
        now=1781222400.0,  # 2026-06-12 前后
    )

    due = pack["review_due"]
    assert len(due) == 1
    assert due[0]["claim_id"] == "1A413050:M06"
    assert due[0]["concept_id"] == "1A413050"
    assert due[0]["days_since_last_evidence"] >= 14
    # 无显式 intent 时，复习项优先驱动下一步动作
    assert pack["active_training_intent"]["concept_id"] == "1A413050"
    nba = pack["next_best_action_candidates"][0]
    assert nba["prescription_authority"] == "training_intent"


def test_personalization_context_review_due_empty_for_fresh_claims() -> None:
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={"compiled_objects": [_claim_with_timeline("2026-06-11T10:00:00+08:00")]},
        active_training_intent=None,
        now=1781222400.0,
    )

    assert pack["review_due"] == []


def test_personalization_context_review_due_skips_improving_claims() -> None:
    claim = _claim_with_timeline("2026-05-01T10:00:00+08:00")
    claim["decay_state"] = "improving"
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={"compiled_objects": [claim]},
        active_training_intent=None,
        now=1781222400.0,
    )

    assert pack["review_due"] == []


def test_review_due_uses_true_last_evidence_not_truncated_timeline() -> None:
    """回归钉：occurrence_timeline 展示截断为最早 5 条；review_due 必须用完整
    timeline 的真末次时间——6+ 次出现且昨天刚练过的 claim 不得被误判该复习。"""
    claim = _claim_with_timeline("2026-05-01T10:00:00+08:00")
    claim["occurrence_timeline"] = [
        {"event_id": f"evt_{i}", "observed_at": f"2026-05-0{i}T10:00:00+08:00", "question_id": "Q", "turn_id": "t"}
        for i in range(1, 7)
    ] + [
        {"event_id": "evt_recent", "observed_at": "2026-06-11T10:00:00+08:00", "question_id": "Q", "turn_id": "t"}
    ]
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={"compiled_objects": [claim]},
        active_training_intent=None,
        now=1781222400.0,
    )

    assert pack["review_due"] == []
    assert pack["top_claims"][0]["last_observed_at"] == "2026-06-11T10:00:00+08:00"


def test_review_due_claim_is_preferred_over_fresh_claim_for_intent() -> None:
    """判别性测试：复习项优先逻辑必须真的在两个 claim 里选中过期那个，
    而不是退化为 claims[0]。"""
    fresh = _claim_with_timeline("2026-06-11T10:00:00+08:00")
    fresh["object_id"] = "1A999999:M01"
    fresh["concept_id"] = "1A999999"
    fresh["confidence"] = 0.99  # 排在前面，确保 claims[0]=fresh
    stale = _claim_with_timeline("2026-05-01T10:00:00+08:00")
    pack = build_personalization_context_pack(
        user_id="student_demo",
        learning_brain={"compiled_objects": [fresh, stale]},
        active_training_intent=None,
        now=1781222400.0,
    )

    assert pack["active_training_intent"]["concept_id"] == "1A413050"


def test_personalization_context_pack_schema_id_is_registered_as_t2() -> None:
    """The single producer's canonical SCHEMA_ID must be registered T2 in the schema
    registry (no unregistered/competing PCP schema can appear). This is the
    register-before-use promotion of a previously integer-versioned, closure-invisible
    cross-domain runtime contract (schema-governance P2, registry beyond grading)."""
    from pathlib import Path

    import yaml

    from deeptutor.services.learner_state.personalization_context import SCHEMA_ID

    assert SCHEMA_ID == "personalization_context_pack.v1"
    registry = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "contracts" / "schema_registry.yaml").read_text("utf-8")
    )
    t2_names = {e["name"] for e in registry["tier2_canonical_contracts"]}
    assert SCHEMA_ID in t2_names, f"{SCHEMA_ID} must be a registered T2 runtime-canonical contract"
