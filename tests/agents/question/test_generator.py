from __future__ import annotations

import pytest

from deeptutor.agents.question.agents.generator import Generator
from deeptutor.agents.question.models import QuestionTemplate


class StubGenerator(Generator):
    def __init__(self, repaired_payload: dict | None = None) -> None:
        self._repaired_payload = repaired_payload or {}

    async def _repair_payload(self, **kwargs):  # type: ignore[override]
        return self._repaired_payload


class PromptCapturingGenerator(Generator):
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.tool_flags = {}

    def _build_available_tools_text(self) -> str:  # type: ignore[override]
        return "(no tools available)"

    async def stream_llm(self, **kwargs):  # type: ignore[override]
        self.prompts.append(str(kwargs.get("user_prompt") or ""))
        yield (
            '{"question_type":"choice","question":"下列哪项说法正确？",'
            '"options":{"A":"甲","B":"乙","C":"丙","D":"丁"},'
            '"correct_answer":"A","explanation":""}'
        )


@pytest.mark.asyncio
async def test_generator_repairs_coding_question_that_looks_like_multiple_choice() -> None:
    generator = StubGenerator(
        repaired_payload={
            "question_type": "coding",
            "question": "Write pseudocode that alternates answer order across iterations to mitigate positional bias.",
            "options": None,
            "correct_answer": "for i in range(total_iterations):\n    if i % 2 == 0:\n        prompt = f\"{query} Answer 1: {answer1} Answer 2: {answer2}\"\n    else:\n        prompt = f\"{query} Answer 1: {answer2} Answer 2: {answer1}\"\n    evaluate(prompt)",
            "explanation": "Alternate the two answers deterministically so each appears in each position equally often.",
        }
    )
    template = QuestionTemplate(
        question_id="q_3",
        concentration="win-rate comparison positional bias mitigation",
        question_type="coding",
        difficulty="hard",
    )
    invalid_payload = {
        "question_type": "coding",
        "question": "Select the code logic that best mitigates positional bias across iterations.",
        "options": {
            "A": "fixed order",
            "B": "alternate order every iteration",
            "C": "randomize order",
            "D": "always reverse order",
        },
        "correct_answer": "B",
        "explanation": "B is correct.",
    }

    normalized, validation = await generator._validate_and_repair_payload(
        template=template,
        payload=invalid_payload,
        user_topic="win-rate comparison",
        preference="",
        history_context="",
        knowledge_context="",
        available_tools="(no tools available)",
    )

    assert normalized["question_type"] == "coding"
    assert normalized["options"] is None
    assert normalized["correct_answer"].startswith("for i in range")
    assert validation["repaired"] is True
    assert validation["schema_ok"] is True
    assert validation["issues"] == []


def test_generator_normalizes_choice_answer_from_option_text() -> None:
    payload = Generator._normalize_payload_shape(
        "choice",
        {
            "question_type": "choice",
            "question": "Which option is correct?",
            "options": {
                "a": "Alpha",
                "b": "Beta",
                "c": "Gamma",
                "d": "Delta",
            },
            "correct_answer": "Gamma",
            "explanation": "Because gamma matches the requirement.",
        },
    )

    assert payload["options"] == {
        "A": "Alpha",
        "B": "Beta",
        "C": "Gamma",
        "D": "Delta",
    }
    assert payload["correct_answer"] == "C"


@pytest.mark.asyncio
async def test_generator_allows_missing_explanation_when_not_required() -> None:
    generator = StubGenerator()
    template = QuestionTemplate(
        question_id="q_1",
        concentration="流水步距与总时差",
        question_type="choice",
        difficulty="easy",
    )

    normalized, validation = await generator._validate_and_repair_payload(
        template=template,
        payload={
            "question_type": "choice",
            "question": "总时差和自由时差的区别，以下哪项正确？",
            "options": {
                "A": "两者都表示总工期余量",
                "B": "自由时差只影响紧后工作的最早开始",
                "C": "总时差只看本工作持续时间",
                "D": "自由时差一定大于总时差",
            },
            "correct_answer": "B",
            "explanation": "",
        },
        user_topic="网络计划",
        preference="只出题",
        history_context="",
        knowledge_context="",
        available_tools="(no tools available)",
        require_explanation=False,
    )

    assert normalized["correct_answer"] == "B"
    assert normalized["explanation"] == ""
    assert validation["schema_ok"] is True
    assert validation["issues"] == []


@pytest.mark.asyncio
async def test_generator_lightweight_prompt_uses_canonical_anchor_only() -> None:
    generator = PromptCapturingGenerator()
    template = QuestionTemplate(
        question_id="q_1",
        concentration="防水工程",
        question_type="choice",
        difficulty="easy",
        reference_question="屋面防水施工基本要求正确的有（　　）。",
        reference_answer="BDE",
        metadata={
            "knowledge_context": (
                "当前学习锚点：防水工程\n"
                "题库参考题目：屋面防水施工基本要求正确的有（　　）。"
            ),
            "lightweight_generation": True,
            "anchor_source": "rag_answer_bundle",
        },
    )

    qa_pair = await generator.process(
        template=template,
        user_topic="我现在在学防水工程，先给我出1道建筑实务单选题，不要给答案。",
        preference="只出题",
        history_context="",
        require_explanation=False,
        lightweight_generation=True,
    )

    assert qa_pair.question == "下列哪项说法正确？"
    assert generator.prompts
    prompt = generator.prompts[0]
    assert "Canonical anchor:" in prompt
    assert "User topic:" not in prompt
    assert '"concentration"' not in prompt
    assert "当前学习锚点：防水工程" in prompt
