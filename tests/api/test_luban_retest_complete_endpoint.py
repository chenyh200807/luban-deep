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
        def __init__(self, *, learner_state_service, review_exam_date_resolver):
            captured["learner_state"] = learner_state_service
            captured["exam_date_resolver"] = review_exam_date_resolver

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
    assert captured["answers"] == [
        {"variant_id": "F16-v1", "choice_ok": False, "selected_option_id": ""}
    ]
    assert captured["learner_state"] is fake_state
    assert captured["exam_date_resolver"] is router._exam_date_for


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            writeback_module.RetestCompletionInProgress("winner-completion"),
            409,
            "retest completion in progress",
        ),
        (
            writeback_module.RetestProbeClaimUnavailable(
                "retest_probe_atomic_authority_unavailable"
            ),
            503,
            "retest probe atomic authority unavailable",
        ),
    ],
)
def test_retest_complete_maps_retryable_probe_authority_failures(
    monkeypatch,
    error,
    expected_status,
    expected_detail,
) -> None:
    class _Service:
        def __init__(self, **_kwargs):
            pass

        def complete(self, **_kwargs):
            raise error

    monkeypatch.setattr(learner_state_module, "get_learner_state_service", object)
    monkeypatch.setattr(writeback_module, "RetestWritebackService", _Service)
    body = router.RetestCompletionRequest(
        completion_id="completion-1",
        selection_id="signed-selection",
        mode="review",
        day_index=2026192,
        probe_id="probe-1",
        answers=[router.RetestAnswerRequest(variant_id="F16-v1", choice_ok=False)],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_complete(
                "F16",
                body,
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == expected_status
    assert exc.value.detail == expected_detail


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


def test_review_selection_requires_exact_server_due_probe(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="review",
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "retest_probe_id_required"


def test_review_selection_signs_server_derived_probe_cycle(monkeypatch) -> None:
    captured = {}

    class _LearnerState:
        def list_learning_evidence_events(self, *_args, **_kwargs):
            return [object()]

    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(
        learner_state_module,
        "get_learner_state_service",
        lambda: _LearnerState(),
    )
    monkeypatch.setattr(
        router,
        "build_review_due_projection",
        lambda **_kwargs: {
            "due": [
                {
                    "pack_id": "F16",
                    "probe_id": "probe-canonical",
                    "cycle_anchor": "cycle-canonical",
                    "retest_available": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        router,
        "build_retest_items",
        lambda *args, **kwargs: [{"variant_id": "F16-v1"}],
    )
    monkeypatch.setattr(
        router,
        "retest_supply_identity",
        lambda *args, **kwargs: {"kind": "signed_variant", "digest": "a" * 64},
    )

    def _issue(**kwargs):
        captured.update(kwargs)
        return "signed-review"

    monkeypatch.setattr(router, "issue_retest_selection", _issue)

    result = asyncio.run(
        router.retest_items(
            "F16",
            mode="review",
            probe_id="probe-canonical",
            current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
        )
    )

    assert result["selection_id"] == "signed-review"
    assert captured["probe_id"] == "probe-canonical"
    assert captured["cycle_anchor"] == "cycle-canonical"


def test_review_selection_rejects_stale_or_forged_probe(monkeypatch) -> None:
    class _LearnerState:
        def list_learning_evidence_events(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(
        learner_state_module,
        "get_learner_state_service",
        lambda: _LearnerState(),
    )
    monkeypatch.setattr(
        router,
        "build_review_due_projection",
        lambda **_kwargs: {"due": []},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="review",
                probe_id="probe-forged",
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "retest_probe_not_due"


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
    monkeypatch.setattr(
        router,
        "list_lesson_catalog",
        lambda: ([{"pack_id": "F16", "retest_available": True}], []),
    )
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: False)

    result = asyncio.run(router.lessons(_=SimpleNamespace(user_id="qa_eval_retest_endpoint")))

    assert result["lessons"][0]["retest_available"] is True
    assert result["lessons"][0]["light_practice_available"] is False


def test_retest_answer_schema_accepts_compiled_html_option_identity() -> None:
    body = router.RetestCompletionRequest(
        completion_id="completion-mcq",
        selection_id="signed-selection",
        mode="forward",
        day_index=2026194,
        answers=[
            router.RetestAnswerRequest(
                variant_id="F16-html-q1-example",
                selected_option_id="F16-html-q1-example:option-2",
            )
        ],
    )

    assert body.answers[0].choice_ok is None
    assert body.answers[0].selected_option_id.endswith("option-2")


def test_forward_compiled_html_endpoint_reports_full_pool_without_answer_key(
    monkeypatch,
) -> None:
    items = [
        {
            "answer_type": "single_choice",
            "variant_id": f"F16-html-q{index}",
            "rule_group": f"group-{index}",
            "stem": f"stem-{index}",
            "options": [{"option_id": f"q{index}:a", "text": "A"}],
        }
        for index in range(5)
    ]
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "build_retest_items", lambda *args, **kwargs: items)
    monkeypatch.setattr(
        router,
        "retest_supply_identity",
        lambda *args, **kwargs: {"kind": "compiled_html", "digest": "a" * 64},
    )
    monkeypatch.setattr(
        router,
        "compiled_practice_pool_meta",
        lambda *args, **kwargs: {"core_total": 16, "rule_groups_total": 6},
    )
    monkeypatch.setattr(router, "issue_retest_selection", lambda **kwargs: "signed-five")

    result = asyncio.run(
        router.retest_items(
            "F16",
            mode="forward",
            current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
        )
    )

    assert result["practice_source"] == "compiled_html"
    assert result["pool"] == {"core_total": 16, "rule_groups_total": 6}
    assert result["selection_id"] == "signed-five"
    assert all("is_correct" not in option for item in result["items"] for option in item["options"])


def test_registered_compiled_supply_never_falls_back_to_empty_signed_selection(
    monkeypatch,
) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "build_retest_items", lambda *args, **kwargs: [])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="forward",
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "compiled practice unavailable"
