import asyncio

from deeptutor.services.notebook_card.service import NotebookCardService
import pytest

from deeptutor.services.notebook_card.store import InMemoryNotebookCardStore, OptimisticConcurrencyError


class _LearnerSpy:
    def __init__(self):
        self.notebook_writeback = 0
        self.refresh = 0

    async def record_notebook_writeback(self, **_kwargs):
        self.notebook_writeback += 1

    async def refresh_from_turn(self, **_kwargs):  # 必须永不被调用
        self.refresh += 1


def test_save_card_uses_light_writeback_only():
    spy = _LearnerSpy()
    svc = NotebookCardService(store=InMemoryNotebookCardStore(), learner_state_service=spy)
    card = asyncio.run(svc.save_card(
        user_id="u1", subject_id="construction_practice", source_bot_id="construction-exam",
        card_type="scoring_card", source_type="grading",
        source_ref={"kind": "learning_evidence", "event_id": "evt_1"},
        evidence_event_ids=["evt_1"], title="责任主体", raw_user_content="记一下",
        ai_enhanced_content={"summary": "高频考点"},
    ))
    assert card["note_id"]
    assert card["mastery_effect"] == "none"
    assert spy.notebook_writeback == 1
    assert spy.refresh == 0  # RED-LINE: 收权后绝不触发 summary 改写


def test_save_card_forces_mastery_effect_none_even_if_caller_lies():
    spy = _LearnerSpy()
    svc = NotebookCardService(store=InMemoryNotebookCardStore(), learner_state_service=spy)
    card = asyncio.run(svc.save_card(
        user_id="u1", subject_id="", source_bot_id="", card_type="manual_note", source_type="manual",
        source_ref={}, evidence_event_ids=[], title="x", raw_user_content="y",
        ai_enhanced_content={}, mastery_effect="strong",  # 调用方撒谎
    ))
    assert card["mastery_effect"] == "none"


def test_card_store_is_owner_scoped_and_delete_hides_asset():
    spy = _LearnerSpy()
    store = InMemoryNotebookCardStore()
    svc = NotebookCardService(store=store, learner_state_service=spy)
    card = asyncio.run(svc.save_card(
        user_id="u1", subject_id="construction_practice", source_bot_id="", card_type="review_note",
        source_type="chat", source_ref={"turn_id": "turn_1"}, evidence_event_ids=[],
        title="承载力笔记", raw_user_content="承载力复盘", ai_enhanced_content={"summary": "承载力要看极限状态"},
    ))

    assert [item["note_id"] for item in svc.list_cards("u1")] == [card["note_id"]]
    assert svc.list_cards("u2") == []

    archived = asyncio.run(svc.delete_card(
        user_id="u1",
        note_id=card["note_id"],
        expected_version=card["version"],
    ))
    assert archived["archived_at"]
    assert svc.list_cards("u1") == []
    assert store.get_card("u1", card["note_id"])["archived_at"]


def test_card_update_uses_optimistic_concurrency():
    svc = NotebookCardService(store=InMemoryNotebookCardStore(), learner_state_service=_LearnerSpy())
    card = asyncio.run(svc.save_card(
        user_id="u1", subject_id="", source_bot_id="", card_type="manual_note", source_type="manual",
        source_ref={}, evidence_event_ids=[], title="旧标题", raw_user_content="",
        ai_enhanced_content={},
    ))

    updated = asyncio.run(svc.update_card(
        user_id="u1",
        note_id=card["note_id"],
        expected_version=1,
        patch={"title": "新标题", "mastery_effect": "strong"},
    ))

    assert updated["version"] == 2
    assert updated["title"] == "新标题"
    assert updated["mastery_effect"] == "none"

    with pytest.raises(OptimisticConcurrencyError):
        asyncio.run(svc.update_card(
            user_id="u1",
            note_id=card["note_id"],
            expected_version=1,
            patch={"title": "过期更新"},
        ))
