from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deeptutor.services.learner_state.learning_report_read_model import (
    build_learning_report_read_model,
)
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent, LearnerStateService
from deeptutor.services.construction_grading.writeback import write_grading_error_events

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def _learning_event(
    event_id: str,
    *,
    days_ago: int = 0,
    concept_id: str = "1A432000",
    question_id: str = "case_001",
    error_code: str = "E02",
    created_at: str | None = None,
    score_awarded: float = 0.0,
    max_score: float = 1.0,
    user_answer: str = "A",
    correct_answer: str = "B",
    question_stem: str = "关于主体结构工程施工的说法，正确的是？",
    explanation: str = "解析：本题应先锁定规范条件，再排除与题干不一致的选项。",
) -> LearnerStateEvent:
    errors = [] if score_awarded >= max_score and max_score > 0 else [
        {
            "error_code": error_code,
            "concept_tag": concept_id,
            "rubric_item_id": "r1",
            "diagnosis": "漏写关键采分点。",
        }
    ]
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago) if created_at is None else created_at,
        payload_json={
            "event_type": "learning_evidence",
            "turn_id": f"turn_{event_id}",
            "question_id": question_id,
            "question_type": "mcq",
            "question_stem": question_stem,
            "options": {"A": "错误做法", "B": "正确做法", "C": "干扰项", "D": "干扰项"},
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "score_awarded": score_awarded,
            "max_score": max_score,
            "explanation": explanation,
            "error_events": errors,
            "next_training_signal": {
                "concept": concept_id,
                "focus": "专家论证程序",
                "mode": "case_repair",
            },
            "typed_edges": [
                {
                    "edge_type": "question_tests_concept",
                    "from": {"type": "question", "id": question_id},
                    "to": {"type": "concept", "id": concept_id},
                    "source_feature": "construction_grading",
                    "confidence": 0.9,
                },
                {
                    "edge_type": "error_points_to_training",
                    "from": {"type": "error", "id": f"{concept_id}:{error_code}"},
                    "to": {"type": "next_training", "id": f"{concept_id}:{error_code}:case_repair"},
                    "source_feature": "construction_grading",
                    "confidence": 0.9,
                },
            ],
        },
    )


class FakeMemberService:
    def get_today_progress(self, user_id: str) -> dict:
        return {"today_done": 0, "daily_target": 30, "streak_days": 0}

    def get_home_dashboard(self, user_id: str) -> dict:
        return {
            "review": {"due_today": 0, "overdue": 0},
            "mastery": {"weak_nodes": [{"name": "建筑构造", "mastery": 20}]},
            "today": {"hint": "优先补强 建筑构造"},
            "study_plan": {"priority_task": "先围绕薄弱点速练 5 题"},
            "progress_feedback": {"cards": [{"label": "近 3 天完成", "value": "0题"}]},
        }

    def get_assessment_profile(self, user_id: str) -> dict:
        return {
            "level": "beginner",
            "chapter_mastery": {"建筑构造": {"name": "建筑构造", "mastery": 20}},
            "diagnostic_feedback": {"learner_profile": {"study_tip": "先补关键采分点"}},
        }

    def get_mastery_dashboard(self, user_id: str) -> dict:
        return {
            "overall_mastery": 20,
            "groups": [{"name": "需要加强", "avg_mastery": 20, "chapters": [{"name": "建筑构造", "mastery": 20}]}],
            "hotspots": [{"name": "建筑构造", "mastery": 20}],
            "review_summary": {"total_due": 0, "overdue_count": 0},
        }


class PathServiceStub:
    def __init__(self, root):
        self._root = root

    @property
    def project_root(self):
        return self._root

    def get_user_root(self):
        return self._root

    def get_tutor_state_root(self):
        return self._root / "tutor_state"

    def get_learner_state_root(self):
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self):
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class DisabledCoreStoreStub:
    is_configured = False


class FakeLearnerStateService:
    def __init__(self, events: list[LearnerStateEvent]) -> None:
        self.events = list(events)

    def list_memory_events(self, user_id: str, limit: int | None = 100) -> list[LearnerStateEvent]:
        return self.events[-limit:] if limit else self.events

    def read_compiled_learning_truth(self, user_id: str) -> dict:
        return {}

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool, event_limit: int | None = None) -> dict:
        assert dry_run is True
        return {"projection": synthesize_learning_truth(self.list_memory_events(user_id, limit=event_limit))}


# ─────────────────────────────────────────────────────────────────────────────
# G1: 完成数 attempt 口径（硬约束）
# ─────────────────────────────────────────────────────────────────────────────


def test_attempt_count_treats_same_question_replay_as_two_attempts() -> None:
    """同题二刷必须算 2 次练习；唯一题数另行暴露。"""
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event("evt_today_1", days_ago=0, question_id="case_001"),
                _learning_event("evt_today_2", days_ago=0, question_id="case_001"),
            ]
        ),
        event_limit=50,
    )

    overview = model["overview"]
    assert overview["today_done"] == 2
    assert overview["recent_three_done"] == 2
    assert overview["attempt_count"] == 2
    assert overview["today_unique_questions"] == 1
    assert overview["recent_three_unique_questions"] == 1
    assert overview["unique_question_count"] == 1


def test_learning_report_exposes_learner_facing_attempt_review_without_machine_ids() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event(
                    "evt_review_1",
                    days_ago=0,
                    concept_id="1A432000",
                    question_id="zh-mcq-001",
                    error_code="M06",
                    user_answer="A",
                    correct_answer="AB",
                    question_stem="关于主体结构验收条件的说法，正确的是？",
                ),
                _learning_event(
                    "evt_review_2",
                    days_ago=0,
                    concept_id="1A432000",
                    question_id="zh-mcq-002",
                    error_code="M06",
                    user_answer="B",
                    correct_answer="BC",
                    question_stem="主体结构施工质量控制应重点核查什么？",
                ),
            ]
        ),
        event_limit=50,
    )

    facing = model["learner_facing"]
    assert facing["summary"]["title"] == "今日学习复盘"
    assert facing["summary"]["recent_three_done"] == 2
    assert facing["recent_attempts"][0]["title"] in {
        "主体结构施工质量控制应重点核查什么？",
        "关于主体结构验收条件的说法，正确的是？",
    }
    assert "你选：" in facing["recent_attempts"][0]["answer_line"]
    assert "正确：" in facing["recent_attempts"][0]["answer_line"]
    assert facing["recent_attempts"][0]["question_text"]
    assert facing["recent_attempts"][0]["explanation"].startswith("解析：")
    assert facing["recent_attempts"][0]["collectable"] is True
    assert facing["diagnoses"][0]["title"] == "工程招标投标与合同管理：多选漏选"
    assert facing["diagnoses"][0]["level_label"] == "需要重点补"
    assert facing["next_action"]["title"].startswith("先做 3 道")
    rendered = str(facing)
    assert "evt_review" not in rendered
    assert "M06" not in rendered
    assert "concept:" not in rendered


def test_learning_report_attempt_keys_are_stable_without_exposing_event_ids() -> None:
    event = _learning_event(
        "evt_stable_key",
        days_ago=0,
        question_id="zh-mcq-stable",
        explanation={"summary": "解析：这道题要先看题干限制条件。"},
    )
    first = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([event]),
        event_limit=50,
    )["learner_facing"]["recent_attempts"][0]
    second = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([event]),
        event_limit=50,
    )["learner_facing"]["recent_attempts"][0]

    assert first["key"] == second["key"]
    assert first["key"].startswith("attempt-")
    assert "evt_stable_key" not in first["key"]
    assert first["explanation"] == "解析：这道题要先看题干限制条件。"


def test_learning_report_attempt_cards_include_opaque_attempt_ref() -> None:
    from deeptutor.services.learner_state.attempt_refs import verify_attempt_ref

    event = _learning_event(
        "evt_attempt_ref_secret",
        days_ago=0,
        question_id="zh-mcq-ref",
    )
    attempt = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([event]),
        event_limit=50,
    )["learner_facing"]["recent_attempts"][0]

    assert attempt["attempt_ref"]
    assert "evt_attempt_ref_secret" not in attempt["attempt_ref"]
    payload = verify_attempt_ref(attempt["attempt_ref"], user_id="student_demo")
    assert payload == {"event_id": "evt_attempt_ref_secret", "question_id": "zh-mcq-ref"}


def test_learning_report_attempt_cards_include_bookmark_projection() -> None:
    event = _learning_event("evt_bookmarked", days_ago=0, question_id="zh-mcq-bookmark")

    class FakeMistakeBookService:
        def bookmark_event_ids(self, *, user_id: str, include_mastered: bool = True):
            assert user_id == "student_demo"
            assert include_mastered is True
            return {"evt_bookmarked"}

    attempt = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([event]),
        mistake_book_service=FakeMistakeBookService(),
        event_limit=50,
    )["learner_facing"]["recent_attempts"][0]

    assert attempt["is_bookmarked"] is True
    assert attempt["bookmark_label"] == "已加入错题"


def test_training_loop_uses_latest_attempt_not_any_past_correct_signal() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event(
                    "evt_old_correct",
                    concept_id="1A432000",
                    question_id="zh-mcq-old",
                    score_awarded=1.0,
                    max_score=1.0,
                    created_at="2026-05-20T10:00:00+08:00",
                ),
                _learning_event(
                    "evt_new_wrong",
                    concept_id="1A432000",
                    question_id="zh-mcq-new",
                    error_code="M06",
                    score_awarded=0.0,
                    max_score=1.0,
                    created_at="2026-05-20T10:05:00+08:00",
                ),
            ]
        ),
        event_limit=50,
    )

    loop = model["learner_facing"]["training_loops"][0]
    assert loop["tone"] == "not-improved"
    assert "仍需" in loop["outcome"]


def test_multi_concept_evidence_updates_progress_feedback_chapter_focus() -> None:
    """多章节练习：不同 concept evidence 推入 progress_feedback 的 focus 卡片，不互相污染。"""
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event("evt_constr_1", days_ago=0, concept_id="1A432000", question_id="case_a"),
                _learning_event("evt_constr_2", days_ago=0, concept_id="1A432000", question_id="case_b"),
                _learning_event("evt_other", days_ago=1, concept_id="1A411011", question_id="case_c"),
            ]
        ),
        event_limit=50,
    )

    # 三条 evidence → attempt_count=3，跨日近 3 天 =3；不同 concept 不会互相吞掉 attempt
    assert model["overview"]["attempt_count"] == 3
    assert model["overview"]["recent_three_done"] == 3
    assert model["overview"]["unique_question_count"] == 3
    # progress_feedback 的"主攻推进"卡片应能选出一个 chapter（不为空标签）
    cards_by_label = {item["label"]: item for item in model["progress_feedback"]["cards"]}
    assert "主攻推进" in cards_by_label
    assert cards_by_label["主攻推进"]["detail"], "multi-chapter evidence should yield a non-empty focus detail"


def test_no_evidence_does_not_inflate_progress() -> None:
    """批改失败未写 event：学情不虚增，read model 不冒充进度。"""
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([]),
        event_limit=50,
    )

    overview = model["overview"]
    assert overview["today_done"] == 0
    assert overview["recent_three_done"] == 0
    assert overview["attempt_count"] == 0
    assert overview["unique_question_count"] == 0
    assert model["freshness"]["event_count"] == 0
    # progress_source authority 仍然指向 evidence ledger，不会回退到旧 daily counts
    assert model["authority"]["progress_source"] == "learner_memory_events.learning_evidence"
    # 近 3 天卡片应展示 0 题（非冒充非负值）
    cards = {item["label"]: item for item in model["progress_feedback"]["cards"]}
    assert cards["近 3 天完成"]["value"] == "0题"


def test_single_correct_attempt_does_not_mark_chapter_as_fully_mastered() -> None:
    """一题答对只能形成低样本掌握信号，不能把章节/全局直接推成 100%。"""

    class OverconfidentMember(FakeMemberService):
        def get_assessment_profile(self, user_id: str) -> dict:
            return {
                "level": "advanced",
                "chapter_mastery": {
                    "1A432000": {"name": "1A432000", "mastery": 100},
                },
                "diagnostic_feedback": {"learner_profile": {"study_tip": "继续做混合难度题确认"}},
            }

        def get_mastery_dashboard(self, user_id: str) -> dict:
            return {
                "overall_mastery": 100,
                "groups": [
                    {
                        "name": "掌握较好",
                        "avg_mastery": 100,
                        "chapters": [{"name": "1A432000", "mastery": 100}],
                    }
                ],
                "hotspots": [{"name": "1A432000", "mastery": 100}],
                "review_summary": {"total_due": 0, "overdue_count": 0},
            }

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=OverconfidentMember(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event(
                    "evt_correct_once",
                    days_ago=0,
                    concept_id="1A432000",
                    question_id="case_once",
                    score_awarded=1.0,
                    max_score=1.0,
                )
            ]
        ),
        event_limit=50,
    )

    assert model["overview"]["attempt_count"] == 1
    assert model["overview"]["overall_mastery"] < 100
    assert model["mastery"]["overall_mastery"] < 100
    assert model["mastery"]["groups"][0]["chapters"][0]["mastery"] <= 60
    assert model["radar_dimensions"][0]["name"] == "工程招标投标与合同管理"
    assert model["radar_dimensions"][0]["value"] <= 0.6


def test_machine_taxonomy_codes_are_normalized_before_report_surface() -> None:
    """read model 输出前先把 taxonomy code 变成中文学习维度，避免前端猜测。"""

    class CodeNamedMember(FakeMemberService):
        def get_assessment_profile(self, user_id: str) -> dict:
            return {
                "level": "beginner",
                "chapter_mastery": {
                    "1A432000": {"name": "1A432000", "mastery": 20},
                    "1A411011": {"name": "1A411011", "mastery": 10},
                },
                "diagnostic_feedback": {"learner_profile": {"study_tip": "先补关键采分点"}},
            }

        def get_mastery_dashboard(self, user_id: str) -> dict:
            return {
                "overall_mastery": 15,
                "groups": [
                    {
                        "name": "需要加强",
                        "avg_mastery": 15,
                        "chapters": [
                            {"name": "1A432000", "mastery": 20},
                            {"name": "1A411011", "mastery": 10},
                        ],
                    }
                ],
                "hotspots": [{"name": "1A432000", "mastery": 20}],
                "review_summary": {"total_due": 0, "overdue_count": 0},
            }

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=CodeNamedMember(),
        learner_state_service=FakeLearnerStateService([]),
        event_limit=50,
    )

    dimension_names = [item["name"] for item in model["radar_dimensions"]]
    chapter_names = [
        chapter["name"]
        for group in model["mastery"]["groups"]
        for chapter in group["chapters"]
    ]
    assert "综合能力" not in dimension_names
    assert "综合能力" not in chapter_names
    assert "工程招标投标与合同管理" in dimension_names
    assert "建筑物分类与构成" in dimension_names
    assert "工程招标投标与合同管理" in chapter_names


def test_attempt_count_across_three_days_uses_attempt_not_unique() -> None:
    """跨日不同题：attempt 与 unique 字段都应符合 attempt 口径。"""
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event("evt_today", days_ago=0, question_id="case_001"),
                _learning_event("evt_yesterday", days_ago=1, question_id="case_002"),
                _learning_event("evt_two_days", days_ago=2, question_id="case_003"),
            ]
        ),
        event_limit=50,
    )

    overview = model["overview"]
    assert overview["recent_three_done"] == 3
    assert overview["recent_three_unique_questions"] == 3
    assert overview["attempt_count"] == 3
    assert overview["unique_question_count"] == 3


def test_learning_report_counts_recent_three_days_from_learning_evidence_not_legacy_daily_counts() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event("evt_today", days_ago=0, question_id="case_001"),
                _learning_event("evt_two_days", days_ago=2, question_id="case_002"),
                _learning_event("evt_old", days_ago=5, question_id="case_003"),
            ]
        ),
        event_limit=50,
    )

    cards = {item["label"]: item for item in model["progress_feedback"]["cards"]}
    assert cards["近 3 天完成"]["value"] == "2题"
    assert model["overview"]["today_done"] == 1
    assert model["authority"]["progress_source"] == "learner_memory_events.learning_evidence"
    assert model["legacy_compat"]["today_progress"]["today_done"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# G2: source_status / degraded / degraded_sources
# ─────────────────────────────────────────────────────────────────────────────


def test_mastery_dashboard_failure_marks_degraded_with_source_status() -> None:
    class FlakyMember(FakeMemberService):
        def get_mastery_dashboard(self, user_id: str) -> dict:
            raise RuntimeError("supabase unreachable: connection refused")

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FlakyMember(),
        learner_state_service=FakeLearnerStateService(
            [_learning_event("evt_today", days_ago=0, question_id="case_001")]
        ),
        event_limit=50,
    )

    assert model["degraded"] is True
    assert "mastery_dashboard" in model["degraded_sources"]
    mastery_status = model["source_status"]["mastery_dashboard"]
    assert mastery_status["ok"] is False
    assert "RuntimeError" in (mastery_status["error"] or "")
    assert "supabase unreachable" in (mastery_status["error"] or "")
    # Evidence-driven progress 仍可见
    assert model["overview"]["today_done"] == 1
    assert model["source_status"]["learner_events"]["ok"] is True


def test_multiple_source_failures_listed_in_degraded_sources() -> None:
    class DoubleFlakyMember(FakeMemberService):
        def get_mastery_dashboard(self, user_id: str) -> dict:
            raise RuntimeError("mastery offline")

        def get_assessment_profile(self, user_id: str) -> dict:
            raise ValueError("assessment offline")

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=DoubleFlakyMember(),
        learner_state_service=FakeLearnerStateService([]),
        event_limit=50,
    )

    assert model["degraded"] is True
    assert "mastery_dashboard" in model["degraded_sources"]
    assert "assessment_profile" in model["degraded_sources"]
    assert model["source_status"]["mastery_dashboard"]["ok"] is False
    assert model["source_status"]["assessment_profile"]["ok"] is False
    assert model["source_status"]["today_progress"]["ok"] is True


def test_degraded_contract_is_consistent_when_all_sources_ok() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([]),
        event_limit=50,
    )

    assert model["degraded"] is False
    assert model["degraded_sources"] == []
    for name, status in model["source_status"].items():
        # ok 必须是 True 或 None（未触发），不能是 False
        assert status["ok"] in (True, None), f"{name} should not be ok=False"


# ─────────────────────────────────────────────────────────────────────────────
# G3: unknown_date_count
# ─────────────────────────────────────────────────────────────────────────────


def test_invalid_timestamps_go_to_unknown_date_count_not_today() -> None:
    events = [
        _learning_event("evt_today", days_ago=0, question_id="case_001"),
        _learning_event("evt_empty_ts", days_ago=0, question_id="case_empty", created_at=""),
        _learning_event("evt_bad_ts", days_ago=0, question_id="case_bad", created_at="not-a-date"),
        _learning_event(
            "evt_future",
            days_ago=0,
            question_id="case_future",
            created_at=(datetime.now(_TZ) + timedelta(days=1)).isoformat(),
        ),
    ]

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(events),
        event_limit=50,
    )

    overview = model["overview"]
    freshness = model["freshness"]
    # Only the legitimately dated event should land in today's attempt bucket.
    assert overview["today_done"] == 1
    assert overview["attempt_count"] == 1
    assert freshness["unknown_date_count"] == 3
    # daily_counts (via progress_feedback) must not contain placeholder buckets like "__unknown__".
    # progress_feedback exposes the cards; we also verify the raw bucket keys live on the
    # internal stats dict by re-running aggregation isn't necessary — the public surface
    # is enough because progress_feedback uses the same map.
    # 进一步：daily_counts 必须是 ISO 日期 key
    for card in model["progress_feedback"]["cards"]:
        assert "__unknown__" not in str(card)


# ─────────────────────────────────────────────────────────────────────────────
# G4: schema_version / overview / freshness / authority 必须字段齐全
# ─────────────────────────────────────────────────────────────────────────────


def test_envelope_contains_required_schema_v1_fields() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [_learning_event("evt_today", days_ago=0, question_id="case_001")]
        ),
        event_limit=50,
    )

    assert model["schema_version"] == 1
    assert model["authority"]["read_model"] == "learning-report-read-model"
    assert model["authority"]["progress_source"] == "learner_memory_events.learning_evidence"
    assert isinstance(model["authority"]["deprecated_page_sources"], list)
    assert len(model["authority"]["deprecated_page_sources"]) == 5

    overview = model["overview"]
    for required in (
        "today_done",
        "recent_three_done",
        "attempt_count",
        "today_unique_questions",
        "recent_three_unique_questions",
        "unique_question_count",
        "daily_target",
        "streak_days",
        "weak_node_count",
        "due_today_count",
        "focus_hint",
        "learner_level",
        "study_tip",
        "overall_mastery",
    ):
        assert required in overview, f"overview missing {required}"

    freshness = model["freshness"]
    for required in ("generated_at", "event_count", "latest_event_at", "unknown_date_count", "window_truncated"):
        assert required in freshness, f"freshness missing {required}"


def test_window_truncated_flag_when_event_count_hits_limit() -> None:
    events = [
        _learning_event(f"evt_{idx}", days_ago=0, question_id=f"case_{idx:03d}")
        for idx in range(5)
    ]
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(events),
        event_limit=5,
    )

    assert model["freshness"]["event_count"] == 5
    assert model["freshness"]["window_truncated"] is True


def test_learning_evidence_limit_is_not_consumed_by_non_learning_events() -> None:
    noisy_events = [
        LearnerStateEvent(
            event_id=f"noise_{idx}",
            user_id="student_demo",
            source_feature="heartbeat",
            source_id=f"noise:{idx}",
            source_bot_id=None,
            memory_kind="heartbeat_delivery",
            dedupe_key=f"noise_{idx}",
            created_at=_iso(0),
            payload_json={"event_type": "heartbeat_delivery"},
        )
        for idx in range(20)
    ]
    learning_events = [
        _learning_event("evt_today_1", days_ago=0, question_id="case_001"),
        _learning_event("evt_today_2", days_ago=0, question_id="case_002"),
    ]

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(learning_events + noisy_events),
        event_limit=2,
    )

    assert model["overview"]["recent_three_done"] == 2
    assert model["freshness"]["event_count"] == 2
    assert model["freshness"]["window_truncated"] is True


def test_window_not_truncated_when_event_count_below_limit() -> None:
    events = [_learning_event("evt_today", days_ago=0, question_id="case_001")]
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(events),
        event_limit=50,
    )

    assert model["freshness"]["window_truncated"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Learning Brain authority / dry_run_synthesis source_status
# ─────────────────────────────────────────────────────────────────────────────


def test_compiled_truth_missing_triggers_dry_run_and_marks_source_status() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [_learning_event("evt_today", days_ago=0, question_id="case_001")]
        ),
        event_limit=50,
    )

    assert model["authority"]["learning_brain_source"] == "dry_run_learning_evidence"
    assert model["source_status"]["dry_run_synthesis"]["ok"] is True
    assert model["source_status"]["compiled_truth"]["ok"] is True
    assert model["learning_brain"]["visible_sections"]


def test_compiled_truth_present_skips_dry_run() -> None:
    class HotProjectionService(FakeLearnerStateService):
        def read_compiled_learning_truth(self, user_id: str) -> dict:
            return {
                "subject": "construction_exam_learning_truth",
                "schema_version": 2,
                "compiled_objects": {},
                "weak_points": [],
                "improvement_signals": [],
                "stale_claims": [],
                "typed_graph": {"edges": [], "readiness_gaps": []},
                "synthesis_run": {"input_event_count": 0, "created_claim_count": 0},
            }

        def synthesize_learning_truth(self, user_id: str, *, dry_run: bool, event_limit: int | None = None) -> dict:
            raise AssertionError("dry_run should not fire when compiled truth is present")

    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=HotProjectionService(
            [_learning_event("evt_today", days_ago=0, question_id="case_001")]
        ),
        event_limit=50,
    )

    assert model["authority"]["learning_brain_source"] == "compiled_learning_truth"
    assert model["source_status"]["compiled_truth"]["ok"] is True
    assert model["source_status"]["dry_run_synthesis"]["ok"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 端到端：通过 grading writeback 写入真实 evidence
# ─────────────────────────────────────────────────────────────────────────────


def test_learning_report_exposes_weak_points_learning_brain_evidence_and_next_training() -> None:
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [
                _learning_event("evt1", days_ago=0, question_id="case_001"),
                _learning_event("evt2", days_ago=0, question_id="case_002"),
            ]
        ),
        event_limit=50,
    )

    learning_brain = model["learning_brain"]
    assert learning_brain["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert learning_brain["visible_sections"]["current_truth"]
    assert learning_brain["visible_sections"]["evidence_flow"]
    assert learning_brain["visible_sections"]["next_training"]
    assert model["next_training"]
    assert model["authority"]["learning_brain_source"] == "dry_run_learning_evidence"


def test_realistic_chinese_grading_event_updates_report_progress_learning_brain_and_training(tmp_path) -> None:
    learner_state = LearnerStateService(
        path_service=PathServiceStub(tmp_path),
        member_service=FakeMemberService(),
        core_store=DisabledCoreStoreStub(),
    )
    user_id = "student_demo"
    for turn_id, question_id in (("turn_chinese_001", "zh-mcq-001"), ("turn_chinese_002", "zh-mcq-002")):
        written = write_grading_error_events(
            learner_state_service=learner_state,
            user_id=user_id,
            source_id=turn_id,
            source_bot_id="construction-exam",
            grading_result={
                "question_id": question_id,
                "question_type": "mcq",
                "user_answer": "A",
                "score_awarded": 0,
                "max_score": 1,
                "grading_mode": "projected_rubric",
                "rubric_items": [{"rubric_item_id": "r1", "criterion": "识别专家论证程序", "status": "miss"}],
                "error_events": [
                    {
                        "error_code": "E02",
                        "concept_tag": "1A432000",
                        "rubric_item_id": "r1",
                        "diagnosis": "中文选择题作答后，漏掉专家论证程序这一采分点。",
                    }
                ],
                "next_training_signal": {
                    "concept": "1A432000",
                    "focus": "专家论证程序",
                    "mode": "case_repair",
                },
                "evidence_refs": [
                    {
                        "source": "rag",
                        "source_id": "kb:construction:expert-review",
                        "snippet": "基坑工程达到专家论证边界时应组织专家论证。",
                    }
                ],
            },
        )
        assert written == 1

    model = build_learning_report_read_model(
        user_id=user_id,
        member_service=FakeMemberService(),
        learner_state_service=learner_state,
        event_limit=50,
    )

    cards = {item["label"]: item for item in model["progress_feedback"]["cards"]}
    assert cards["近 3 天完成"]["value"] == "2题"
    assert model["overview"]["today_done"] == 2
    assert model["overview"]["attempt_count"] == 2
    assert model["overview"]["unique_question_count"] == 2
    assert model["learning_brain"]["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert model["learning_brain"]["visible_sections"]["evidence_flow"]
    assert model["learning_brain"]["visible_sections"]["next_training"][0]["display_meta"]
    assert model["learning_brain"]["graph_chain"]["has_training_uses_question"] is True


# ─────────────────────────────────────────────────────────────────────────────
# G5: quality gate — recent_attempts expose quality contract
# ─────────────────────────────────────────────────────────────────────────────


def test_recent_attempts_quality_field_present_and_has_required_keys() -> None:
    """recent_attempts cards must include a quality dict with the full contract."""
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService(
            [_learning_event("evt_quality_check", days_ago=0, question_id="q_quality")]
        ),
        event_limit=50,
    )

    attempt = model["learner_facing"]["recent_attempts"][0]
    quality = attempt["quality"]
    for required_key in (
        "evidence_level",
        "writeback_eligible",
        "stable_truth_eligible",
        "evidence_cap_reasons",
        "detail_ready",
        "progress_countable",
        "truth_eligible",
        "missing_fields",
        "degraded_reason",
    ):
        assert required_key in quality, f"quality missing {required_key}"
    # Event has explanation → detail_ready
    assert quality["detail_ready"] is True
    assert quality["progress_countable"] is True


def test_recent_attempts_quality_detail_ready_false_when_no_explanation() -> None:
    """An event without explanation: recent_attempts quality.detail_ready is False."""
    event = _learning_event(
        "evt_no_explain",
        days_ago=0,
        question_id="q_no_explain",
        # Pass explanation="" to simulate missing explanation
        explanation="",
    )
    model = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([event]),
        event_limit=50,
    )

    attempt = model["learner_facing"]["recent_attempts"][0]
    quality = attempt["quality"]
    assert quality["detail_ready"] is False
    assert "explanation" in quality["missing_fields"]
