from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import luban_lesson as router
from deeptutor.services.learner_state import service as learner_state_module
from deeptutor.services.luban_lesson import retest_writeback as writeback_module


def test_retest_complete_is_thin_authenticated_adapter(monkeypatch) -> None:
    captured = {}

    class _Service:
        def __init__(self, *, learner_state_service):
            captured["learner_state"] = learner_state_service

        def complete(self, **kwargs):
            captured.update(kwargs)
            return {"sync_status": "synced", "completion_id": kwargs["completion_id"]}

    fake_state = object()
    monkeypatch.setattr(learner_state_module, "get_learner_state_service", lambda: fake_state)
    monkeypatch.setattr(writeback_module, "RetestWritebackService", _Service)
    body = router.RetestCompletionRequest(
        completion_id="completion-1",
        selection_id="signed-selection",
        mode="forward",
        day_index=2026192,
        answers=[router.RetestAnswerRequest(variant_id="F16-v1", choice_ok=False)],
        training_intent_id="lti-f16",
    )

    result = asyncio.run(
        router.retest_complete(
            "F16",
            body,
            current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
        )
    )

    assert result == {"sync_status": "synced", "completion_id": "completion-1"}
    assert captured["user_id"] == "qa_eval_retest_endpoint"
    assert captured["pack_id"] == "F16"
    assert captured["selection_id"] == "signed-selection"
    assert captured["answers"] == [{"variant_id": "F16-v1", "choice_ok": False}]
    assert captured["learner_state"] is fake_state


def test_retest_item_supply_is_hidden_when_rollout_is_off(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="review",
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 404


def test_forward_item_supply_requires_light_practice_flag(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="forward",
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 404


def test_lesson_listing_exposes_rollout_gated_light_practice_truth(monkeypatch) -> None:
    monkeypatch.setattr(router, "list_green_lessons", lambda: [{"pack_id": "F16", "retest_available": True}])
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: False)

    result = asyncio.run(router.lessons(_=SimpleNamespace(user_id="qa_eval_retest_endpoint")))

    assert result["lessons"][0]["retest_available"] is True
    assert result["lessons"][0]["light_practice_available"] is False
