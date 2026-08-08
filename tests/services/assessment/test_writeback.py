from __future__ import annotations

import os

import pytest

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY
from deeptutor.services.assessment.writeback import AssessmentWritebackService
from deeptutor.services.learner_state.attempt_refs import verify_attempt_ref
from deeptutor.services.learner_state.mistake_book import InMemoryMistakeBookStore, MistakeBookService


class _LearnerState:
    def __init__(self) -> None:
        self.events = []
        self.progress_patches = []

    def append_memory_event(self, user_id, **kwargs):
        dedupe_key = kwargs.get("dedupe_key")
        for event in self.events:
            if event.dedupe_key == dedupe_key:
                return event
        event = type(
            "Event",
            (),
            {
                "event_id": f"evt_{len(self.events) + 1}",
                "user_id": user_id,
                "dedupe_key": dedupe_key,
                **kwargs,
            },
        )()
        self.events.append(event)
        return event

    def merge_progress(self, user_id, patch):
        self.progress_patches.append({"user_id": user_id, "patch": patch})
        return patch


def _scored_result() -> dict:
    return {
        "score_summary": {"score_pct": 50, "correct_count": 1, "scored_count": 2},
        "measurement_confidence": {"level": "medium", "reasons": []},
        "items": [
            {
                "question_id": "q1",
                "source_question_id": "src_1",
                "learner_answer": "A",
                "correct_answer": "A",
                "is_correct": True,
                "knowledge_points": ["防水工程"],
                "simple_explanation": "卷材搭接方向正确。",
                "error_codes": [],
                "measurement_confidence": "medium",
            },
            {
                "question_id": "q2",
                "source_question_id": "src_2",
                "learner_answer": "B",
                "correct_answer": "A",
                "is_correct": False,
                "knowledge_points": ["防水工程"],
                "simple_explanation": "防水节点应按规范处理。",
                "error_codes": ["M01"],
                "measurement_confidence": "medium",
            },
        ],
    }


def _service(monkeypatch: pytest.MonkeyPatch) -> tuple[AssessmentWritebackService, _LearnerState, MistakeBookService]:
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", "1")
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", "1")
    learner = _LearnerState()
    mistake_book = MistakeBookService(store=InMemoryMistakeBookStore())
    return AssessmentWritebackService(learner_state_service=learner, mistake_book_service=mistake_book), learner, mistake_book


def test_submit_writes_one_learning_evidence_event_per_scored_item(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    refs = service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    assert len([event for event in learner.events if event.memory_kind == "learning_evidence"]) == 2
    assert refs["learning_event_refs"][0]["event_id"] == "evt_1"
    assert learner.events[0].source_feature == "assessment_testset"
    assert learner.events[0].payload_json["event_type"] == "learning_evidence"


def test_assessment_writeback_updates_home_personalization_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    refs = service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam_1",
        scored_result=_scored_result(),
    )

    assert len(learner.progress_patches) == 1
    projection = learner.progress_patches[0]["patch"]["home_personalization"]
    # resolved taxonomy node is not overridden by the textbook-section alias (branch behavior,
    # merge resolution per owner decision)
    assert projection["today_focus"]["title"] == "今日焦点：防水工程"
    assert projection["today_focus"]["prompt"] == "用 3 道题训练防水工程"
    assert projection["recommended_prompts"][0]["prompt_type"] == "practice_prompt"
    assert projection["recommended_prompts"][0]["intent"]["evidence_refs"] == [
        "evt_2",
        refs["learning_event_refs"][1]["attempt_ref"],
    ]
    assert projection["source_status"]["learning_report"] == "projection"


def test_assessment_writeback_uses_question_taxonomy_code_for_home_projection_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, learner, _mistake_book = _service(monkeypatch)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.home_personalization.infer_learning_topic_with_llm",
        lambda _payload, _candidates: "",
    )
    scored = _scored_result()
    scored["items"][1]["node_code"] = "1A413050"

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam_1",
        scored_result=scored,
    )

    projection = learner.progress_patches[0]["patch"]["home_personalization"]
    assert projection["today_focus"]["title"] == "今日焦点：屋面与防水工程施工"
    assert projection["today_focus"]["intent"]["taxonomy_code"] == "1A413050"
    assert projection["recommended_prompts"][0]["text"] == "用 3 道题训练屋面与防水工程施工"


def test_submit_duplicate_does_not_duplicate_learning_events(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )
    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    assert len(learner.events) == 2


def test_attempt_ref_is_signed_after_event_id_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _learner, _mistake_book = _service(monkeypatch)

    refs = service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    wrong_ref = refs["learning_event_refs"][1]["attempt_ref"]
    verified = verify_attempt_ref(wrong_ref, user_id="student_demo")
    assert verified["event_id"] == "evt_2"
    assert verified["question_id"] == "q2"


def test_wrong_item_is_saved_to_mistake_book_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _learner, mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    items = mistake_book.list_items(user_id="student_demo", subject_id="construction_exam")["items"]
    assert len(items) == 1
    assert items[0]["question_id"] == "q2"
    assert items[0]["concept_label"] == "防水工程"


def test_error_codes_must_exist_in_error_code_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _learner, _mistake_book = _service(monkeypatch)
    result = _scored_result()
    result["items"][1]["error_codes"] = ["NOT_REGISTERED"]

    with pytest.raises(Exception, match="unregistered_error_code"):
        service.writeback(
            user_id="student_demo",
            quiz_id="quiz_1",
            form_id="form_1",
            assessment_type="topic_diagnostic",
            subject_id="construction_exam",
            scored_result=result,
        )


def test_assessment_submit_does_not_mutate_training_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    assert all(event.memory_kind != "training_intent" for event in learner.events)
    assert "M01" in ERROR_CODE_REGISTRY


def test_assessment_wrong_item_writes_actionable_learning_graph_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
    )

    wrong_payload = learner.events[1].payload_json
    edges = wrong_payload["typed_edges"]

    assert any(edge["edge_type"] == "question_tests_concept" for edge in edges)
    assert any(edge["edge_type"] == "submission_triggered_error" for edge in edges)
    action_edge = next(edge for edge in edges if edge["edge_type"] == "error_points_to_training")
    assert action_edge["from"] == {"type": "error", "id": "防水工程:M01"}
    assert action_edge["to"]["type"] == "next_training"
    assert action_edge["source_feature"] == "assessment_testset"


def test_assessment_graph_edges_prefer_canonical_concept_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service, learner, _mistake_book = _service(monkeypatch)
    result = _scored_result()
    result["items"][1]["section_id"] = "1A432000"

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=result,
    )

    wrong_payload = learner.events[1].payload_json
    action_edge = next(edge for edge in wrong_payload["typed_edges"] if edge["edge_type"] == "error_points_to_training")

    assert wrong_payload["concept_id"] == "1A432000"
    assert wrong_payload["error_events"][0]["concept_tag"] == "1A432000"
    assert action_edge["from"] == {"type": "error", "id": "1A432000:M01"}


def test_node_code_requires_taxonomy_resolver_existence(monkeypatch: pytest.MonkeyPatch) -> None:
    # §6-6:自由中文串经 normalize_taxonomy_code 只做形态归一不校验存在性,
    # 曾照落 node_code 污染 taxonomy join;写入侧必须过 resolver 存在性校验。
    service, learner, _mistake_book = _service(monkeypatch)
    scored = _scored_result()
    scored["items"][0]["node_code"] = "把防水节点再复习一遍"  # 自由串,resolver 不认识
    scored["items"][1]["node_code"] = "1A413050"  # 真实 taxonomy code

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_node_code",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=scored,
    )

    free_text = learner.events[0].payload_json
    real_code = learner.events[1].payload_json
    assert "node_code" not in free_text, f"free-text node_code leaked: {free_text.get('node_code')!r}"
    assert "taxonomy_code" not in free_text
    assert real_code["node_code"] == "1A413050"
    assert real_code["taxonomy_code"] == "1A413050"


def _pass_readiness_scored_result() -> dict:
    return {
        "score_summary": {"score_pct": 50, "correct_count": 1, "scored_count": 2},
        "measurement_confidence": {"level": "medium", "reasons": []},
        "items": [
            {
                "question_id": "q1",
                "source_question_id": "src_1",
                "section_id": "pr_objective_single",
                "learner_answer": "A",
                "correct_answer": "A",
                "is_correct": True,
                "knowledge_points": ["主体结构"],
                "simple_explanation": "作答正确。",
                "error_codes": [],
                "measurement_confidence": "medium",
            },
            {
                "question_id": "q2",
                "source_question_id": "src_2",
                "section_id": "pr_case_quality",
                "learner_answer": "B",
                "correct_answer": "A",
                "is_correct": False,
                "knowledge_points": ["质量验收", "检验批"],
                "simple_explanation": "验收程序错误。",
                "error_codes": ["M01"],
                "measurement_confidence": "medium",
            },
        ],
    }


def test_pass_readiness_writeback_carries_dimension_and_scoring_point_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_pr_1",
        form_id="pass_readiness_architecture_v1_form_1",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        scored_result=_pass_readiness_scored_result(),
        blueprint_version="pass_readiness_architecture_v1",
    )

    correct_payload = learner.events[0].payload_json
    wrong_payload = learner.events[1].payload_json
    assert learner.events[0].source_feature == "assessment_testset"
    assert correct_payload["ability_dimension"] == "core_knowledge"
    assert correct_payload["scoring_point_observations"] == [
        {"scoring_point": "主体结构", "observed": "correct", "error_codes": []}
    ]
    assert wrong_payload["ability_dimension"] == "case_scoring_point_recognition"
    assert wrong_payload["scoring_point_observations"] == [
        {"scoring_point": "质量验收", "observed": "incorrect", "error_codes": ["M01"]},
        {"scoring_point": "检验批", "observed": "incorrect", "error_codes": ["M01"]},
    ]
    # Canonical registry codes only; no display-bucket vocabulary persisted.
    for payload in (correct_payload, wrong_payload):
        for observation in payload["scoring_point_observations"]:
            for code in observation["error_codes"]:
                assert code in ERROR_CODE_REGISTRY
        assert "display_bucket" not in str(payload)


def test_non_pass_readiness_writeback_payload_shape_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, learner, _mistake_book = _service(monkeypatch)

    service.writeback(
        user_id="student_demo",
        quiz_id="quiz_topic_1",
        form_id="form_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        scored_result=_scored_result(),
        blueprint_version="topic_waterproof_v1",
    )

    for event in learner.events:
        assert "ability_dimension" not in event.payload_json
        assert "scoring_point_observations" not in event.payload_json


def test_writeback_rejects_unregistered_error_codes_in_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _learner, _mistake_book = _service(monkeypatch)
    scored = _pass_readiness_scored_result()
    scored["items"][1]["error_codes"] = ["X99"]

    with pytest.raises(Exception):
        service.writeback(
            user_id="student_demo",
            quiz_id="quiz_pr_bad_code",
            form_id="pass_readiness_architecture_v1_form_1",
            assessment_type="pass_readiness",
            subject_id="construction_exam",
            scored_result=scored,
            blueprint_version="pass_readiness_architecture_v1",
        )


def test_single_item_failure_does_not_kill_whole_writeback(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-08-07 审计回归:错题本单题写入抛错曾中止整卷循环(3/30 写入即停,
    后 27 题全部丢失)。逐题隔离后:失败题留痕计数,其余题照常写入。"""

    service, learner, _ = _service(monkeypatch)

    class _ExplodingMistakeBook:
        def __init__(self) -> None:
            self.calls = 0

        def save_item(self, **kwargs):
            self.calls += 1
            raise RuntimeError("mistake_book_write_disabled")

    exploding = _ExplodingMistakeBook()
    service._mistake_book_service = exploding
    scored = _scored_result()
    # 两道错题夹一道对题:第一道错题炸掉后,后续题必须继续写。
    scored["items"].append(
        {
            "question_id": "q3",
            "source_question_id": "src_3",
            "learner_answer": "C",
            "correct_answer": "A",
            "is_correct": False,
            "knowledge_points": ["防水工程"],
            "simple_explanation": "",
            "error_codes": ["M01"],
            "measurement_confidence": "medium",
        }
    )

    refs = service.writeback(
        user_id="u1",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        scored_result=scored,
    )

    # 两道错题都尝试过(没有在第一题就中止)
    assert exploding.calls == 2
    assert refs["failed_item_count"] == 2
    # 对题的 learning_evidence 照常写入(q1 全量 + q2/q3 事件在 save_item 前已落)
    assert len(refs["learning_event_refs"]) >= 1
    assert refs["writeback_status"]["failed_item_count"] == 2
    assert refs["mistake_book_refs"] == []


def test_pass_readiness_wrong_compiled_items_emit_assigned_practice_intents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """体检错题→处方指派(owner 2026-08-08「诊断要驱动计划」):编译车道错题按
    pack 派一条 assigned 处方事件(幂等,每 pack 一条);processing 走既有处方
    read-model,练习臂/计划同源出现。无 pack 绑定的车道诚实不派。"""

    from deeptutor.services.learner_state.prescription_outcome_read_model import (
        build_prescription_outcomes_read_projection,
        requires_active_practice,
    )

    service, learner, _ = _service(monkeypatch)
    scored = _scored_result()
    session_questions = [
        {
            "question_id": "q1",
            "provenance": {"source_meta": {"aggregation": "compiled_practice_readside", "pack_id": "a01", "rule_group": "拆模强度·条件维"}},
        },
        {
            "question_id": "q2",
            "provenance": {"source_meta": {"aggregation": "compiled_practice_readside", "pack_id": "a01", "rule_group": "拆模强度·条件维"}},
        },
    ]
    service.writeback(
        user_id="u1",
        quiz_id="quiz_1",
        form_id="form_1",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        scored_result=scored,
        session_questions=session_questions,
    )

    intent_events = [
        e for e in learner.events
        if str((e.payload_json or {}).get("training_intent_id") or "").startswith("ti_assessment:")
    ]
    # q1 对 q2 错,同 pack 只派一条;label 剥内部维度段
    assert len(intent_events) == 1
    payload = intent_events[0].payload_json
    assert payload["training_intent_id"] == "ti_assessment:quiz_1:A01"
    assert payload["prescription_phase"] == "assigned"
    assert payload["target_pack_id"] == "A01"
    assert payload["concept_label"] == "体检失分点·拆模强度"
    # 幂等:重放不加倍
    service.writeback(
        user_id="u1", quiz_id="quiz_1", form_id="form_1",
        assessment_type="pass_readiness", subject_id="construction_exam",
        scored_result=scored, session_questions=session_questions,
    )
    assert len([e for e in learner.events if str((e.payload_json or {}).get("training_intent_id") or "").startswith("ti_assessment:")]) == 1
    # 经同一处方 read-model → assigned → 练习臂激活
    outcomes = build_prescription_outcomes_read_projection(events=learner.events)
    target = next(o for o in outcomes if o["training_intent_id"] == "ti_assessment:quiz_1:A01")
    assert target["status"] == "assigned"
    assert requires_active_practice(target)
    assert target["target_pack_id"] == "A01"

    # 非体检类型不派
    service.writeback(
        user_id="u2", quiz_id="quiz_2", form_id="form_1",
        assessment_type="topic_diagnostic", subject_id="construction_exam",
        scored_result=_scored_result(), session_questions=session_questions,
    )
    assert not [
        e for e in learner.events
        if e.user_id == "u2" and str((e.payload_json or {}).get("training_intent_id") or "")
    ]
