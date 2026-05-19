from __future__ import annotations

from deeptutor.services.learner_state.learning_brain_read_model import (
    build_learning_brain_read_model,
    extract_learning_brain_projection,
    wrap_learning_brain_projection,
)


def _projection() -> dict:
    return {
        "schema_version": 2,
        "subject": "construction_exam_learning_truth",
        "compiled_objects": {
            "concept:1A432000": {
                "object_type": "concept",
                "object_id": "1A432000",
                "current_truth": "1A432000 上出现 E02 错因观察",
                "evidence_level": "L1_repeated",
                "confidence": 0.72,
                "supporting_event_ids": ["evt1", "evt2"],
                "timeline_refs": [{"event_id": "evt1"}],
                "decay_state": "active",
            }
        },
        "weak_points": [
            {
                "concept_id": "1A432000",
                "error_code": "E02",
                "claim": "1A432000 上出现 E02 错因观察",
                "evidence_level": "L1_repeated",
                "supporting_event_ids": ["evt1", "evt2"],
                "recommended_training": {"mode": "case_repair", "focus": "专家论证程序"},
            }
        ],
        "typed_graph": {
            "edges": [
                {
                    "edge_type": "question_tests_concept",
                    "from": {"type": "question", "id": "case_001"},
                    "to": {"type": "concept", "id": "1A432000"},
                    "evidence_event_id": "evt1",
                },
                {
                    "edge_type": "error_points_to_training",
                    "from": {"type": "error", "id": "1A432000:E02"},
                    "to": {"type": "next_training", "id": "1A432000:E02:case_repair"},
                    "evidence_event_id": "evt2",
                },
            ],
            "readiness_gaps": [],
        },
        "synthesis_run": {
            "input_event_count": 2,
            "created_claim_count": 1,
            "output_projection_hash": "sha256:test",
        },
    }


def test_mobile_read_model_uses_shared_learning_brain_projection() -> None:
    model = build_learning_brain_read_model(
        user_id="student_demo",
        projection=_projection(),
        surface="mobile",
    )

    assert model["projection_subject"] == "construction_exam_learning_truth"
    assert model["typed_graph_edges"][0]["display_title"] == "题目考查知识点"
    assert model["typed_graph_edges"][0]["display_path"] == "案例题：case_001 → 知识点：工程招标投标与合同管理"
    assert model["visible_sections"]["current_truth"][0]["object_key"] == "concept:1A432000"
    assert model["visible_sections"]["current_truth"][0]["display_title"] == "工程招标投标与合同管理 上出现 采分点遗漏 错因"
    assert model["visible_sections"]["current_truth"][0]["display_meta"] == "知识点：工程招标投标与合同管理"
    assert model["visible_sections"]["next_training"][0]["error_code"] == "E02"
    assert model["visible_sections"]["next_training"][0]["display_meta"] == (
        "知识点：工程招标投标与合同管理；错因：采分点遗漏；案例题补强"
    )
    assert model["graph_chain"]["has_training_not_improved_error"] is True


def test_mobile_read_model_outputs_learner_facing_edge_paths() -> None:
    model = build_learning_brain_read_model(
        user_id="student_demo",
        projection=_projection(),
        surface="mobile",
    )

    chain_edge = model["graph_chain"]["training_not_improved_error"][0]
    assert chain_edge["display_title"] == "训练后仍需巩固"
    assert chain_edge["display_path"] == (
        "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏"
    )
    assert model["visible_sections"]["evidence_flow"][-1]["display_path"] == chain_edge["display_path"]


def test_qa_read_model_uses_same_projection_with_section_list() -> None:
    model = build_learning_brain_read_model(
        user_id="qa_student",
        projection=_projection(),
        surface="qa",
    )

    assert [section["id"] for section in model["visible_sections"]] == [
        "weak_points",
        "compiled_objects",
        "typed_graph",
    ]
    assert model["typed_graph_edge_count"] == 2
    assert model["graph_chain"]["has_training_not_improved_error"] is True


def test_extract_learning_brain_projection_ignores_guide_completion_payload() -> None:
    assert extract_learning_brain_projection({"guide_completion": {"guide_id": "guide_42"}}) == {}


def test_wrap_and_extract_learning_brain_projection_uses_namespaced_truth() -> None:
    projection = _projection()
    wrapped = wrap_learning_brain_projection(projection)

    assert extract_learning_brain_projection(wrapped)["subject"] == "construction_exam_learning_truth"


def test_read_model_uses_backend_taxonomy_display_labels() -> None:
    projection = _projection()
    projection["compiled_objects"] = {
        "concept:1A412030": {
            "object_type": "concept",
            "object_id": "1A412030",
            "current_truth": "1A412030 上出现 E04 错因观察",
            "evidence_level": "L1_repeated",
            "confidence": 0.72,
            "supporting_event_ids": ["evt1"],
        }
    }
    projection["weak_points"] = [
        {
            "concept_id": "1A412030",
            "error_code": "E04",
            "claim": "1A412030 上出现 E04 错因观察",
            "evidence_level": "L1_repeated",
            "supporting_event_ids": ["evt1"],
            "recommended_training": {"mode": "case_repair"},
        }
    ]

    model = build_learning_brain_read_model(user_id="student_demo", projection=projection, surface="mobile")

    truth = model["visible_sections"]["current_truth"][0]
    training = model["visible_sections"]["next_training"][0]
    assert truth["display_title"] == "建筑功能材料 上出现 口号化表达 错因"
    assert truth["display_meta"] == "知识点：建筑功能材料"
    assert "1A412030" not in truth["display_title"]
    assert "知识点：建筑功能材料" in training["display_meta"]
