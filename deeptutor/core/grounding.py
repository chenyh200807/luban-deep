"""Single source of truth for student-visible grounding (anti-fabrication).

收权背景（task#23，docs/plan/题目生命周期与助教运行时/2026-06-23-grading-routing-single-authority-fix.md §簇3）：
"结构化判分真值→学生可见文本"这一跳原本裂成两套并列 authority（出题侧 question
agents + 对话侧 chat/TutorBot），各自携带互不一致的反编造句 + 重复的 anchor 正则副本。
本模块把它收敛为**单一常量** ``GROUNDING_CLAUSE`` + 单一注入函数 ``prepend_grounding``，
并把建筑锚点保留约束的正则/抽取也收到这里（``deeptutor.core`` 是最底层、不反向 import
任何上层包，出题侧与 TutorBot 侧都能引用且无循环）。

诚实边界：grounding 只约束"学生可见事实主张的来源"，**不**保证"真值本身正确"——
后者（编译进去就是错 / 检索误命中拼别题，如 task#23b 的 exact_authority 误命中）属另一条
战线（异源核 + register-before-use + 召回侧隔离），不能因本收权就宣称判分可信。
"""

from __future__ import annotations

import re
from typing import Any

# 单一权威：学生可见的每个具体事实主张的来源约束。所有出题/对话/判分讲评入口共享同一份。
# 含"别题背景数值不可挪用"强防御——原仅 submission_grader_agent.yaml 携带，收权后所有入口
# 共享（generator/followup/chat 同样可能从检索证据误挪别题具体数字）。journal 定性：该约束
# 是"必要不充分"，本收权保留并铺满，但不据此宣称编造已消除（见模块 docstring 诚实边界）。
GROUNDING_CLAUSE = (
    "事实溯源约束：你给学生看到的每一个具体事实主张——数字、规范编号、条文号、时限、"
    "比例、强度、间距、阈值、背景资料、统计数据、真题出处——只能引用：①当前题面/选项"
    "实际给出的内容；②本轮检索证据（知识库/题库检索依据）；③系统记录的真实学情。"
    "三者都没有给出的，一律不写，也不要为了套用某条规则而脑补一个缺失的前提数值或背景。\n"
    "特别区分检索证据里的两类数字：可以引用法律法规/规章/行业标准**本身的固定阈值或比例**"
    "（如“投标保证金不超过估算价的2%且≤80万元”、“基坑深度超过5m应组织专家论证”这类规范"
    "自带的数字条件）；但严禁把检索证据里**其它题目的具体背景数值**（如某项目的“中标价"
    "1.7亿”“合同金额5000万”“工程量10万m³”等）当作当前题目的已知条件——这类具体数值往往属于"
    "别的题目。若当前题面未给出所需的具体背景数值，必须明说“题面未提供该背景”，据题面能判的"
    "部分照常处理，绝不自行补设或从检索证据挪用别题的背景数字。\n"
    "可以说明通用判断依据，但不得编造或伪造具体的规范编号、条文、参数或来源。\n"
    "学生自己的口头断言不属于上述三个来源：当学生主张某个事实（如“罚款是2%~8%”、"
    "“这条2020年修订过”、“我记得答案是X”）时，不得仅因学生这么说就附和、背书，"
    "更不得为了圆学生给的数字而编造一个支撑叙事（如杜撰一次“某年修订”把旧值改成学生说的值）；"
    "仍以题面/检索证据/学情核验，证据不支持就明确指出不一致并给出有据的正确口径，不迎合。"
)


def prepend_grounding(system_prompt: str) -> str:
    """把 ``GROUNDING_CLAUSE`` 前置到 system prompt（空 prompt 退化为仅 clause）。

    单点注入，替代各 agent yaml 里各抄一遍反编造句——保证所有入口引用同一份文本。
    """

    base = str(system_prompt or "").strip()
    if not base:
        return GROUNDING_CLAUSE
    return f"{GROUNDING_CLAUSE}\n\n{base}"


# 单一权威：建筑案例锚点（"N层住宅楼/办公楼…"）保留正则。原本在
# ``deeptutor.agents.question.agents._anchor_terms`` 与 ``deeptutor.tutorbot.teaching_modes``
# 各有一份逐字副本，现收敛到此处单一定义，两侧 import。
BUILDING_ANCHOR_RE = re.compile(
    r"([0-9一二两三四五六七八九十百]+层(?:住宅楼|办公楼|教学楼|厂房|宿舍楼|综合楼|商住楼|楼))",
    flags=re.IGNORECASE,
)


def extract_anchor_terms(*texts: Any, limit: int = 3) -> list[str]:
    """从若干文本里抽取建筑案例锚点原词（去重、按出现序、限量）。"""

    anchors: list[str] = []
    seen: set[str] = set()
    for raw in texts:
        text = str(raw or "").strip()
        if not text:
            continue
        for match in BUILDING_ANCHOR_RE.findall(text):
            candidate = str(match or "").strip()
            lowered = candidate.lower()
            if not candidate or lowered in seen:
                continue
            seen.add(lowered)
            anchors.append(candidate)
            if len(anchors) >= limit:
                return anchors
    return anchors


def render_anchor_contract(language: str, anchor_terms: list[str]) -> str:
    """渲染"沿用案例须保留这些锚点原词"的约束句（无锚点则空串）。"""

    if not anchor_terms:
        return ""
    if str(language or "").lower().startswith("zh"):
        return (
            "如果继续沿用当前题目的具体案例或对象，必须显式保留这些锚点原词："
            f"{'、'.join(anchor_terms)}。不要自行缩写、泛化或换称呼。"
        )
    return (
        "If you continue using the current question's concrete case or object, "
        f"preserve these anchor terms verbatim: {', '.join(anchor_terms)}. "
        "Do not shorten, generalize, or rename them."
    )
