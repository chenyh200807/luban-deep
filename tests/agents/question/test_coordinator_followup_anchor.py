from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator


@pytest.mark.asyncio
async def test_coordinator_generate_from_followup_context_builds_templates_without_idea_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("followup anchor generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_generation_loop(
        self,
        templates,
        user_topic: str,
        preference: str,
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ):
        captured["templates"] = templates
        captured["user_topic"] = user_topic
        captured["preference"] = preference
        captured["history_context"] = history_context
        captured["require_explanation"] = require_explanation
        captured["lightweight_generation"] = lightweight_generation
        return []

    monkeypatch.setattr(AgentCoordinator, "_generation_loop", _fake_generation_loop)

    coordinator = AgentCoordinator(language="zh", enable_idea_rag=True)
    result = await coordinator.generate_from_followup_context(
        user_topic="继续出2道很简单的选择题，只考刚才这几个概念。",
        preference="",
        num_questions=2,
        difficulty="easy",
        question_type="choice",
        followup_question_context={
            "question_id": "set_1",
            "question": "上一轮练习",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_prev_1",
                    "question": "流水节拍反映什么？",
                    "question_type": "choice",
                    "correct_answer": "A",
                    "explanation": "节拍反映本专业队在一个施工段上的持续时间。",
                    "concentration": "流水节拍",
                    "difficulty": "easy",
                    "knowledge_context": "上一轮重点 1",
                },
                {
                    "question_id": "q_prev_2",
                    "question": "流水步距反映什么？",
                    "question_type": "choice",
                    "correct_answer": "B",
                    "explanation": "步距反映相邻专业队投入间隔。",
                    "concentration": "流水步距",
                    "difficulty": "easy",
                    "knowledge_context": "上一轮重点 2",
                },
            ],
        },
        history_context="最近一直在讲流水节拍和流水步距。",
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 2
    assert [template.source for template in templates] == ["followup_anchor", "followup_anchor"]
    assert [template.concentration for template in templates] == ["流水节拍", "流水步距"]
    assert all(template.question_type == "choice" for template in templates)
    assert all(template.difficulty == "easy" for template in templates)
    assert captured["require_explanation"] is True
    assert captured["lightweight_generation"] is False
    assert result["trace"]["anchor_generation"] is True
    assert result["trace"]["anchor_item_count"] == 2


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_skips_idea_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_generation_loop(
        self,
        templates,
        user_topic: str,
        preference: str,
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ):
        captured["templates"] = templates
        captured["require_explanation"] = require_explanation
        captured["lightweight_generation"] = lightweight_generation
        captured["user_topic"] = user_topic
        return []

    monkeypatch.setattr(AgentCoordinator, "_generation_loop", _fake_generation_loop)

    coordinator = AgentCoordinator(language="zh", enable_idea_rag=True)
    result = await coordinator.generate_from_topic(
        user_topic="我现在学到网络计划了，先给我出3道很短的小题，只出题不要答案。",
        preference="只出题",
        num_questions=3,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 3
    assert all(template.source == "lightweight_topic" for template in templates)
    assert all(template.question_type == "choice" for template in templates)
    assert all(template.difficulty == "easy" for template in templates)
    assert all(
        template.metadata["knowledge_context"] == "当前练习主题：我现在学到网络计划了，先给我出3道很短的小题，只出题不要答案。"
        for template in templates
    )
    assert captured["require_explanation"] is False
    assert captured["lightweight_generation"] is True
    assert result["trace"]["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_uses_single_rag_anchor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured["rag_kwargs"] = kwargs
        return {
            "query": kwargs.get("query", ""),
            "provider": "supabase",
            "kb_name": kwargs.get("kb_name"),
            "answer": "【题目】关于流水节拍，下列说法正确的是？\n【选项】{\"A\":\"反映工序持续时间\"}\n【答案】A\n【解析】流水节拍反映本专业队在一个施工段上的持续时间。",
            "exact_question": {
                "stem": "关于流水节拍，下列说法正确的是？",
                "question_type": "choice",
                "correct_answer": "A",
                "analysis": "流水节拍反映本专业队在一个施工段上的持续时间。",
                "options": {"A": "反映工序持续时间"},
                "source_group": "question_exact_text",
                "confidence": 0.93,
            },
        }

    async def _fake_generation_loop(
        self,
        templates,
        user_topic: str,
        preference: str,
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ):
        captured["templates"] = templates
        captured["require_explanation"] = require_explanation
        captured["lightweight_generation"] = lightweight_generation
        return []

    monkeypatch.setattr("deeptutor.agents.question.coordinator.rag_search", _fake_rag_search)
    monkeypatch.setattr(AgentCoordinator, "_generation_loop", _fake_generation_loop)

    coordinator = AgentCoordinator(language="zh", kb_name="construction-exam", enable_idea_rag=True)
    result = await coordinator.generate_from_topic(
        user_topic="我现在学到流水节拍了，先给我出1道很短的小题，只出题不要答案。",
        preference="只出题",
        num_questions=1,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 1
    assert captured["rag_kwargs"]["query"] == "我现在学到流水节拍了，先给我出1道很短的小题，只出题不要答案。"
    assert captured["rag_kwargs"]["kb_name"] == "construction-exam"
    assert captured["rag_kwargs"]["only_need_context"] is True
    assert captured["lightweight_generation"] is True
    assert captured["require_explanation"] is False
    assert "题库参考题目：关于流水节拍，下列说法正确的是？" in templates[0].metadata["knowledge_context"]
    assert "题库解析要点：流水节拍反映本专业队在一个施工段上的持续时间。" in templates[0].metadata["knowledge_context"]
    assert result["trace"]["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_falls_back_when_rag_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured["rag_kwargs"] = kwargs
        return {
            "query": kwargs.get("query", ""),
            "provider": "supabase",
            "kb_name": kwargs.get("kb_name"),
            "answer": "",
            "exact_question": {},
        }

    async def _fake_generation_loop(
        self,
        templates,
        user_topic: str,
        preference: str,
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ):
        captured["templates"] = templates
        return []

    monkeypatch.setattr("deeptutor.agents.question.coordinator.rag_search", _fake_rag_search)
    monkeypatch.setattr(AgentCoordinator, "_generation_loop", _fake_generation_loop)

    coordinator = AgentCoordinator(language="zh", kb_name="construction-exam", enable_idea_rag=True)
    await coordinator.generate_from_topic(
        user_topic="我现在学到网络计划了，先给我出1道很短的小题，只出题不要答案。",
        preference="只出题",
        num_questions=1,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 1
    assert templates[0].metadata["knowledge_context"] == "当前练习主题：我现在学到网络计划了，先给我出1道很短的小题，只出题不要答案。"
