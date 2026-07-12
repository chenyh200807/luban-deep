"""③稳定性 B2/B4 followup 判定器提速 — 差分 harness（硬门）。

背景（2026-06-29 Phase2a + 2026-07-12 Battle1 两次独立调查共同指认）：
`interpret_question_followup_action` 是首答前阻塞分类器的 ~79%，p99 17-19s。
2026-07-12 生产 Langfuse 全量解剖（188 turn/4125 observations）修正了根因画像：
单次延迟与 prompt 大小基本无关（pt<1000 p50=3.7s vs pt≥1000 p50=4.0s），慢在
**输出** p50=216 token 的 JSON（冗长 rationale），~65 tok/s → ≈3.3s 即延迟主体。
故 B2 主杠杆 = 输出 schema 瘦身（reason 收成可选默认空串，仅低置信给一句短说明；
下游只把 reason 透传进 decision trace 且有 or-默认串兜底，无逻辑分支消费）；
输入载荷裁剪降为次杠杆（省成本为主）。B4 = 快档模型（`resolve_fast_tier_model`，
W4 唯一档位 accessor）。两者共用单一灰度门 `LUBAN_FOLLOWUP_FAST_TIER_ENABLED`
（默认关）。

本文件是 B2/B4 的**硬门**，四层断言：

1. 差分裁决一致（主门，按 2026-07-12 修正后的口径）：≥30 个真实形态输入（提交/
   追问/回指切换/继续出题/无关闲聊 + 解析边界形态），给每臂喂**各自 schema 形状**
   的 mock 答复（原臂=冗长 rationale 版，slim 臂=reason 空的短版），断言解析后的
   **裁决字段**（intent/route/answers/preserve_other_answers/confidence）逐用例
   一致——不是原始 JSON 字节一致（输出 schema 变了，字节必然不同）。
2. 解析路径无分叉：mock LLM **同一答复**喂两臂 → 最终 action 逐字段相同（解析/
   规范化/Step4.5 backstop 是共享代码，flag 不得使其分叉）。
3. 瘦身信号保全：SEV 承载规则 1-8 逐字节不变（提交优先/3b 反例/Step4.5），仅规则 9
   输出契约收紧；payload 保留判定必需信号（全部选项字母/question_id/index/
   is_correct/multi_select/has_grading_result/next_training_signal/user_message
   原文），只裁题干尾部/选项文本尾部/作答尾部/history 远端头部。
4. flag 关 = bit-for-bit 守门（B4 门）：flag 未设置/显式 false 时，发给 LLM 的
   prompt 与独立重建的原版逐字节一致、model 参数为 None（主模型）；flag 开时才
   吃 W4 档位 accessor 的快模型，未配置快模型则仍走主模型（仅 B2 生效）。

真 LLM 差分（判定分布是否漂移）**不在本文件**：那是 observe-only 报告，不做门
（eval-design 纪律：mock 差分证"解析路径等价"，不自证"裁决分布等价"）。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from deeptutor.services import question_followup as qf
from deeptutor.services.question_followup import (
    _build_followup_action_prompt,
    interpret_question_followup_action,
    normalize_question_followup_context,
)

_FLAG = "LUBAN_FOLLOWUP_FAST_TIER_ENABLED"
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# 语料：真实形态输入用例。
# 来源 A：tests/fixtures/control_plane_hard_cases.jsonl（控制面硬用例，含
#         question_followup_context 的 9 条——试探提交/假设作答/改答/追问/回指切换/
#         结合教材复述/单字母提交/案例作答/fat-kernel 复用）。
# 来源 B：test_question_followup.py 既有语料形态（_S45_CTX 多选、质量检查题组
#         带 construction_grading_result）。
# 来源 C：生产形态重型 context（长案例题干/长选项/长 history），专门压出裁剪路径。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    label: str
    message: str
    context: dict[str, Any] | None
    history: str = ""
    # mock LLM 的固定答复（两臂同喂）——覆盖各 intent 与解析边界形态。
    llm_reply: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def _reply(intent: str, *, answers: list[dict[str, Any]] | None = None,
           confidence: float = 0.9, preserve: bool = False, reason: str = "差分固定答复") -> str:
    return json.dumps(
        {
            "intent": intent,
            "confidence": confidence,
            "preserve_other_answers": preserve,
            "answers": answers or [],
            "reason": reason,
        },
        ensure_ascii=False,
    )


# 来源 A：control_plane_hard_cases.jsonl → tag 映射到 live 实证过的 LLM 答复形态。
_HARD_CASE_REPLIES: dict[str, str] = {
    # live NO-GO 实证：LLM 带"提交优先"偏置把试探判 answer_questions → Step4.5 降级路径。
    "tentative_answer_hold": _reply(
        "answer_questions",
        answers=[{"question_index": 1, "question_id": "q1", "answer": "A"}],
        reason="提交优先原则",
    ),
    "hypothetical_answer": _reply(
        "answer_questions",
        answers=[{"question_index": 1, "question_id": "q1", "answer": "D"}],
        reason="提交优先原则",
    ),
    "answer_revision": _reply(
        "revise_answers",
        answers=[{"question_index": 1, "question_id": "q1", "answer": "D"}],
        preserve=True,
    ),
    "only_question_no_answer": _reply("ask_followup"),
    "unresolved_switch_followup": _reply("ask_other_question"),
    "source_backed_variant": _reply("ask_followup"),
    "active_submission_mcq": _reply(
        "answer_questions",
        answers=[{"question_index": 1, "question_id": "q1", "answer": "B"}],
    ),
    "active_submission_case": _reply(
        "answer_questions",
        answers=[{"question_index": 1, "question_id": "q1",
                  "answer": "施工单位应组织专家论证危大工程方案"}],
    ),
    "fat_kernel_reads_scene_then_reroutes": _reply(
        "answer_questions",
        answers=[{"question_index": 1, "question_id": "q1", "answer": "B"}],
    ),
}


def _load_hard_cases() -> list[Case]:
    cases: list[Case] = []
    path = _FIXTURES / "control_plane_hard_cases.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        context = (raw.get("metadata") or {}).get("question_followup_context")
        if not context:
            continue  # 无 context 的用例在 interpret 入口就短路（下面有专门用例）
        name = str(raw.get("name") or "")
        reply = _HARD_CASE_REPLIES.get(name) or _reply("unknown")
        cases.append(
            Case(
                label=f"hard::{name}",
                message=str(raw.get("user_message") or ""),
                context=context,
                llm_reply=reply,
                tags=tuple(raw.get("tags") or ()),
            )
        )
    return cases


# 来源 B/C：既有测试语料形态 + 生产形态重型 context。
_S45_CTX = {
    "question_id": "wp-s45",
    "question": "建筑工程安全检查方法包括（多选）？",
    "question_type": "multiple_choice",
    "options": {"A": "听", "B": "写", "C": "量", "D": "测", "E": "运转试验"},
    "correct_answer": "ACDE",
    "multi_select": True,
}

_GRADED_QUIZ_CTX = {
    "question_id": "quiz_quality_inspection",
    "question": "项目施工质量检查与检验训练题组",
    "question_type": "choice",
    "items": [
        {
            "question_id": "q_quality_1",
            "question": "基础工程质量检查分类题",
            "question_type": "single_choice",
            "options": {"A": "自检", "B": "互检", "C": "专检", "D": "抽检"},
            "correct_answer": "B",
            "user_answer": "C",
            "is_correct": False,
            "construction_grading_result": {
                "authority": "construction_grading",
                "next_training_signal": {
                    "concept": "项目施工质量检查与检验",
                    "focus": "基础检查分类混淆",
                    "mode": "practice",
                },
            },
        },
        {
            "question_id": "q_quality_2",
            "question": "混凝土结构实体检验的组织方，正确的是？",
            "question_type": "single_choice",
            "options": {"A": "监理单位", "B": "施工单位", "C": "建设单位", "D": "检测机构"},
            "correct_answer": "A",
            "user_answer": "A",
            "is_correct": True,
        },
    ],
}

# 生产形态：长案例题干 + 长选项 + 长作答（压出 B2 裁剪路径的真实形态）。
_LONG_STEM = (
    "背景资料：某新建办公楼工程，建筑面积 45000 平方米，地下二层，地上十八层，"
    "框架-剪力墙结构，合同工期 720 日历天。施工过程中发生如下事件：事件一：项目部"
    "编制了塔式起重机安装拆卸专项施工方案并组织了专家论证；事件二：基坑开挖深度"
    "5.8m，采用排桩+内支撑的支护形式，监测单位在巡视中发现支撑轴力超过报警值；"
    "事件三：主体结构施工期间，公司安全部门检查发现五层临边防护缺失、部分作业人员"
    "未佩戴安全帽等隐患，下发了隐患整改通知单。问题：1.指出事件一中专项方案论证"
    "程序的不妥之处并说明理由。2.事件二中监测单位和施工单位应分别采取哪些措施？"
    "3.针对事件三中的隐患，写出整改回复的主要内容。"
)
_LONG_OPTIONS = {
    "A": "由总承包单位技术负责人组织专家论证会，论证通过后直接实施，无需重新审批签字确认流程",
    "B": "由施工单位组织召开专家论证会，专家组书面论证报告应经本单位技术负责人、总监理工程师审核签字",
    "C": "由建设单位组织召开专家论证会并邀请质监站参加，论证报告由项目经理签字确认后实施",
    "D": "由监理单位组织召开专家论证会，论证报告经建设单位项目负责人签字后交施工单位实施",
}
_LONG_CASE_CTX = {
    "question_id": "case-2026-jz-018",
    "question": _LONG_STEM,
    "question_type": "case",
    "options": _LONG_OPTIONS,
    "user_answer": (
        "事件一不妥之处：专项方案论证前未经施工单位审核，专家组成员中含本项目参建方"
        "人员不符合规定；理由：危大工程专项方案应先由施工单位技术部门组织审核，专家"
        "应从专家库中随机抽取且与本项目无利害关系。"
    ),
    "multi_select": False,
}

_LONG_HISTORY = (
    "[题目1] 下列关于施工现场消防安全的说法正确的是？（用户答 B，判对）\n"
    "[讲解] 临时消防车道宽度不应小于4m……\n"
    "[题目2] 关于模板支架搭设的说法，正确的是？（用户答 C，判错，正确 A）\n"
    "[讲解] 模板支架立杆间距应经计算确定……\n"
) * 80 + "[老师] 根据你的错因，下一步建议做2道模板支架计算类的题巩固。"
# ×80 ≈ 8400 字符，对齐 turn_runtime history fallback 的 8000 字符预算上限——
# 让重型用例真实压出 history 尾部裁剪，而不是擦边。

_CHATTER_CTX = dict(_S45_CTX)


def _programmatic_cases() -> list[Case]:
    return [
        # --- submission 形态 ---
        Case("sub::clean_letters", "我选ACDE", _S45_CTX,
             llm_reply=_reply("answer_questions",
                              answers=[{"question_index": 1, "question_id": "wp-s45", "answer": "ACDE"}])),
        Case("sub::structured_front_end", "提交作答，请批改：第1题：C；第2题：A", _GRADED_QUIZ_CTX,
             llm_reply=_reply("answer_questions",
                              answers=[{"question_index": 1, "question_id": "q_quality_1", "answer": "C"},
                                       {"question_index": 2, "question_id": "q_quality_2", "answer": "A"}])),
        Case("sub::submit_with_followup_words", "我选ACDE，错因10字以内", _S45_CTX,
             llm_reply=_reply("answer_questions",
                              answers=[{"question_index": 1, "question_id": "wp-s45", "answer": "ACDE"}])),
        Case("sub::option_text_answer", "我选'运转试验'那个", _S45_CTX,
             llm_reply=_reply("answer_questions",
                              answers=[{"question_index": 1, "question_id": "wp-s45", "answer": "运转试验"}])),
        Case("sub::long_case_answer", _LONG_CASE_CTX["user_answer"], _LONG_CASE_CTX,
             llm_reply=_reply("answer_questions",
                              answers=[{"question_index": 1, "question_id": "case-2026-jz-018",
                                        "answer": "事件一不妥之处见作答"}])),
        # Step4.5 backstop：LLM 说提交但消息是试探+推迟 → 两臂必须同样降级 ask_followup。
        Case("sub::tentative_defer_downgrade", "我猜是A但不确定，你先别判", _S45_CTX,
             llm_reply=_reply("answer_questions",
                              answers=[{"question_index": 1, "question_id": "wp-s45", "answer": "A"}],
                              reason="提交优先原则")),
        # submission intent 但 answers 空 → 规范化强制降 unknown（解析路径边界）。
        Case("sub::empty_answers_forced_unknown", "就按我刚才说的交卷", _S45_CTX,
             llm_reply=_reply("answer_questions", answers=[])),
        # --- revise 形态 ---
        Case("rev::change_one_keep_rest", "第2题改成C，其他不变", _GRADED_QUIZ_CTX,
             llm_reply=_reply("revise_answers",
                              answers=[{"question_index": 2, "question_id": "q_quality_2", "answer": "C"}],
                              preserve=True)),
        Case("rev::change_after_grading", "答案改成D", _S45_CTX,
             llm_reply=_reply("revise_answers",
                              answers=[{"question_index": 1, "question_id": "wp-s45", "answer": "D"}])),
        # --- followup 形态 ---
        Case("fu::why_answer", "为什么选B不对？", _GRADED_QUIZ_CTX,
             llm_reply=_reply("ask_followup")),
        Case("fu::which_wrong", "我哪题错了", _GRADED_QUIZ_CTX,
             llm_reply=_reply("ask_followup")),
        Case("fu::explain_long_case", "第2问的整改回复具体怎么写？", _LONG_CASE_CTX,
             llm_reply=_reply("ask_followup")),
        Case("fu::challenge_grading", "我觉得判错了，动火证当日有效为什么不对", _GRADED_QUIZ_CTX,
             llm_reply=_reply("ask_followup")),
        Case("fu::with_long_history", "刚才讲的立杆间距和这道题什么关系", _LONG_CASE_CTX,
             history=_LONG_HISTORY, llm_reply=_reply("ask_followup")),
        # --- switch / 回指 形态（规则 3b）---
        Case("switch::ordinal_history_ref", "最开始那道消防题的正确答案为什么是B", _LONG_CASE_CTX,
             history=_LONG_HISTORY, llm_reply=_reply("ask_other_question")),
        Case("switch::wrong_one_ref", "我做错的那道模板支架题再讲一遍", _LONG_CASE_CTX,
             history=_LONG_HISTORY, llm_reply=_reply("ask_other_question")),
        # 3b 硬性前置：history 找不到被指的题 → unknown（不要猜）。
        Case("switch::ref_not_in_history", "上上上一道题呢", _S45_CTX,
             history="", llm_reply=_reply("unknown")),
        # 序数落在 active set 槽位内 → 不是回指，是 ask_followup（3b 反例②）。
        Case("switch::ordinal_in_active_set", "第2题为什么选A", _GRADED_QUIZ_CTX,
             llm_reply=_reply("ask_followup")),
        # --- practice_generation 形态 ---
        Case("gen::more_questions", "再来3道类似的", _GRADED_QUIZ_CTX,
             llm_reply=_reply("generate_more_questions")),
        Case("gen::next_step_acceptance", "好的，按这个安排", _GRADED_QUIZ_CTX,
             history="上一轮老师说：请按下一步操作巩固。",
             llm_reply=_reply("generate_more_questions")),
        Case("gen::topic_request", "出一道危大工程考点的真题", _LONG_CASE_CTX,
             llm_reply=_reply("generate_more_questions")),
        # --- 无关闲聊 形态 ---
        Case("chat::thanks", "谢谢老师，讲得真好", _CHATTER_CTX,
             llm_reply=_reply("unrelated")),
        Case("chat::weather", "今天天气怎么样", _CHATTER_CTX,
             llm_reply=_reply("unrelated")),
        Case("chat::exam_anxiety", "还有40天考试，我好慌", _CHATTER_CTX,
             llm_reply=_reply("unrelated")),
        # --- 解析边界形态（两臂必须走完全相同的解析分支）---
        Case("parse::json_wrapped_in_prose", "为什么选B", _S45_CTX,
             llm_reply="好的，我的判定如下：\n" + _reply("ask_followup") + "\n以上。"),
        Case("parse::invalid_json_returns_none", "为什么选B", _S45_CTX,
             llm_reply="intent: ask_followup（这不是 JSON）"),
        Case("parse::empty_reply_returns_none", "为什么选B", _S45_CTX,
             llm_reply=""),
        Case("parse::unknown_intent_token", "嗯", _S45_CTX,
             llm_reply=_reply("whatever_new_intent")),
        Case("parse::confidence_garbage", "为什么选B", _S45_CTX,
             llm_reply=json.dumps({"intent": "ask_followup", "confidence": "很高",
                                   "answers": [], "reason": "x"}, ensure_ascii=False)),
        Case("parse::answers_bad_shape", "我选B", _S45_CTX,
             llm_reply=json.dumps({"intent": "answer_questions", "confidence": 0.9,
                                   "answers": ["B"], "reason": "x"}, ensure_ascii=False)),
    ]


CASES: list[Case] = _load_hard_cases() + _programmatic_cases()


def test_corpus_meets_minimum_width() -> None:
    # 任务硬要求：≥30 个真实输入用例，覆盖五类形态。
    assert len(CASES) >= 30
    labels = " ".join(case.label for case in CASES)
    for family in ("sub::", "fu::", "switch::", "gen::", "chat::", "parse::", "hard::"):
        assert family in labels, f"corpus missing family {family}"


# ---------------------------------------------------------------------------
# 第 1 层（主门，2026-07-12 修正后的口径）：各臂喂各自 schema 形状的答复，
# 解析后的裁决字段逐用例一致。
# ---------------------------------------------------------------------------


def _short_schema_reply(verbose_reply: str) -> str:
    """从冗长答复派生 slim 输出契约形状的答复：同 intent/confidence/answers/preserve，
    reason 空串（规则 9 slim 版的常态输出）。非 JSON/空串等解析边界形态原样返回——
    这些用例考察的是两臂走同一失败路径。"""
    try:
        payload = json.loads(verbose_reply)
    except (json.JSONDecodeError, TypeError):
        return verbose_reply
    if not isinstance(payload, dict):
        return verbose_reply
    slim_payload = dict(payload)
    slim_payload["reason"] = ""
    return json.dumps(slim_payload, ensure_ascii=False)


def _adjudication(action: dict[str, Any] | None) -> dict[str, Any] | None:
    """裁决投影：下游真正消费的字段（reason 是 trace 透传，不进裁决面）。"""
    if action is None:
        return None
    return {
        "intent": action.get("intent"),
        "route": qf.followup_action_route(action),
        "answers": action.get("answers"),
        "preserve_other_answers": action.get("preserve_other_answers"),
        "confidence": action.get("confidence"),
    }


def _run_interpret(case: Case, monkeypatch: pytest.MonkeyPatch, flag_value: str) -> tuple[
    dict[str, Any] | None, list[dict[str, Any]]
]:
    captured: list[dict[str, Any]] = []

    async def fake_complete(**kwargs: Any) -> str:
        captured.append(kwargs)
        return case.llm_reply

    monkeypatch.setattr(qf, "complete", fake_complete)
    monkeypatch.setenv(_FLAG, flag_value)
    action = asyncio.run(
        interpret_question_followup_action(case.message, case.context, history_context=case.history)
    )
    return action, captured


@pytest.mark.parametrize("case", CASES, ids=[case.label for case in CASES])
def test_adjudication_parity_with_arm_appropriate_replies(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 主门：原臂喂冗长 rationale 版答复，slim 臂喂短 schema 版答复（输出瘦身后 JSON
    # 形状必然不同），解析后的裁决字段必须逐用例一致。
    baseline_action, _ = _run_interpret(case, monkeypatch, "false")
    slim_case = replace(case, llm_reply=_short_schema_reply(case.llm_reply))
    slim_action, _ = _run_interpret(slim_case, monkeypatch, "true")
    assert _adjudication(slim_action) == _adjudication(baseline_action)


# ---------------------------------------------------------------------------
# 第 2 层：解析路径无分叉 —— mock LLM 同一答复喂两臂 → 最终 action 逐字段相同。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=[case.label for case in CASES])
def test_slim_and_original_walk_identical_parse_path(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_action, baseline_calls = _run_interpret(case, monkeypatch, "false")
    slim_action, slim_calls = _run_interpret(case, monkeypatch, "true")

    # 同 mock 答复 → 最终 action 逐字段一致（解析/规范化/Step4.5 全链路无分叉）。
    assert slim_action == baseline_action

    # 两臂各只发一次 LLM 调用，且发出的 prompt 分别逐字节等于 builder 两种模式的输出。
    assert len(baseline_calls) == 1 and len(slim_calls) == 1
    normalized = normalize_question_followup_context(case.context)
    assert normalized is not None
    assert baseline_calls[0]["prompt"] == _build_followup_action_prompt(
        user_message=case.message, question_context=normalized,
        history_context=case.history, slim=False,
    )
    assert slim_calls[0]["prompt"] == _build_followup_action_prompt(
        user_message=case.message, question_context=normalized,
        history_context=case.history, slim=True,
    )
    # B1 收口的重试上限在两臂都保持。
    assert baseline_calls[0]["max_retries"] == 1
    assert slim_calls[0]["max_retries"] == 1


def test_context_that_normalizes_to_none_short_circuits_both_arms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_complete(**kwargs: Any) -> str:
        nonlocal called
        called = True
        return _reply("unknown")

    monkeypatch.setattr(qf, "complete", fake_complete)
    for flag_value in ("false", "true"):
        monkeypatch.setenv(_FLAG, flag_value)
        action = asyncio.run(interpret_question_followup_action("我选B", {}, history_context=""))
        assert action is None
    assert called is False


# ---------------------------------------------------------------------------
# 第 3 层：瘦身 prompt 的信号保全与裁剪不变量。
# ---------------------------------------------------------------------------


def _split_prompt(prompt: str) -> tuple[str, dict[str, Any]]:
    marker = '{"history_context"'
    idx = prompt.index(marker)
    return prompt[:idx], json.loads(prompt[idx:])


@pytest.mark.parametrize("case", CASES, ids=[case.label for case in CASES])
def test_slim_prompt_preserves_decision_signals(case: Case) -> None:
    normalized = normalize_question_followup_context(case.context)
    assert normalized is not None
    original = _build_followup_action_prompt(
        user_message=case.message, question_context=normalized,
        history_context=case.history, slim=False,
    )
    slim = _build_followup_action_prompt(
        user_message=case.message, question_context=normalized,
        history_context=case.history, slim=True,
    )

    original_rules, original_payload = _split_prompt(original)
    slim_rules, slim_payload = _split_prompt(slim)
    # 规则 1-8 承载 SEV 修复（提交优先/3b 反例/Step4.5 铺垫），逐字节不变；
    # slim 只允许改规则 9 的输出契约（B2 主杠杆=输出 schema 收紧）。
    assert slim_rules.split("9. ")[0] == original_rules.split("9. ")[0]
    assert "提交优先" in slim_rules
    assert "硬性前置" in slim_rules  # 3b 回指前置
    assert "不要猜" in slim_rules  # 规则 5 fail-safe
    # slim 的规则 9 必须带输出收紧契约；原版不得带（bit-for-bit）。
    assert "reason 默认给空字符串" in slim_rules
    assert "reason 默认给空字符串" not in original_rules
    # user_message 永不裁剪（判定的第一信号）。
    assert slim_payload["user_message"] == original_payload["user_message"]

    original_items = original_payload["active_question_set"]
    slim_items = slim_payload["active_question_set"]
    assert len(slim_items) == len(original_items)
    for orig_item, slim_item in zip(original_items, slim_items):
        # 身份/状态信号逐字段保全。
        for key in ("question_index", "question_id", "question_type", "is_correct",
                    "multi_select", "has_grading_result", "next_training_signal"):
            assert slim_item[key] == orig_item[key]
        # 全部选项字母保全（规则 2/6/7 吃字母；文本→字母映射在下游用未裁剪 context）。
        if isinstance(orig_item["options"], dict):
            assert set(slim_item["options"].keys()) == set(orig_item["options"].keys())
            for letter, text in slim_item["options"].items():
                assert str(orig_item["options"][letter]).strip().startswith(
                    text.removesuffix(qf._SLIM_ELLIPSIS)
                )
        # 题干/作答只裁尾部，头部前缀保全（识别"是哪道题"的信号）。
        assert orig_item["question"].startswith(
            slim_item["question"].removesuffix(qf._SLIM_ELLIPSIS)
        )
        assert orig_item["user_answer"].startswith(
            slim_item["user_answer"].removesuffix(qf._SLIM_ELLIPSIS)
        )
    # history 只裁远端头部，近端尾部保全（规则 4 的"上一轮老师说"信号在近端）。
    assert original_payload["history_context"].endswith(
        slim_payload["history_context"].removeprefix(qf._SLIM_ELLIPSIS)
    )
    # 输入载荷只减不增（次杠杆：省成本）。
    assert len(json.dumps(slim_payload, ensure_ascii=False)) <= len(
        json.dumps(original_payload, ensure_ascii=False)
    )


def test_slim_prompt_actually_bounds_heavy_payload() -> None:
    # 可证伪性：对生产形态重型输入，瘦身必须真的把各载荷段收进上限（否则 B2 输入侧是
    # 空转）。注意口径（2026-07-12 修正）：输入裁剪是"防极端的上限兜底+省成本"，
    # 不是延迟主杠杆——history 上限刻意取宽（6000），因为真 LLM observe 差分实测
    # 裁太狠会把回指目标裁掉、诱发 mis-act 方向的误判。
    normalized = normalize_question_followup_context(_LONG_CASE_CTX)
    assert normalized is not None
    slim = _build_followup_action_prompt(
        user_message="为什么", question_context=normalized,
        history_context=_LONG_HISTORY, slim=True,
    )
    _, payload = _split_prompt(slim)
    ellipsis_len = len(qf._SLIM_ELLIPSIS)
    assert len(payload["history_context"]) <= qf._SLIM_HISTORY_TAIL_CHARS + ellipsis_len
    item = payload["active_question_set"][0]
    assert len(item["question"]) <= qf._SLIM_QUESTION_CHARS + ellipsis_len
    assert len(item["user_answer"]) <= qf._SLIM_USER_ANSWER_CHARS + ellipsis_len
    for text in item["options"].values():
        assert len(text) <= qf._SLIM_OPTION_CHARS + ellipsis_len
    # 且重型输入下整体载荷确实变小（fixture history 8400+ 字符 > 6000 上限）。
    original = _build_followup_action_prompt(
        user_message="为什么", question_context=normalized,
        history_context=_LONG_HISTORY, slim=False,
    )
    _, original_payload = _split_prompt(original)
    assert len(json.dumps(payload, ensure_ascii=False)) < len(
        json.dumps(original_payload, ensure_ascii=False)
    )


# ---------------------------------------------------------------------------
# 第 4 层（B4 守门）：flag 语义 —— 关 = bit-for-bit；开 = 快档模型（未配置则主模型）。
# ---------------------------------------------------------------------------


def _capture_complete(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    async def fake_complete(**kwargs: Any) -> str:
        captured.append(kwargs)
        return _reply("ask_followup")

    monkeypatch.setattr(qf, "complete", fake_complete)
    return captured


def _expected_original_prompt(message: str, context: dict[str, Any], history: str) -> str:
    """独立重建 flag 关时的 prompt 载荷（不走生产 builder 的 slim 分支常量），
    钉住 bit-for-bit 语义——若有人改动非 slim 路径的字节形状，这里必须红。"""
    normalized = normalize_question_followup_context(context)
    assert normalized is not None
    items = normalized.get("items") or [normalized]
    snapshot = [
        {
            "question_index": index,
            "question_id": str(item.get("question_id") or "").strip(),
            "question_type": str(item.get("question_type") or "").strip(),
            "question": str(item.get("question") or "").strip(),
            "options": item.get("options") or {},
            "user_answer": str(item.get("user_answer") or "").strip(),
            "is_correct": item.get("is_correct"),
            "multi_select": bool(item.get("multi_select", False)),
            "has_grading_result": isinstance(item.get("construction_grading_result"), dict)
            and bool(item.get("construction_grading_result")),
            "next_training_signal": (
                (item.get("construction_grading_result") or {}).get("next_training_signal")
                if isinstance(item.get("construction_grading_result"), dict)
                else {}
            ),
        }
        for index, item in enumerate(items, 1)
    ]
    payload = json.dumps(
        {
            "history_context": history.strip(),
            "user_message": message.strip(),
            "active_question_set": snapshot,
        },
        ensure_ascii=False,
    )
    prompt = _build_followup_action_prompt(
        user_message=message, question_context=normalized, history_context=history,
    )
    assert prompt.endswith(payload), "非 slim prompt 载荷字节形状漂移"
    # 独立钉住原版规则 9 的字节形状（slim 的输出收紧契约不得漏进非 slim 路径）。
    assert (
        "9. 输出必须是 JSON 对象，键固定为 intent, confidence, preserve_other_answers, answers, reason。\n\n"
        in prompt
    ), "非 slim prompt 规则 9 字节形状漂移"
    assert "reason 默认给空字符串" not in prompt
    return prompt


def test_flag_unset_is_bit_for_bit_original_prompt_and_primary_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_FLAG, raising=False)
    captured = _capture_complete(monkeypatch)
    asyncio.run(
        interpret_question_followup_action(
            "为什么选B", _LONG_CASE_CTX, history_context=_LONG_HISTORY
        )
    )
    assert len(captured) == 1
    assert captured[0]["prompt"] == _expected_original_prompt(
        "为什么选B", _LONG_CASE_CTX, _LONG_HISTORY
    )
    # 主模型：model=None → complete() 内部用 effective config 的主模型。
    assert captured[0]["model"] is None
    assert captured[0]["max_retries"] == 1


def test_flag_explicit_false_matches_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_FLAG, "false")
    captured = _capture_complete(monkeypatch)
    asyncio.run(
        interpret_question_followup_action(
            "为什么选B", _LONG_CASE_CTX, history_context=_LONG_HISTORY
        )
    )
    assert captured[0]["prompt"] == _expected_original_prompt(
        "为什么选B", _LONG_CASE_CTX, _LONG_HISTORY
    )
    assert captured[0]["model"] is None


def test_flag_on_with_fast_model_uses_fast_tier_accessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(
        "deeptutor.services.llm.config.resolve_fast_tier_model", lambda: "qwen-fast-x"
    )
    captured = _capture_complete(monkeypatch)
    asyncio.run(
        interpret_question_followup_action(
            "为什么选B", _LONG_CASE_CTX, history_context=_LONG_HISTORY
        )
    )
    assert captured[0]["model"] == "qwen-fast-x"
    # B2 同门联动：flag 开 → 瘦身 prompt。
    normalized = normalize_question_followup_context(_LONG_CASE_CTX)
    assert normalized is not None
    assert captured[0]["prompt"] == _build_followup_action_prompt(
        user_message="为什么选B", question_context=normalized,
        history_context=_LONG_HISTORY, slim=True,
    )


def test_flag_on_without_fast_model_keeps_primary_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # W4 accessor 语义：未配置 LLM_FAST_MODEL → "" → fail-open 保持主模型（仅 B2 生效）。
    monkeypatch.setenv(_FLAG, "true")
    monkeypatch.setattr(
        "deeptutor.services.llm.config.resolve_fast_tier_model", lambda: ""
    )
    captured = _capture_complete(monkeypatch)
    asyncio.run(
        interpret_question_followup_action(
            "为什么选B", _LONG_CASE_CTX, history_context=_LONG_HISTORY
        )
    )
    assert captured[0]["model"] is None
    normalized = normalize_question_followup_context(_LONG_CASE_CTX)
    assert normalized is not None
    assert captured[0]["prompt"] == _build_followup_action_prompt(
        user_message="为什么选B", question_context=normalized,
        history_context=_LONG_HISTORY, slim=True,
    )
