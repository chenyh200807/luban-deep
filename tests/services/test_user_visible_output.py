from __future__ import annotations

from deeptutor.services.user_visible_output import (
    coerce_user_visible_answer,
    looks_like_internal_output,
    redact_internal_output,
)


def test_detects_internal_skill_loading_output() -> None:
    text = (
        "我来读取相关技能文件，了解详细的使用说明。\n\n"
        "现在让我查看一下这些技能文件所在的目录结构。"
    )
    assert looks_like_internal_output(text) is True


def test_coerce_user_visible_answer_fails_closed_for_internal_output() -> None:
    text = "你是鲁班智考的 thinking 阶段。这里输出的是 tutor 的内部思路，不是最终回复。"
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"


def test_redact_internal_output_recursively() -> None:
    payload = {
        "assistant_content": "我来读取相关技能文件。",
        "safe": "建筑构造是研究建筑物各组成部分构造做法的学科。",
    }
    assert redact_internal_output(payload) == {
        "assistant_content": "[INTERNAL_OUTPUT_REDACTED]",
        "safe": "建筑构造是研究建筑物各组成部分构造做法的学科。",
    }


def test_coerce_user_visible_answer_blocks_tool_command_leakage() -> None:
    text = (
        "我先查一下防水专题讲义，确保数值和层级准确。\n\n"
        "```bash\n"
        "read_file path=\"/app/data/tutorbot/construction-exam-coach/workspace/skills/references/waterproof.md\"\n"
        "```"
    )
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"


def test_coerce_user_visible_answer_blocks_rag_xml_and_provider_errors() -> None:
    rag_text = "<rags>{\"query\":\"防水等级\",\"results\":[]}</rags>"
    provider_error = "{'error': {'code': 'InternalError.Algo.DataInspectionFailed'}}"

    assert coerce_user_visible_answer(rag_text) == "暂时未生成适合直接展示的答案，请重试一次。"
    assert coerce_user_visible_answer(provider_error) == "暂时未生成适合直接展示的答案，请重试一次。"
