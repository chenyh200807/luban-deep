import pytest

from deeptutor.agents.question.agents.submission_grader_agent import SubmissionGraderAgent


@pytest.mark.asyncio
async def test_submission_grader_process_preserves_concrete_case_anchor_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    agent = SubmissionGraderAgent(language="zh")

    async def _fake_stream_llm(*_args, **kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        yield "ok"

    monkeypatch.setattr(agent, "stream_llm", _fake_stream_llm)

    result = await agent.process(
        user_message="我选A",
        question_context={
            "question_id": "q_anchor",
            "question": "某6层住宅楼外墙保温系统的防火做法，哪项正确？",
            "question_type": "choice",
            "correct_answer": "B",
            "user_answer": "A",
            "is_correct": False,
            "explanation": "6层住宅楼仍要按住宅建筑要求判断外保温防火分隔。",
        },
        history_context="学员一直沿用同一个案例答题。",
    )

    assert result == "ok"
    assert "6层住宅楼" in captured["user_prompt"]
    assert "必须显式保留这些锚点原词" in captured["user_prompt"]
