"""W5 golden: 可见答案修正链单一管道 ``AgentLoop._finalize_visible_answer`` 的行为保持凭证。

四条 finalize 分支(exact fast path / prefetched authority / fast policy / agent loop)历史上各手抄
一遍 8 级修正链，且 prefetched 分支漂移成 6 级(漏 ``_case_exact_authority_fallback`` 与
``_apply_v1_or_case_fallback``)。T1 把四处收权到单一管道、prefetched 分支统一为全 8 级。

本文件是收权的**行为保持凭证**，分两类断言:

1. **不可变 golden**(T0 先行、T1 后原样通过): prefetched 分支新纳入的 2 个修正器对该分支的
   代表性输入是可证明 no-op(返回 ''，链约定 ``X(...) or final`` 保持原文)，以及 case_grading
   缺 V1 权威时降级模板与 runtime_metadata 副作用键逐一锁定。这些断言 T1 前后一字不改。
2. **结构 golden**(T1 落地后新增): 单一管道按 canonical 9 步顺序驱动 + 四处调用点收敛证据。

全 hermetic: ``AgentLoop.__new__(AgentLoop)`` + monkeypatch，不触网络/LLM/磁盘。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import deeptutor.tutorbot.agent.loop as loop_module
from deeptutor.services.construction_grading.case_output_policy import (
    build_case_grading_diagnostic_only_response,
)
from deeptutor.services.rag.exact_authority import (
    build_exact_authority_response,
    should_force_exact_authority,
)
from deeptutor.tutorbot.agent.loop import AgentLoop

_LOOP_SOURCE_PATH = Path(loop_module.__file__)


def _loop() -> AgentLoop:
    # 修正链修正器都是纯方法/静态助手，无需完整构造。
    return AgentLoop.__new__(AgentLoop)


def _case_study_eq(authoritative_answer: str) -> dict:
    """一个完全覆盖(coverage_ratio=1.0、无 missing)的 case_study 精确题权威。"""

    return {
        "answer_kind": "case_study",
        "question_id": "CASE-W5",
        "coverage_ratio": 1.0,
        "missing_subquestions": [],
        "covered_subquestions": [
            {
                "display_index": "1",
                "prompt": "计算并说明。",
                "authoritative_answer": authoritative_answer,
                "analysis": "依据现行规范。",
            }
        ],
    }


def _mcq_eq() -> dict:
    return {
        "answer_kind": "mcq",
        "question_id": "MCQ-W5",
        "correct_answer": "B",
        "options": [
            {"letter": "A", "text": "错误项一"},
            {"letter": "B", "text": "正确项"},
            {"letter": "C", "text": "错误项二"},
            {"letter": "D", "text": "错误项三"},
        ],
        "analysis": "本题选 B。",
    }


def _free_text_eq() -> dict:
    return {
        "answer_kind": "free_text",
        "question_id": "FT-W5",
        "correct_answer": "应编制专项施工方案并组织专家论证。",
        "analysis": "依据危大工程管理规定。",
    }


def _patch_v1_inert(loop: AgentLoop) -> None:
    """把 V1 case grading 计划钉成 None——scene 非 case_grading 时本就不触 LLM，这里再钉一层，
    保证任何路径都 hermetic(不进 deep_question / factory.complete)。"""

    async def _none(**_kwargs):
        return None

    loop._v1_case_stream_plan = _none  # type: ignore[method-assign]


# --------------------------------------------------------------------------------------
# 不可变 golden #1: prefetched(branch B)新纳入的 _case_exact_authority_fallback 对该分支输入 no-op
# --------------------------------------------------------------------------------------
_NUMBER_SHAPES = [
    pytest.param("本工程总造价为50.00万元", id="wanyuan_50.00"),
    pytest.param("综合费率为3.5%", id="percent_3.5"),
    pytest.param("系数取0.85", id="bare_decimal_0.85"),
]


@pytest.mark.parametrize("authoritative_answer", _NUMBER_SHAPES)
def test_case_exact_authority_fallback_is_noop_for_prefetched_branch(authoritative_answer: str) -> None:
    """branch B 的 final 是 ``build_exact_authority_response`` 的 case_study 渲染(该分支不消费
    user_message，故重建恒等)。统一为全链后新跑的 ``_case_exact_authority_fallback`` 对这类
    完全覆盖、数字齐全的输入返回 ''(no-op)，且链约定 ``(r or final) == final`` 成立。"""

    loop = _loop()
    eq = _case_study_eq(authoritative_answer)
    md = {"question_lifecycle_scene": "", "_prefetched_exact_question": eq}
    final = build_exact_authority_response(eq, user_message="这题标准作答是什么")
    assert final  # 前置: 渲染非空

    result = loop._case_exact_authority_fallback(final, runtime_metadata=md)

    assert result == ""  # 直接 no-op
    assert (result or final) == final  # 链行为保持(唯一真正的不变量)


def test_case_exact_authority_fallback_is_noop_for_mcq_and_free_text() -> None:
    """branch B 也承载 mcq / free_text 精确权威——``_case_exact_authority_fallback`` 的 answer_kind
    门(仅 case_study 生效)对它们立即返回 '',统一入链无副作用。"""

    loop = _loop()
    for eq in (_mcq_eq(), _free_text_eq()):
        md = {"question_lifecycle_scene": "", "_prefetched_exact_question": eq}
        final = build_exact_authority_response(eq, user_message="这题答案是什么")
        result = loop._case_exact_authority_fallback(final, runtime_metadata=md)
        assert result == ""
        assert (result or final) == final


# --------------------------------------------------------------------------------------
# 不可变 golden #2: prefetched(branch B)新纳入的 _apply_v1_or_case_fallback 对该分支输入 no-op
# --------------------------------------------------------------------------------------
def _prefetched_metadata_shapes() -> list:
    shapes = [
        pytest.param(_case_study_eq("本工程总造价为50.00万元"), False, id="case_study_wanyuan"),
        pytest.param(_case_study_eq("综合费率为3.5%"), False, id="case_study_percent"),
        pytest.param(_case_study_eq("系数取0.85"), False, id="case_study_bare_decimal"),
        pytest.param(_mcq_eq(), False, id="mcq"),
        pytest.param(_free_text_eq(), False, id="free_text"),
        pytest.param(_case_study_eq("综合费率为3.5%"), True, id="case_study_rag_degraded"),
    ]
    return shapes


@pytest.mark.parametrize("exact_question, rag_degraded", _prefetched_metadata_shapes())
def test_apply_v1_or_case_fallback_is_noop_for_prefetched_branch(
    exact_question: dict, rag_degraded: bool
) -> None:
    """branch B 一定持有 ``_prefetched_exact_question`` 且 scene 非 case_grading(候选门排除)。
    此时 ``_apply_v1_or_case_fallback``:V1 render 因 scene 非 case_grading 返 ''、no-authority
    降级因 ``_has_any_grading_authority`` 为真返 ''——整体 no-op。"""

    loop = _loop()
    _patch_v1_inert(loop)
    md: dict = {"question_lifecycle_scene": "", "_prefetched_exact_question": exact_question}
    if rag_degraded:
        md["rag_retrieval_degraded"] = True
    final = build_exact_authority_response(exact_question, user_message="这题答案是什么") or "占位答案文本"

    result = asyncio.run(
        loop._apply_v1_or_case_fallback(final, runtime_metadata=md, user_message="这题答案是什么")
    )

    assert result == ""
    assert (result or final) == final
    # branch B 不得被误标成已判分/缺权威。
    assert "v1_case_graded" not in md
    assert md.get("score_authority") in (None, "")


# --------------------------------------------------------------------------------------
# golden #3（P0 2026-07-29 改契约）: case_grading 缺 V1 权威 → 实质诊断保留，模板收回
# 整篇替换权；零产出时模板才兜底。runtime_metadata 副作用键不变。
# --------------------------------------------------------------------------------------
def test_apply_v1_or_case_fallback_case_grading_missing_v1_authority_golden() -> None:
    """scene=case_grading 且 V1 计划返 None(缺权威)时：实质诊断文本（无硬分口径）
    原样保留（返 ''）；副作用键照写。模板只在生成路径零产出时整篇出场——
    「不硬估官方分」(出生使命) ≠「不给任何反馈」(越权，已收回)。"""

    loop = _loop()
    _patch_v1_inert(loop)
    user_message = "【题目】某工程临时用电管理问题。\n【我的作答】共用一个开关箱不妥，应采用专用开关箱。"
    md: dict = {"question_lifecycle_scene": "case_grading", "user_id": "qa_loop_w5"}

    result = asyncio.run(
        loop._apply_v1_or_case_fallback("模型原始诊断文本", runtime_metadata=md, user_message=user_message)
    )

    assert result == ""  # 实质诊断保留（链约定 '' = 保持原文）
    assert md["v1_case_graded"] is False
    assert md["score_authority"] == "missing_v1_authority"


def test_case_grading_missing_authority_empty_content_still_gets_template() -> None:
    """零产出兜底：生成路径什么都没给时，模板保留出生使命整篇出场。"""

    loop = _loop()
    _patch_v1_inert(loop)
    user_message = "【题目】某工程临时用电管理问题。\n【我的作答】共用一个开关箱不妥。"
    md: dict = {"question_lifecycle_scene": "case_grading", "user_id": "qa_loop_w5"}

    result = loop._case_grading_no_authority_score_fallback(
        "", runtime_metadata=md, user_message=user_message
    )

    assert result == build_case_grading_diagnostic_only_response(user_message)


def test_case_grading_missing_authority_hard_score_gets_disclaimer_append() -> None:
    """硬分口径降级：含官方分声称的实质诊断 → 追加评分口径免责声明，正文保留。"""

    loop = _loop()
    _patch_v1_inert(loop)
    md: dict = {"question_lifecycle_scene": "case_grading", "user_id": "qa_loop_w5"}
    content = "你的作答得8分，命中4个采分点，扣2分。"

    result = loop._case_grading_no_authority_score_fallback(
        content, runtime_metadata=md, user_message="【题目】题\n【我的作答】答"
    )

    assert result.startswith(content)
    assert "评分口径说明" in result and "不构成官方阅卷得分" in result
    assert md["grading_engine_version"] == "luban_case_rubric_v1"


# --------------------------------------------------------------------------------------
# 结构 golden(T1 后新增): 单一管道顺序 + 四处调用点收敛
# --------------------------------------------------------------------------------------
_CANONICAL_ORDER = [
    "strip_leading_meta_narration",
    "normalize_anchor_terms",
    "case_exact_authority",
    "apply_v1_or_case",
    # 口诀权威收权（2026-08-01，r6 宣传门 A3）：必须排在 apply_v1_or_case **之后** ——
    # V1 判分链自己已按同一权威渲染过口诀，本层只管它没接管的自由作文道。
    "case_mnemonic_authority",
    "degraded_exact_claim",
    "degraded_mcq",
    "content_truth",
    "guard_output",
]


class _GuardResult:
    def __init__(self, content: str) -> None:
        self.content = content
        self.blocked = False


def _install_recording_correctors(monkeypatch: pytest.MonkeyPatch, loop: AgentLoop) -> list[str]:
    """把 8 个修正器换成记录调用名并返回 ''(保持原文)的桩;guard 返回 content='' 的对象。"""

    calls: list[str] = []

    def _rec(label: str):
        def _fn(*_args, **_kwargs):
            calls.append(label)
            return ""

        return _fn

    loop._strip_leading_meta_narration = _rec("strip_leading_meta_narration")  # type: ignore[method-assign]
    monkeypatch.setattr(loop_module, "normalize_anchor_terms_in_response", _rec("normalize_anchor_terms"))

    async def _apply(*_args, **_kwargs):
        calls.append("apply_v1_or_case")
        return ""

    loop._case_exact_authority_fallback = _rec("case_exact_authority")  # type: ignore[method-assign]
    loop._apply_v1_or_case_fallback = _apply  # type: ignore[method-assign]
    loop._case_mnemonic_authority_guard = _rec("case_mnemonic_authority")  # type: ignore[method-assign]
    loop._degraded_exact_answer_claim_response = _rec("degraded_exact_claim")  # type: ignore[method-assign]
    loop._degraded_mcq_grading_response = _rec("degraded_mcq")  # type: ignore[method-assign]
    loop._content_truth_guard = _rec("content_truth")  # type: ignore[method-assign]

    def _guard(_content):
        calls.append("guard_output")
        return _GuardResult("")

    monkeypatch.setattr(loop_module, "guard_tutorbot_output", _guard)
    return calls


@pytest.mark.parametrize(
    "finalize_path",
    ["exact_fast_path", "prefetched_authority", "fast_policy", "agent_loop"],
)
def test_finalize_visible_answer_runs_canonical_eight_step_order(
    monkeypatch: pytest.MonkeyPatch, finalize_path: str
) -> None:
    """T1 收权凭证: 四条 finalize 分支全部经同一 ``_finalize_visible_answer`` 管道,按 canonical
    9 步顺序驱动(prefetched 不再是漂移的 6 步)。finalize_path 仅观测标签,不改变链行为。"""

    loop = _loop()
    calls = _install_recording_correctors(monkeypatch, loop)

    out = asyncio.run(
        loop._finalize_visible_answer(
            "定稿前文本",
            user_message="用户问题",
            runtime_metadata={"question_lifecycle_scene": ""},
            finalize_path=finalize_path,
        )
    )

    assert calls == _CANONICAL_ORDER
    # 所有修正器返回 ''(保持原文)+ guard content='' → 管道回落到入参 final_content。
    assert out == "定稿前文本"


def test_correction_chain_has_single_call_site_in_loop_source() -> None:
    """收权 tripwire: 修正链修正器只许在单一管道内出现一次,四处 finalize 分支只留一行调用。
    防止未来分支再内联复刻 9 级链(补丁螺旋回归)。"""

    source = _LOOP_SOURCE_PATH.read_text(encoding="utf-8")
    # 这些修正器唯一的调用点就是单一管道——四处 finalize 分支不再各内联一遍。
    assert source.count("normalize_anchor_terms_in_response(") == 1
    assert source.count("self._apply_v1_or_case_fallback(") == 1
    assert source.count("self._degraded_exact_answer_claim_response(") == 1
    assert source.count("self._degraded_mcq_grading_response(") == 1
    assert source.count("self._content_truth_guard(") == 1
    assert source.count("self._case_mnemonic_authority_guard(") == 1
    assert source.count("self._strip_leading_meta_narration(") == 1
    # _case_exact_authority_fallback 有 2 处:管道内 1 处 + ``_run_agent_loop`` 内层 seam 1 处
    # (line ~2326,非 finalize 分支,设计明确冻结不纳入管道)。
    assert source.count("self._case_exact_authority_fallback(") == 2
    # 4 处 finalize 分支各一行调用(方法定义 ``def _finalize_visible_answer(`` 单独计)。
    assert source.count("self._finalize_visible_answer(") == 4
    assert source.count("def _finalize_visible_answer(") == 1


# --------------------------------------------------------------------------------------
# 反事实不变量(F3 加固): prefetched-authority(branch B)结构上不可能携带 case_study 形状
# --------------------------------------------------------------------------------------
def _scene_clear_prefetched_md(exact_question: dict) -> dict:
    """branch B 的典型 runtime_metadata: 持 _prefetched_exact_question 且 scene 非 case_grading
    (候选门对 case_grading 显式排除),未被 block、非 review、无 suppress-on-generate。"""

    return {"question_lifecycle_scene": "", "_prefetched_exact_question": exact_question}


def test_prefetched_branch_b_structurally_cannot_carry_case_study() -> None:
    """把『branch B 永不携带 case_study』从巧合升级为显式锁定的反事实不变量。

    case_study 命中是**内容权威**而非**表达权威**——必须交给最终合成层渲染,绝不能作为
    branch B 的即答精确权威直出。两层证据:

    1. 语义闸 ``should_force_exact_authority``: case_study 恒 False,mcq/free_text 恒 True。
    2. 结构闸 ``_prefetched_exact_authority_candidate``: 对 case_study 返回 None(拿不到候选),
       同一选择器对 mcq/free_text 却产出候选——证明 None 是 case_study 专属排除,而非选择器
       对一切输入都返回 None 的平凡真(阳性对照,反证)。
    """

    # 1) 语义闸:should_force_exact_authority 的 answer_kind 边界。
    assert should_force_exact_authority(_case_study_eq("综合费率为3.5%")) is False
    assert should_force_exact_authority(_mcq_eq()) is True
    assert should_force_exact_authority(_free_text_eq()) is True

    # 2) 结构闸:候选选择器对 case_study 排除 → branch B 结构上拿不到 case_study。
    assert (
        AgentLoop._prefetched_exact_authority_candidate(
            _scene_clear_prefetched_md(_case_study_eq("系数取0.85")),
            current_message="这题答案是什么",
        )
        is None
    )

    # 反证(阳性对照):同一选择器对 mcq / free_text 确实产出候选,
    # 证明上面的 None 是 case_study 专属排除,而非平凡的『恒 None』。
    assert (
        AgentLoop._prefetched_exact_authority_candidate(
            _scene_clear_prefetched_md(_mcq_eq()),
            current_message="这题答案是什么",
        )
        is not None
    )
    assert (
        AgentLoop._prefetched_exact_authority_candidate(
            _scene_clear_prefetched_md(_free_text_eq()),
            current_message="这题答案是什么",
        )
        is not None
    )


# --------------------------------------------------------------------------------------
# 开头独白剥离器(确定性低成本保底;主修复在 prompt 层)
# --------------------------------------------------------------------------------------
def test_strip_leading_meta_narration_strips_incident_prefix() -> None:
    """生产事故 trace 19912c2d:终态以两句内心独白开头。剥离后正文以答案开头,并打遥测标记。"""
    md: dict = {}
    out = AgentLoop._strip_leading_meta_narration(
        "现在我有足够的知识库证据来回答第3题。让我来组织完整回答。\n\n## 第3题：临时用水管理中的不妥及正确做法",
        runtime_metadata=md,
    )
    assert out.startswith("## 第3题")
    assert md["leading_meta_narration_stripped"] is True


def test_strip_leading_meta_narration_keeps_legitimate_openings() -> None:
    for text in (
        "现在我们来计算管径。d=93.4mm，选DN100。",
        "我先给结论：不妥之处有三处。第一，水管未加套管。",
        "## 第1问：答案主体",
    ):
        assert AgentLoop._strip_leading_meta_narration(text, runtime_metadata={}) == ""


def test_strip_leading_meta_narration_requires_substantive_remainder() -> None:
    """独白后没有实质正文时保持原文(返 ''),不许剥成空答案。"""
    assert AgentLoop._strip_leading_meta_narration("让我来整理一下采分点。", runtime_metadata={}) == ""


def test_strip_leading_meta_narration_never_eats_answer_bearing_first_sentence() -> None:
    """Review B1 反例:命中模式的首句若携带答案负载,一律保持原文——剥离器只吃纯独白,不吃结论。"""
    for text in (
        "我检索到的信息显示，答案选B。理由是水泥强度等级不符。",
        "我掌握的资料表明正确答案是ACD。因为脚手架连墙件设置不符合规范。",
        "我整理了三处不妥的信息：不妥一是坡度偏小。不妥二是消火栓间距超限。",
    ):
        assert AgentLoop._strip_leading_meta_narration(text, runtime_metadata={}) == ""


def test_strip_leading_meta_narration_strips_c3_retrieval_monologue() -> None:
    """2026-08-01 C3 重放实证形态（非批改链）：服务端落库正文逐字以这句独白开头。

    见 `docs/原始数据/数据盘点/2026-08-01-历史错误逐案重放回归.md` §7.2。族1/族2 的动词集
    都够不着「我注意到…让我补充检索…」，这条钉死族3。
    """
    md: dict = {}
    out = AgentLoop._strip_leading_meta_narration(
        "我注意到检索证据中未直接给出表6.0.15的具体数值和甲醛限值，让我补充检索这两个关键参数。"
        "\n\n根据《民用建筑工程室内环境污染控制标准》GB50325-2020，标准间的甲醛限值为 "
        "0.07mg/m³；检测点数按房间使用面积确定，100~500m² 时不少于 3 个点。",
        runtime_metadata=md,
    )
    assert out.startswith("根据《民用建筑工程室内环境污染控制标准》")
    assert "我注意到" not in out
    assert md["leading_meta_narration_stripped"] is True


def test_strip_leading_meta_narration_keeps_observation_about_the_learner() -> None:
    """族3 的危险边界：观察句是**讲评**（谈学生作答）时一律保持原文，只有同句里同时出现
    证据侧名词 + 自述取证动作才算独白。"""
    for text in (
        "我注意到你的第3问漏了一个采分点，这里补一下。\n\n专项施工方案必须经过专家论证。",
        "我发现你把安全网的层间距记成了 15m。\n\n正确做法是每隔 10m 设置一道水平安全网。",
        "我注意到这道题的证据链其实很清楚。\n\n施工单位应当在开工前编制专项方案并报监理审批。",
    ):
        assert AgentLoop._strip_leading_meta_narration(text, runtime_metadata={}) == ""


def test_case_grading_disclaimer_is_idempotent_across_double_seam() -> None:
    """Review B-1 回归：诊断先后过内 seam 与外 seam，免责声明只许追加一次
    ——声明自含"阅卷"会命中 demote 正则，无幂等闸则主线确定性双写。"""

    loop = _loop()
    md: dict = {"question_lifecycle_scene": "case_grading"}
    content = "你的作答得8分，命中4个采分点，扣2分。"

    first = loop._case_grading_no_authority_score_fallback(
        content, runtime_metadata=md, user_message="【题目】题\n【我的作答】答"
    )
    assert first.count("评分口径说明") == 1

    second = loop._case_grading_no_authority_score_fallback(
        first, runtime_metadata=md, user_message="【题目】题\n【我的作答】答"
    )
    assert second == ""  # 幂等：已带声明的文本原样保持
    assert ((second or first)).count("评分口径说明") == 1
