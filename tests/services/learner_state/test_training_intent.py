from __future__ import annotations

from deeptutor.services.learner_state.training_intent import (
    PRESCRIPTION_AUTHORITY,
    build_learning_training_intent,
    prioritize_training_intents,
)
from deeptutor.services.learner_state.home_personalization import (
    build_home_personalization_projection_from_learning_signal,
    write_home_personalization_projection,
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
    assert intent["prescription_authority"] == PRESCRIPTION_AUTHORITY
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
    assert projection["source_status"]["home_projection_contract"] == "canonical_taxonomy_v1"
    assert (
        projection["source_status"]["topic_authority"]
        == "learner_state.home_personalization.canonical_taxonomy"
    )
    # learning_evidence already resolved "防水工程" to canonical node 1A413000-C24; the home
    # projection must NOT override a resolved taxonomy node with the textbook-section alias
    # (merge resolution: ship branch behavior per owner decision).
    assert projection["today_focus"]["title"] == "今日焦点：防水工程"
    intent = projection["recommended_prompts"][0]["intent"]
    assert intent["concept_label"] == "防水工程"
    assert intent["error_label"] == "M01"
    assert intent["evidence_refs"] == ["evt_assessment_1", "attempt_ref_1"]
    written: dict[str, object] = {}

    class _FakeLearnerStateService:
        def merge_progress(self, user_id: str, patch: dict[str, object]) -> None:
            written["user_id"] = user_id
            written["patch"] = patch

    assert write_home_personalization_projection(
        _FakeLearnerStateService(), user_id="u_assessment", projection=projection
    )
    assert written["patch"] == {"home_personalization": projection}


def test_home_projection_still_canonicalizes_free_text_alias_to_textbook_section() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "event_type": "learning_evidence",
            "knowledge_points": ["主体结构"],
            "error_codes": ["M01"],
            "event_id": "evt_subjective_alias",
            "attempt_ref": "attempt_ref_alias",
            "subject_id": "construction_exam_1",
        }
    )

    assert projection is not None
    assert projection["today_focus"]["title"] == "今日焦点：主体结构工程施工"
    assert projection["recommended_prompts"][0]["intent"]["concept_label"] == "主体结构工程施工"


def test_home_projection_surfaces_six_distinct_next_learning_actions() -> None:
    projection = build_home_personalization_projection_from_learning_signal(
        {
            "event_type": "learning_evidence",
            "knowledge_points": ["项目质量计划管理"],
            "error_codes": ["质量计划和质量保证混淆"],
            "event_id": "evt_quality_plan",
            "subject_id": "construction_exam_1",
        }
    )

    assert projection is not None
    assert [item["prompt_type"] for item in projection["recommended_prompts"]] == [
        "practice_prompt",
        "mistake_review",
        "concept_explain",
        "exam_transfer",
        "knowledge_map",
        "quick_check",
    ]
    assert projection["recommended_prompts"][5]["text"] == (
        "用 1 个小问题验证项目质量计划管理是否真会了"
    )


def test_fresh_legacy_home_projection_is_upgraded_by_reader() -> None:
    from datetime import datetime, timedelta, timezone

    from deeptutor.services.learner_state.home_personalization import (
        build_home_dashboard_learning_projection,
    )

    tz = timezone(timedelta(hours=8))
    dashboard = build_home_dashboard_learning_projection(
        projection={
            "generated_at": datetime(2026, 5, 21, 9, 0, tzinfo=tz).isoformat(),
            "source_status": {"fallback_used": False, "learning_report": "projection"},
            "today_focus": {"title": "今日焦点：项目质量计划管理"},
            "recommended_prompts": [
                {
                    "prompt_type": "practice_prompt",
                    "text": "用 3 道题训练项目质量计划管理",
                    "intent": {
                        "source": "home_dashboard",
                        "concept_label": "项目质量计划管理",
                        "error_label": "质量计划和质量保证混淆",
                    },
                },
                {
                    "prompt_type": "mistake_review",
                    "text": "复盘项目质量计划管理里的质量计划和质量保证混淆",
                    "intent": {
                        "source": "home_dashboard",
                        "concept_label": "项目质量计划管理",
                        "error_label": "质量计划和质量保证混淆",
                    },
                },
                {
                    "prompt_type": "concept_explain",
                    "text": "讲清楚项目质量计划管理的关键判断",
                    "intent": {
                        "source": "home_dashboard",
                        "concept_label": "项目质量计划管理",
                        "error_label": "质量计划和质量保证混淆",
                    },
                },
            ],
        },
        now=datetime(2026, 5, 21, 10, 0, tzinfo=tz),
    )

    assert len(dashboard["recommended_prompts"]) == 6
    assert dashboard["recommended_prompts"][4]["prompt_type"] == "knowledge_map"


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


def test_training_intent_schema_id_is_registered_as_t2() -> None:
    """The sole prescription authority's canonical SCHEMA_ID must be registered T2 in the
    schema registry (no unregistered/competing training_intent schema can appear). This is
    the register-before-use promotion of a previously integer-versioned, closure-invisible
    cross-domain runtime contract (schema-governance P2, registry beyond grading)."""
    from pathlib import Path

    import yaml

    from deeptutor.services.learner_state.training_intent import SCHEMA_ID

    assert SCHEMA_ID == "learning_training_intent.v2"
    registry = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "contracts" / "schema_registry.yaml").read_text("utf-8")
    )
    t2_names = {e["name"] for e in registry["tier2_canonical_contracts"]}
    assert SCHEMA_ID in t2_names, f"{SCHEMA_ID} must be a registered T2 runtime-canonical contract"
