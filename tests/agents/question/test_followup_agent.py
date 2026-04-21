import pytest

from deeptutor.agents.question.agents.followup_agent import FollowupAgent


def test_render_question_context_includes_question_set_items() -> None:
    rendered = FollowupAgent._render_question_context(
        {
            "question_id": "question_set",
            "question": "第1题、第2题批改",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "第1题题干",
                    "question_type": "choice",
                    "options": {"A": "甲", "B": "乙"},
                    "user_answer": "A",
                    "correct_answer": "B",
                    "explanation": "第1题解析",
                },
                {
                    "question_id": "q_2",
                    "question": "第2题题干",
                    "question_type": "choice",
                    "options": {"A": "丙", "B": "丁"},
                    "user_answer": "B",
                    "correct_answer": "B",
                    "explanation": "第2题解析",
                },
            ],
        },
        reveal_reference_material=True,
    )

    assert "Question set items:" in rendered
    assert "Item 1 ID: q_1" in rendered
    assert "Item 2 ID: q_2" in rendered
    assert "Reference answer: B" in rendered
    assert "第2题解析" in rendered


@pytest.mark.asyncio
async def test_followup_agent_process_preserves_concrete_case_anchor_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    agent = FollowupAgent(language="zh")

    async def _fake_stream_llm(*_args, **kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        yield "ok"

    monkeypatch.setattr(agent, "stream_llm", _fake_stream_llm)

    result = await agent.process(
        user_message="为什么不能这样判断？",
        question_context={
            "question_id": "q_anchor",
            "question": "关于一栋6层住宅楼的防火分区，下列说法正确的是？",
            "question_type": "choice",
        },
        history_context="上轮正在围绕同一案例讲解。",
    )

    assert result == "ok"
    assert "6层住宅楼" in captured["user_prompt"]
    assert "必须显式保留这些锚点原词" in captured["user_prompt"]
