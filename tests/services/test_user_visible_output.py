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


def test_coerce_strips_orphan_reference_markers_when_citations_disabled():
    """task #25 单一公开 sink:引用关闭(生产默认)时,coerce 剥离漏给学生的孤儿〔N〕脚注
    (主 LLM 输出但无来源的内部引用噪声)。覆盖判分/讲解/出题所有 emit 路径(它们都经此)。"""
    from deeptutor.services.user_visible_output import coerce_user_visible_answer

    out = coerce_user_visible_answer("### 阅卷结论\n你答了A，正确答案C，得0分。〔3〕诊断：概念混淆〔5〕")
    assert "〔3〕" not in out and "〔5〕" not in out
    assert "阅卷结论" in out and "概念混淆" in out  # 正文保留


def test_coerce_preserves_reference_markers_with_backing_footer():
    """有合法引用 footer(`依据`段+来源线索)时 〔N〕 是合法引用渲染,coerce 不得误删。
    判据是 footer 在不在,与全局 citation flag 无关。"""
    from deeptutor.services.user_visible_output import coerce_user_visible_answer

    text = "正确答案是 C〔1〕。\n\n依据\n〔1〕2026建筑实务教材 §3.1"
    out = coerce_user_visible_answer(text)
    assert "〔1〕" in out  # 有 footer,合法标注保留


def test_coerce_strips_orphan_markers_even_when_citation_flag_enabled(monkeypatch):
    """关键回归(2026-06-23):citation flag=True 但判分 LLM 吐的 〔N〕 没 footer=孤儿,
    仍必须剥(flag≠footer——test2 实证 flag 开但孤儿〔N〕漏给学生)。"""
    import deeptutor.services.citations.config as cfg

    monkeypatch.setattr(cfg, "answer_citations_enabled", lambda: True)
    from deeptutor.services.user_visible_output import coerce_user_visible_answer

    out = coerce_user_visible_answer("### 阅卷结论\n你答了A，正确答案B，得0分。〔2〕诊断：概念混淆〔4〕")
    assert "〔2〕" not in out and "〔4〕" not in out  # 无 footer 的孤儿,flag 开也剥


def test_coerce_strips_rich_grounding_source_markers():
    """task#27:判分/教学 judge 把检索 grounding 标记 〔源:chunk_id〕(rich_leaf_runtime,
    supporting-citation-only)模仿进输出时,终端 sink 必须剥——它绝不该露给学生。"""
    from deeptutor.services.user_visible_output import coerce_user_visible_answer

    out = coerce_user_visible_answer(
        "### 阅卷结论\n你答了A，正确答案C，得0分。诊断：危大工程需专家论证〔源:CK_1A_0001〕"
    )
    assert "〔源:CK_1A_0001〕" not in out and "〔源" not in out
    assert "阅卷结论" in out and "危大工程需专家论证" in out  # 正文保留


def test_coerce_strips_body_marker_not_backed_by_footer_marker() -> None:
    text = "正确答案是 C〔2〕。\n\n依据\n〔1〕2026建筑实务教材 §3.1"

    out = coerce_user_visible_answer(text)

    assert "C〔2〕" not in out
    assert "正确答案是 C" in out
    assert "〔1〕2026建筑实务教材 §3.1" in out


def test_coerce_blocks_prompt_envelope_and_profile_projection_labels() -> None:
    text = (
        "参考证据：题库命中片段\n"
        "局部工作记忆投影：上一轮判分摘要\n"
        "长期画像提示：M07 画像提示，学生近期薄弱点为防水构造。"
    )

    assert looks_like_internal_output(text) is True
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"


def test_coerce_blocks_internal_learner_summary_source_title_leak() -> None:
    text = (
        "以下是本轮回答中引用的证据来源：\n\n"
        "1. **`learner_summary`** — 学员学习摘要，其中提到"
        "\"防水工程学习：已练屋面防水卷材空铺法短边搭接宽度题，答100mm（标准150mm）\"。\n\n"
        "没有引用其他证据源。"
    )

    assert looks_like_internal_output(text) is True
    assert coerce_user_visible_answer(text) == "暂时未生成适合直接展示的答案，请重试一次。"
