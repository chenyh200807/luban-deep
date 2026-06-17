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
        captured["system_prompt"] = kwargs["system_prompt"]
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
    assert "知识库/题库检索依据" in captured["user_prompt"]
    assert "逐项解析" in captured["system_prompt"]
    assert "### 记忆口诀" in captured["system_prompt"]
    assert "关键词抓手" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_submission_grader_prompt_adds_open_world_directive_when_answer_authority_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺标准答案 authority 时必须注入开放世界裁决指令（2026-06-11 根因修复）。"""
    captured: dict[str, str] = {}
    agent = SubmissionGraderAgent(language="zh")

    async def _fake_stream_llm(*_args, **kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        yield "ok"

    monkeypatch.setattr(agent, "stream_llm", _fake_stream_llm)

    await agent.process(
        user_message="我选B",
        question_context={
            "question_id": "tb_q_1",
            "question": "模板拆除应优先满足哪项要求？",
            "question_type": "choice",
            "options": {"A": "进度计划", "B": "混凝土强度"},
            "correct_answer": "",
            "user_answer": "B",
            "is_correct": None,
            "diagnosis": "OPEN_WORLD",
        },
    )

    prompt = captured["user_prompt"]
    assert "Open-world adjudication directive" in prompt
    assert "独立裁决正确答案" in prompt
    assert "禁止以缺少标准答案为由拒绝判分" in prompt
    # is_correct=None 时不得渲染误导性的 Score: 0。
    assert "Score: 0" not in prompt


@pytest.mark.asyncio
async def test_submission_grader_prompt_omits_open_world_directive_when_answer_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    agent = SubmissionGraderAgent(language="zh")

    async def _fake_stream_llm(*_args, **kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        yield "ok"

    monkeypatch.setattr(agent, "stream_llm", _fake_stream_llm)

    await agent.process(
        user_message="我选A",
        question_context={
            "question_id": "q_known",
            "question": "流水步距反映的是什么？",
            "question_type": "choice",
            "options": {"A": "工期", "B": "相邻专业队投入间隔"},
            "correct_answer": "B",
            "user_answer": "A",
            "is_correct": False,
        },
    )

    assert "Open-world adjudication directive" not in captured["user_prompt"]
    assert "Score: 0" in captured["user_prompt"]
