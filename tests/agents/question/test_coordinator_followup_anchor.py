from __future__ import annotations

from pathlib import Path

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
    ):
        captured["templates"] = templates
        captured["user_topic"] = user_topic
        captured["preference"] = preference
        captured["history_context"] = history_context
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
    assert result["trace"]["anchor_generation"] is True
    assert result["trace"]["anchor_item_count"] == 2
