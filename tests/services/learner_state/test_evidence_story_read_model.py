from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deeptutor.services.learner_state.evidence_story_read_model import (
    build_evidence_story_read_model,
    redact_chat_text,
)
from deeptutor.services.learner_state.prescription_outcome_read_model import (
    build_prescription_outcomes_read_projection,
)
from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: float = 0) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def _case_event(
    *,
    event_id: str,
    days_ago: float = 0,
    hit: bool = False,
    point_id: str = "sp_fire_door_order",
    point_label: str = "双扇防火门应按顺序关闭",
    user_id: str = "openid_oops_13800138000",
    question_stem: str = "关于防火门的构造要求，下列哪项说法是正确的？",
    user_answer: str = "张三选了A，手机号13800138000",
) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id=user_id,
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "construction_grading",
            "question_id": f"q_{event_id}",
            "question_stem": question_stem,
            "user_answer": user_answer,
            "score_awarded": 1 if hit else 0,
            "max_score": 1,
            "rubric": {
                "rubric_mode": "curated_rubric",
                "granularity": "scoring_point",
                "scoring_points": [
                    {
                        "point_id": point_id,
                        "label": point_label,
                        "knowledge_node_id": "1A412010",
                        "ability_dimension": "code_application",
                    }
                ],
                "scoring_point_hits": [
                    {
                        "point_id": point_id,
                        "hit": hit,
                        "error_code": "E02",
                        "miss_reason": "没有识别顺序关闭要求",
                    }
                ],
            },
            "error_events": [
                {
                    "error_code": "E02",
                    "concept_tag": "1A412010",
                    "diagnosis": "漏写防火门顺序关闭要求",
                }
            ],
            "next_training_signal": {"concept": "1A412010", "focus": "防火门构造"},
        },
    )


def _prescription_event(
    *,
    event_id: str,
    training_intent_id: str,
    phase: str,
    status: str,
    score_ratio: float | None = None,
) -> LearnerStateEvent:
    event = _case_event(event_id=event_id, hit=(score_ratio or 0) >= 1)
    event.payload_json["training_intent_id"] = training_intent_id
    event.payload_json["prescription_phase"] = phase
    event.payload_json["prescription_result"] = {"status": status}
    if score_ratio is not None:
        event.payload_json["prescription_result"]["score_ratio"] = score_ratio
        event.payload_json["score_ratio"] = score_ratio
    return event


def _conversation_event() -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id="evt_chat",
        user_id="openid_private",
        source_feature="conversation_synthesis",
        source_id="turn-chat",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="evt_chat",
        created_at=_iso(0),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "conversation_synthesis",
            "learning_signal_type": "mistake_explain",
            "raw_chat": "我是李四，电话 13800138000，邮箱 a@example.com，身份证 110101199003071234",
            "quality": {"progress_countable": False, "truth_eligible": False},
        },
    )


def test_evidence_story_links_initial_cluster_prescription_and_verification() -> None:
    events = [
        _case_event(event_id="evt_miss_1", days_ago=2),
        _case_event(event_id="evt_miss_2", days_ago=1),
        _prescription_event(
            event_id="evt_assigned",
            training_intent_id="intent_fire",
            phase="assigned",
            status="assigned",
        ),
        _prescription_event(
            event_id="evt_verified",
            training_intent_id="intent_fire",
            phase="verification_probe",
            status="verified",
            score_ratio=1.0,
        ),
    ]
    story = build_evidence_story_read_model(
        user_id="openid_secret_13800138000",
        evidence_events=events,
        scoring_point_map=build_scoring_point_map_read_projection(
            events=events, user_id="openid_secret_13800138000"
        ),
        prescription_outcomes=build_prescription_outcomes_read_projection(events=events),
    )

    assert story["headline"]
    assert [item["type"] for item in story["evidence_chain"]] == [
        "initial_pattern",
        "prescription_assigned",
        "verified_improvement",
    ]
    assert story["privacy"] == {
        "redacted": True,
        "learner_handle": "learner_a",
        "raw_chat_included": False,
    }
    assert story["sales_summary"]["value_claim"] == "locate_miss_mechanism_and_verify_repair"
    assert story["sales_summary"]["value_claim_label"] == "不是多刷题，而是定位丢分机制并验证修复"
    assert story["teacher_summary"]["evidence_refs"]


def test_every_story_claim_has_evidence_refs() -> None:
    story = build_evidence_story_read_model(
        user_id="u",
        evidence_events=[_case_event(event_id="evt_miss_1"), _case_event(event_id="evt_miss_2")],
        scoring_point_map=build_scoring_point_map_read_projection(
            events=[_case_event(event_id="evt_miss_1"), _case_event(event_id="evt_miss_2")],
            user_id="u",
        ),
        prescription_outcomes=[],
    )

    assert story["evidence_chain"]
    assert all(item["evidence_refs"] for item in story["evidence_chain"])
    assert story["teacher_summary"]["evidence_refs"]
    assert story["sales_summary"]["evidence_refs"]


def test_missing_evidence_refs_claim_is_dropped_or_degraded() -> None:
    story = build_evidence_story_read_model(
        user_id="u",
        evidence_events=[],
        scoring_point_map={"items": [{"point_id": "bad", "miss_count": 2, "evidence_refs": []}]},
        prescription_outcomes=[
            {
                "status": "verified",
                "training_intent_id": "intent_bad",
                "evidence_refs": [],
            }
        ],
    )

    assert story["evidence_chain"] == []
    assert story["source_status"]["degraded"] is True
    assert "insufficient_evidence" in story["source_status"]["blocked_reasons"]
    assert story["sales_summary"]["value_claim"] == ""
    assert story["sales_summary"]["claim_strength"] == "insufficient_evidence"


def test_raw_chat_and_pii_are_redacted_from_entire_payload() -> None:
    raw = _conversation_event().payload_json["raw_chat"]
    story = build_evidence_story_read_model(
        user_id="openid_private_13800138000",
        evidence_events=[_conversation_event(), _case_event(event_id="evt_miss_1")],
    )
    rendered = json.dumps(story, ensure_ascii=False)

    for forbidden in [
        raw,
        "13800138000",
        "a@example.com",
        "110101199003071234",
        "李四",
        "openid_private",
    ]:
        assert forbidden not in rendered
    assert "[手机号]" in redact_chat_text(raw)


def test_sales_summary_uses_closed_enum_without_exaggerated_claims() -> None:
    story = build_evidence_story_read_model(
        user_id="u",
        evidence_events=[_case_event(event_id="evt_miss_1"), _case_event(event_id="evt_miss_2")],
    )
    rendered = json.dumps(story["sales_summary"], ensure_ascii=False)

    assert story["sales_summary"]["value_claim"] in {
        "observed_learning_pattern",
        "locate_miss_mechanism_and_verify_repair",
    }
    for forbidden in ["保证提分", "必过", "提升20分", "7天通过"]:
        assert forbidden not in rendered


def test_no_public_endpoint_added_for_evidence_story() -> None:
    mobile_router = Path("deeptutor/api/routers/mobile.py").read_text(encoding="utf-8")

    assert "evidence_story" not in mobile_router
    assert "evidence-story" not in mobile_router


def test_service_tolerates_legacy_evidence() -> None:
    legacy = _case_event(event_id="legacy")
    legacy.payload_json.pop("rubric")
    legacy.payload_json.pop("error_events")

    story = build_evidence_story_read_model(user_id="u", evidence_events=[legacy])

    assert story["ok"] is True
    assert story["source_status"]["legacy_event_count"] == 1
