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


@pytest.mark.unit
def test_auto_card_overlay_patch_excludes_working_memory_projection(tmp_path, monkeypatch):
    """#23 第二层(2026-06-23,DeepSeek-V4-Pro 异源核):自动卡(无 card_type)走重路径
    仍 patch_overlay,但**不再**把判分输出 / 卡片摘要写进 working_memory_projection。

    该字段经 turn_runtime 当 EVIDENCE 注入下一轮 judge;写判分输出会让 judge 跨会话
    自我强化幻觉(抄回自己上一轮脑补的"中标价1.7亿")。断写入链=循环自灭。
    只保留 local_notebook_scope_refs(无害 scope 引用)。
    """
    _fake_learner_state_service(monkeypatch)

    captured: dict = {}

    class _FakeOverlay:
        def patch_overlay(self, bot_id, user_id, patch, *, source_feature, source_id):
            captured["operations"] = patch.get("operations", [])

    import deeptutor.services.learner_state as ls

    monkeypatch.setattr(ls, "get_bot_learner_overlay_service", lambda: _FakeOverlay())
    mgr = notebook_service.NotebookManager(base_dir=str(tmp_path))

    ok = asyncio.run(
        mgr._writeback_learner_state(
            user_id="u1",
            source_bot_id="bot_alpha",            # 有 bot + 无 card_type → 走 patch_overlay
            notebook_id="nb1",
            title="招投标判分",
            user_query="判对错",
            summary="背景中标价1.7亿，2%为340万，500万超标。",   # 模拟含脑补数值的判分输出
            output="",
            metadata={"record_type": "question"},  # 无 card_type = 自动卡
        )
    )

    assert ok is True
    fields = [op.get("field") for op in captured.get("operations", [])]
    assert "local_notebook_scope_refs" in fields
    assert "working_memory_projection" not in fields  # 关键:判分输出不回灌 overlay
