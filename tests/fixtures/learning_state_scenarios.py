from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def learning_event(
    event_id: str,
    *,
    days_ago: int = 0,
    hit: bool = False,
    point_id: str = "sp_case",
    node_id: str = "1A412010",
    ability_dimension: str = "code_application",
    error_code: str = "E02",
    source: str = "construction_grading",
    quality: dict | None = None,
) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature=source,
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": source,
            "question_id": f"q_{event_id}",
            "score_awarded": 1 if hit else 0,
            "max_score": 1,
            "quality": quality or {"progress_countable": True, "truth_eligible": True},
            "rubric": {
                "rubric_mode": "curated_rubric",
                "granularity": "scoring_point",
                "scoring_points": [
                    {
                        "point_id": point_id,
                        "label": "防火门顺序关闭",
                        "knowledge_node_id": node_id,
                        "ability_dimension": ability_dimension,
                    }
                ],
                "scoring_point_hits": [
                    {
                        "point_id": point_id,
                        "hit": hit,
                        "error_code": "" if hit else error_code,
                    }
                ],
            },
            "error_events": []
            if hit
            else [{"error_code": error_code, "concept_tag": node_id}],
        },
    )


def cold_start() -> list[LearnerStateEvent]:
    return []


def abandonment() -> list[LearnerStateEvent]:
    event = learning_event("evt_abandoned", days_ago=8)
    event.payload_json["training_intent_id"] = "intent_abandoned"
    event.payload_json["prescription_phase"] = "assigned"
    event.payload_json["prescription_result"] = {"status": "assigned"}
    return [event]


def multi_prescription() -> list[LearnerStateEvent]:
    first = learning_event("evt_multi_1", days_ago=5)
    first.payload_json["training_intent_id"] = "intent_a"
    second = learning_event("evt_multi_2", days_ago=4, node_id="1A413020")
    second.payload_json["training_intent_id"] = "intent_b"
    return [first, second]


def multi_device() -> list[LearnerStateEvent]:
    first = learning_event("evt_phone", days_ago=2)
    first.payload_json["device"] = "phone"
    second = learning_event("evt_tablet", days_ago=1, hit=True)
    second.payload_json["device"] = "tablet"
    return [first, second]


def free_tier() -> list[LearnerStateEvent]:
    event = learning_event("evt_free", days_ago=1)
    event.payload_json["member_tier"] = "free"
    return [event]


def low_quality_chat() -> list[LearnerStateEvent]:
    return [
        learning_event(
            "evt_low_quality_chat",
            source="conversation_synthesis",
            quality={"progress_countable": False, "truth_eligible": False},
        )
    ]


def contradiction() -> list[LearnerStateEvent]:
    return [
        learning_event("evt_contra_miss", days_ago=2),
        learning_event("evt_contra_hit", days_ago=0, hit=True),
    ]


def backfill() -> list[LearnerStateEvent]:
    event = learning_event("evt_backfill", days_ago=10)
    event.payload_json.pop("rubric")
    return [event]


def revalidation() -> list[LearnerStateEvent]:
    miss = learning_event("evt_reval_miss", days_ago=4)
    hit = learning_event("evt_reval_hit", days_ago=0, hit=True)
    hit.payload_json["training_intent_id"] = "intent_reval"
    hit.payload_json["prescription_phase"] = "verification_probe"
    hit.payload_json["prescription_result"] = {"status": "verified", "score_ratio": 1.0}
    return [miss, hit]


SCENARIOS: dict[str, Callable[[], list[LearnerStateEvent]]] = {
    "cold_start": cold_start,
    "abandonment": abandonment,
    "multi_prescription": multi_prescription,
    "multi_device": multi_device,
    "free_tier": free_tier,
    "low_quality_chat": low_quality_chat,
    "contradiction": contradiction,
    "backfill": backfill,
    "revalidation": revalidation,
}
