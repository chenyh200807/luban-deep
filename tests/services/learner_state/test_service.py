from __future__ import annotations

import asyncio
import json

import pytest

from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
from deeptutor.services.learner_state.service import LearnerStateEvent, LearnerStateOutboxService, LearnerStateService


class _PathServiceStub:
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


class _FakeMemberService:
    def get_profile(self, user_id: str):
        return {
            "user_id": user_id,
            "display_name": "陈同学",
            "tier": "vip",
            "status": "active",
            "difficulty_preference": "medium",
            "explanation_style": "detailed",
            "daily_target": 30,
            "review_reminder": True,
            "level": 7,
            "points": 240,
            "exam_date": "2026-09-19",
            "focus_topic": "地基基础承载力",
            "focus_query": "承载力和沉降控制怎么区分",
        }

    def get_today_progress(self, user_id: str):
        return {"today_done": 6, "daily_target": 30, "streak_days": 4}

    def get_chapter_progress(self, user_id: str):
        return [
            {"chapter_id": "ch_1", "chapter_name": "地基基础", "done": 12, "total": 30},
            {"chapter_id": "ch_2", "chapter_name": "结构构造", "done": 8, "total": 30},
        ]


class _CoreStoreStub:
    def __init__(self) -> None:
        self.is_configured = True
        self.profile: dict[str, object] = {}
        self.progress: dict[str, object] = {}
        self.compiled_learning_truth: dict[str, object] = {}
        self.memory_events: list[dict[str, object]] = []
        self.goals: list[dict[str, object]] = []
        self.fail_goal_title: str | None = None

    def read_profile(self, _user_id: str):
        return dict(self.profile)

    def write_profile(self, _user_id: str, profile: dict[str, object]):
        self.profile = dict(profile)
        return dict(profile)

    def read_progress(self, _user_id: str):
        return dict(self.progress)

    def write_progress(self, _user_id: str, progress: dict[str, object]):
        self.progress = dict(progress)
        return dict(progress)

    def read_compiled_learning_truth(self, _user_id: str):
        return dict(self.compiled_learning_truth)

    def read_memory_events(self, _user_id: str, limit: int | None = 20):
        rows = [dict(item) for item in self.memory_events]
        if limit is None or limit < 0:
            return rows
        return rows[-int(limit):]

    def read_learning_evidence_event(self, user_id: str, event_id: str):
        for row in self.memory_events:
            if row.get("user_id") == user_id and row.get("event_id") == event_id:
                return dict(row)
        return None

    def read_goals(self, _user_id: str):
        return [dict(item) for item in self.goals]

    def upsert_goal(self, _user_id: str, goal: dict[str, object]):
        title = str(goal.get("title") or "")
        if self.fail_goal_title and title == self.fail_goal_title:
            raise RuntimeError("goal sync failed")
        saved = dict(goal)
        saved.setdefault("id", title or f"goal_{len(self.goals) + 1}")
        goal_id = str(saved["id"])
        self.goals = [item for item in self.goals if str(item.get("id")) != goal_id] + [saved]
        return dict(saved)

    def delete_goal(self, goal_id: str) -> None:
        self.goals = [item for item in self.goals if str(item.get("id")) != str(goal_id)]


class _DisabledCoreStoreStub:
    is_configured = False


def _make_service(tmp_path, *, core_store=None):
    return LearnerStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_FakeMemberService(),
        core_store=core_store or _DisabledCoreStoreStub(),
    )


def test_learner_state_build_context_seeds_profile_summary_progress(tmp_path) -> None:
    service = _make_service(tmp_path)

    context = service.build_context("student_demo", language="zh")
    profile_path = tmp_path / "learner_state" / "student_demo" / "PROFILE.json"
    summary_path = tmp_path / "learner_state" / "student_demo" / "SUMMARY.md"
    progress_path = tmp_path / "learner_state" / "student_demo" / "PROGRESS.json"

    assert "学员级长期状态" in context
    assert "地基基础承载力" in context
    assert "今日进度" in context
    assert profile_path.exists()
    assert summary_path.exists()
    assert progress_path.exists()

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    summary = summary_path.read_text(encoding="utf-8")

    assert profile["display_name"] == "陈同学"
    assert "points" not in profile
    assert progress["today"]["today_done"] == 6
    assert "当前学习概览" in summary
    assert "积分余额" not in context


def test_learner_state_context_renders_construction_grading_error_events(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1:q-law",
        source_bot_id="construction-exam-coach",
        memory_kind="mcq_error_event",
        payload_json={
            "event_type": "construction_grading_error",
            "question_type": "mcq",
            "question_id": "q-law",
            "score_awarded": 0.0,
            "max_score": 1.0,
            "error_events": [
                {
                    "error_code": "M02",
                    "diagnosis": "把行政法规与部门规章层级混淆。",
                }
            ],
            "next_training_signal": {
                "concept": "法规层级",
                "focus": "行政法规与部门规章辨析",
            },
        },
    )

    context = service.build_context("student_demo", language="zh")
    candidates = service.build_context_candidates(
        user_id="student_demo",
        query="继续练刚才薄弱的点",
        route="recall",
        language="zh",
    )

    assert "建筑实务批改错因" in context
    assert "把行政法规与部门规章层级混淆" in context
    assert "行政法规与部门规章辨析" in context
    assert any(
        "行政法规与部门规章辨析" in str(candidate.get("content") or "")
        for candidate in candidates.get("candidates", [])
    )


def test_learner_state_context_renders_learning_evidence_events(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1:q-law",
        source_bot_id="construction-exam-coach",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "question_type": "mcq",
            "question_id": "q-law",
            "score_awarded": 0.0,
            "max_score": 1.0,
            "error_events": [
                {
                    "error_code": "M02",
                    "diagnosis": "把行政法规与部门规章层级混淆。",
                }
            ],
            "next_training_signal": {
                "concept": "法规层级",
                "focus": "行政法规与部门规章辨析",
            },
        },
    )

    context = service.build_context("student_demo", language="zh")
    candidates = service.build_context_candidates(
        user_id="student_demo",
        query="继续练刚才薄弱的点",
        route="recall",
        language="zh",
    )

    assert "建筑实务批改错因" in context
    assert "把行政法规与部门规章层级混淆" in context
    assert "行政法规与部门规章辨析" in context
    assert any(
        "行政法规与部门规章辨析" in str(candidate.get("content") or "")
        for candidate in candidates.get("candidates", [])
    )


def test_read_learning_evidence_event_local_hit_miss_and_cache(tmp_path) -> None:
    service = _make_service(tmp_path)
    saved = service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1:q-local",
        source_bot_id="construction-exam-coach",
        memory_kind="learning_evidence",
        payload_json={"event_type": "learning_evidence", "question_id": "q-local"},
    )

    hit = service.read_learning_evidence_event("student_demo", saved.event_id)
    assert hit is not None
    assert hit.event_id == saved.event_id
    assert service.read_learning_evidence_event("student_demo", "missing") is None
    assert service.read_learning_evidence_event("other_user", saved.event_id) is None

    event_path = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"
    event_path.write_text("", encoding="utf-8")
    cached = service.read_learning_evidence_event("student_demo", saved.event_id)
    assert cached is not None
    assert cached.event_id == saved.event_id


def test_read_learning_evidence_event_remote_first_when_configured(tmp_path) -> None:
    store = _CoreStoreStub()
    store.memory_events = [
        {
            "event_id": "evt_remote",
            "user_id": "student_demo",
            "source_feature": "construction_grading",
            "source_id": "turn:remote",
            "source_bot_id": "construction-exam-coach",
            "memory_kind": "learning_evidence",
            "payload_json": {"event_type": "learning_evidence", "question_id": "q-remote"},
            "dedupe_key": "evt_remote",
            "created_at": "2026-05-21T00:00:00+08:00",
        }
    ]
    service = _make_service(tmp_path, core_store=store)

    event = service.read_learning_evidence_event("student_demo", "evt_remote")

    assert event is not None
    assert event.event_id == "evt_remote"
    assert event.payload_json["question_id"] == "q-remote"


def test_learner_state_synthesize_learning_truth_dry_run_does_not_enqueue(tmp_path) -> None:
    service = _make_service(tmp_path)
    for index in range(2):
        service.append_memory_event(
            "student_demo",
            source_feature="construction_grading",
            source_id=f"turn-{index}",
            source_bot_id="construction-exam",
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "learning_evidence",
                "turn_id": f"turn-{index}",
                "question_id": f"q-{index}",
                "question_type": "case",
                "score_awarded": 0,
                "max_score": 1,
                "error_events": [
                    {"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}
                ],
                "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
                "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
            },
        )

    result = service.synthesize_learning_truth("student_demo", dry_run=True)

    assert result["projection"]["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert result["outbox_item"] is None
    assert [
        item for item in service.outbox_service.list_pending("student_demo")
        if item.event_type == "summary_refresh"
    ] == []
    assert service.read_compiled_learning_truth("student_demo") == {}


def test_learner_state_synthesize_learning_truth_enqueues_summary_refresh(tmp_path) -> None:
    service = _make_service(tmp_path)
    for index in range(2):
        service.append_memory_event(
            "student_demo",
            source_feature="construction_grading",
            source_id=f"turn-{index}",
            source_bot_id="construction-exam",
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "learning_evidence",
                "turn_id": f"turn-{index}",
                "question_id": f"q-{index}",
                "question_type": "case",
                "score_awarded": 0,
                "max_score": 1,
                "error_events": [
                    {"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}
                ],
                "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
                "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
            },
        )

    result = service.synthesize_learning_truth("student_demo", dry_run=False)

    pending = [
        item for item in service.outbox_service.list_pending("student_demo")
        if item.event_type == "summary_refresh"
    ]
    assert result["outbox_item"] is not None
    assert pending[0].event_type == "summary_refresh"
    assert (
        pending[0].payload_json["summary_structured_json"]["learning_brain"]["subject"]
        == "construction_exam_learning_truth"
    )
    assert result["projection"]["synthesis_run"]["status"] == "persisted_enqueued"
    assert (
        pending[0].payload_json["summary_structured_json"]["learning_brain"]["synthesis_run"]["status"]
        == "persisted_enqueued"
    )
    projection = service.read_compiled_learning_truth("student_demo")
    assert projection["subject"] == "construction_exam_learning_truth"
    assert service.build_context_candidates("student_demo")["compiled_learning_truth"]["subject"] == (
        "construction_exam_learning_truth"
    )
    read_model = build_learning_brain_read_model(
        user_id="student_demo",
        projection=projection,
        surface="mobile",
    )
    visible_text = json.dumps(
        [
            item.get("display_title", "") + " " + item.get("display_meta", "") + " " + item.get("display_path", "")
            for section in read_model["visible_sections"].values()
            for item in section
            if isinstance(item, dict)
        ],
        ensure_ascii=False,
    )
    assert "工程招标投标与合同管理" in visible_text
    assert "1A432000" not in visible_text
    assert "E02" not in visible_text


def test_learner_state_synthesis_reads_remote_memory_events_when_configured(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.memory_events = [
        {
            "event_id": f"remote_evt_{index}",
            "user_id": "student_demo",
            "source_feature": "construction_grading",
            "source_id": f"remote-turn-{index}",
            "source_bot_id": "construction-exam",
            "memory_kind": "learning_evidence",
            "payload_json": {
                "event_type": "learning_evidence",
                "turn_id": f"remote-turn-{index}",
                "question_id": f"remote-q-{index}",
                "question_type": "case",
                "score_awarded": 0,
                "max_score": 1,
                "error_events": [
                    {"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}
                ],
                "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
                "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
            },
            "dedupe_key": f"remote-dedupe-{index}",
            "created_at": f"2026-05-18T10:0{index}:00+08:00",
        }
        for index in range(2)
    ]
    service = _make_service(tmp_path, core_store=core_store)
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="local-stale",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "turn_id": "local-stale",
            "question_id": "local-q",
            "question_type": "case",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [
                {"error_code": "E04", "concept_tag": "1A421000", "diagnosis": "本地旧事件。"}
            ],
            "next_training_signal": {"concept": "1A421000", "focus": "本地旧弱点"},
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )

    result = service.synthesize_learning_truth("student_demo", dry_run=True)

    assert result["projection"]["weak_points"][0]["concept_id"] == "1A432000"
    assert result["projection"]["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert all(
        item.get("concept_id") != "1A421000"
        for item in result["projection"].get("weak_points", [])
    )


def test_learner_state_local_projection_fallback_reads_local_events_before_remote(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK", "1")
    core_store = _CoreStoreStub()
    service = _make_service(tmp_path, core_store=core_store)
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="local-turn",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "turn_id": "local-turn",
            "question_id": "local-q",
            "question_type": "case",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [
                {"error_code": "E04", "concept_tag": "1A421000", "diagnosis": "本地事件。"}
            ],
            "next_training_signal": {"concept": "1A421000", "focus": "本地弱点"},
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )

    events = service.list_memory_events("student_demo", limit=None)

    assert [event.source_id for event in events] == ["local-turn"]


def test_learner_state_non_production_falls_back_to_local_memory_events_when_remote_empty(tmp_path) -> None:
    core_store = _CoreStoreStub()
    service = _make_service(tmp_path, core_store=core_store)
    saved = service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="local-turn",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "turn_id": "local-turn",
            "question_id": "local-q",
            "question_type": "case",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [
                {"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}
            ],
            "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
        },
    )

    events = service.list_memory_events("student_demo", limit=None)

    assert [event.event_id for event in events] == [saved.event_id]


def test_append_memory_event_dedupe_returns_existing_event_without_second_outbox_item(tmp_path) -> None:
    service = _make_service(tmp_path)
    first = service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1",
        memory_kind="learning_evidence",
        payload_json={"event_type": "learning_evidence", "question_id": "q-1"},
        dedupe_key="same-event",
    )
    second = service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1-retry",
        memory_kind="learning_evidence",
        payload_json={"event_type": "learning_evidence", "question_id": "q-1"},
        dedupe_key="same-event",
    )

    assert second.event_id == first.event_id
    assert second.source_id == first.source_id
    assert [event.event_id for event in service.list_memory_events("student_demo", limit=None)] == [
        first.event_id
    ]
    pending_learning_events = [
        item
        for item in service.outbox_service.list_pending("student_demo", limit=None)
        if item.event_type == "learning_evidence"
    ]
    assert len(pending_learning_events) == 1


def test_learner_state_reads_remote_compiled_truth_before_local_cache(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.compiled_learning_truth = {
        "subject": "construction_exam_learning_truth",
        "weak_points": [{"concept_id": "1A432000", "error_code": "E04"}],
    }
    service = _make_service(tmp_path, core_store=core_store)
    service.write_compiled_learning_truth(
        "student_demo",
        {
            "subject": "stale_local_projection",
            "weak_points": [{"concept_id": "1A421000", "error_code": "E01"}],
        },
    )

    projection = service.read_compiled_learning_truth("student_demo")
    context_candidates = service.build_context_candidates("student_demo")

    assert projection["subject"] == "construction_exam_learning_truth"
    assert projection["weak_points"][0]["error_code"] == "E04"
    assert context_candidates["compiled_learning_truth"]["weak_points"][0]["error_code"] == "E04"


def test_learner_state_configured_core_store_is_compiled_truth_authority(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.compiled_learning_truth = {
        "learning_brain": {
            "subject": "construction_exam_learning_truth",
            "weak_points": [{"concept_id": "1A432000", "error_code": "E02"}],
            "typed_graph": {},
            "synthesis_run": {
                "generated_at": "2026-05-18T10:00:00+08:00",
                "output_projection_hash": "sha256:old",
            },
        },
    }
    service = _make_service(tmp_path, core_store=core_store)
    service.write_compiled_learning_truth(
        "student_demo",
        {
            "subject": "construction_exam_learning_truth",
            "weak_points": [{"concept_id": "1A432000", "error_code": "E04"}],
            "synthesis_run": {
                "generated_at": "2026-05-18T11:00:00+08:00",
                "output_projection_hash": "sha256:new",
            },
        },
    )

    projection = service.read_compiled_learning_truth("student_demo")

    assert projection["synthesis_run"]["output_projection_hash"] == "sha256:old"
    assert projection["weak_points"][0]["error_code"] == "E02"


def test_learner_state_production_without_core_store_does_not_read_local_compiled_truth(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    service = _make_service(tmp_path)
    service.write_compiled_learning_truth(
        "student_demo",
        {
            "subject": "construction_exam_learning_truth",
            "weak_points": [{"concept_id": "1A432000", "error_code": "E02"}],
        },
    )

    assert service.read_compiled_learning_truth("student_demo") == {}
    assert service.build_context_candidates("student_demo")["compiled_learning_truth"] == {}
    assert not (tmp_path / "learner_state" / "student_demo" / "COMPILED_TRUTH.json").exists()


def test_learner_state_ignores_non_learning_brain_summary_structured_json(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.compiled_learning_truth = {
        "guide_completion": {
            "guide_id": "guide_42",
            "notebook_name": "地基基础",
        }
    }
    service = _make_service(tmp_path, core_store=core_store)

    assert service.read_compiled_learning_truth("student_demo") == {}


def test_learning_synthesis_summary_refresh_dedupe_includes_projection_hash(tmp_path) -> None:
    service = _make_service(tmp_path)
    base_payload = {
        "event_type": "learning_evidence",
        "turn_id": "turn-1",
        "question_id": "q-1",
        "question_type": "case",
        "score_awarded": 0,
        "max_score": 1,
        "error_events": [{"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}],
        "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
        "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
    }
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json=base_payload,
    )
    first = service.synthesize_learning_truth("student_demo", dry_run=False)

    second_payload = dict(base_payload)
    second_payload["turn_id"] = "turn-2"
    second_payload["question_id"] = "q-2"
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-2",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        payload_json=second_payload,
    )
    second = service.synthesize_learning_truth("student_demo", dry_run=False)

    pending = [
        item for item in service.outbox_service.list_pending("student_demo", limit=None)
        if item.event_type == "summary_refresh"
    ]
    assert first["outbox_item"].id != second["outbox_item"].id
    assert len(pending) == 2
    learning_brain = pending[-1].payload_json["summary_structured_json"]["learning_brain"]
    assert second["projection"]["synthesis_run"]["previous_projection_hash"] == (
        first["projection"]["synthesis_run"]["output_projection_hash"]
    )
    assert second["projection"]["synthesis_run"]["status"] == "persisted_enqueued"
    assert len(learning_brain["observed_candidates"]) == 0
    assert learning_brain["weak_points"][0]["evidence_level"] == "L1_repeated"


def test_learner_state_build_compact_context_returns_learner_facts_only(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.goals = [
        {
            "id": "goal_1",
            "user_id": "student_demo",
            "goal_type": "study",
            "title": "掌握承载力与沉降控制区分",
            "progress": 35,
            "deadline": "2026-05-01",
        }
    ]
    service = _make_service(tmp_path, core_store=core_store)

    compact = service.build_compact_context("student_demo", language="zh")

    assert compact["user_id"] == "student_demo"
    assert "learner_profile" in compact["source_tags"]
    assert "learner_summary" in compact["source_tags"]
    assert "learner_progress" in compact["source_tags"]
    assert "learner_goals" in compact["source_tags"]
    assert "memory_hit" not in compact["content"]
    assert any(segment["source_tag"] == "learner_profile" for segment in compact["segments"])
    assert any(segment["source_tag"] == "learner_goals" for segment in compact["segments"])


def test_learner_state_build_context_candidates_default_skips_memory_hits(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.goals = [
        {
            "id": "goal_1",
            "user_id": "student_demo",
            "goal_type": "study",
            "title": "掌握承载力与沉降控制区分",
            "progress": 35,
            "deadline": "2026-05-01",
        }
    ]
    service = _make_service(tmp_path, core_store=core_store)
    service.record_turn_event(
        user_id="student_demo",
        session_id="session_1",
        capability="chat",
        user_message="我刚才问的是承载力怎么区分。",
        assistant_message="先看承载力，再看沉降控制。",
        source_bot_id="bot_a",
    )

    candidates = service.build_context_candidates("student_demo", query="继续讲解", language="zh")

    assert candidates["route"] == "default"
    assert candidates["memory_candidates"] == []
    assert candidates["candidates"]
    assert all(item["source_tag"] != "memory_hit" for item in candidates["candidates"])
    assert {item["source_tag"] for item in candidates["learner_candidates"]} >= {
        "learner_profile",
        "learner_summary",
        "learner_progress",
        "learner_goals",
    }


def test_learner_state_build_context_candidates_recall_includes_memory_hits(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.record_turn_event(
        user_id="student_demo",
        session_id="session_2",
        capability="chat",
        user_message="承载力和沉降控制要怎么区分？",
        assistant_message="承载力看极限状态，沉降控制看正常使用阶段。",
        source_bot_id="bot_a",
    )
    asyncio.run(
        service.record_notebook_writeback(
            user_id="student_demo",
            notebook_id="nb_1",
            record_id="rec_1",
            operation="writeback",
            title="承载力和沉降控制",
            summary="先分清极限承载和正常使用阶段。",
            user_query="回顾承载力和沉降控制",
            record_type="guide",
            source_bot_id="bot_a",
        )
    )

    candidates = service.build_context_candidates(
        "student_demo",
        query="请回顾一下刚才承载力和沉降控制的说法",
        language="zh",
    )

    assert candidates["route"] == "recall"
    assert candidates["memory_candidates"]
    assert any(item["source_tag"] == "memory_hit" for item in candidates["candidates"])
    assert any("承载力和沉降控制" in item["content"] for item in candidates["memory_candidates"])


def test_learner_state_build_context_candidates_accepts_orchestration_route_aliases(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.record_turn_event(
        user_id="student_demo",
        session_id="session_2",
        capability="chat",
        user_message="我喜欢先讲概念再做题。",
        assistant_message="记住了，你偏好先讲概念再做题。",
        source_bot_id="bot_a",
    )

    candidates = service.build_context_candidates(
        "student_demo",
        query="你还记得我偏好吗",
        route="personal_recall",
        language="zh",
    )

    assert candidates["route"] == "recall"
    assert candidates["memory_candidates"]
    assert any(item["source_tag"] == "memory_hit" for item in candidates["candidates"])


def test_learner_state_write_progress_and_refresh_from_turn(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    service.build_context("student_demo", language="zh")
    service.merge_progress("student_demo", {"today": {"today_done": 8}})

    async def _rewrite_stream(**_kwargs):
        yield (
            "## 当前学习概览\n"
            "- 已完成一轮概念巩固。\n\n"
            "## 稳定偏好\n"
            "- 继续保持详细讲解。\n\n"
            "## 待持续观察\n"
            "- 继续关注承载力与沉降控制的区分。"
        )

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _rewrite_stream)

    result = asyncio.run(
        service.refresh_from_turn(
            user_id="student_demo",
            user_message="我总是把承载力和沉降控制混在一起。",
            assistant_message="先区分极限承载能力和正常使用阶段的沉降控制，再做两道案例题。",
            session_id="session_1",
            capability="chat",
            language="zh",
        )
    )

    summary_path = tmp_path / "learner_state" / "student_demo" / "SUMMARY.md"
    events_path = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"

    assert result.changed is True
    assert "已完成一轮概念巩固" in result.content
    assert "沉降控制" in summary_path.read_text(encoding="utf-8")

    event_lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(event_lines) == 1
    event = json.loads(event_lines[0])
    assert event["memory_kind"] == "turn"
    assert event["payload_json"]["assistant_message"].startswith("先区分极限承载能力")

    pending = service.outbox_service.list_pending("student_demo", limit=None)
    event_types = [item.event_type for item in pending]
    assert "turn" in event_types
    assert "summary_refresh" in event_types


def test_learner_state_skips_low_signal_turn_writeback(monkeypatch, tmp_path) -> None:
    service = _make_service(tmp_path)
    service.build_context("student_demo", language="zh")
    before_summary = service.read_summary("student_demo")

    async def _unexpected_stream(**_kwargs):
        raise AssertionError("low-signal turn should not trigger summary rewrite")
        yield ""

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _unexpected_stream)

    result = asyncio.run(
        service.refresh_from_turn(
            user_id="student_demo",
            user_message="你好",
            assistant_message="你好，我在。",
            session_id="session_hello",
            capability="chat",
            language="zh",
        )
    )

    events_path = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"
    assert result.changed is False
    assert service.read_summary("student_demo") == before_summary
    assert not events_path.exists()


def test_learner_state_learning_plan_store_tracks_plan_and_pages(tmp_path) -> None:
    service = _make_service(tmp_path)

    async def _run():
        await service.upsert_learning_plan(
            user_id="student_demo",
            plan_id="session_demo",
            source_bot_id="bot_alpha",
            source_material_refs_json=[
                {"kind": "user_input", "content": "请帮我设计一个学习计划。"},
            ],
            knowledge_points_json=[
                {
                    "knowledge_title": "地基基础承载力",
                    "knowledge_summary": "梳理极限承载力与正常使用阶段控制。",
                }
            ],
            status="initialized",
            current_index=-1,
        )
        await service.update_learning_plan_page(
            user_id="student_demo",
            plan_id="session_demo",
            page_index=0,
            page_status="ready",
            html_content="<div class='page'>学习页面</div>",
            error_message="",
            source_bot_id="bot_alpha",
        )
        await service.update_learning_plan_page(
            user_id="student_demo",
            plan_id="session_demo",
            page_index=1,
            page_status="failed",
            html_content="<div class='page'>学习页面</div>",
            error_message="llm timeout",
            source_bot_id="bot_alpha",
        )
        await service.upsert_learning_plan(
            user_id="student_demo",
            plan_id="session_demo",
            source_bot_id="bot_alpha",
            knowledge_points_json=[
                {
                    "knowledge_title": "地基基础承载力",
                    "knowledge_summary": "梳理极限承载力与正常使用阶段控制。",
                }
            ],
            status="completed",
            current_index=0,
            completion_summary_md="## 完成总结\n- 已完成本次 guided learning。",
        )

    asyncio.run(_run())

    plan_path = tmp_path / "workspace" / "guide" / "learning_plans" / "session_demo.json"
    pages_path = tmp_path / "workspace" / "guide" / "learning_plan_pages" / "session_demo.json"

    assert plan_path.exists()
    assert pages_path.exists()

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    pages = json.loads(pages_path.read_text(encoding="utf-8"))

    assert plan["session_id"] == "session_demo"
    assert plan["user_id"] == "student_demo"
    assert plan["status"] == "completed"
    assert plan["current_index"] == 0
    assert plan["source_bot_id"] == "bot_alpha"
    assert plan["summary"].startswith("## 完成总结")
    assert plan["source_material_refs_json"][0]["kind"] == "user_input"

    assert pages[0]["session_id"] == "session_demo"
    assert pages[0]["page_status"] == "ready"
    assert pages[0]["html"] == "<div class='page'>学习页面</div>"
    assert pages[0]["updated_at"]
    assert pages[1]["session_id"] == "session_demo"
    assert pages[1]["page_status"] == "failed"
    pending = service.outbox_service.list_pending("student_demo", limit=None)
    assert any(item.event_type == "learning_plan_page" for item in pending)


def test_learner_state_outbox_enqueue_and_status_transitions(tmp_path) -> None:
    outbox = LearnerStateOutboxService(path_service=_PathServiceStub(tmp_path))
    payload = {
        "event_id": "evt_1",
        "source_feature": "progress",
        "source_id": "progress_1",
        "source_bot_id": "bot_a",
        "memory_kind": "progress",
        "payload_json": {"done": 1},
    }

    first = outbox.enqueue(
        id="evt_1",
        user_id="student_demo",
        event_type="progress",
        payload_json=payload,
        dedupe_key="dedupe_1",
        created_at="2026-04-15T10:00:00+08:00",
    )
    second = outbox.enqueue(
        id="evt_1_dup",
        user_id="student_demo",
        event_type="progress",
        payload_json=payload,
        dedupe_key="dedupe_1",
        created_at="2026-04-15T10:00:01+08:00",
    )

    assert first.id == second.id
    assert len(outbox.list_pending("student_demo")) == 1
    failed = outbox.mark_failed(first.id, last_error="network down")
    assert failed is not None
    assert failed.status == "pending"
    assert failed.retry_count == 1

    failed_view = outbox.enqueue(
        id="evt_1_retry",
        user_id="student_demo",
        event_type="progress",
        payload_json=payload,
        dedupe_key="dedupe_1",
        created_at="2026-04-15T10:00:02+08:00",
    )
    assert failed_view.status == "pending"
    assert failed_view.retry_count == 1

    sent = outbox.mark_sent(first.id)
    assert sent is not None
    assert sent.status == "sent"


def test_learner_state_guide_completion_enqueues_outbox_event(tmp_path) -> None:
    service = _make_service(tmp_path)

    event = asyncio.run(
        service.record_guide_completion(
            user_id="student_demo",
            guide_id="guide_42",
            notebook_name="地基基础",
            summary="已完成本次引导并收口关键误区。",
            knowledge_points=[
                {
                    "knowledge_title": "承载力和沉降控制",
                    "knowledge_summary": "先分清极限承载和正常使用极限状态。",
                    "user_difficulty": "medium",
                }
            ],
            source_bot_id="bot_a",
        )
    )

    pending = service.outbox_service.list_pending("student_demo")
    guide_events = [item for item in pending if item.event_type == "guide_completion"]

    assert len(guide_events) == 1
    item = guide_events[0]
    assert item.id == event.event_id
    assert item.event_type == "guide_completion"
    assert item.payload_json["source_feature"] == "guide"
    assert item.payload_json["payload_json"]["summary"] == "已完成本次引导并收口关键误区。"
    assert (
        item.payload_json["payload_json"]["knowledge_points"][0]["knowledge_title"]
        == "承载力和沉降控制"
    )
    progress = service.read_progress("student_demo")
    profile = service.read_profile("student_demo")
    assert progress["today"]["today_done"] == 7
    assert progress["knowledge_map"]["guided_learning"]["guide_id"] == "guide_42"
    assert progress["knowledge_map"]["guided_learning"]["completed_titles"] == ["承载力和沉降控制"]
    assert profile["focus_topic"] == "承载力和沉降控制"
    assert profile["focus_query"] == "继续巩固承载力和沉降控制"
    summary = service.read_summary("student_demo")
    assert "最近完成的引导学习" in summary
    assert "已完成本次引导并收口关键误区。" in summary
    assert "承载力和沉降控制" in summary
    compact = service.build_context_candidates(
        user_id="student_demo",
        query="下一步怎么复习？",
        route="default",
        language="zh",
    )
    learner_summary = next(
        item for item in compact["learner_candidates"] if item["source_tag"] == "learner_summary"
    )
    assert "已完成本次引导并收口关键误区。" in learner_summary["content"]


def test_learner_state_guide_completion_is_idempotent_by_guide_id(tmp_path) -> None:
    service = _make_service(tmp_path)

    asyncio.run(
        service.record_guide_completion(
            user_id="student_demo",
            guide_id="guide_42",
            notebook_name="地基基础",
            summary="第一次完成引导。",
            knowledge_points=[
                {
                    "knowledge_title": "承载力和沉降控制",
                    "knowledge_summary": "先分清极限承载和正常使用极限状态。",
                    "user_difficulty": "medium",
                }
            ],
            source_bot_id="bot_a",
        )
    )
    asyncio.run(
        service.record_guide_completion(
            user_id="student_demo",
            guide_id="guide_42",
            notebook_name="地基基础",
            summary="重复回放同一个引导，但内容略有变化。",
            knowledge_points=[
                {
                    "knowledge_title": "地基承载力验算",
                    "knowledge_summary": "重复调用不应再累计今日完成。",
                    "user_difficulty": "hard",
                },
                {
                    "knowledge_title": "沉降控制",
                    "knowledge_summary": "重复调用不应再插入等价历史记录。",
                    "user_difficulty": "medium",
                },
            ],
            source_bot_id="bot_a",
        )
    )

    progress = service.read_progress("student_demo")
    profile = service.read_profile("student_demo")
    guided_learning = progress["knowledge_map"]["guided_learning"]
    history = progress["knowledge_map"]["guided_learning_history"]

    assert progress["today"]["today_done"] == 7
    assert guided_learning["guide_id"] == "guide_42"
    assert guided_learning["total_points"] == 1
    assert guided_learning["completed_titles"] == ["承载力和沉降控制"]
    assert len(history) == 1
    assert history[0]["guide_id"] == "guide_42"
    assert profile["focus_topic"] == "承载力和沉降控制"
    assert profile["focus_query"] == "继续巩固承载力和沉降控制"


def test_learner_state_guide_completion_prefers_hard_point_for_profile_focus(tmp_path) -> None:
    service = _make_service(tmp_path)

    asyncio.run(
        service.record_guide_completion(
            user_id="student_demo",
            guide_id="guide_focus_1",
            notebook_name="地基基础",
            summary="本次重点暴露在承载力验算。",
            knowledge_points=[
                {
                    "knowledge_title": "沉降控制",
                    "knowledge_summary": "先区分工后沉降和总沉降。",
                    "user_difficulty": "medium",
                },
                {
                    "knowledge_title": "地基承载力验算",
                    "knowledge_summary": "要先明确承载力修正与基础埋深。",
                    "user_difficulty": "hard",
                },
            ],
            source_bot_id="bot_a",
        )
    )

    profile = service.read_profile("student_demo")

    assert profile["focus_topic"] == "地基承载力验算"
    assert profile["focus_query"] == "继续巩固地基承载力验算"


def test_sync_goals_strict_rolls_back_partial_goal_updates(tmp_path) -> None:
    core_store = _CoreStoreStub()
    core_store.goals = [
        {
            "id": "goal_existing",
            "user_id": "student_demo",
            "goal_type": "study",
            "title": "旧目标",
            "target_question_count": 10,
        }
    ]
    core_store.fail_goal_title = "失败目标"
    service = _make_service(tmp_path, core_store=core_store)

    with pytest.raises(RuntimeError):
        service.sync_goals_strict(
            "student_demo",
            [
                {
                    "id": "goal_new",
                    "goal_type": "study",
                    "title": "新目标",
                    "target_question_count": 20,
                },
                {
                    "id": "goal_fail",
                    "goal_type": "study",
                    "title": "失败目标",
                    "target_question_count": 30,
                },
            ],
        )

    assert core_store.goals == [
        {
            "id": "goal_existing",
            "user_id": "student_demo",
            "goal_type": "study",
            "title": "旧目标",
            "target_question_count": 10,
        }
    ]


def test_learner_state_heartbeat_job_sync_enqueues_outbox_event(tmp_path) -> None:
    service = _make_service(tmp_path)

    job = service.ensure_default_job(
        "student_demo",
        bot_id="bot_alpha",
        channel="web",
        policy_json={"enabled": True, "consent": True, "interval_hours": 3},
    )

    pending = service.outbox_service.list_pending("student_demo")
    assert len(pending) == 1
    first = pending[0]
    assert first.event_type == "heartbeat_job"
    assert first.payload_json["job_id"] == job.job_id
    assert first.payload_json["last_result_json"] == {}
    assert first.dedupe_key.startswith(f"heartbeat-job:{job.job_id}:")

    service.outbox_service.mark_sent(first.id)
    updated = service.record_run_result(
        job_id=job.job_id,
        success=True,
        result_json={"message": "sent"},
    )

    pending_after = service.outbox_service.list_pending("student_demo")
    assert len(pending_after) == 2
    job_event = next(item for item in pending_after if item.event_type == "heartbeat_job")
    delivery_event = next(item for item in pending_after if item.event_type == "heartbeat_delivery")
    assert job_event.payload_json["job_id"] == updated.job_id
    assert job_event.payload_json["last_result_json"]["success"] is True
    assert job_event.payload_json["last_result_json"]["delivery"]["state"] == "sent"
    assert job_event.payload_json["last_result_json"]["audit"]["status"] == "ok"
    assert delivery_event.payload_json["payload_json"]["job_id"] == updated.job_id
    assert delivery_event.payload_json["payload_json"]["delivery"]["state"] == "sent"
    assert delivery_event.payload_json["payload_json"]["audit"]["status"] == "ok"
    assert job_event.id != first.id
