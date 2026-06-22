from __future__ import annotations

from deeptutor.services.learner_state.learning_synthesis import _ALLOWED_EDGE_TYPES
from deeptutor.services.learner_state.next_best_action import (
    ACTIONABLE_EDGE_TYPES,
    build_next_best_actions,
)
from deeptutor.services.learner_state.training_intent import build_learning_training_intent


def test_next_best_actions_are_views_over_training_intent() -> None:
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A432000",
        concept_label="工程招标投标与合同管理",
        error_code="E02",
        error_label="采分点遗漏",
        evidence_refs=["evt1", "evt2"],
        training_mode="case_repair",
    )
    action = build_next_best_actions(
        user_id="student_demo",
        training_intents=[intent],
        graph_chain={
            "error_points_to_training": [
                {
                    "edge_type": "error_points_to_training",
                    "from": {"type": "error", "id": "1A432000:E02"},
                    "to": {"type": "next_training", "id": f"{intent['training_intent_id']}:case_repair"},
                    "evidence_event_id": "evt1",
                }
            ]
        },
    )[0]

    assert action["training_intent_id"] == intent["training_intent_id"]
    assert action["intent"]["training_intent_id"] == intent["training_intent_id"]
    assert action["intent"]["evidence_refs"] == intent["evidence_refs"]
    assert action["source"] == "training_intent"
    assert action["prescription_authority"] == "training_intent"
    assert action["evidence_refs"] == ["evt1", "evt2"]
    assert action["why_this_now"]
    assert action["query"] == (
        "针对我的薄弱点出一道练习题：工程招标投标与合同管理 · 采分点遗漏。出题后等我作答再批改。"
    )


def test_next_best_action_uses_only_real_learning_graph_edge_types() -> None:
    assert ACTIONABLE_EDGE_TYPES.issubset(_ALLOWED_EDGE_TYPES)


def test_next_best_action_treats_string_evidence_ref_as_single_ref() -> None:
    action = build_next_best_actions(
        user_id="student_demo",
        training_intents=[
            {
                "training_intent_id": "lti_string_ref",
                "status": "active",
                "concept_label": "防水工程",
                "evidence_refs": "evt_string",
            }
        ],
    )[0]

    assert action["evidence_refs"] == ["evt_string"]
    # book-derived axis: "防水工程" resolves to its own canonical node
    assert action["title"] == "先练防水工程"
    assert action["target"] == "防水工程"
    assert action["query"] == "针对我的薄弱点出一道练习题：防水工程。出题后等我作答再批改。"
    assert action["materials"][0] == "教材：防水工程相关章节"


def test_next_best_action_does_not_surface_unmapped_raw_concept_label() -> None:
    action = build_next_best_actions(
        user_id="student_demo",
        training_intents=[
            {
                "training_intent_id": "lti_raw_topic",
                "status": "active",
                "concept_label": "专家论证程序",
                "evidence_refs": ["evt_raw"],
            }
        ],
    )[0]

    assert action["title"] == "先补一题可诊断练习"
    assert action["target"] == "诊断练习"
    assert action["query"] == "针对我的薄弱点出一道练习题：诊断练习。出题后等我作答再批改。"
    assert "专家论证程序" not in str(action["materials"])
    assert "专家论证程序" not in action["query"]
