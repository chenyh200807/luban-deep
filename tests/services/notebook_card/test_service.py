import asyncio

from deeptutor.services.notebook_card.service import NotebookCardService
from deeptutor.services.notebook_card.store import InMemoryNotebookCardStore


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
