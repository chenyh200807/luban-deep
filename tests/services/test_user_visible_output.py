from __future__ import annotations

from deeptutor.services.user_visible_output import (
    coerce_user_visible_answer,
    looks_like_internal_output,
    looks_like_unsafe_visible_output,
    redact_internal_output,
)


def test_detects_internal_skill_loading_output() -> None:
    text = (
        "我来读取相关技能文件，了解详细的使用说明。\n\n"
        "现在让我查看一下这些技能文件所在的目录结构。"
    )
    assert looks_like_internal_output(text) is True


def test_detects_soft_skill_reference_process_output() -> None:
    text = (
        "好的，我来加载建筑构造相关的专题内容，帮你出题练习。\n\n"
        "先读取 skill 总则和选择题讲解 reference。"
    )
    assert looks_like_internal_output(text) is True
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"


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


def test_coerce_user_visible_answer_blocks_dsml_tool_leakage() -> None:
    text = (
        "让我先查一下你的学习记录。\n\n"
        '< | DSML | toolcalls>< | DSML | invoke name="readfile">< | DSML | parameter '
        'name="filepath" string="true">/app/data/tutorbot/construction-exam-coach/'
        "workspace/skills/memory/PROFILE.md</ | DSML | parameter></ | DSML | invoke>"
    )

    assert looks_like_internal_output(text) is True
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"


def test_coerce_user_visible_answer_blocks_learning_plan_file_leakage() -> None:
    text = (
        "我来帮你查看当前的学习计划。首先让我检查一下是否有HEARTBEAT.md文件，"
        "然后读取 workspace 里的计划配置。"
    )
    assert looks_like_internal_output(text) is True
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"


def test_coerce_user_visible_answer_blocks_rag_xml_and_provider_errors() -> None:
    rag_text = "<rags>{\"query\":\"防水等级\",\"results\":[]}</rags>"
    provider_error = "{'error': {'code': 'InternalError.Algo.DataInspectionFailed'}}"
    auth_error = (
        "Error: {'message': 'Authentication Fails, Your api key: ****486e is invalid', "
        "'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}"
    )
    html_error = (
        '<!doctype html><html lang="en"><head><title>Example Domain</title></head>'
        "<body><h1>Example Domain</h1></body></html>"
    )

    assert coerce_user_visible_answer(rag_text) == "暂时未生成适合直接展示的答案，请重试一次。"
    assert coerce_user_visible_answer(provider_error) == "暂时未生成适合直接展示的答案，请重试一次。"
    assert coerce_user_visible_answer(auth_error) == "暂时未生成适合直接展示的答案，请重试一次。"
    assert coerce_user_visible_answer(html_error) == "暂时未生成适合直接展示的答案，请重试一次。"


def test_coerce_user_visible_answer_blocks_malformed_multilingual_model_output() -> None:
    text = (
        "我是鲁班铎学法发芽鹤 minimumimericussyactivationayan.Man轉 재 "
        "MedievalGeneration吞ienna单据_counter年轻的 Nash喔ufficient impactfuledsAg "
        "превра就是把CU就是个even流水构件手势ポ_ac HAVEStates稍微 Highland "
        "مرض习Bearer Experts皖二战 pathway Binghamoo Hoffmanncloud教育学 "
        " بیت心率 transformed怒气 extraordinary многие suppressor"
    )

    assert looks_like_unsafe_visible_output(text) is True
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"
