"""goal2+3 Step 1 — generator subject lock (foundation).

S3 patch-spiral proved the generator has NO subject lock: when the topic/anchor is
unresolved it improvises off-domain garbage ("中国最长的河流 / 太阳从哪升起 / 四大发明"
for a 流水施工 request, live 3/3). Two structural holes:
  1. `prompts/zh/generator.yaml` system prompt never says "only construction questions".
  2. The lightweight path drops the real ``user_topic`` (generator.py:315 placeholder
     "(lightweight anchor only)"), so a RAG-miss leaves the LLM with no topic signal.

This locks both so the generator structurally cannot emit a non-construction question.
Hermetic: prompt-contract + captured-prompt assertions, no live LLM.
"""
from __future__ import annotations

import pytest

from deeptutor.agents.question.agents.generator import Generator
from deeptutor.agents.question.models import QuestionTemplate


class _CapturingGenerator(Generator):
    """Real zh-prompt Generator that captures the built user/system prompts."""

    def __init__(self) -> None:
        super().__init__(language="zh")
        self.captured: list[dict] = []

    def _build_available_tools_text(self) -> str:  # type: ignore[override]
        return "(no tools available)"

    async def stream_llm(self, **kwargs):  # type: ignore[override]
        self.captured.append(
            {"user": str(kwargs.get("user_prompt") or ""), "system": str(kwargs.get("system_prompt") or "")}
        )
        yield (
            '{"question_type":"choice","question":"关于流水施工的说法，下列正确的是？",'
            '"options":{"A":"甲","B":"乙","C":"丙","D":"丁"},"correct_answer":"A","explanation":""}'
        )


def _template() -> QuestionTemplate:
    return QuestionTemplate(
        question_id="q_1",
        concentration="流水施工",
        difficulty="medium",
        question_type="choice",
        source="topic",
    )


# ---- hole 1: the system prompt must lock the construction subject -----------------------
def test_system_prompt_locks_construction_subject() -> None:
    system = str(Generator(language="zh").get_prompt("system") or "")
    assert "建筑实务" in system, "generator system prompt must name the construction-exam subject"
    # an explicit "only construction / never off-domain" lock (not just a topic mention).
    assert ("只" in system or "不得" in system or "禁止" in system), (
        "system prompt must explicitly forbid non-construction questions"
    )


# ---- hole 2: the lightweight path must NOT drop the real user_topic --------------------
@pytest.mark.asyncio
async def test_lightweight_payload_keeps_user_topic() -> None:
    gen = _CapturingGenerator()
    await gen._generate_payload(
        template=_template(),
        user_topic="流水施工",
        preference="",
        history_context="",
        knowledge_context="",  # RAG miss — the failure mode that used to garbage out
        available_tools="(no tools available)",
        previous_questions="",
        require_explanation=False,
        lightweight_generation=True,
    )
    built = gen.captured[-1]
    assert "(lightweight anchor only)" not in built["user"], "lightweight path must not drop user_topic"
    assert "流水施工" in (built["user"] + built["system"]), "the real topic must reach the generator"
    # subject lock present on the lightweight path too.
    assert "建筑实务" in (built["user"] + built["system"])
