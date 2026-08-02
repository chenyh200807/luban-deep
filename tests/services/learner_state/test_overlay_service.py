from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from deeptutor.services.learner_state.overlay_service import (
    BotLearnerOverlayService,
    stamp_admin_working_memory_provenance,
)


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


# task#32 出处链化：working_memory_projection 的非空 set 必须携带来源指针。
_WM_PROVENANCE = {"turn_id": "turn-0001", "source_kind": "assistant_response"}


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
                {"op": "set", "field": "working_memory_projection", "value": "先盯住承载力与沉降控制的区分。", "provenance": dict(_WM_PROVENANCE)},
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
                {"op": "set", "field": "working_memory_projection", "value": "当前 Bot 正在带用户复习关键线路。", "provenance": dict(_WM_PROVENANCE)},
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
                {"op": "set", "field": "working_memory_projection", "value": "先做第 2 问。", "provenance": dict(_WM_PROVENANCE)},
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


# =========================================================================
# task#32 working_memory 出处链化（2026-08-01 吸收态 SEV 的结构免疫）
# =========================================================================


def _wm_events(tmp_path, name="student_demo__bot_alpha"):
    events_path = tmp_path / "learner_state" / "bot_overlays" / f"{name}.events.jsonl"
    if not events_path.exists():
        return []
    return [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_wm_set_without_provenance_is_fail_closed_and_loud(tmp_path) -> None:
    """无出处不入记：投影被拒，同批其余 op 照常，拒绝落审计事件（不静默）。"""
    service = _make_service(tmp_path)

    overlay = service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "operations": [
                {"op": "set", "field": "working_memory_projection", "value": "裸写内容不应入记"},
                {"op": "merge", "field": "engagement_state", "value": {"last_capability": "chat"}},
            ]
        },
        source_feature="turn",
        source_id="session-1",
    )

    assert overlay["effective_overlay"]["working_memory_projection"] == ""
    assert overlay["effective_overlay"]["working_memory_provenance"] == {}
    assert overlay["effective_overlay"]["engagement_state"]["last_capability"] == "chat"

    rejected = [
        item
        for item in _wm_events(tmp_path)
        if item["event_type"] == "overlay_working_memory_rejected"
    ]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "missing_provenance"
    assert rejected[0]["detail"]["missing_keys"] == ["turn_id", "source_kind"]
    assert "裸写内容" in rejected[0]["detail"]["content_preview"]
    # 拒入事件必须进既有审计 API
    audit_events = service.list_overlay_audit("bot_alpha", "student_demo")
    assert any(
        item["event_type"] == "overlay_working_memory_rejected" for item in audit_events
    )


def test_wm_set_with_provenance_persists_and_roundtrips(tmp_path) -> None:
    """带出处写入：service 补章（written_at/hash），且落盘后重读不被白名单剥掉。"""
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "op": "set",
            "field": "working_memory_projection",
            "value": "刚讲完承载力，下一步对比沉降控制。",
            "provenance": {
                "turn_id": "turn-42",
                "source_kind": "assistant_response",
                "session_id": "sess-9",
                "capability": "chat",
                "ignored_junk": "should_be_dropped",
            },
        },
        source_feature="turn",
        source_id="sess-9",
    )

    # 新实例重读 = 证明 _ALLOWED_FIELDS 回读名单包含 provenance（漏名单=永久0命中）
    reread = _make_service(tmp_path).read_overlay("bot_alpha", "student_demo")
    provenance = reread["effective_overlay"]["working_memory_provenance"]
    assert provenance["turn_id"] == "turn-42"
    assert provenance["source_kind"] == "assistant_response"
    assert provenance["session_id"] == "sess-9"
    assert provenance["source_feature"] == "turn"
    assert provenance["written_at"]
    assert provenance["content_sha256"]
    assert provenance["content_chars"] > 0
    assert "ignored_junk" not in provenance
    assert "legacy_no_provenance" not in provenance
    assert not [
        item
        for item in _wm_events(tmp_path)
        if item["event_type"] == "overlay_working_memory_rejected"
    ]


def test_wm_provenance_field_is_service_managed(tmp_path) -> None:
    service = _make_service(tmp_path)
    try:
        service.patch_overlay(
            "bot_alpha",
            "student_demo",
            {"op": "set", "field": "working_memory_provenance", "value": {"turn_id": "forged"}},
            source_feature="admin_overlay",
            source_id="admin-1",
        )
    except ValueError as exc:
        assert "service-managed" in str(exc)
    else:
        raise AssertionError("expected direct working_memory_provenance write to be rejected")


def test_wm_clear_and_empty_set_clear_provenance_together(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "op": "set",
            "field": "working_memory_projection",
            "value": "有内容",
            "provenance": dict(_WM_PROVENANCE),
        },
        source_feature="turn",
        source_id="s-1",
    )
    cleared = service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {"op": "clear", "field": "working_memory_projection"},
        source_feature="turn",
        source_id="s-2",
    )
    assert cleared["effective_overlay"]["working_memory_projection"] == ""
    assert cleared["effective_overlay"]["working_memory_provenance"] == {}
    # 空 set 等价 clear，且不需要出处、不算拒入
    emptied = service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {"op": "set", "field": "working_memory_projection", "value": "  "},
        source_feature="turn",
        source_id="s-3",
    )
    assert emptied["effective_overlay"]["working_memory_projection"] == ""
    assert not [
        item
        for item in _wm_events(tmp_path)
        if item["event_type"] == "overlay_working_memory_rejected"
    ]


def test_wm_legacy_record_without_provenance_reads_with_grace_tag(tmp_path) -> None:
    """生产存量（477 条）兼容：宽限读 + legacy 标记，禁一刀切清空。"""
    service = _make_service(tmp_path)
    stored_dir = tmp_path / "learner_state" / "bot_overlays"
    stored_dir.mkdir(parents=True, exist_ok=True)
    legacy_payload = {
        "bot_id": "bot_alpha",
        "user_id": "student_demo",
        "version": 7,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "overlay": {
            "working_memory_projection": "出处强制上线前写入的旧记忆",
        },
    }
    (stored_dir / "student_demo__bot_alpha.json").write_text(
        json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8"
    )

    overlay = service.read_overlay("bot_alpha", "student_demo")

    # 内容照常可用（不惩罚存量学员），但审计面显式标 legacy
    assert overlay["effective_overlay"]["working_memory_projection"] == "出处强制上线前写入的旧记忆"
    assert overlay["effective_overlay"]["working_memory_provenance"] == {
        "legacy_no_provenance": True
    }


def test_wm_decay_expires_projection_and_provenance_together(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "op": "set",
            "field": "working_memory_projection",
            "value": "会过期的记忆",
            "provenance": dict(_WM_PROVENANCE),
        },
        source_feature="turn",
        source_id="s-1",
    )
    stored_path = tmp_path / "learner_state" / "bot_overlays" / "student_demo__bot_alpha.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=96)).astimezone().isoformat()
    stored_path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    decayed = service.decay_overlay("bot_alpha", "student_demo", max_age_hours=72)

    assert decayed["overlay_decay_applied"] is True
    persisted = json.loads(stored_path.read_text(encoding="utf-8"))
    assert persisted["overlay"]["working_memory_projection"] == ""
    assert persisted["overlay"]["working_memory_provenance"] == {}


def test_record_working_memory_rejection_is_visible_in_events_and_audit(tmp_path) -> None:
    """#638 安全模板拒入从静默升级为发声：事件可见、审计可见。"""
    service = _make_service(tmp_path)

    service.record_working_memory_rejection(
        "bot_alpha",
        "student_demo",
        reason="security_template_response",
        turn_id="turn-77",
        source_feature="turn",
        source_id="sess-3",
    )

    events = service.list_overlay_events(
        "bot_alpha", "student_demo", event_type="overlay_working_memory_rejected"
    )
    assert len(events) == 1
    assert events[0]["reason"] == "security_template_response"
    assert events[0]["turn_id"] == "turn-77"
    audit = service.list_overlay_audit("bot_alpha", "student_demo")
    assert any(item["event_type"] == "overlay_working_memory_rejected" for item in audit)


# --- admin 边界盖章（出处强制不是"禁止 admin 写"，是"admin 写也要可回溯"）---


def test_stamp_admin_provenance_only_touches_nonempty_working_memory_sets() -> None:
    operations = [
        {"op": "set", "field": "working_memory_projection", "value": "运营手工修正的记忆"},
        {"op": "set", "field": "working_memory_projection", "value": "   "},
        {"op": "clear", "field": "working_memory_projection"},
        {"op": "merge", "field": "local_focus", "value": {"topic": "foundation"}},
    ]

    stamped = stamp_admin_working_memory_provenance(
        operations, actor="admin_zhang", surface="tutor_state_admin_overlay"
    )

    assert stamped[0]["provenance"] == {
        "turn_id": "admin:admin_zhang",
        "source_kind": "admin_override",
        "source_event_type": "tutor_state_admin_overlay",
        "actor": "admin_zhang",
    }
    # 空写 / clear / 其它字段一律原样透传，不被盖章
    assert "provenance" not in stamped[1]
    assert "provenance" not in stamped[2]
    assert stamped[3] == {"op": "merge", "field": "local_focus", "value": {"topic": "foundation"}}
    # 不得就地改调用方的 list
    assert "provenance" not in operations[0]


def test_stamp_admin_provenance_raises_when_actor_is_unresolved() -> None:
    """拿不到身份宁可显式报错（各入口转 4xx），也不静默丢弃——静默 + 200 = 假成功。"""
    for actor in ("", "   ", None):
        with pytest.raises(ValueError) as excinfo:
            stamp_admin_working_memory_provenance(
                [{"op": "set", "field": "working_memory_projection", "value": "无主写入"}],
                actor=actor,
                surface="member_console_overlay",
            )
        assert "authenticated actor" in str(excinfo.value)
        assert "member_console_overlay" in str(excinfo.value)


def test_stamp_admin_provenance_allows_other_ops_without_actor() -> None:
    """只有 working_memory 写需要 actor：其余 admin 运维 op 不受影响。"""
    stamped = stamp_admin_working_memory_provenance(
        [{"op": "clear", "field": "local_focus"}], actor="", surface="admin"
    )
    assert stamped == [{"op": "clear", "field": "local_focus"}]


def test_admin_stamped_write_lands_with_admin_override_provenance(tmp_path) -> None:
    """端到端：admin 盖章后的写入真的入记，且出处能查到是谁改的。"""
    service = _make_service(tmp_path)
    operations = stamp_admin_working_memory_provenance(
        [{"op": "set", "field": "working_memory_projection", "value": "运营手工修正的记忆"}],
        actor="admin_zhang",
        surface="tutor_state_admin_overlay",
    )

    overlay = service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {"operations": operations},
        source_feature="admin_overlay",
        source_id="admin_zhang",
    )

    assert overlay["effective_overlay"]["working_memory_projection"] == "运营手工修正的记忆"
    provenance = overlay["effective_overlay"]["working_memory_provenance"]
    assert provenance["source_kind"] == "admin_override"
    assert provenance["actor"] == "admin_zhang"
    assert provenance["turn_id"] == "admin:admin_zhang"
    assert provenance["written_at"]
    # 关键反向断言：admin 写不再被静默丢弃（原假成功形态）
    assert not [
        item
        for item in _wm_events(tmp_path)
        if item["event_type"] == "overlay_working_memory_rejected"
    ]


def test_admin_stamped_write_is_visible_to_audit_script(tmp_path) -> None:
    """审计通道可见性（owner 纪律：交付必须可感知）。"""
    from scripts.audit_working_memory import collect_rows

    service = _make_service(tmp_path)
    service.patch_overlay(
        "bot_alpha",
        "student_demo",
        {
            "operations": stamp_admin_working_memory_provenance(
                [{"op": "set", "field": "working_memory_projection", "value": "运营手工修正的记忆"}],
                actor="admin_zhang",
                surface="member_console_overlay",
            )
        },
        source_feature="member_console_overlay",
        source_id="admin_zhang",
    )

    rows = collect_rows(tmp_path / "learner_state" / "bot_overlays")

    assert len(rows) == 1
    assert rows[0]["provenance_source_kind"] == "admin_override"
    assert rows[0]["provenance_turn_id"] == "admin:admin_zhang"
    assert rows[0]["provenance_actor"] == "admin_zhang"
    assert rows[0]["legacy_no_provenance"] is False
    assert rows[0]["rejected_count"] == 0
