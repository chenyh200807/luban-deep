from __future__ import annotations

import pytest

from deeptutor.services.observability.product_behavior_catalog import (
    PRODUCT_BEHAVIOR_EVENT_NAMES,
    validate_product_behavior_event,
)


def test_product_behavior_catalog_includes_p0_events() -> None:
    assert {
        "module_viewed",
        "section_viewed",
        "section_expanded",
        "note_card_suggested",
        "note_card_saved",
        "note_card_rejected",
        "note_action_started",
        "probe_requested_from_note",
        "today_task_rendered",
        "today_task_started",
        "learning_action_started",
        "learning_action_completed",
        "module_returned",
        "module_exited",
        "event_error",
    }.issubset(PRODUCT_BEHAVIOR_EVENT_NAMES)


def test_validate_accepts_and_gates_practice_mode() -> None:
    """spike 命门判别位:forward/review 合法进 validated dict;白名单外值拒收
    (register-before-use,防拼写漂移);缺省=空(既有事件不受影响)。"""
    for mode in ("forward", "review"):
        out = validate_product_behavior_event(
            event_name="learning_action_completed",
            metadata={
                "visit_id": "v1", "module": "practice", "action": "complete",
                "surface": "wechat_yousenwebview", "object_type": "retest",
                "practice_mode": mode,
            },
        )
        assert out["practice_mode"] == mode
    with pytest.raises(ValueError, match="practice_mode"):
        validate_product_behavior_event(
            event_name="learning_action_completed",
            metadata={
                "visit_id": "v1", "module": "practice", "action": "complete",
                "surface": "wechat_yousenwebview", "practice_mode": "frwrd",
            },
        )
    # 缺省不带 practice_mode 的既有事件仍合法(空串)
    out = validate_product_behavior_event(
        event_name="module_viewed",
        metadata={"visit_id": "v1", "module": "learning", "action": "view",
                  "surface": "web"},
    )
    assert out["practice_mode"] == ""


def test_validate_product_behavior_event_accepts_learning_report_section() -> None:
    event = validate_product_behavior_event(
        event_name="section_viewed",
        metadata={
            "visit_id": "visit-u1-1",
            "module": "learning_report",
            "section": "next_action",
            "action": "view",
            "surface": "web",
            "visible_ms": 1400,
        },
    )

    assert event["module"] == "learning_report"
    assert event["section"] == "next_action"
    assert event["visit_id"] == "visit-u1-1"


def test_validate_product_behavior_event_accepts_p0_note_asset_event() -> None:
    event = validate_product_behavior_event(
        event_name="note_card_saved",
        metadata={
            "visit_id": "visit-u1-1",
            "module": "learning_report",
            "section": "note_assets",
            "action": "save_note",
            "surface": "wechat_yousenwebview",
            "object_type": "notebook_card",
            "object_id": "note_abc",
        },
    )

    assert event["event_name"] == "note_card_saved"
    assert event["section"] == "note_assets"
    assert event["surface"] == "wechat_yousenwebview"


def test_validate_product_behavior_event_rejects_raw_learning_text_for_p0_note_event() -> None:
    with pytest.raises(ValueError, match="Forbidden product behavior field"):
        validate_product_behavior_event(
            event_name="note_card_saved",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "learning_report",
                "section": "note_assets",
                "action": "save_note",
                "surface": "wechat_yousenwebview",
                "object_type": "notebook_card",
                "full_chat_text": "raw transcript must not enter product_behavior_events",
            },
        )


def test_validate_product_behavior_event_rejects_unknown_module() -> None:
    with pytest.raises(ValueError, match="Unsupported module"):
        validate_product_behavior_event(
            event_name="module_viewed",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "random_page",
                "action": "view",
                "surface": "web",
            },
        )


def test_validate_product_behavior_event_rejects_unknown_product_like_event_name() -> None:
    with pytest.raises(ValueError, match="Unsupported product behavior event_name"):
        validate_product_behavior_event(
            event_name="module_clicked",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "history",
                "action": "view",
                "surface": "web",
            },
        )


def test_validate_product_behavior_event_allows_error_without_visit_id() -> None:
    event = validate_product_behavior_event(
        event_name="event_error",
        metadata={
            "module": "learning_report",
            "action": "error",
            "surface": "web",
            "error_code": "observer_unavailable",
        },
    )

    assert event["event_name"] == "event_error"
    assert event["visit_id"] == ""
    assert event["error_code"] == "observer_unavailable"


def test_validate_product_behavior_event_rejects_forbidden_payload_fields() -> None:
    with pytest.raises(ValueError, match="Forbidden product behavior field"):
        validate_product_behavior_event(
            event_name="module_viewed",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "history",
                "action": "view",
                "surface": "web",
                "full_answer_text": "should not be stored",
            },
        )


def test_validate_product_behavior_event_rejects_nested_forbidden_payload_fields() -> None:
    with pytest.raises(ValueError, match="Forbidden product behavior field"):
        validate_product_behavior_event(
            event_name="module_viewed",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "history",
                "action": "view",
                "surface": "web",
                "extra": {"complete_subjective_answer": "should not be stored"},
            },
        )


def test_luban_spike_d15_events_registered():
    """双轮 spike D15 三个新事件名过 catalog 校验（维度走 object/result 约定）。"""
    from deeptutor.services.observability.product_behavior_catalog import (
        validate_product_behavior_event,
    )
    for name, meta in [
        ("handoff_rendered", {"module": "learning", "action": "render",
                              "object_type": "station", "object_id": "S05",
                              "visit_id": "v1", "surface": "wechat_yousenwebview"}),
        ("retest_item_answered", {"module": "practice", "action": "complete",
                                  "object_type": "variant", "object_id": "S05-B-003",
                                  "result": "correct", "visit_id": "v1"}),
        ("subscribe_prompt_result", {"module": "learning", "action": "complete",
                                     "object_type": "station", "object_id": "S05",
                                     "result": "red_dot", "visit_id": "v1"}),
    ]:
        record = validate_product_behavior_event(name, meta)
        assert record["event_name"] == name
        assert record["object_id"] == meta["object_id"]


def test_first_experience_funnel_events_registered() -> None:
    """首体验漏斗（2026-07-10 登记）：老蓝版小程序埋点通电的 5 个新事件名 +
    login module + authorize/send action。60% 零消息流失的定位事件。"""
    for name, meta in [
        ("module_viewed", {"module": "login", "action": "view",
                           "surface": "wechat_miniprogram", "visit_id": "v1"}),
        ("auth_authorize_clicked", {"module": "login", "action": "authorize",
                                    "object_type": "phone_auth",
                                    "result": "granted",
                                    "surface": "wechat_miniprogram",
                                    "visit_id": "v1"}),
        ("auth_result", {"module": "login", "action": "complete",
                         "object_type": "phone_auth", "result": "success",
                         "surface": "wechat_miniprogram", "visit_id": "v1"}),
        ("chat_message_sent", {"module": "chat", "action": "send",
                               "object_type": "chat_turn",
                               "surface": "wechat_miniprogram",
                               "visit_id": "v1"}),
        ("chat_first_answer_rendered", {"module": "chat", "action": "render",
                                        "object_type": "first_answer",
                                        "duration_ms": 3200,
                                        "surface": "wechat_miniprogram",
                                        "visit_id": "v1"}),
        ("assessment_prompt_result", {"module": "assessment",
                                      "action": "dismiss", "result": "later",
                                      "entry_source": "chat_home",
                                      "surface": "wechat_miniprogram",
                                      "visit_id": "v1"}),
    ]:
        record = validate_product_behavior_event(name, meta)
        assert record["event_name"] == name
        assert record["module"] == meta["module"]
        assert record["action"] == meta["action"]
