from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import luban_lesson as router
from deeptutor.services.learner_state import service as learner_state_module
from deeptutor.services.luban_lesson import retest_writeback as writeback_module
from deeptutor.services.luban_lesson.practice_html import PracticeHtmlInvalid


def _receipt_token(
    variant_ids: list[str],
    *,
    pack_id: str = "F16",
    surface_id: str = "practice.html",
    projection_digest: str = "b" * 64,
    source_digest: str = "c" * 64,
) -> str:
    body = {
        "schema": "luban_practice_projection_receipt.v1",
        "pack_id": pack_id,
        "surface_id": surface_id,
        "ordered_variant_ids": list(variant_ids),
        "source_digest": source_digest,
        "projection_digest": projection_digest,
    }
    raw = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


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


def test_forward_receipt_selection_echoes_bridged_receipt(monkeypatch) -> None:
    """B2 桥接:合法 receipt → 选题=receipt 题集,响应回显同一 receipt。"""
    ids = [f"F16-html-q{index}" for index in range(5)]
    receipt = _receipt_token(ids)
    items = [
        {
            "answer_type": "single_choice",
            "variant_id": vid,
            "rule_group": f"group-{index}",
            "stem": f"stem-{index}",
            "options": [{"option_id": f"{vid}:a", "text": "A"}],
        }
        for index, vid in enumerate(ids)
    ]
    captured: dict = {}

    def _build(*_args, **kwargs):
        captured["build"] = kwargs
        return items

    def _issue(**kwargs):
        captured["selection"] = kwargs
        return "signed-receipt"

    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "build_retest_items", _build)
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
    monkeypatch.setattr(router, "issue_retest_selection", _issue)

    result = asyncio.run(
        router.retest_items(
            "F16",
            mode="forward",
            practice_surface="practice.html",
            projection_receipt=receipt,
            current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
        )
    )

    # receipt 作为"客户所见题集"身份进入唯一 builder,不在路由层旁路选题。
    assert captured["build"]["projection_receipt"] == receipt
    assert result["projection_receipt"] == receipt
    assert result["projection_digest"] == "b" * 64
    assert result["practice_source"] == "compiled_html"
    assert [item["variant_id"] for item in result["items"]] == ids
    # selection identity 签发的题序与 receipt 完全一致(completion 重判同一集合)。
    assert captured["selection"]["variant_ids"] == ids


def test_forward_receipt_drift_fails_closed_as_content_updated_retake(
    monkeypatch,
) -> None:
    """供给漂移(重签/撤销/篡改)→ 语义错误 content_updated_retake,绝不按 index 换题。"""
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)

    def _build(*_args, **_kwargs):
        raise PracticeHtmlInvalid("content_updated_retake")

    monkeypatch.setattr(router, "build_retest_items", _build)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="forward",
                practice_surface="practice.html",
                projection_receipt=_receipt_token(
                    [f"F16-html-q{index}" for index in range(5)]
                ),
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == {"error": "content_updated_retake"}


def test_forward_practice_not_released_is_distinct_from_content_updated(
    monkeypatch,
) -> None:
    """资格未就绪(供给未签发发布)→ 独立 409 ``practice_not_released``。

    绝不冒充 ``content_updated_retake``——前端据此给"练习还在签发中,先看讲解"
    暖文案,而非误导性的"题目已更新,请重做"。"""
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)

    def _build(*_args, **_kwargs):
        raise PracticeHtmlInvalid("practice_not_released")

    monkeypatch.setattr(router, "build_retest_items", _build)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="forward",
                practice_surface="practice.html",
                projection_receipt=_receipt_token(
                    [f"F16-html-q{index}" for index in range(5)]
                ),
                current_user=SimpleNamespace(user_id="qa_eval_retest_endpoint"),
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == {"error": "practice_not_released"}


def test_forward_without_receipt_keeps_legacy_projection_shape(monkeypatch) -> None:
    """无 receipt 的旧路径不回归:不回显 receipt 字段,builder 收到空 receipt。"""
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
    captured: dict = {}

    def _build(*_args, **kwargs):
        captured["build"] = kwargs
        return items

    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "build_retest_items", _build)
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

    assert "projection_receipt" not in result
    assert "projection_digest" not in result
    assert captured["build"]["projection_receipt"] == ""


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


# ---------------------------------------- 变体判断题消费接线（切片三：router 两消费点）

_PROBE_ROWS = [
    {
        "variant_id": "S05-A-ic-000",
        "rule_group": "A-send",
        "surface": "送电顺序题面",
        "expected_ok": True,
        "correct_statement": "总→分→开关",
        "anchor": "kc:s05:1",
        "fact_id": "fact-a",
        "skeleton_id": "skel-a1",
        "probe_role": "immediate_confirm",
        "temptation": "顺序易反",
        "loss_reason": "顺序错零分",
    }
]


def _review_learner(monkeypatch):
    class _LearnerState:
        def list_learning_evidence_events(self, *_a, **_k):
            return [object()]

    monkeypatch.setattr(
        learner_state_module, "get_learner_state_service", lambda: _LearnerState()
    )


def test_confirm_facts_forward_serves_variant_probe(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)
    _review_learner(monkeypatch)
    monkeypatch.setattr(router, "validate_immediate_confirm_parent", lambda *a, **k: True)
    captured: dict = {}

    def _probe(pack_id, *, user_id, day_index, probe_role, fact_ids=None, limit=5):
        captured["probe"] = {"probe_role": probe_role, "fact_ids": fact_ids}
        return list(_PROBE_ROWS)

    monkeypatch.setattr(router, "build_variant_probe_items", _probe)
    monkeypatch.setattr(
        router,
        "variant_probe_supply_identity",
        lambda *a, **k: {"kind": "signed_variant", "digest": "a" * 64},
    )

    def _issue(**kwargs):
        captured["selection"] = kwargs
        return "signed-variant-sel"

    monkeypatch.setattr(router, "issue_retest_selection", _issue)

    def _no_compiled(*_a, **_k):
        raise AssertionError("compiled build must not run for a confirm request")

    monkeypatch.setattr(router, "build_retest_items", _no_compiled)

    result = asyncio.run(
        router.retest_items(
            "S05",
            mode="forward",
            confirm_facts="fact-a,fact-b",
            confirm_anchor="terminal-forward-1",
            current_user=SimpleNamespace(user_id="u1"),
        )
    )

    assert result["practice_source"] == "signed_variant"
    assert result["variant_probe_role"] == "immediate_confirm"
    assert [i["variant_id"] for i in result["items"]] == ["S05-A-ic-000"]
    assert result["selection_id"] == "signed-variant-sel"
    assert captured["probe"]["probe_role"] == "immediate_confirm"
    assert captured["probe"]["fact_ids"] == ["fact-a", "fact-b"]
    assert captured["selection"]["supply_kind"] == "signed_variant"
    assert captured["selection"]["cycle_anchor"] == "terminal-forward-1"


def test_confirm_facts_flag_off_fails_closed_without_compiled_fallback(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: False)

    def _no_compiled(*_args, **_kwargs):
        raise AssertionError("confirm must never downgrade to compiled forward")

    monkeypatch.setattr(router, "build_retest_items", _no_compiled)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "F16",
                mode="forward",
                confirm_facts="fact-a",
                confirm_anchor="terminal-forward-1",
                current_user=SimpleNamespace(user_id="u1"),
            )
        )

    assert exc.value.status_code == 404


def test_confirm_facts_no_supply_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)
    _review_learner(monkeypatch)
    monkeypatch.setattr(router, "validate_immediate_confirm_parent", lambda *a, **k: True)
    monkeypatch.setattr(router, "build_variant_probe_items", lambda *a, **k: [])

    def _no_compiled(*_args, **_kwargs):
        raise AssertionError("confirm supply failure must not enter compiled fallback")

    monkeypatch.setattr(router, "build_retest_items", _no_compiled)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "S05",
                mode="forward",
                confirm_facts="fact-none",
                confirm_anchor="terminal-forward-1",
                current_user=SimpleNamespace(user_id="u1"),
            )
        )

    assert exc.value.status_code == 404


def test_confirm_facts_rejects_missing_parent_anchor(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router.retest_items(
                "S05",
                mode="forward",
                confirm_facts="fact-a",
                current_user=SimpleNamespace(user_id="u1"),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "retest_confirm_anchor_required"


def test_compiled_forward_exposes_confirm_facts_ready(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_light_practice_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)
    items = [
        {
            "answer_type": "single_choice",
            "variant_id": f"S05-html-q{index}",
            "rule_group": f"group-{index}",
            "stem": f"stem-{index}",
            "options": [{"option_id": f"q{index}:a", "text": "A"}],
        }
        for index in range(5)
    ]
    monkeypatch.setattr(router, "build_retest_items", lambda *a, **k: items)
    monkeypatch.setattr(
        router,
        "retest_supply_identity",
        lambda *a, **k: {"kind": "compiled_html", "digest": "a" * 64},
    )
    monkeypatch.setattr(
        router,
        "compiled_practice_pool_meta",
        lambda *a, **k: {"core_total": 16, "rule_groups_total": 6},
    )
    monkeypatch.setattr(router, "issue_retest_selection", lambda **k: "signed-five")
    monkeypatch.setattr(
        router,
        "variant_probe_fact_ids",
        lambda *a, **k: frozenset({"fact-a"}),
    )

    result = asyncio.run(
        router.retest_items(
            "S05",
            mode="forward",
            current_user=SimpleNamespace(user_id="u1"),
        )
    )

    assert result["practice_source"] == "compiled_html"
    # 只含有 immediate_confirm 供给的 fact（fact-b 计数 0 被排除）。
    assert result["confirm_facts_ready"] == ["fact-a"]


def _due_projection(state: str):
    return {
        "due": [
            {
                "pack_id": "S05",
                "probe_id": "probe-1",
                "cycle_anchor": "cycle-1",
                "retest_available": True,
                "state": state,
            }
        ]
    }


def test_review_weak_state_serves_d1_variant(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)
    _review_learner(monkeypatch)
    monkeypatch.setattr(
        router, "build_review_due_projection", lambda **k: _due_projection("weak")
    )
    captured: dict = {}

    def _probe(pack_id, *, user_id, day_index, probe_role, fact_ids=None, limit=5):
        captured["probe_role"] = probe_role
        return [dict(_PROBE_ROWS[0], probe_role="d1_probe", expected_ok=False)]

    monkeypatch.setattr(router, "build_variant_probe_items", _probe)
    monkeypatch.setattr(
        router,
        "variant_probe_supply_identity",
        lambda *a, **k: {"kind": "signed_variant", "digest": "a" * 64},
    )
    monkeypatch.setattr(router, "issue_retest_selection", lambda **k: "signed-d1")

    def _no_compiled(*_a, **_k):
        raise AssertionError("compiled build must not run when variant serves review")

    monkeypatch.setattr(router, "build_retest_items", _no_compiled)

    result = asyncio.run(
        router.retest_items(
            "S05",
            mode="review",
            probe_id="probe-1",
            current_user=SimpleNamespace(user_id="u1"),
        )
    )

    assert result["practice_source"] == "signed_variant"
    assert result["variant_probe_role"] == "d1_probe"
    assert captured["probe_role"] == "d1_probe"


def test_review_fresh_state_keeps_compiled_mcq(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)
    _review_learner(monkeypatch)
    monkeypatch.setattr(
        router, "build_review_due_projection", lambda **k: _due_projection("fresh")
    )

    def _no_variant(*_a, **_k):
        raise AssertionError("fresh (D+1) must stay on anchor MCQ, never variant")

    monkeypatch.setattr(router, "build_variant_probe_items", _no_variant)
    monkeypatch.setattr(
        router, "build_retest_items", lambda *a, **k: [{"variant_id": "S05-mcq-1"}]
    )
    monkeypatch.setattr(
        router,
        "retest_supply_identity",
        lambda *a, **k: {"kind": "compiled_html", "digest": "a" * 64},
    )
    monkeypatch.setattr(router, "issue_retest_selection", lambda **k: "signed-mcq")

    result = asyncio.run(
        router.retest_items(
            "S05",
            mode="review",
            probe_id="probe-1",
            current_user=SimpleNamespace(user_id="u1"),
        )
    )

    # fresh 不换变体：走 compiled MCQ builder（review 顶层 practice_source 恒
    # signed_variant 是既有行为；变体身份由 variant_probe_role 缺省区分）。
    assert [i["variant_id"] for i in result["items"]] == ["S05-mcq-1"]
    assert "variant_probe_role" not in result


def test_review_variant_empty_falls_back_to_compiled_no_blank(monkeypatch) -> None:
    monkeypatch.setattr(router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(router, "_variant_probe_enabled", lambda: True)
    _review_learner(monkeypatch)
    monkeypatch.setattr(
        router, "build_review_due_projection", lambda **k: _due_projection("stable")
    )
    monkeypatch.setattr(router, "build_variant_probe_items", lambda *a, **k: [])
    monkeypatch.setattr(
        router, "build_retest_items", lambda *a, **k: [{"variant_id": "S05-mcq-1"}]
    )
    monkeypatch.setattr(
        router,
        "retest_supply_identity",
        lambda *a, **k: {"kind": "compiled_html", "digest": "a" * 64},
    )
    monkeypatch.setattr(router, "issue_retest_selection", lambda **k: "signed-mcq")

    result = asyncio.run(
        router.retest_items(
            "S05",
            mode="review",
            probe_id="probe-1",
            current_user=SimpleNamespace(user_id="u1"),
        )
    )

    # 变体空 → 退 compiled MCQ（绝不空窗）；无 variant_probe_role 标记。
    assert [i["variant_id"] for i in result["items"]] == ["S05-mcq-1"]
    assert "variant_probe_role" not in result
