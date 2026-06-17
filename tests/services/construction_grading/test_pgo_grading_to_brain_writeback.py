from __future__ import annotations

from deeptutor.services.construction_grading.writeback import record_pgo_shadow_to_brain
from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)


class _FakeEvent:
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        self.memory_kind = "learning_evidence"
        self.payload_json: dict[str, object] = {}
        self.created_at = event_id


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def append_memory_event(self, user_id: str, **kwargs: object) -> object:
        event = _FakeEvent(f"evt-{len(self.calls) + 1}")
        event.payload_json = dict(kwargs.get("payload_json") or {})
        self.calls.append({"user_id": user_id, "event": event, **kwargs})
        return event

    def list_memory_events(self, user_id: str) -> list[object]:
        return [dict(call)["event"] for call in self.calls if call["user_id"] == user_id]

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool, event_limit: int = 50) -> dict[str, object]:
        assert dry_run is True
        return {"projection": {"observed_candidates": []}, "event_limit": event_limit}


def _shadow_payload() -> dict[str, object]:
    return {
        "authority": "luban_case_rubric_pgo_shadow",
        "question_id": "2015::EXAM_XW2015_CASE_1::E0",
        "student_id": "qa-pgo",
        "shadow_status": "ok",
        "not_production_grade": True,
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "writeback_performed": False,
        "runtime_points": [
            {
                "point_id": "P1",
                "official_slice": "施工总进度计划表",
                "sub_type": "free_text_point",
            },
            {
                "point_id": "P2",
                "official_slice": "开竣工日期及工期一览表",
                "sub_type": "free_text_point",
            },
        ],
        "point_verdicts": {"P1": "hit", "P2": "miss"},
        "score": {
            "awarded_score": 5.0,
            "max_score": 10.0,
            "coverage": 0.5,
            "score_authority": "official_total_x_verdict_coverage",
        },
        "knowql_query": {
            "runtime_consumed": True,
            "found": True,
            "artifact_version": "case_rubric_scored_pgo",
        },
    }


def test_record_pgo_shadow_to_brain_reads_back_point_map_and_next_action() -> None:
    service = _FakeLearnerStateService()

    meta = record_pgo_shadow_to_brain(
        learner_state_service=service,
        user_id="qa-pgo",
        shadow_payload=_shadow_payload(),
        source_id="turn-g3:2015::EXAM_XW2015_CASE_1::E0",
        source_bot_id="construction-exam",
        session_id="sess-g3",
    )

    assert meta["pgo_grading_to_brain"]["writeback_count"] == 1
    assert meta["pgo_grading_to_brain"]["artifact_version"] == "case_rubric_scored_pgo"
    assert meta["pgo_grading_to_brain"]["canonical_truth_written"] is False
    assert meta["pgo_grading_to_brain"]["claim_promotion_allowed"] is False
    assert meta["pgo_grading_to_brain"]["scoring_point_map_readback"]["items_count"] == 1
    assert meta["pgo_grading_to_brain"]["next_best_action"]["prescription_authority"] == "training_intent"

    call = service.calls[0]
    assert call["source_feature"] == "construction_grading"
    assert call["memory_kind"] == "learning_evidence"
    payload = call["payload_json"]
    assert payload["learning_signal_type"] == "pgo_case_rubric_shadow"
    assert payload["canonical_truth_written"] is False
    assert payload["claim_promotion_allowed"] is False
    assert payload["rubric"]["artifact_version"] == "case_rubric_scored_pgo"
    assert "施工总进度计划表" not in str(payload)
    assert "开竣工日期及工期一览表" not in str(payload)

    point_map = build_scoring_point_map_read_projection(
        events=service.list_memory_events("qa-pgo"),
        user_id="qa-pgo",
    )
    assert point_map["source_status"]["authority"] == "learner_memory_events.learning_evidence"
    assert point_map["items"][0]["point_id"] == "P2"
    assert point_map["items"][0]["miss_reasons"] == ["miss"]

    actions = build_next_best_actions(
        user_id="qa-pgo",
        training_intents=[point_map["items"][0]["next_action"]["intent"]],
    )
    assert actions[0]["prescription_authority"] == "training_intent"
