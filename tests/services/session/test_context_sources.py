from __future__ import annotations

from dataclasses import dataclass

import pytest

from deeptutor.services.session.context_sources import (
    ContextSourceLoader,
)


@dataclass
class _NotebookManagerStub:
    records: list[dict[str, object]]

    def get_records_by_references(self, notebook_references: list[dict[str, object]]) -> list[dict[str, object]]:
        resolved: list[dict[str, object]] = []
        for ref in notebook_references:
            notebook_id = str(ref.get("notebook_id", "") or "")
            record_ids = [str(item or "").strip() for item in (ref.get("record_ids") or []) if str(item or "").strip()]
            for record in self.records:
                if str(record.get("notebook_id", "") or "") != notebook_id:
                    continue
                if record_ids and str(record.get("id", "") or "") not in record_ids:
                    continue
                resolved.append(dict(record))
        return resolved


@dataclass
class _SessionStoreStub:
    sessions: dict[str, dict[str, object]]
    messages: dict[str, list[dict[str, object]]]
    owned_sessions: list[dict[str, object]] | None = None

    async def get_session(self, session_id: str) -> dict[str, object] | None:
        payload = self.sessions.get(session_id)
        return dict(payload) if payload is not None else None

    async def get_messages_for_context(self, session_id: str) -> list[dict[str, object]]:
        return [dict(item) for item in self.messages.get(session_id, [])]

    async def list_sessions_by_owner(
        self,
        owner_key: str,
        source: str | None = None,
        archived: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        before_updated_at: float | None = None,
        before_session_id: str | None = None,
    ) -> list[dict[str, object]]:
        del owner_key, source, archived, offset, before_updated_at, before_session_id
        sessions = [dict(item) for item in (self.owned_sessions or [])]
        return sessions[:limit]


@dataclass
class _LearningPlanServiceStub:
    views: dict[str, dict[str, object]]

    def read_guided_session_view(self, plan_id: str) -> dict[str, object] | None:
        payload = self.views.get(plan_id)
        return dict(payload) if payload is not None else None


def test_context_source_loader_prefers_summary_and_caps_notebook_output() -> None:
    loader = ContextSourceLoader(
        notebook_manager=_NotebookManagerStub(
            records=[
                {
                    "id": "record-1",
                    "notebook_id": "notebook-1",
                    "notebook_name": "地基基础",
                    "title": "承载力判定",
                    "summary": "判断承载力的核心是先看极限状态。",
                    "output": "X" * 2000,
                    "type": "solve",
                    "user_query": "承载力怎么判断？",
                    "created_at": 123.0,
                    "kb_name": "construction-exam",
                }
            ]
        ),
        session_store=_SessionStoreStub({}, {}),
        learning_plan_service=_LearningPlanServiceStub({}),
    )

    candidates = loader.load_notebook_candidates(
        user_question="承载力怎么判断？",
        notebook_references=[{"notebook_id": "notebook-1", "record_ids": ["record-1"]}],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_kind == "notebook"
    assert candidate.fragment_kind == "summary"
    assert candidate.authority == "primary"
    assert candidate.content == "判断承载力的核心是先看极限状态。"
    assert "X" * 100 not in candidate.content
    assert candidate.metadata["notebook_id"] == "notebook-1"


@pytest.mark.asyncio
async def test_context_source_loader_prefers_history_summary_and_avoids_full_transcript() -> None:
    loader = ContextSourceLoader(
        notebook_manager=_NotebookManagerStub([]),
        session_store=_SessionStoreStub(
            sessions={
                "session-summary": {
                    "id": "session-summary",
                    "title": "地基复习",
                    "compressed_summary": "已经复习了承载力与沉降控制。",
                    "updated_at": "2026-04-16T10:00:00+08:00",
                },
                "session-fallback": {
                    "id": "session-fallback",
                    "title": "历史会话",
                    "compressed_summary": "",
                    "updated_at": "2026-04-16T10:00:00+08:00",
                },
            },
            messages={
                "session-summary": [
                    {"role": "user", "content": "旧问题 A"},
                    {"role": "assistant", "content": "旧回答 A"},
                    {"role": "user", "content": "旧问题 B"},
                    {"role": "assistant", "content": "旧回答 B"},
                ],
                "session-fallback": [
                    {"role": "user", "content": "最早的问题，不应整体泄露。"},
                    {"role": "assistant", "content": "中间回答，不应整体泄露。"},
                    {"role": "user", "content": "最新问题片段"},
                    {"role": "assistant", "content": "最新回答片段"},
                ],
            },
        ),
        learning_plan_service=_LearningPlanServiceStub({}),
    )

    candidates = await loader.load_history_candidates(
        user_question="承载力和沉降控制怎么区分？",
        history_references=["session-summary", "session-fallback"],
    )

    assert len(candidates) == 2
    summary_candidate = next(item for item in candidates if item.fragment_id == "session-summary")
    fallback_candidate = next(item for item in candidates if item.fragment_id == "session-fallback")

    assert summary_candidate.fragment_kind == "summary"
    assert summary_candidate.authority == "supporting"
    assert summary_candidate.content == "已经复习了承载力与沉降控制。"
    assert "旧问题 A" not in summary_candidate.content

    assert fallback_candidate.fragment_kind == "excerpt"
    assert fallback_candidate.authority == "fallback"
    assert "最早的问题" not in fallback_candidate.content
    assert "最新问题片段" in fallback_candidate.content
    assert "最新回答片段" in fallback_candidate.content


@pytest.mark.asyncio
async def test_context_source_loader_implicit_cross_session_recall_excludes_current_session() -> None:
    loader = ContextSourceLoader(
        notebook_manager=_NotebookManagerStub([]),
        session_store=_SessionStoreStub(
            sessions={},
            messages={
                "session-older-1": [
                    {"role": "user", "content": "当时我问过沉降控制"},
                    {"role": "assistant", "content": "建议分三步复习。"},
                ],
                "session-older-2": [
                    {"role": "user", "content": "我偏好先看例题"},
                    {"role": "assistant", "content": "那就先看例题再回顾原理。"},
                ],
                "session-current": [
                    {"role": "user", "content": "现在继续这个题"},
                    {"role": "assistant", "content": "正在处理当前题。"},
                ],
            },
            owned_sessions=[
                {
                    "id": "session-current",
                    "title": "当前会话",
                    "compressed_summary": "当前轮次的会话摘要。",
                    "summary": "当前轮次的会话摘要。",
                    "updated_at": 300.0,
                },
                {
                    "id": "session-older-1",
                    "title": "地基回顾",
                    "compressed_summary": "之前复习过沉降控制。",
                    "summary": "之前复习过沉降控制。",
                    "last_message": "建议分三步复习。",
                    "updated_at": 200.0,
                },
                {
                    "id": "session-older-2",
                    "title": "学习偏好",
                    "compressed_summary": "我偏好先看例题。",
                    "summary": "我偏好先看例题。",
                    "last_message": "那就先看例题再回顾原理。",
                    "updated_at": 100.0,
                },
            ],
        ),
        learning_plan_service=_LearningPlanServiceStub({}),
    )

    candidates = await loader.load_history_candidates(
        user_question="你上次建议我怎么学？",
        user_id="student-1",
        history_references=[],
        max_candidates=2,
    )

    assert [item.fragment_id for item in candidates] == ["session-older-1", "session-older-2"]
    assert all(item.metadata["load_mode"] == "implicit_cross_session_recall" for item in candidates)
    assert all(item.metadata["excluded_current_session"] is True for item in candidates)
    assert all("session-current" != item.fragment_id for item in candidates)
    assert "Title: 地基回顾" in candidates[0].content
    assert "Recent content" in candidates[0].content


@pytest.mark.asyncio
async def test_context_source_loader_does_not_implicitly_recall_without_cross_session_signal() -> None:
    loader = ContextSourceLoader(
        notebook_manager=_NotebookManagerStub([]),
        session_store=_SessionStoreStub(
            sessions={},
            messages={},
            owned_sessions=[
                {
                    "id": "session-current",
                    "title": "当前会话",
                    "updated_at": 300.0,
                },
                {
                    "id": "session-older",
                    "title": "旧会话",
                    "compressed_summary": "旧摘要。",
                    "updated_at": 200.0,
                },
            ],
        ),
        learning_plan_service=_LearningPlanServiceStub({}),
    )

    candidates = await loader.load_history_candidates(
        user_question="请解释一下沉降控制",
        user_id="student-1",
        history_references=[],
    )

    assert candidates == []


def test_context_source_loader_uses_active_plan_anchor_and_adjacent_pages_only() -> None:
    loader = ContextSourceLoader(
        notebook_manager=_NotebookManagerStub([]),
        session_store=_SessionStoreStub({}, {}),
        learning_plan_service=_LearningPlanServiceStub(
            {
                "plan-1": {
                    "session_id": "plan-1",
                    "user_id": "student-1",
                    "notebook_name": "地基基础",
                    "summary": "## 完成总结\n- 已完成前两页。",
                    "status": "learning",
                    "current_index": 2,
                    "page_count": 5,
                    "ready_count": 2,
                    "progress": 40,
                    "pages": [
                        {
                            "page_index": 0,
                            "knowledge_title": "承载力",
                            "knowledge_summary": "承载力基础概念。",
                            "user_difficulty": "easy",
                            "html": "<h1>page-0</h1>",
                        },
                        {
                            "page_index": 1,
                            "knowledge_title": "基础处理",
                            "knowledge_summary": "基础处理方法。",
                            "user_difficulty": "medium",
                            "html": "<h1>page-1</h1>",
                        },
                        {
                            "page_index": 2,
                            "knowledge_title": "沉降控制",
                            "knowledge_summary": "沉降控制与验算。",
                            "user_difficulty": "medium",
                            "html": "<h1>page-2</h1>",
                        },
                        {
                            "page_index": 3,
                            "knowledge_title": "施工注意",
                            "knowledge_summary": "施工注意事项。",
                            "user_difficulty": "hard",
                            "html": "<h1>page-3</h1>",
                        },
                        {
                            "page_index": 4,
                            "knowledge_title": "收尾复盘",
                            "knowledge_summary": "最后复盘。",
                            "user_difficulty": "hard",
                            "html": "<h1>page-4</h1>",
                        },
                    ],
                }
            }
        ),
    )

    candidates = loader.load_active_plan_page_candidates(
        user_question="沉降控制怎么理解？",
        user_id="student-1",
        plan_id="plan-1",
    )

    assert len(candidates) == 4
    assert candidates[0].fragment_id == "2"
    fragment_ids = [item.fragment_id for item in candidates]
    assert "plan-summary" in fragment_ids
    assert "0" not in fragment_ids
    assert "4" not in fragment_ids
    assert candidates[0].content.startswith("沉降控制")
    assert "完成总结" in next(item for item in candidates if item.fragment_id == "plan-summary").content
