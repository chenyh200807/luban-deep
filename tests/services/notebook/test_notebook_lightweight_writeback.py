"""G1 — 笔记轻/重路径分流（写回收权）。

手动工作台卡片（metadata 带 ``card_type``）只走轻路径
``record_notebook_writeback``，**不**触发 ``refresh_from_turn``（summary LLM
改写 / compiled-truth refresh）与 Bot-Learner Overlay ``patch_overlay``。

无 ``card_type`` 的 legacy 记录行为不回归：仍走重路径。

依据：docs/plan/2026-05-26-luban-learner-workspace-notebook-calendar-prd.md §1.2 /
docs/plan/2026-05-30-luban-learner-profile-wiring-execution-plan.md Task 1 GATE。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from deeptutor.services.notebook import service as notebook_service


def _fake_learner_state_service(monkeypatch) -> AsyncMock:
    fake = AsyncMock()
    fake.record_notebook_writeback = AsyncMock()
    fake.refresh_from_turn = AsyncMock()
    monkeypatch.setattr(notebook_service, "get_learner_state_service", lambda: fake)
    return fake


@pytest.mark.unit
def test_manual_card_skips_heavy_writeback(tmp_path, monkeypatch):
    fake = _fake_learner_state_service(monkeypatch)
    mgr = notebook_service.NotebookManager(base_dir=str(tmp_path))

    ok = asyncio.run(
        mgr._writeback_learner_state(
            user_id="u1",
            source_bot_id="",
            notebook_id="nb1",
            title="责任主体",
            user_query="",
            summary="采分模板：发现问题→分析原因→处理→复查验收→记录→预防",
            output="",
            metadata={"card_type": "scoring_card", "record_id": "r1"},
        )
    )

    assert ok is True
    fake.record_notebook_writeback.assert_awaited_once()       # 轻路径仍写 notebook_* 事件
    fake.refresh_from_turn.assert_not_awaited()                # 关键：手动卡片不污染 summary


@pytest.mark.unit
def test_legacy_record_still_runs_heavy_writeback(tmp_path, monkeypatch):
    fake = _fake_learner_state_service(monkeypatch)
    mgr = notebook_service.NotebookManager(base_dir=str(tmp_path))

    ok = asyncio.run(
        mgr._writeback_learner_state(
            user_id="u1",
            source_bot_id="",
            notebook_id="nb1",
            title="某次答疑",
            user_query="专项方案审批流程？",
            summary="编制→审核→审批→论证→交底→验收",
            output="",
            metadata={"record_type": "question"},        # 无 card_type
        )
    )

    assert ok is True
    fake.refresh_from_turn.assert_awaited_once()               # legacy 行为不回归
