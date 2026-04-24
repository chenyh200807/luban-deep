from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.overlay_service import BotLearnerOverlayService


class _PathServiceStub:
    def __init__(self, root):
        self._root = root

    @property
    def project_root(self):
        return self._root

    def get_learner_state_root(self):
        path = self._root / "learner_state"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"


def _make_service(tmp_path) -> BotLearnerOverlayService:
    return BotLearnerOverlayService(path_service=_PathServiceStub(tmp_path))


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.goals: list[dict[str, object]] = []
        self.profile: dict[str, object] = {}
        self.progress: dict[str, object] = {"knowledge_map": {"weak_points": []}}
        self.events: list[dict[str, object]] = []

    def upsert_goal(self, _user_id: str, goal: dict[str, object]):
        self.goals.append(dict(goal))
        return dict(goal)

    def merge_profile(self, _user_id: str, patch: dict[str, object]):
        self.profile.update(dict(patch))
        return dict(self.profile)

    def read_progress(self, _user_id: str):
        return dict(self.progress)

    def merge_progress(self, _user_id: str, patch: dict[str, object]):
        knowledge_map = dict(self.progress.get("knowledge_map") or {})
        incoming = dict(patch.get("knowledge_map") or {})
        knowledge_map.update(incoming)
        self.progress["knowledge_map"] = knowledge_map
        return dict(self.progress)

    def append_memory_event(
        self,
        _user_id: str,
        *,
        source_feature: str,
        source_id: str,
        source_bot_id: str | None,
        memory_kind: str,
        payload_json: dict[str, object],
        **_kwargs,
    ):
        self.events.append(
            {
                "source_feature": source_feature,
                "source_id": source_id,
                "source_bot_id": source_bot_id,
                "memory_kind": memory_kind,
                "payload_json": dict(payload_json),
            }
        )
        return self.events[-1]


def test_read_overlay_returns_empty_structure_when_missing(tmp_path) -> None:
    service = _make_service(tmp_path)

    overlay = service.read_overlay("bot_alpha", "student_demo")

    assert overlay["exists"] is False
    assert overlay["effective_overlay"]["local_focus"] == {}
    assert overlay["effective_overlay"]["promotion_candidates"] == []
    assert overlay["heartbeat_override_candidate"] == {}


def test_patch_overlay_rejects_forbidden_fields(tmp_path) -> None:
    service = _make_service(tmp_path)

    try:
        service.patch_overlay(
            "bot_alpha",
            "student_demo",
            {"op": "set", "field": "profile", "value": {"level": "advanced"}},
            source_feature="guide",
            source_id="guide_1",
        )
    except ValueError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("expected forbidden overlay field to be rejected")


def test_patch_overlay_supports_set_merge_clear_and_append_candidate(tmp_path) -> None:
    service = _make_service(tmp_path)

    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "operations": [
                {"op": "set", "field": "working_memory_projection", "value": "先盯住承载力与沉降控制的区分。"},
                {"op": "set", "field": "local_notebook_scope_refs", "value": ["nb-1", "rec-2"]},
                {"op": "merge", "field": "local_focus", "value": {"topic": "foundation", "status": "active"}},
                {"op": "append_candidate", "field": "promotion_candidates", "value": {"candidate_kind": "stable_preference"}},
            ]
        },
        source_feature="guide",
        source_id="guide_1",
    )
    overlay = service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {"op": "clear", "field": "working_memory_projection"},
        source_feature="guide",
        source_id="guide_2",
    )

    assert overlay["exists"] is True
    assert overlay["effective_overlay"]["local_focus"]["topic"] == "foundation"
    assert overlay["effective_overlay"]["working_memory_projection"] == ""
    assert overlay["effective_overlay"]["local_notebook_scope_refs"] == ["nb-1", "rec-2"]
    assert len(overlay["promotion_candidates"]) == 1
    assert overlay["promotion_candidates"][0]["source_feature"] == "guide"
    events_path = tmp_path / "learner_state" / "bot_overlays" / "student_demo__bot_alpha.events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events
    assert events[-1]["event_type"] == "overlay_patch"
    assert events[-1]["overlay_write_reason"] == "guide"
    outbox_path = tmp_path / "runtime" / "outbox.db"
    assert outbox_path.exists()


def test_build_context_fragment_renders_local_overlay_only(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "operations": [
                {"op": "merge", "field": "local_focus", "value": {"topic": "network_plan"}},
                {"op": "set", "field": "working_memory_projection", "value": "当前 Bot 正在带用户复习关键线路。"},
            ]
        },
        source_feature="chat",
        source_id="turn_1",
    )

    fragment = service.build_context_fragment("bot_alpha", "student_demo", language="zh", max_chars=500)

    assert "Bot-Learner Overlay" in fragment
    assert "network_plan" in fragment
    assert "关键线路" in fragment
    assert "全局 learner truth" in fragment


def test_promote_candidate_appends_candidate_with_metadata(tmp_path) -> None:
    service = _make_service(tmp_path)

    overlay = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "stable_goal_signal",
        {"goal": "case-study"},
        source_feature="review",
        source_id="turn_7",
    )

    candidates = overlay["promotion_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["candidate_kind"] == "stable_goal_signal"
    assert candidates[0]["payload"] == {"goal": "case-study"}
    assert candidates[0]["source_feature"] == "review"
    assert candidates[0]["source_id"] == "turn_7"

    stored_path = tmp_path / "learner_state" / "bot_overlays" / "student_demo__bot_alpha.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    assert stored["overlay"]["promotion_candidates"][0]["candidate_kind"] == "stable_goal_signal"
    assert stored["overlay"]["promotion_candidates"][0]["candidate_id"]


def test_collect_ack_and_drop_promotions_only_manage_candidates(tmp_path) -> None:
    service = _make_service(tmp_path)

    first = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "stable_goal_signal",
        {"goal": "case-study", "confidence": 0.9, "promotion_basis": "structured_result"},
        source_feature="review",
        source_id="turn_7",
    )["promotion_candidates"][0]
    second = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "possible_weak_point",
        {"topic": "fire_distance", "confidence": 0.85, "promotion_basis": "structured_result"},
        source_feature="review",
        source_id="turn_8",
    )["promotion_candidates"][-1]

    eligible = service.collect_promotion_candidates("bot_alpha", "student_demo")
    assert {item["candidate_id"] for item in eligible} == {
        first["candidate_id"],
        second["candidate_id"],
    }

    acked = service.ack_promotions(
        "bot_alpha",
        "student_demo",
        [first["candidate_id"]],
        reason="promoted_to_global_core",
    )
    assert acked["affected_count"] == 1
    assert acked["affected_candidates"][0]["promotion_action"] == "ack"
    assert len(acked["promotion_candidates"]) == 1

    dropped = service.drop_promotions(
        "bot_alpha",
        "student_demo",
        [second["candidate_id"]],
        reason="insufficient_signal",
    )
    assert dropped["affected_count"] == 1
    assert dropped["affected_candidates"][0]["promotion_action"] == "drop"
    assert dropped["promotion_candidates"] == []


def test_collect_promotion_candidates_requires_confidence_and_basis(tmp_path) -> None:
    service = _make_service(tmp_path)

    low_evidence = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "possible_weak_point",
        {"topic": "防火间距", "confidence": 0.95},
        source_feature="chat",
        source_id="turn_1",
    )["promotion_candidates"][0]
    low_confidence = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "possible_weak_point",
        {"topic": "施工缝", "confidence": 0.2, "promotion_basis": "structured_result"},
        source_feature="quiz",
        source_id="turn_2",
    )["promotion_candidates"][-1]
    eligible = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "possible_weak_point",
        {"topic": "关键线路", "confidence": 0.9, "promotion_basis": "structured_result"},
        source_feature="quiz",
        source_id="turn_3",
    )["promotion_candidates"][-1]

    candidates = service.collect_promotion_candidates(
        "bot_alpha",
        "student_demo",
        min_confidence=0.7,
    )

    assert [item["candidate_id"] for item in candidates] == [eligible["candidate_id"]]
    assert low_evidence["candidate_id"] not in {item["candidate_id"] for item in candidates}
    assert low_confidence["candidate_id"] not in {item["candidate_id"] for item in candidates}


def test_apply_promotions_reports_skipped_candidates_without_global_write(tmp_path) -> None:
    service = _make_service(tmp_path)
    learner_state_service = _FakeLearnerStateService()
    candidate = service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "possible_weak_point",
        {"topic": "防火间距", "confidence": 0.95},
        source_feature="chat",
        source_id="turn_1",
    )["promotion_candidates"][0]

    result = service.apply_promotions(
        "bot_alpha",
        "student_demo",
        learner_state_service=learner_state_service,
        min_confidence=0.7,
    )

    assert result["applied"] == []
    assert result["dropped"] == []
    assert result["skipped_ids"] == [candidate["candidate_id"]]
    assert result["skipped"][0]["reasons"] == ["missing_promotion_basis"]
    assert learner_state_service.progress["knowledge_map"]["weak_points"] == []
    assert service.read_overlay("bot_alpha", "student_demo")["promotion_candidates"][0]["candidate_id"] == candidate["candidate_id"]


def test_resolve_heartbeat_inputs_returns_override_candidate_only(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "operations": [
                {"op": "merge", "field": "heartbeat_override", "value": {"priority_bonus": 8, "cadence": "review"}},
                {"op": "merge", "field": "local_focus", "value": {"topic": "network_plan"}},
            ]
        },
        source_feature="guide",
        source_id="guide_1",
    )

    inputs = service.resolve_heartbeat_inputs("bot_alpha", "student_demo")

    assert inputs["heartbeat_override_present"] is True
    assert inputs["heartbeat_override_candidate"]["priority_bonus"] == 8
    assert inputs["local_focus"]["topic"] == "network_plan"
    assert inputs["overlay_version"] >= 2


def test_decay_overlay_clears_expired_ephemeral_fields_on_read_and_persist(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "operations": [
                {"op": "merge", "field": "local_focus", "value": {"topic": "foundation"}},
                {"op": "set", "field": "working_memory_projection", "value": "先做第 2 问。"},
            ]
        },
        source_feature="chat",
        source_id="turn_1",
    )

    stored_path = tmp_path / "learner_state" / "bot_overlays" / "student_demo__bot_alpha.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=96)).astimezone().isoformat()
    stored_path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")

    preview = service.read_overlay("bot_alpha", "student_demo")
    assert set(preview["expired_fields"]) >= {"local_focus", "working_memory_projection"}
    assert preview["effective_overlay"]["local_focus"] == {}
    assert preview["effective_overlay"]["working_memory_projection"] == ""

    decayed = service.decay_overlay("bot_alpha", "student_demo", max_age_hours=72)
    assert decayed["overlay_decay_applied"] is True
    persisted = json.loads(stored_path.read_text(encoding="utf-8"))
    assert persisted["overlay"]["local_focus"] == {}
    assert persisted["overlay"]["working_memory_projection"] == ""


def test_apply_promotions_updates_global_learner_state_and_acks_candidates(tmp_path) -> None:
    service = _make_service(tmp_path)
    learner_state_service = _FakeLearnerStateService()

    service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "stable_goal_signal",
        {
            "goal": "完成案例题专项训练",
            "progress": 10,
            "deadline": "2026-05-01",
            "confidence": 0.92,
            "promotion_basis": "structured_result",
        },
        source_feature="review",
        source_id="turn_1",
    )
    service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "stable_preference",
        {
            "difficulty_preference": "hard",
            "explanation_style": "detailed",
            "confidence": 0.88,
            "promotion_basis": "user_confirmed",
        },
        source_feature="review",
        source_id="turn_2",
    )
    service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "possible_weak_point",
        {"topic": "防火间距", "confidence": 0.9, "promotion_basis": "structured_result"},
        source_feature="quiz",
        source_id="turn_3",
    )
    service.promote_candidate(
        "bot_alpha",
        "student_demo",
        "working_memory_note",
        {"text": "这类不能晋升", "confidence": 0.95, "promotion_basis": "structured_result"},
        source_feature="chat",
        source_id="turn_4",
    )

    result = service.apply_promotions(
        "bot_alpha",
        "student_demo",
        learner_state_service=learner_state_service,
        min_confidence=0.7,
    )

    assert [item["applied_kind"] for item in result["applied"]] == ["goal", "profile", "progress"]
    assert len(result["dropped"]) == 1
    assert learner_state_service.goals[0]["title"] == "完成案例题专项训练"
    assert learner_state_service.profile["difficulty_preference"] == "hard"
    assert learner_state_service.progress["knowledge_map"]["weak_points"] == ["防火间距"]
    assert learner_state_service.events
    assert all(item["memory_kind"] == "overlay_promotion" for item in learner_state_service.events)

    overlay = service.read_overlay("bot_alpha", "student_demo")
    assert overlay["promotion_candidates"] == []
    events_path = tmp_path / "learner_state" / "bot_overlays" / "student_demo__bot_alpha.events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(item["event_type"] == "overlay_promotion_apply" for item in events)
    outbox_path = tmp_path / "runtime" / "outbox.db"
    assert outbox_path.exists()


def test_list_overlay_events_and_audit_support_filters(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {"op": "merge", "field": "local_focus", "value": {"topic": "foundation"}},
        source_feature="guide",
        source_id="guide_1",
    )
    service.decay_overlay(
        "bot_alpha",
        "student_demo",
        now=(datetime.now(timezone.utc) + timedelta(hours=96)).astimezone().isoformat(),
        max_age_hours=1,
    )

    patch_events = service.list_overlay_events(
        "bot_alpha",
        "student_demo",
        event_type="overlay_patch",
    )
    audit_events = service.list_overlay_audit("bot_alpha", "student_demo")

    assert patch_events
    assert all(item["event_type"] == "overlay_patch" for item in patch_events)
    assert audit_events
    assert {item["event_type"] for item in audit_events} >= {"overlay_patch", "overlay_decay"}


def test_list_user_overlays_returns_per_bot_view_sorted_by_updated_at(tmp_path) -> None:
    service = _make_service(tmp_path)
    first = service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {"op": "merge", "field": "local_focus", "value": {"topic": "foundation"}},
        source_feature="guide",
        source_id="guide_1",
    )
    second = service.patch_overlay(
        "bot_beta",
        "student_demo",
        {"op": "merge", "field": "local_focus", "value": {"topic": "fire_distance"}},
        source_feature="guide",
        source_id="guide_2",
    )
    assert first["version"] >= 2
    assert second["version"] >= 2

    items = service.list_user_overlays("student_demo")

    assert [item["bot_id"] for item in items] == ["bot_beta", "bot_alpha"]
    assert items[0]["effective_overlay"]["local_focus"]["topic"] == "fire_distance"
    assert items[0]["event_count"] >= 1
