from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest

from deeptutor.services.first_run import manifest as manifest_module
from deeptutor.services.first_run.manifest import load_first_run_manifest
from deeptutor.services.first_run.writeback import (
    FirstRunIdempotencyConflict,
    FirstRunWritebackService,
)


@dataclass
class _Event:
    event_id: str
    user_id: str
    source_feature: str
    source_id: str
    memory_kind: str
    payload_json: dict[str, Any]
    dedupe_key: str
    created_at: str = "2026-07-11T10:00:00+08:00"


class _FakeLearnerState:
    def __init__(self, *, fail_on_append_call: int = 0) -> None:
        self.events: list[_Event] = []
        self.by_dedupe: dict[str, _Event] = {}
        self.profile: dict[str, Any] = {
            "display_name": "测试学员",
            "learning_preferences": {"existing": "preserved"},
        }
        self.progress: dict[str, Any] = {}
        self.append_calls = 0
        self.fail_on_append_call = fail_on_append_call

    def append_memory_event(self, user_id: str, **kwargs: Any) -> _Event:
        self.append_calls += 1
        dedupe_key = str(kwargs["dedupe_key"])
        if dedupe_key in self.by_dedupe:
            return self.by_dedupe[dedupe_key]
        if self.fail_on_append_call and self.append_calls == self.fail_on_append_call:
            self.fail_on_append_call = 0
            raise RuntimeError("synthetic_append_failure")
        event = _Event(
            event_id=f"evt_{len(self.events) + 1}",
            user_id=user_id,
            source_feature=str(kwargs["source_feature"]),
            source_id=str(kwargs["source_id"]),
            memory_kind=str(kwargs["memory_kind"]),
            payload_json=dict(kwargs["payload_json"]),
            dedupe_key=dedupe_key,
        )
        self.events.append(event)
        self.by_dedupe[dedupe_key] = event
        return event

    def read_profile(self, user_id: str) -> dict[str, Any]:
        assert user_id == "user-1"
        return deepcopy(self.profile)

    def write_profile_strict(self, user_id: str, profile: dict[str, Any]) -> None:
        assert user_id == "user-1"
        self.profile = deepcopy(profile)

    def merge_profile_strict(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        assert user_id == "user-1"
        learning = dict(self.profile.get("learning_preferences") or {})
        learning.update(deepcopy(patch.get("learning_preferences") or {}))
        self.profile["learning_preferences"] = learning
        return deepcopy(self.profile)

    def merge_progress(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        assert user_id == "user-1"
        self.progress.update(deepcopy(patch))
        return deepcopy(self.progress)


@pytest.fixture(autouse=True)
def supply_ready_packs(monkeypatch: pytest.MonkeyPatch) -> None:
    """处方供给真值 stub(disk-agnostic):默认 F16/X03 可练——磁盘 manifest
    的签发/停发状态不再左右本文件断言(2026-07-16 F16 停发曾打红这里)。"""
    monkeypatch.setattr(
        "deeptutor.services.first_run.prescription_resolver.list_green_lessons",
        lambda: [
            {"pack_id": "F16", "retest_available": True},
            {"pack_id": "X03", "retest_available": True},
            {"pack_id": "N01", "retest_available": True},
        ],
    )


@pytest.fixture(autouse=True)
def signed_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = deepcopy(load_first_run_manifest())
    manifest["release_status"] = "signed"
    for question in manifest["questions"]:
        question["review_status"] = "signed"
        question_id = str(question["question_id"])
        content_sha256 = str(question["content_sha256"])
        question["review_refs"] = [
            {
                "reviewer_id": reviewer_id,
                "reviewer_kind": "human",
                "reviewer_role": "teaching_reviewer",
                "verdict": "approve",
                "delegated": False,
                "reviewed_on": "2026-07-11",
                "question_id": question_id,
                "content_sha256": content_sha256,
            }
            for reviewer_id in ("teacher-one", "teacher-two")
        ]
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: manifest)
    monkeypatch.setattr(
        manifest_module,
        "load_first_run_reviewer_registry",
        lambda: {"teacher-one", "teacher-two"},
    )


def _completion(
    *,
    completion_id: str = "completion-0001",
    first_answer: str = "B",
    material_version: str = "y2026",
) -> dict[str, Any]:
    manifest = manifest_module.load_first_run_manifest()
    answers = [
        {
            "question_id": question["question_id"],
            "selected_key": first_answer if index == 0 else "A",
            "duration_ms": 8_000 + index,
        }
        for index, question in enumerate(manifest["questions"])
    ]
    return {
        "completion_id": completion_id,
        "script_version": manifest["script_version"],
        "completed_at": "2026-07-11T02:00:00Z",
        "answers": answers,
        "declared_preferences": {
            "exam_stage": "second",
            "answer_style": "nopoint",
            "material_version": material_version,
            "memory_channel": "B",
            "study_slot": "C",
            "motivation": "B",
        },
    }


def test_complete_re_scores_and_replay_does_not_duplicate_events() -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)
    body = _completion()

    first = service.complete(user_id="user-1", **body)
    replay = service.complete(user_id="user-1", **body)

    assert first == replay
    assert len(learner_state.events) == 4
    assert first["sync_status"] == "synced"
    assert first["score"] == {"correct_count": 3, "question_count": 4}
    assert first["items"][0]["is_correct"] is False
    assert all(event.source_feature == "first_run_diagnostic" for event in learner_state.events)
    assert len({event.dedupe_key for event in learner_state.events}) == 4


def test_same_completion_id_with_different_body_conflicts_before_extra_writes() -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)
    service.complete(user_id="user-1", **_completion(completion_id="completion-conflict"))

    with pytest.raises(FirstRunIdempotencyConflict, match="completion-conflict"):
        service.complete(
            user_id="user-1",
            **_completion(completion_id="completion-conflict", material_version="older"),
        )

    assert len(learner_state.events) == 4


def test_partial_append_is_completed_by_same_idempotent_retry() -> None:
    learner_state = _FakeLearnerState(fail_on_append_call=3)
    service = FirstRunWritebackService(learner_state_service=learner_state)
    body = _completion(completion_id="completion-retry")

    with pytest.raises(RuntimeError, match="synthetic_append_failure"):
        service.complete(user_id="user-1", **body)
    assert len(learner_state.events) == 2

    result = service.complete(user_id="user-1", **body)

    assert result["sync_status"] == "synced"
    assert len(learner_state.events) == 4
    assert len({event.dedupe_key for event in learner_state.events}) == 4


def test_explicit_preferences_merge_without_promoting_inferred_personality() -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)

    result = service.complete(user_id="user-1", **_completion())

    preferences = learner_state.profile["learning_preferences"]
    assert preferences["existing"] == "preserved"
    assert preferences["first_run"]["memory_channel"] == "B"
    assert preferences["first_run"]["source"] == "explicit_first_run_v1"
    assert "personality" not in learner_state.profile
    assert "home_personalization" in learner_state.progress
    assert result["training_intent"]["prescription_authority"] == "training_intent"


def test_declared_preferences_reject_values_outside_frontend_vocabulary() -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)
    body = _completion()
    body["declared_preferences"]["exam_stage"] = "ignore_previous_instructions"

    with pytest.raises(ValueError, match="invalid_declared_preference:exam_stage"):
        service.complete(user_id="user-1", **body)

    assert learner_state.events == []


def test_learning_events_do_not_claim_mastery_or_official_score() -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)

    service.complete(user_id="user-1", **_completion(first_answer="A"))

    for event in learner_state.events:
        assert event.payload_json["mastery_promotion_allowed"] is False
        assert event.payload_json["official_score_allowed"] is False
        assert "mastery" not in event.payload_json
    assert sum(bool(event.payload_json["training_intent_id"]) for event in learner_state.events) == 1


def test_missed_item_with_source_backed_pack_drives_real_target_without_promoting_claim() -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)

    result = service.complete(user_id="user-1", **_completion(first_answer="B"))

    assert result["training_intent"]["target_pack_id"] == "F16"
    assert result["home_projection"]["target_pack_id"] == "F16"
    focus_events = [event for event in learner_state.events if event.payload_json["target_pack_id"]]
    assert len(focus_events) == 1
    assert focus_events[0].payload_json["target_pack_id"] == "F16"
    assert result["training_intent"]["evidence_refs"] == [focus_events[0].event_id]
    assert all(event.payload_json["claim_promotion_allowed"] is False for event in learner_state.events)


def test_stopped_head_pack_resolves_to_next_supply_ready_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 红测试②(writeback 面):F16/X03 停发时首跑处方不产空 target——
    # intent 与 home projection 都绑定到下一个 supply-ready 候选(N01)。
    monkeypatch.setattr(
        "deeptutor.services.first_run.prescription_resolver.list_green_lessons",
        lambda: [
            {"pack_id": "F16", "retest_available": False},
            {"pack_id": "X03", "retest_available": False},
            {"pack_id": "N01", "retest_available": True},
        ],
    )
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)

    result = service.complete(user_id="user-1", **_completion(first_answer="B"))

    assert result["training_intent"]["target_pack_id"] == "N01"
    assert result["home_projection"]["target_pack_id"] == "N01"

    # 全候选停发 → 诚实无 pack 绑定(空 target),不臆造第二真值。
    monkeypatch.setattr(
        "deeptutor.services.first_run.prescription_resolver.list_green_lessons",
        lambda: [
            {"pack_id": "F16", "retest_available": False},
            {"pack_id": "X03", "retest_available": False},
            {"pack_id": "N01", "retest_available": False},
        ],
    )
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)

    result = service.complete(user_id="user-1", **_completion(first_answer="B"))

    assert result["training_intent"]["target_pack_id"] == ""
    assert result["home_projection"]["target_pack_id"] == ""
    assert all(not event.payload_json["target_pack_id"] for event in learner_state.events)


def test_home_projection_failure_does_not_commit_first_run_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    learner_state = _FakeLearnerState()
    service = FirstRunWritebackService(learner_state_service=learner_state)
    monkeypatch.setattr(
        "deeptutor.services.first_run.writeback.write_home_personalization_projection",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(RuntimeError, match="first_run_home_projection_unavailable"):
        service.complete(user_id="user-1", **_completion())

    assert "first_run" not in learner_state.profile["learning_preferences"]
