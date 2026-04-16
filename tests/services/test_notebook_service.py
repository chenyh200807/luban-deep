"""Notebook service regression tests."""

from __future__ import annotations

import importlib

from deeptutor.services.notebook.service import NotebookManager, RecordType

notebook_service_module = importlib.import_module("deeptutor.services.notebook.service")


def test_add_record_accepts_enum_record_type(tmp_path) -> None:
    manager = NotebookManager(base_dir=str(tmp_path))
    notebook = manager.create_notebook("CLI test notebook")

    result = manager.add_record(
        notebook_ids=[notebook["id"]],
        record_type=RecordType.CO_WRITER,
        title="Sample",
        user_query="Sample",
        output="# Sample",
    )

    assert result["record"]["type"] == RecordType.CO_WRITER

    stored = manager.get_notebook(notebook["id"])
    assert stored is not None
    assert stored["records"][0]["type"] == "co_writer"


def test_add_and_update_record_trigger_learner_state_writeback(monkeypatch, tmp_path) -> None:
    calls: list[dict] = []

    class _FakeLearnerStateService:
        def __init__(self, *args, **kwargs):
            pass

        async def record_notebook_writeback(self, **kwargs):
            calls.append({"kind": "event", **kwargs})

        async def refresh_from_turn(self, **kwargs):
            calls.append({"kind": "refresh", **kwargs})
            return None

    class _FakeOverlayService:
        def patch_overlay(self, bot_id: str, user_id: str, patch: dict, *, source_feature: str, source_id: str):
            calls.append(
                {
                    "kind": "overlay_patch",
                    "bot_id": bot_id,
                    "user_id": user_id,
                    "patch": patch,
                    "source_feature": source_feature,
                    "source_id": source_id,
                }
            )
            return {"effective_overlay": {}}

    monkeypatch.setattr(
        notebook_service_module,
        "get_learner_state_service",
        lambda: _FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: _FakeOverlayService(),
    )

    manager = NotebookManager(base_dir=str(tmp_path))
    notebook = manager.create_notebook("Learner notebook")

    created = manager.add_record(
        notebook_ids=[notebook["id"]],
        record_type=RecordType.GUIDED_LEARNING,
        title="Learning note",
        summary="结构化总结",
        user_query="我想整理一下地基基础的知识点。",
        output="## Output",
        metadata={"user_id": "student_demo", "source_bot_id": "bot_alpha", "ui_language": "zh"},
    )

    assert created["record"]["metadata"]["user_id"] == "student_demo"
    assert calls[0]["kind"] == "event"
    assert calls[0]["user_id"] == "student_demo"
    assert calls[0]["record_id"] == created["record"]["id"]
    assert calls[0]["operation"] == "add"
    assert calls[0]["source_bot_id"] == "bot_alpha"
    assert calls[1]["kind"] == "refresh"
    assert calls[1]["session_id"] == notebook["id"]
    assert calls[1]["capability"] == "notebook:bot_alpha"
    assert "结构化总结" in calls[1]["assistant_message"]
    assert calls[2]["kind"] == "overlay_patch"
    assert calls[2]["bot_id"] == "bot_alpha"
    assert calls[2]["user_id"] == "student_demo"
    assert any(item["field"] == "local_notebook_scope_refs" for item in calls[2]["patch"]["operations"])
    assert any(item["field"] == "working_memory_projection" for item in calls[2]["patch"]["operations"])

    updated = manager.update_record(
        notebook["id"],
        created["record"]["id"],
        summary="更新后的总结",
        output="## Updated output",
    )

    assert updated is not None
    assert len(calls) == 6
    assert calls[3]["kind"] == "event"
    assert calls[3]["operation"] == "update"
    assert calls[3]["user_id"] == "student_demo"
    assert calls[4]["kind"] == "refresh"
    assert calls[4]["session_id"] == notebook["id"]
    assert calls[4]["assistant_message"] == "更新后的总结"
    assert calls[5]["kind"] == "overlay_patch"
    assert calls[5]["source_feature"] == "notebook"
