from deeptutor.services.notebook.service import NotebookManager, RecordType


def test_baseline_manual_save_currently_triggers_refresh_from_turn(tmp_path, monkeypatch):
    """RED-LINE BASELINE: 证明收权前手动收藏（无 card_type，legacy 路径）会调用 refresh_from_turn。
    Phase 2 收权后，card_type 卡片走 NotebookCardService（轻路径），不再触发；本基线锁定 legacy 污染事实。"""
    calls = {"refresh": 0, "overlay": 0}

    async def _fake_refresh(**_kwargs):
        calls["refresh"] += 1

    class _FakeLearner:
        async def record_notebook_writeback(self, **_kwargs):
            return None
        refresh_from_turn = staticmethod(_fake_refresh)

    manager = NotebookManager(base_dir=str(tmp_path))
    monkeypatch.setattr(
        "deeptutor.services.notebook.service.get_learner_state_service",
        lambda: _FakeLearner(),
    )
    manager.create_notebook("默认", owner_key="ok_user_001")
    nb_id = manager.list_notebooks(owner_key="ok_user_001")[0]["id"]

    manager.add_record(
        notebook_ids=[nb_id],
        record_type=RecordType.CHAT,
        title="专项施工方案审批流程",
        user_query="这个流程我记不住",
        output="编制->审核->审批->论证->交底->验收",
        metadata={"user_id": "user_001", "operation": "add"},
        user_id="user_001",
        owner_key="ok_user_001",
    )
    # 无运行中的事件循环时，NotebookManager._dispatch_writeback 走 asyncio.run(coro)
    # 同步执行写回（service.py:225-230），因此 add_record 返回时 refresh 已被调用。
    assert calls["refresh"] >= 1  # 基线：当前 legacy(非 card_type) 收藏确实走重路径
