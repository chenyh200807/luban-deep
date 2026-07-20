"""公开练习页交卷薄适配器（/luban-preview/practice-submit）域测试。

单一权威合同：
- 公开页嵌入零答案键投影，交卷只上报「看到的题集(receipt) + 所选 option_id」；
- 判分与全部学习证据 append 只发生在 ``RetestWritebackService.complete()``；
- 适配器自身零判分、零证据语义，selection 在同一请求内服务端自签自验。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import luban_preview
from deeptutor.services.learner_state import service as learner_state_module
from deeptutor.services.luban_lesson.practice_html import load_compiled_practice

_PACK = "N01"
_USER = "qa_eval_practice_submit"


def _hosted_cards() -> list[dict[str, Any]]:
    from deeptutor.services.luban_lesson import list_green_lessons

    return [
        row
        for row in list_green_lessons()
        if str(row.get("pack_id") or "").upper() == _PACK
    ]


@dataclass
class _Event:
    event_id: str
    user_id: str
    source_feature: str
    source_id: str
    memory_kind: str
    payload_json: dict[str, Any]
    dedupe_key: str


class _LearnerState:
    def __init__(self) -> None:
        self.events: list[_Event] = []
        self.by_dedupe: dict[str, _Event] = {}

    def append_memory_event(self, user_id: str, **kwargs: Any) -> _Event:
        key = str(kwargs["dedupe_key"])
        if key in self.by_dedupe:
            return self.by_dedupe[key]
        event = _Event(
            event_id=f"evt_{len(self.events) + 1}",
            user_id=user_id,
            source_feature=str(kwargs["source_feature"]),
            source_id=str(kwargs["source_id"]),
            memory_kind=str(kwargs["memory_kind"]),
            payload_json=dict(kwargs["payload_json"]),
            dedupe_key=key,
        )
        self.events.append(event)
        self.by_dedupe[key] = event
        return event

    def list_memory_events(self, user_id: str, limit: Any = None) -> list[_Event]:
        return list(self.events)


class _Store:
    def __init__(self, *, user_id: str | None = _USER) -> None:
        self.user_id = user_id
        self.seen: dict[str, Any] = {}

    async def resolve_luban_card_entry_ticket(self, ticket: str, *, pack_id: str):
        self.seen["ticket"] = ticket
        self.seen["pack_id"] = pack_id
        if not self.user_id:
            return None
        return {"user_id": self.user_id, "pack_id": pack_id}


def _receipt_and_answers(*, wrong: int = 0) -> tuple[str, list[dict[str, str]]]:
    """从签发 sidecar 取 public 五题 receipt 与作答（测试侧允许读服务端真值）。"""
    authority = load_compiled_practice(_PACK)
    assert authority is not None
    surface = authority["surfaces"][0]
    by_id = {item["variant_id"]: item for item in authority["items"]}
    answers: list[dict[str, str]] = []
    for index, variant_id in enumerate(surface["variant_ids"]):
        options = by_id[variant_id]["options"]
        correct = next(opt for opt in options if opt["is_correct"] is True)
        distractor = next(opt for opt in options if opt["is_correct"] is not True)
        chosen = distractor if index < wrong else correct
        answers.append(
            {"variant_id": variant_id, "selected_option_id": chosen["option_id"]}
        )
    return str(surface["projection_receipt"]), answers


def _payload(
    receipt: str, answers: list[dict[str, str]], *, completion: str = "round-0001"
) -> luban_preview.LubanPracticeSubmitRequest:
    return luban_preview.LubanPracticeSubmitRequest(
        contextId=_PACK,
        entryTicket="card-capability",
        practiceSurface="practice.html",
        projectionReceipt=receipt,
        completionId=completion,
        answers=[luban_preview.LubanPracticeSubmitAnswer(**answer) for answer in answers],
    )


@pytest.fixture()
def _wired(monkeypatch):
    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "1")
    monkeypatch.setenv("LUBAN_LIGHT_PRACTICE_ENABLED", "1")
    monkeypatch.setattr(luban_preview, "list_green_lessons", _hosted_cards)
    state = _LearnerState()
    store = _Store()
    monkeypatch.setattr(luban_preview, "get_sqlite_session_store", lambda: store)
    monkeypatch.setattr(
        learner_state_module, "get_learner_state_service", lambda: state
    )
    return state, store


def test_submit_grades_only_through_retest_writeback_seam(_wired) -> None:
    state, store = _wired
    receipt, answers = _receipt_and_answers(wrong=2)

    result = asyncio.run(
        luban_preview.submit_luban_preview_practice(_payload(receipt, answers))
    )

    assert store.seen == {"ticket": "card-capability", "pack_id": _PACK}
    assert result["pack_id"] == _PACK
    assert result["mode"] == "forward"
    assert result["completion_id"] == "h5:round-0001"
    assert result["score"] == {"correct_count": 3, "question_count": 5}
    by_id = {item["variant_id"]: item for item in result["items"]}
    wrong_ids = {answer["variant_id"] for answer in answers[:2]}
    for answer in answers:
        item = by_id[answer["variant_id"]]
        assert item["is_correct"] is (answer["variant_id"] not in wrong_ids)
        # 逐项解析（诱因/丢分点/怎么改）只在服务端判定后下发。
        assert set(item["feedback"]) == {
            "correct_statement",
            "temptation",
            "loss_reason",
            "fix",
        }
        assert item["correct_option_id"]

    terminals = [
        event
        for event in state.events
        if event.payload_json.get("completion_terminal") is True
    ]
    assert len(terminals) == 1
    terminal = terminals[0].payload_json
    assert terminal["practice_mode"] == "forward"
    assert terminal["retest_completion_id"] == "h5:round-0001"
    assert terminal["quality"]["authority"] == "compiled_html_server_rescore"
    item_events = [
        event
        for event in state.events
        if event.payload_json.get("event_type") == "learning_evidence"
        and event.payload_json.get("completion_terminal") is not True
    ]
    assert len(item_events) == 5
    for event in item_events:
        payload = event.payload_json
        assert payload["answer_type"] == "single_choice"
        if payload["is_correct"] is False:
            # canonical GradingErrorEvent 形状由 seam 统一签发，适配器不改写。
            assert payload["error_events"] and set(payload["error_events"][0]) == {
                "error_code",
                "concept_tag",
                "diagnosis",
            }


def test_submit_is_idempotent_for_same_completion(_wired) -> None:
    state, _store = _wired
    receipt, answers = _receipt_and_answers(wrong=1)
    payload = _payload(receipt, answers, completion="round-replay")

    first = asyncio.run(luban_preview.submit_luban_preview_practice(payload))
    events_after_first = len(state.events)
    second = asyncio.run(luban_preview.submit_luban_preview_practice(payload))

    assert second["score"] == first["score"]
    assert second["completion_id"] == first["completion_id"] == "h5:round-replay"
    assert len(state.events) == events_after_first


def test_submit_without_valid_ticket_fails_closed(monkeypatch, _wired) -> None:
    monkeypatch.setattr(
        luban_preview, "get_sqlite_session_store", lambda: _Store(user_id=None)
    )
    receipt, answers = _receipt_and_answers()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            luban_preview.submit_luban_preview_practice(_payload(receipt, answers))
        )

    assert exc.value.status_code == 401


def test_submit_tampered_receipt_maps_to_content_updated_retake(_wired) -> None:
    receipt, answers = _receipt_and_answers()
    tampered = receipt[:-4] + ("AAAA" if not receipt.endswith("AAAA") else "BBBB")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            luban_preview.submit_luban_preview_practice(_payload(tampered, answers))
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == {"error": "content_updated_retake"}


def test_submit_answer_set_must_match_receipt_question_set(_wired) -> None:
    receipt, answers = _receipt_and_answers()
    answers[0] = {
        "variant_id": "N01-html-practice-html-q99-000000000000",
        "selected_option_id": "N01-html-practice-html-q99-000000000000:option-1",
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            luban_preview.submit_luban_preview_practice(_payload(receipt, answers))
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "practice_submit_answer_set_mismatch"


def test_submit_rollout_disabled_is_honest_not_released(monkeypatch, _wired) -> None:
    monkeypatch.setenv("LUBAN_LIGHT_PRACTICE_ENABLED", "0")
    receipt, answers = _receipt_and_answers()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            luban_preview.submit_luban_preview_practice(_payload(receipt, answers))
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == {"error": "practice_not_released"}


def test_submit_unhosted_card_rejected_before_any_grading(monkeypatch) -> None:
    monkeypatch.setattr(luban_preview, "list_green_lessons", lambda: [])
    receipt, answers = _receipt_and_answers()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            luban_preview.submit_luban_preview_practice(_payload(receipt, answers))
        )

    assert exc.value.status_code == 400
