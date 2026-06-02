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
        "learning_action_started",
        "learning_action_completed",
        "module_returned",
        "module_exited",
        "event_error",
    }.issubset(PRODUCT_BEHAVIOR_EVENT_NAMES)


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
