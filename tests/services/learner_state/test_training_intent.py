from __future__ import annotations

from deeptutor.services.learner_state.training_intent import (
    build_learning_training_intent,
    prioritize_training_intents,
)
from deeptutor.services.learner_state.home_personalization import (
    build_home_personalization_projection_from_learning_signal,
)


def test_training_intent_contains_concept_error_attempt_and_question_count() -> None:
    intent = build_learning_training_intent(
        user_id="u1",
        concept_id="1A432000",
        concept_label="主体结构",
        error_code="M06",
        error_label="多选漏选",
        attempt_refs=["ref1"],
        question_count=9,
        training_mode="mcq_discrimination",
    )

    assert intent["source"] == "learning_report"
    assert intent["concept_label"] == "主体结构"
    assert intent["error_label"] == "多选漏选"
    assert intent["attempt_refs"] == ["ref1"]
    assert intent["question_count"] == 5
    assert intent["training_mode"] == "mcq_discrimination"
    assert intent["training_intent_id"].startswith("lti_")


# ─── Batch C Task 6: prescription intent v2 ───────────────────────────────


def test_training_intent_v2_contains_repair_expression_transfer_and_probe() -> None:
    """Plan's literal failing test. When evidence_refs are present, the
    intent emits the 4-phase prescription spine plus a success_criteria
    block."""
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A412010",
        concept_label="防火门耐火极限",
        error_code="M08",
        error_label="规范数字混淆",
        source="learning_report",
        reason="repeated_code_application_error",
        evidence_refs=["attempt_1", "attempt_2"],
        ability_dimension="code_application",
        behavior_state="recurring",
    )

    assert intent["intent_version"] == 2
    assert [step["phase"] for step in intent["prescription_steps"]] == [
        "repair_root",
        "expression_drill",
        "transfer_case",
        "verification_probe",
    ]
    assert all(
        isinstance(step["question_count"], int) and step["question_count"] >= 1
        for step in intent["prescription_steps"]
    )
    assert intent["success_criteria"]["requires_revalidation"] is True
    assert intent["success_criteria"]["min_correct_probe_count"] >= 1
    assert intent["success_criteria"]["max_repeat_error_count"] == 0
    assert intent["evidence_refs"] == ["attempt_1", "attempt_2"]
    assert intent["ability_dimension"] == "code_application"
    assert intent["behavior_state"] == "recurring"


def test_training_intent_v2_preserves_v1_compat_fields() -> None:
    """v1 consumers (home_personalization, learning_report_read_model)
    must continue to read concept_id / error_label / training_mode /
    training_intent_id / source / attempt_refs without breakage."""
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A412010",
        concept_label="防火门耐火极限",
        error_code="M08",
        error_label="规范数字混淆",
        attempt_refs=["attempt_1"],
        evidence_refs=["attempt_1"],
        ability_dimension="code_application",
    )

    # v1 fields preserved.
    assert intent["source"] == "learning_report"
    assert intent["concept_id"] == "1A412010"
    assert intent["concept_label"] == "防火门耐火极限"
    assert intent["error_code"] == "M08"
    assert intent["error_label"] == "规范数字混淆"
    assert intent["attempt_refs"] == ["attempt_1"]
    assert intent["training_mode"] in {
        "mixed_review", "mcq_discrimination", "case_repair", "rubric_recall",
    }
    assert intent["training_intent_id"].startswith("lti_")

    # v2 additive.
    assert intent["intent_version"] == 2
    assert intent["evidence_refs"] == ["attempt_1"]


def test_home_projection_v1_consumer_derives_intent_from_assessment_evidence() -> None:
    """Assessment evidence does not emit next_training_signal; the home
    projection still needs a valid v1 training intent from canonical evidence.
    """
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "event_type": "learning_evidence",
            "knowledge_points": ["防水工程"],
            "error_codes": ["M01"],
            "event_id": "evt_assessment_1",
            "attempt_ref": "attempt_ref_1",
            "subject_id": "construction_exam_1",
        }
    )

    assert projection is not None
    assert projection["today_focus"]["title"] == "今日焦点：防水工程"
    intent = projection["recommended_prompts"][0]["intent"]
    assert intent["concept_label"] == "防水工程"
    assert intent["error_label"] == "M01"
    assert intent["evidence_refs"] == ["evt_assessment_1", "attempt_ref_1"]


def test_training_intent_v2_degrades_when_evidence_refs_empty() -> None:
    """Hard rule from the brief: evidence_refs 为空时不生成强处方，只生成
    degraded/pending action. The intent must still be valid v2 shape but
    its prescription_steps shrinks to a single discovery probe and
    success_criteria does not enforce revalidation."""
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="",
        concept_label="",
        evidence_refs=[],
        attempt_refs=[],
    )

    assert intent["intent_version"] == 2
    phases = [step["phase"] for step in intent["prescription_steps"]]
    assert "repair_root" not in phases
    assert phases == ["discovery_probe"]
    assert intent["success_criteria"]["requires_revalidation"] is False
    assert intent["evidence_refs"] == []
    assert intent["status"] == "degraded"


def test_training_intent_v2_falls_back_to_attempt_refs_for_evidence() -> None:
    """When the caller only supplies the legacy attempt_refs (v1), v2
    fills evidence_refs from those — neither field gets lost."""
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A412010",
        concept_label="防火门耐火极限",
        attempt_refs=["attempt_legacy_1", "attempt_legacy_2"],
    )

    assert intent["evidence_refs"] == ["attempt_legacy_1", "attempt_legacy_2"]
    assert intent["attempt_refs"] == ["attempt_legacy_1", "attempt_legacy_2"]


def test_training_intent_v2_ability_dimension_validated_against_registry() -> None:
    """ability_dimension must be one of the canonical six; an unknown
    value is silently dropped (does not raise, but also does not get
    surfaced as authoritative)."""
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A412010",
        evidence_refs=["a1"],
        ability_dimension="not_a_real_dim",
    )

    assert intent["ability_dimension"] == ""


def test_training_intent_v2_intent_id_is_stable_for_same_inputs() -> None:
    """Two intents with identical inputs produce the same training_intent_id
    so home_personalization / report can dedupe across surfaces."""
    a = build_learning_training_intent(
        user_id="u1",
        concept_id="1A412010",
        concept_label="x",
        error_code="M08",
        evidence_refs=["a1"],
        ability_dimension="code_application",
    )
    b = build_learning_training_intent(
        user_id="u1",
        concept_id="1A412010",
        concept_label="x",
        error_code="M08",
        evidence_refs=["a1"],
        ability_dimension="code_application",
    )
    assert a["training_intent_id"] == b["training_intent_id"]


def test_training_intent_v2_question_counts_sum_to_question_count() -> None:
    """Sum of phase question_counts must equal the legacy ``question_count``
    field so v1 consumers' budget assumptions still hold."""
    intent = build_learning_training_intent(
        user_id="u1",
        concept_id="1A412010",
        evidence_refs=["a1", "a2"],
        ability_dimension="code_application",
    )

    total = sum(step["question_count"] for step in intent["prescription_steps"])
    assert total == intent["question_count"]
    assert 1 <= total <= 5


def test_prioritize_training_intents_caps_active_and_queues_rest() -> None:
    intents = []
    for index in range(5):
        intent = build_learning_training_intent(
            user_id="student_demo",
            concept_id=f"1A4120{index}",
            concept_label=f"节点{index}",
            error_code="E02",
            evidence_refs=[f"evt_{index}"],
            ability_dimension="code_application",
        )
        intent["forgetting_risk"] = 0.9 - index * 0.1
        intent["exam_weight"] = 1.0
        intent["recurrence"] = 2
        intents.append(intent)

    ranked = prioritize_training_intents(intents, max_active=3)

    assert [item["status"] for item in ranked].count("active") == 3
    assert [item["status"] for item in ranked].count("queued") == 2
    assert ranked[0]["priority"] >= ranked[-1]["priority"]
