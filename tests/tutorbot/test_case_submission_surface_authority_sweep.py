"""尺与面收权清剿（2026-08-01）——判分链上剩余病灶的可证伪回归。

病理（今天五张脸的共性）：
- **病 A（第二把尺子）**：同一事实被多套独立实现测量。
- **病 B（错误的面）**：消费者拿组装后的 ``current_message``（含 ``[History Context]`` /
  ``### 局部工作记忆投影`` 等跨轮包装，随账号历史逐轮变化）当"学生这轮的真实提交"用。

权威：``AgentLoop._case_submission_surface``（提交面）、
``_extract_case_question_titles_for_scope``（小问计数）。

每个用例都构造"包装污染 / 行内数字污染"输入——**修前红、修后绿**。
测绘清单见 ``docs/原始数据/数据盘点/2026-08-01-尺与面收权清剿测绘.md``。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from deeptutor.tutorbot.agent.loop import AgentLoop
from deeptutor.tutorbot.bus.events import InboundMessage
from deeptutor.tutorbot.session.manager import Session


# 干净的整卷案例提交（学生这轮真的发了什么）。
CLEAN_CASE_PASTE = (
    "【背景资料】某工程施工过程描述，事件一至事件四。" * 6
    + "\n【问题】1. 指出事件一中的不妥之处并说明理由？\n"
    "2. 写出正确做法？\n3. 写出该构造的名称？\n4. 补充工艺流程？\n"
    "我的答案：\n1. 不妥之处是未编制专项方案。\n2. 应先编制后审批。\n"
    "3. 后浇带。\n4. 测量放线—钢筋绑扎—浇筑。"
)

# turn_runtime 的 context pack 组装出来的样子：跨轮包装里含"下一题"与旧轮字母声明。
# 这两个 marker 都不是学生这轮说的，却会被子串判据当成本轮意图。
WRAPPER_PREFIX = (
    "## 参考证据\n上一题解析：本题答案是 B，注意区分。做完这道我们看下一题。\n\n"
    "### 局部工作记忆投影\n学员上轮问「我选ABCD 对吗」，已批改。\n\n"
    "## 当前用户问题\n"
)
WRAPPED_CASE_PASTE = WRAPPER_PREFIX + CLEAN_CASE_PASTE


def _md(**extra: Any) -> dict[str, Any]:
    md: dict[str, Any] = {
        "question_lifecycle_scene": "case_grading",
        "raw_user_message": CLEAN_CASE_PASTE,
    }
    md.update(extra)
    return md


# ---------------------------------------------------------------------------
# 病 A：`_case_grading_live_preview_text` 的 fallback 第二把尺子
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "paste"),
    [
        # 权威 `_extract_case_question_titles` 的序号闸是 `[1-9]\d{0,1}` 且 idx<=30；
        # 删掉的 fallback 用的是裸 `\d+`，两把尺子在这两族输入上确定性分叉。
        ("index_above_30", "【问题】\n31. 指出不妥之处？\n32. 写出正确做法？\n33. 补充流程？\n我的答案：\n甲。"),
        ("leading_zero", "【问题】\n01. 指出不妥？\n02. 正确做法？\n我的答案：\n甲。"),
    ],
)
def test_narration_count_has_no_second_ruler_fallback(name: str, paste: str) -> None:
    """A1：#641 收权后残留的 fallback findall 已删除。

    实证分叉（非推断）：这两族题面上，判分分母权威返回 **0** 个小问，而删掉的 fallback
    正则返回 3 / 2 个——开场白会报一个**判分分母根本不会用**的数字，正是 #641 要治的
    「同一事实两把尺子」从 fallback 分支复发。

    权威数不出来时**不报数**：报一个错数比不报数坏。
    """
    from deeptutor.tutorbot.agent.loop import _extract_case_question_titles_for_scope

    stem, _answer = AgentLoop._split_case_grading_submission(paste)
    assert _extract_case_question_titles_for_scope(stem) == {}, (
        f"用例失效：{name} 的题面必须是权威数不出小问的那一族"
    )
    text = AgentLoop._case_grading_live_preview_text(paste)
    assert "个小问" not in text, f"权威数不出小问时不得用第二把尺子兜底报数：{text}"
    assert "逐采分点批改" in text


# ---------------------------------------------------------------------------
# 病 B1/B2：出题意图判据的面
# ---------------------------------------------------------------------------


class _FakeSkills:
    def list_skills(self, filter_unavailable: bool = False) -> list[dict[str, Any]]:
        return []


class _FakeContext:
    def __init__(self) -> None:
        self.skills = _FakeSkills()

    def build_messages(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"role": "user", "content": "x"}]

    def add_assistant_message(
        self, messages: list[dict[str, Any]], content: str
    ) -> list[dict[str, Any]]:
        return list(messages) + [{"role": "assistant", "content": content}]


def _loop() -> AgentLoop:
    return AgentLoop.__new__(AgentLoop)


@pytest.mark.asyncio
async def test_direct_grading_not_kicked_out_by_wrapper_practice_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B1（task#23）：包装里注入的"下一题"不得把整卷提交踢出直批判分链。

    ``looks_like_practice_generation_request`` 是纯子串测试；喂组装面时，参考证据里
    上一题解析的"下一题"就足以让整卷判分回落通用链（学生看到的是"请把标准答案发来"
    之类的无权威模板，而不是判分）。
    """
    loop = _loop()
    loop.context = _FakeContext()
    loop.memory_consolidator = type(
        "NoopMemory",
        (),
        {"maybe_consolidate_by_tokens": lambda self, _session: asyncio.sleep(0)},
    )()
    loop.sessions = type("NoopSessions", (), {"save": lambda self, _session: None})()

    async def _fake_v1_case_stream_plan(*, runtime_metadata, user_message, **_kwargs):
        runtime_metadata["_v1_case_graded"] = True
        runtime_metadata["v1_case_graded"] = True
        runtime_metadata["score_authority"] = "rubric_scored_v1"
        score_first = "## 批改结论\n**得分预估：** 6 / 10 分。"
        return {
            "mode": "score_first_sealed_blocks",
            "score_first": score_first,
            "sealed_blocks": [],
            "final_text": score_first,
            "presentation": None,
        }

    async def _agent_loop_should_not_run(*_args: Any, **_kwargs: Any):
        raise AssertionError("整卷案例提交必须留在直批链，不得回落通用 agent loop")

    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_v1_case_stream_plan)
    monkeypatch.setattr(loop, "_run_agent_loop", _agent_loop_should_not_run)

    md = _md()
    session = Session(key="web:surface-sweep")
    msg = InboundMessage(
        channel="web",
        sender_id="user",
        chat_id="surface-sweep",
        content=WRAPPED_CASE_PASTE,
        metadata=md,
    )

    out = await loop._run_case_grading_direct(
        msg=msg,
        session=session,
        history=[],
        current_message=WRAPPED_CASE_PASTE,
        runtime_metadata=md,
        runtime_instruction="",
    )

    assert out is not None, "包装里的『下一题』把整卷判分踢出了直批链（病 B1）"
    assert out.content.startswith("## 批改结论")


def test_no_authority_fallback_not_skipped_by_wrapper_practice_marker() -> None:
    """B2（B1 的镜像）：finalize 链上的判分降级兜底不得被包装里的"下一题"静默跳过。

    四个 ``_finalize_visible_answer`` 调用点一律传组装后的 ``current_message``；
    该函数看错面时，无权威轮既不判分也不给降级说明，学生拿到空/裸文案。
    """
    md = _md()
    out = AgentLoop._case_grading_no_authority_score_fallback(
        "",
        runtime_metadata=md,
        user_message=WRAPPED_CASE_PASTE,
    )
    assert out, "包装里的『下一题』让无权威降级兜底被跳过（病 B2）"
    assert md.get("score_authority") == "missing_v1_authority"


def test_no_authority_fallback_still_yields_to_real_practice_request() -> None:
    """收权不得一刀切：学生**这轮真的**在要新题时，兜底模板仍必须让路（S4 反向不变量）。"""
    md = {"question_lifecycle_scene": "case_grading", "raw_user_message": "再出一道新题"}
    out = AgentLoop._case_grading_no_authority_score_fallback(
        "",
        runtime_metadata=md,
        user_message="再出一道新题",
    )
    assert out == "", "真实出题请求不得被判分兜底模板夺走（死锁回归）"


# ---------------------------------------------------------------------------
# 病 B3：作答标记探针的面
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_marker_count_measures_submission_not_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B3：``case_probe_marker_count`` 是"同题面不同作答走不同通道"的判别位。

    面不对＝观测说谎：包装里旧轮作答的标记会被数进本轮，判别位失去分组能力。
    """
    from deeptutor.services.construction_grading.case_output_policy import (
        CASE_ANSWER_MARKER_PATTERN,
    )
    import re as _re

    wrapper_polluted = (
        "## 参考证据\n上一轮学员提交如下。\n"
        "我的答案：旧作答一。\n"
        "答案：旧作答二。\n\n"
        "## 当前用户问题\n" + CLEAN_CASE_PASTE
    )
    surface = AgentLoop._case_submission_surface(
        {"raw_user_message": CLEAN_CASE_PASTE}, wrapper_polluted
    )
    surface_markers = len(
        _re.findall(CASE_ANSWER_MARKER_PATTERN, surface, flags=_re.IGNORECASE)
    )
    wrapped_markers = len(
        _re.findall(CASE_ANSWER_MARKER_PATTERN, wrapper_polluted, flags=_re.IGNORECASE)
    )
    assert wrapped_markers > surface_markers, "用例本身失效：包装必须真的引入额外标记"

    loop = _loop()
    loop.context = _FakeContext()
    loop.memory_consolidator = type(
        "NoopMemory",
        (),
        {"maybe_consolidate_by_tokens": lambda self, _session: asyncio.sleep(0)},
    )()
    loop.sessions = type("NoopSessions", (), {"save": lambda self, _session: None})()

    async def _fake_prefetch(*, initial_messages, **_kwargs):
        return initial_messages

    async def _fake_v1_case_stream_plan(*, runtime_metadata, user_message, **_kwargs):
        runtime_metadata["_v1_case_graded"] = True
        return {
            "mode": "score_first_sealed_blocks",
            "score_first": "## 批改结论",
            "sealed_blocks": [],
            "final_text": "## 批改结论",
            "presentation": None,
        }

    monkeypatch.setattr(loop, "_maybe_prefetch_grounded_rag", _fake_prefetch)
    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_v1_case_stream_plan)
    monkeypatch.setattr(loop, "_run_agent_loop", _fake_v1_case_stream_plan)

    md = _md(default_kb="luban")
    session = Session(key="web:probe")
    msg = InboundMessage(
        channel="web",
        sender_id="user",
        chat_id="probe",
        content=wrapper_polluted,
        metadata=md,
    )
    await loop._run_case_grading_direct(
        msg=msg,
        session=session,
        history=[],
        current_message=wrapper_polluted,
        runtime_metadata=md,
        runtime_instruction="",
    )
    assert md.get("case_probe_marker_count") == surface_markers, (
        "探针数的是组装面而不是学生提交面（病 B3）"
    )


# ---------------------------------------------------------------------------
# 病 B4/B5/B6：降级期字母声明族的面
# ---------------------------------------------------------------------------


_DEGRADED_MD_BASE = {
    "rag_retrieval_degraded": True,
    "question_lifecycle_scene": "case_grading",
}
# 旧轮字母声明藏在包装里；学生这轮发的是整卷案例题，一个字母都没声明。
_WRAPPED_STALE_CLAIM = (
    "## 参考证据\n这道真题的标准答案是 B，学员上轮问「我选 A、C 对吗」。\n\n"
    "## 当前用户问题\n" + CLEAN_CASE_PASTE
)


def test_degraded_exact_answer_guard_ignores_stale_wrapper_claim() -> None:
    """B4：降级期"不能确认或否定 X"的主语是学生**这轮**声明的字母。

    看组装面时，包装里上一题的"我选 A、C"会被抽成本轮 claim，bot 对着上一题的字母
    吐拒答——学生这轮根本没提字母。
    """
    md = dict(_DEGRADED_MD_BASE, raw_user_message=CLEAN_CASE_PASTE)
    should_guard, claim = AgentLoop._should_guard_degraded_exact_answer_claim(
        user_message=_WRAPPED_STALE_CLAIM,
        final_content="这道题答案不是 A。",
        runtime_metadata=md,
    )
    assert not should_guard, f"包装里的旧字母声明被当成本轮 claim（病 B4）：{claim}"


def test_degraded_exact_answer_guard_still_fires_on_real_claim() -> None:
    """反向不变量：学生这轮**真的**声明字母时，降级闸必须照常拦（收权不得放松安全语义）。"""
    real = "这道真题我选 A、C，标准答案是不是 AC？"
    md = dict(_DEGRADED_MD_BASE, raw_user_message=real)
    should_guard, claim = AgentLoop._should_guard_degraded_exact_answer_claim(
        user_message=real,
        final_content="不对，答案不是 AC。",
        runtime_metadata=md,
    )
    assert should_guard and claim == "AC", (claim, should_guard)


def test_degraded_mcq_grading_response_ignores_stale_wrapper_claim() -> None:
    """B5：降级期 MCQ 批改罐头同族——面必须是学生这轮真实提交。"""
    md = dict(_DEGRADED_MD_BASE, raw_user_message=CLEAN_CASE_PASTE)
    out = AgentLoop._degraded_mcq_grading_response(
        user_message=_WRAPPED_STALE_CLAIM,
        final_content="",
        runtime_metadata=md,
    )
    assert out == "", "包装里的旧 MCQ 提交把本轮案例题判成了 MCQ 批改（病 B5）"
    assert "degraded_mcq_grading_guard_applied" not in md


def test_suppress_stream_gate_ignores_stale_wrapper_claim() -> None:
    """B6：抑制流式与否的主语=学生这轮真实提交。

    注意本用例把 scene 置成非 case_grading——``_should_suppress_stream_for_degraded_answer``
    的第一条分支（case_grading 且无判分权威即抑制）是**另一条独立且正确的**规则，
    不能盖住我们要证伪的字母声明分支。
    """
    md = {
        "rag_retrieval_degraded": True,
        "question_lifecycle_scene": "explain",
        "raw_user_message": CLEAN_CASE_PASTE,
    }
    assert not AgentLoop._should_suppress_stream_for_degraded_answer(
        user_message=_WRAPPED_STALE_CLAIM,
        runtime_metadata=md,
    ), "包装里的旧字母声明让本轮吐字被误抑制（病 B6）"


def test_suppress_stream_gate_still_fires_on_real_claim() -> None:
    """反向不变量：真实字母声明轮仍必须抑制流式。"""
    real = "这道真题我选 A、C，标准答案是不是 AC？"
    assert AgentLoop._should_suppress_stream_for_degraded_answer(
        user_message=real,
        runtime_metadata={
            "rag_retrieval_degraded": True,
            "question_lifecycle_scene": "explain",
            "raw_user_message": real,
        },
    )
