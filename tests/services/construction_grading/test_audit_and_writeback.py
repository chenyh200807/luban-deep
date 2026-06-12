from __future__ import annotations

from deeptutor.services.construction_grading.audit import evaluate_grading_supabase_audit
from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.writeback import (
    write_case_grading_event_learning_evidence,
    write_grading_error_events,
)


class _FakeEvent:
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id


def test_audit_accepts_projected_rubric_assets_without_requiring_curated_rubric() -> None:
    report = evaluate_grading_supabase_audit(
        {
            "questions_bank": {
                "count_total": 4638,
                "field_fill_mcq": {
                    "total": 2659,
                    "correct_answer__filled": 2659,
                    "analysis__filled": 2655,
                    "options__filled": 2655,
                    "option_reasoning__filled": 80,
                },
                "field_fill_case": {
                    "total": 1961,
                    "correct_answer__filled": 1950,
                    "analysis__filled": 1332,
                    "grading_rubric__filled": 0,
                    "grading_keywords__filled": 960,
                    "structured_rules__filled": 661,
                    "node_code__filled": 1916,
                },
            },
            "online_evidence_tables": {
                "kb_chunks": {
                    "exists": True,
                    "count_total": 15432,
                    "metadata_key_fill": {
                        "exam_matrix": 1192,
                        "structured_rules": 884,
                        "logic_chains": 1074,
                        "pitfalls": 240,
                    },
                },
                "standard_articles": {
                    "exists": True,
                    "count_total": 3319,
                    "field_fill": {"logic_constraints__filled": 908},
                },
                "syllabus_tree": {
                    "exists": True,
                    "count_total": 1284,
                    "field_fill": {"node_code__filled": 1284, "keywords__filled": 780},
                },
                "knowledge_cards": {"exists": False},
            },
        }
    )

    assert report["status"] == "pass"
    assert "projected_rubric_ready" in report["ready_modes"]
    assert "curated_rubric_ready" not in report["ready_modes"]
    assert any(issue["code"] == "curated_rubric_empty" for issue in report["issues"])


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.progress_patches: list[dict[str, object]] = []

    def append_memory_event(self, user_id: str, **kwargs: object) -> object:
        self.calls.append({"user_id": user_id, **kwargs})
        return _FakeEvent(f"evt-{len(self.calls)}")

    def merge_progress(self, user_id: str, patch: dict[str, object]) -> dict[str, object]:
        self.progress_patches.append({"user_id": user_id, "patch": patch})
        return patch


class _FakeMistakeBookService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def save_item(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"ok": True, **dict(kwargs)}


def test_writeback_uses_existing_learner_memory_events() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={
            "id": "case-1",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证。",
            "grading_keywords": ["专家论证"],
            "node_code": "1A432000",
        },
        user_answer="应加强管理。",
    )
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        grading_result=result,
        source_id="submission-1",
        source_bot_id="construction-exam",
    )

    assert count == 1
    call = service.calls[0]
    assert call["source_feature"] == "construction_grading"
    assert call["memory_kind"] == "learning_evidence"
    assert call["source_bot_id"] == "construction-exam"
    assert call["dedupe_key"]
    assert call["payload_json"]["event_type"] == "learning_evidence"
    assert call["payload_json"]["legacy_event_type"] == "construction_grading_error"
    assert call["payload_json"]["question_id"] == "case-1"
    assert call["payload_json"]["error_events"][0]["error_code"] in {"E02", "E03", "E04"}
    assert call["payload_json"]["errors"][0]["error_code"] in {"E02", "E03", "E04"}
    assert call["payload_json"]["quality"]["evidence_level"] == "L0_observed"
    assert call["payload_json"]["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert service.progress_patches
    projection = service.progress_patches[0]["patch"]["home_personalization"]
    assert projection["recommended_prompts"][0]["intent"]["source"] == "home_dashboard"
    assert projection["source_status"]["learning_report"] == "projection"


def test_v1_case_grading_event_writeback_uses_learning_evidence_stream() -> None:
    service = _FakeLearnerStateService()

    result = write_case_grading_event_learning_evidence(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-case-v1",
        source_bot_id="construction-exam-coach",
        user_answer="普通钢筋调直机",
        question_stem="指出钢筋调直设备的不妥之处。",
        node_code="1A413050",
        grading_event={
            "event_type": "case_grading_completed",
            "student_id": "student-1",
            "question_id": "Q10",
            "awarded_score": 0.0,
            "max_score": 1.0,
            "high_risk_review": True,
            "scoring_points": [
                {
                    "point_id": "P4",
                    "knowledge_point": "钢筋调直工艺",
                    "policy_type": "exact_required",
                    "hit": "miss",
                    "score": 0.0,
                    "max_score": 1.0,
                    "mistake_type": "near_synonym_not_exact",
                    "evidence_span": "普通钢筋调直机",
                    "required_terms": ["数控钢筋调直切断机"],
                }
            ],
        },
    )

    assert result["writeback_count"] == 1
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["source_feature"] == "construction_grading"
    assert call["memory_kind"] == "learning_evidence"
    assert call["source_bot_id"] == "construction-exam-coach"
    payload = call["payload_json"]
    assert payload["event_type"] == "learning_evidence"
    assert payload["legacy_event_type"] == "case_grading_completed"
    assert payload["grading_event"]["event_type"] == "case_grading_completed"
    assert payload["preview_only"] is True
    assert payload["claim_promotion_allowed"] is False
    assert payload["canonical_truth_written"] is False
    assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert payload["score_awarded"] == 0.0
    assert payload["awarded_score"] == 0.0
    assert payload["next_training_signal"]["concept"] == "1A413050"
    assert payload["next_training_signal"]["focus"] == "钢筋调直工艺"
    assert payload["next_training_signal"]["error_code"] == "E02"
    error = payload["error_events"][0]
    assert error["concept_tag"] == "1A413050"
    assert error["error_code"] == "E02"
    assert error["mistake_type"] == "near_synonym_not_exact"
    assert error["evidence_span"] == "普通钢筋调直机"
    assert payload["errors"] == payload["error_events"]
    hit = payload["rubric"]["scoring_point_hits"][0]
    assert hit["point_id"] == "P4"
    assert hit["hit"] is False
    assert hit["policy_type"] == "exact_required"
    assert hit["required_terms"] == ["数控钢筋调直切断机"]
    assert payload["weak_points"][0]["concept_label"] == "钢筋调直工艺"
    assert payload["weak_points"][0]["concept_id"] is None


def test_writeback_auto_saves_wrong_attempt_to_mistake_book() -> None:
    service = _FakeLearnerStateService()
    mistake_book = _FakeMistakeBookService()

    count = write_grading_error_events(
        learner_state_service=service,
        mistake_book_service=mistake_book,
        user_id="student-1",
        source_id="turn-wrong-1",
        source_bot_id="construction-exam",
        grading_result={
            "type": "mcq",
            "question_id": "q-wrong-1",
            "question_stem": "危大工程专项方案审批边界是什么？",
            "user_answer": "A",
            "score_awarded": 0.0,
            "max_score": 1.0,
            "error_events": [{"error_code": "M06", "diagnosis": "混淆审批与专家论证"}],
            "next_training_signal": {"concept": "危大工程", "focus": "专项方案审批"},
        },
    )

    assert count == 1
    assert len(mistake_book.calls) == 1
    call = mistake_book.calls[0]
    assert call["user_id"] == "student-1"
    assert call["subject_id"] == "construction_exam_1"
    assert call["bot_id"] == "construction-exam"
    assert call["title"] == "危大工程专项方案审批边界是什么？"
    assert call["concept_label"] == "专项方案审批"
    assert call["error_label"] == "混淆审批与专家论证"
    assert call["attempt_ref"]


def test_writeback_does_not_save_success_attempt_to_mistake_book() -> None:
    service = _FakeLearnerStateService()
    mistake_book = _FakeMistakeBookService()

    count = write_grading_error_events(
        learner_state_service=service,
        mistake_book_service=mistake_book,
        user_id="student-1",
        source_id="turn-correct-1",
        source_bot_id="construction-exam",
        include_success_events=True,
        grading_result={
            "type": "mcq",
            "question_id": "q-correct-1",
            "question_stem": "危大工程专项方案审批边界是什么？",
            "user_answer": "D",
            "score_awarded": 1.0,
            "max_score": 1.0,
            "error_events": [],
            "next_training_signal": {"concept": "危大工程", "focus": "专项方案审批"},
        },
    )

    assert count == 1
    assert mistake_book.calls == []


def test_writeback_accepts_runtime_batch_dict_result() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-1",
        source_bot_id="construction-exam",
        grading_result={
            "type": "batch",
            "authority": "construction_grading",
            "items": [
                {
                    "type": "mcq",
                    "question_id": "q-1",
                    "question_type": "choice",
                    "user_answer": "A",
                    "score_awarded": 0.0,
                    "max_score": 1.0,
                    "error_events": [
                        {
                            "error_code": "M02",
                            "severity": 0.7,
                            "concept_tag": "法规层级",
                            "evidence": "A",
                            "diagnosis": "作答与标准答案不一致。",
                        }
                    ],
                    "next_training_signal": {
                        "concept": "法规层级",
                        "focus": "行政法规与部门规章辨析",
                    },
                },
                {
                    "type": "mcq",
                    "question_id": "q-2",
                    "question_type": "choice",
                    "user_answer": "B",
                    "score_awarded": 1.0,
                    "max_score": 1.0,
                    "error_events": [],
                    "next_training_signal": {},
                },
            ],
        },
    )

    assert count == 1
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["source_id"] == "turn-1:q-1"
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["question_id"] == "q-1"
    assert call["payload_json"]["next_training_signal"]["focus"] == "行政法规与部门规章辨析"


def test_writeback_can_persist_success_learning_event_for_improvement_signal() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-2",
        source_bot_id="construction-exam",
        include_success_events=True,
        grading_result={
            "type": "case",
            "question_id": "case-2",
            "question_type": "case",
            "user_answer": "应组织专家论证，编制专项施工方案并审批。",
            "score_awarded": 1.0,
            "max_score": 1.0,
            "rubric_items": [{"rubric_item_id": "r1", "criterion": "专家论证程序", "status": "full"}],
            "error_events": [],
            "next_training_signal": {
                "concept": "1A432000",
                "focus": "专家论证程序",
                "mode": "case_repair",
            },
        },
    )

    assert count == 1
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["error_events"] == []
    assert call["payload_json"]["score_awarded"] == 1.0
    assert call["payload_json"]["quality"]["writeback_eligible"] is True
    assert call["payload_json"]["quality"]["writeback_reason"] == "success_improvement_signal"


def test_writeback_persists_training_intent_id() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-3",
        source_bot_id="construction-exam",
        training_intent_id="lti_123",
        grading_result={
            "type": "mcq",
            "question_id": "q-3",
            "user_answer": "A",
            "score_awarded": 0.0,
            "max_score": 1.0,
            "error_events": [{"error_code": "M06", "concept_tag": "1A432000"}],
            "next_training_signal": {"concept": "1A432000", "focus": "多选漏选"},
        },
    )

    assert count == 1
    assert service.calls[0]["payload_json"]["training_intent_id"] == "lti_123"


def test_writeback_persists_prescription_verification_payload() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-verify",
        source_bot_id="construction-exam",
        include_success_events=True,
        training_intent_id="lti_verify",
        prescription_phase="verification_probe",
        prescription_result={
            "status": "verified",
            "score_ratio": 1.0,
            "verified_at": "2026-05-22T10:00:00+08:00",
        },
        grading_result={
            "type": "mcq",
            "question_id": "q-verify",
            "user_answer": "D",
            "score_awarded": 1.0,
            "max_score": 1.0,
            "error_events": [],
            "next_training_signal": {"concept": "1A432000", "focus": "验证复测"},
        },
    )

    assert count == 1
    payload = service.calls[0]["payload_json"]
    assert payload["training_intent_id"] == "lti_verify"
    assert payload["prescription_phase"] == "verification_probe"
    assert payload["prescription_result"] == {
        "status": "verified",
        "score_ratio": 1.0,
        "verified_at": "2026-05-22T10:00:00+08:00",
    }


def test_writeback_preserves_m35_point_evidence_without_canonical_truth() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-m35-q1",
        source_bot_id="construction-exam",
        grading_result={
            "type": "case",
            "question_id": "Q1-NA",
            "score_awarded": 6,
            "max_score": 10,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
            "next_training_signal": {"concept": "1A432000", "focus": "专项方案审批"},
            "rubric": {
                "artifact_version": "m35_case_scoring_20260609",
                "rubric_mode": "curated_rubric",
                "scoring_points": [
                    {"point_id": "Q1-NA::P2", "label": "专项方案审批", "max_score": 2},
                ],
                "scoring_point_hits": [
                    {
                        "point_id": "Q1-NA::P2",
                        "hit": False,
                        "awarded_score": 0,
                        "error_code": "E02",
                        "mistake_type": "omitted",
                        "evidence_span": "",
                        "source_ref_ids": ["2026_case_set_x#p2"],
                        "high_risk_review": True,
                    },
                ],
            },
        },
    )

    assert count == 1
    payload = service.calls[0]["payload_json"]
    assert payload["rubric"]["artifact_version"] == "m35_case_scoring_20260609"
    hit = payload["rubric"]["scoring_point_hits"][0]
    assert hit["point_id"] == "Q1-NA::P2"
    assert hit["match_status"] == "miss"
    assert hit["awarded_score"] == 0
    assert hit["mistake_type"] == "omitted"
    assert hit["source_ref_ids"] == ["2026_case_set_x#p2"]
    assert hit["high_risk_review"] is True
    assert payload["canonical_truth_written"] is False


def test_writeback_attaches_canonical_topic_for_open_world_grading() -> None:
    """开放世界批改（无 node_code）：writer seam 必须经 taxonomy resolver
    产出 canonical_topic（命中才写、不命中留空 fail-open），让合成层能把
    重复错误聚合成 claim。"""
    service = _FakeLearnerStateService()
    grading_event = {
        "event_type": "case_grading_completed",
        "question_id": "OPEN-1",
        "awarded_score": 0,
        "max_score": 1,
        "scoring_points": [
            {
                "point_id": "P1",
                "knowledge_point": "屋面与防水工程施工",
                "hit": "miss",
                "score": 0,
                "max_score": 1,
                "mistake_type": "miss",
                "evidence_span": "搭接宽度不足",
                "policy_type": "exact_required",
            }
        ],
    }

    result = write_case_grading_event_learning_evidence(
        learner_state_service=service,
        user_id="student-1",
        grading_event=grading_event,
        source_id="turn-open-1",
        question_stem="案例背景：某屋面防水工程采用卷材防水……指出施工不妥之处。",
        node_code="",
    )

    assert result["writeback_count"] == 1
    payload = service.calls[0]["payload_json"]
    assert payload.get("error_events"), "开放世界也必须有 error_events"
    topic = payload.get("canonical_topic") or {}
    assert topic.get("label") == "屋面与防水工程施工", "采分点 knowledge_point 携带 taxonomy 叶子标签时必须命中"
    assert topic.get("taxonomy_code") == "1A413050"


def test_writeback_canonical_topic_fail_open_when_unresolvable() -> None:
    service = _FakeLearnerStateService()
    grading_event = {
        "event_type": "case_grading_completed",
        "question_id": "OPEN-2",
        "awarded_score": 0,
        "max_score": 1,
        "scoring_points": [
            {"point_id": "P1", "knowledge_point": "xq", "hit": "miss", "score": 0, "max_score": 1,
             "mistake_type": "miss", "evidence_span": "", "policy_type": "exact_required"}
        ],
    }

    result = write_case_grading_event_learning_evidence(
        learner_state_service=service,
        user_id="student-1",
        grading_event=grading_event,
        source_id="turn-open-2",
        question_stem="zz",
        node_code="",
    )

    assert result["writeback_count"] == 1
    assert "canonical_topic" not in service.calls[0]["payload_json"]


class _BrainAwareLearnerStateService(_FakeLearnerStateService):
    def __init__(self, *, cached_projection: dict | None = None) -> None:
        super().__init__()
        self._cached_projection = cached_projection
        self.synthesize_calls: list[dict] = []

    def read_compiled_learning_truth(self, user_id: str) -> dict:
        return dict(self._cached_projection or {})

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool = True, event_limit=None):
        self.synthesize_calls.append({"user_id": user_id, "dry_run": dry_run, "event_limit": event_limit})
        return {"projection": {"compiled_objects": []}}


def _case_event_for_recorder() -> dict:
    return {
        "event_type": "case_grading_completed",
        "question_id": "CASE-R1",
        "awarded_score": 0,
        "max_score": 1,
        "scoring_points": [
            {
                "point_id": "P1",
                "knowledge_point": "屋面与防水工程施工",
                "hit": "miss",
                "score": 0,
                "max_score": 1,
                "mistake_type": "miss",
                "evidence_span": "搭接宽度不足",
                "policy_type": "exact_required",
            }
        ],
    }


def test_record_case_grading_to_brain_is_the_single_turn_side_seam() -> None:
    """recorder = writeback + intent + 画像(缓存优先) + PCP + NBA 的唯一组合 seam；
    聊天与练题两个入口都只 update 它返回的 meta，不得各自再拼装。"""
    from deeptutor.services.construction_grading.writeback import record_case_grading_to_brain

    service = _BrainAwareLearnerStateService(cached_projection={
        "compiled_objects": [
            {
                "object_id": "1A413050:M06",
                "object_type": "error",
                "claim_status": "confirmed",
                "concept_id": "1A413050",
                "label": "屋面与防水工程施工：采分点遗漏",
                "supporting_event_ids": ["evt_cached"],
                "confidence": 0.9,
            }
        ],
    })

    meta = record_case_grading_to_brain(
        learner_state_service=service,
        user_id="student-1",
        grading_event=_case_event_for_recorder(),
        source_id="turn-r1:CASE-R1",
        question_stem="案例……",
        user_answer="作答……",
        node_code="",
        session_id="sess-1",
    )

    assert meta["learning_evidence_event_id"] == "evt-1"
    assert meta["grading_to_brain_loop"]["authority"] == "learner_memory_events.learning_evidence"
    assert meta["learning_training_intent"]["concept_label"] == "屋面与防水工程施工"
    # 缓存优先：有 compiled 投影时不内联重算
    assert service.synthesize_calls == []
    pcp = meta["personalization_context"]
    assert pcp["top_claims"][0]["claim_id"] == "1A413050:M06"
    assert meta["next_best_action"]["prescription_authority"] == "training_intent"


def test_record_case_grading_to_brain_falls_back_to_inline_synthesis() -> None:
    from deeptutor.services.construction_grading.writeback import record_case_grading_to_brain

    service = _BrainAwareLearnerStateService(cached_projection=None)

    meta = record_case_grading_to_brain(
        learner_state_service=service,
        user_id="student-1",
        grading_event=_case_event_for_recorder(),
        source_id="turn-r2:CASE-R1",
    )

    assert meta["learning_evidence_event_id"]
    assert len(service.synthesize_calls) == 1
    assert service.synthesize_calls[0] == {"user_id": "student-1", "dry_run": True, "event_limit": 50}


def test_record_case_grading_to_brain_non_case_event_returns_empty() -> None:
    from deeptutor.services.construction_grading.writeback import record_case_grading_to_brain

    service = _BrainAwareLearnerStateService()
    meta = record_case_grading_to_brain(
        learner_state_service=service,
        user_id="student-1",
        grading_event={"status": "unavailable"},
        source_id="turn-r3",
    )
    assert meta == {}
    assert service.calls == []
