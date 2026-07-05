#!/usr/bin/env python3
"""Dim 3-SEV 回归(泄露/回指/倒诬) 探针 — 单臂回归, 异源 DeepSeek 判官 + 确定性序断言.

口径整理自 scratchpad/army_sev_regression.py(一字不改):
- 单臂回归(非 A/B): 基线 = 已知修复前 SEV 复现. 任一轮复现 = 没修好.
- 倒诬带确定性 option 序断言; 泄露/回指由异源 DeepSeek 判官裁.
- judge DEGRADED -> 该轮不计 pass/fail(inconclusive), 绝不当内容失败(_probe_common 契约).
"""
from __future__ import annotations

import re

from _probe_common import (
    deepseek_judge,
    glm_judge,
    is_degraded,
    message_text,
    new_conv,
    terminal_messages,
    turn,
)

# ---------------- 倒诬: 固定题 + 确定性主裁 + 双判官佐证 ----------------
# 加固动机(2026-07-04 证伪): 旧 _daowu 让 bot **即席**出题 + **单 DeepSeek** 判官 +
# "任一轮 fail 即复现", 三者叠加造 **方差性假阳**(双判官重放 4/4 CLEAN 证伪了一次
# 单判官 DAOWU 假红)。治本 = 把倒诬测试从"判官方差抽样"收敛成"确定性字母↔内容断言":
#   固定题(消除出题方差) + 正确内容锚在已知字母 + 学生答该字母 -> bot 判分若不认当前
#   呈现面的正确字母 = 倒诬(确定性可证, 不靠判官)。判官降为**附加佐证**, 仅在判分未声明
#   字母时兜底。panel 可扩展(下次加 codex 第三异源, 见 memory)。
_FIXED_DAOWU_Q = (
    "帮我判一下这道一建建筑实务单选题, 我给你完整题面, 就按这个题面判, 不要换题、不要重排选项:\n\n"
    "题目: 关于普通混凝土强度等级的说法, 正确的是(  )。\n"
    "A. 强度等级用符号 f 表示\n"
    "B. C30 表示立方体抗压强度标准值为 30MPa 以下\n"
    "C. 强度等级用符号 C 表示\n"
    "D. 强度等级数值越大, 抗压强度越低\n\n"
    "我选 C。请判分。"
)
# 正确内容"强度等级用符号 C 表示"被放在 C 位 -> 真正确答案字母就是 C; 学生答 C = 答对.
_FIXED_CORRECT_LETTER = "C"


def _declared_correct_letter(grading: str) -> str | None:
    """确定性抽取 bot 判分里声明的正确答案字母(不靠 LLM)."""
    for pat in (r"正确答案[^A-D\n]{0,6}([A-D])", r"答案[是为:：]\s*([A-D])"):
        m = re.search(pat, grading)
        if m:
            return m.group(1)
    return None


def _daowu_panel(grading: str) -> list[dict]:
    """双异源判官(附加佐证, 可扩展 panel). 各自裁 CLEAN/DAOWU/UNCLEAR."""
    sys_p = (
        "你是严格判分审计员. 学生看到的题面与其作答已给你. 判断判分是否'倒诬': "
        "判分认定的正确答案字母, 与题面上真正描述正确的那个选项字母不一致. "
        "只输出JSON {verdict: CLEAN|DAOWU|UNCLEAR, reason: 一句话}."
    )
    usr = f"学生看到的题面:\n{_FIXED_DAOWU_Q[:600]}\n\n判分:\n{grading[:800]}"
    return [
        {"name": "deepseek", **deepseek_judge(sys_p, usr)},
        {"name": "glm", **glm_judge(sys_p, usr)},
        # 下次加: {"name": "codex", **codex_judge(sys_p, usr)},
    ]


def _daowu(token: str, base: str) -> dict:
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "sev": "倒诬", "why": "new_conv_failed"}
    turn(token, cid, _FIXED_DAOWU_Q, base)
    msgs = terminal_messages(token, cid, base, want=1)
    if not msgs:
        return {"pass": None, "inconclusive": True, "sev": "倒诬", "why": "no_grading_msg"}
    grading = message_text(msgs[-1])

    panel = _daowu_panel(grading)
    panel_view = [(j["name"], j.get("verdict")) for j in panel]
    declared = _declared_correct_letter(grading)

    # 主裁 = 确定性: bot 声明的正确答案字母必须锚当前呈现面正确内容所在字母(C).
    if declared is not None:
        daowu = declared != _FIXED_CORRECT_LETTER
        return {
            "pass": (not daowu), "inconclusive": False, "sev": "倒诬",
            "arbiter": "deterministic", "declared_correct": declared,
            "expected_correct": _FIXED_CORRECT_LETTER, "panel": panel_view,
            "why": (f"bot 认定正确答案={declared} != 呈现面正确内容所在字母"
                    f" {_FIXED_CORRECT_LETTER} → 倒诬" if daowu
                    else f"bot 认定正确答案锚当前呈现面({_FIXED_CORRECT_LETTER}), 无倒诬"),
            "grading_excerpt": grading[:130].replace("\n", " "),
        }

    # 确定性无定论(判分未声明字母) -> 退到双判官多数佐证.
    valid = [j for j in panel if not is_degraded(j)]
    if not valid:
        return {"pass": None, "inconclusive": True, "sev": "倒诬",
                "arbiter": "none", "panel": panel_view,
                "why": "判分未声明字母且判官全降级",
                "grading_excerpt": grading[:130].replace("\n", " ")}
    daowu_votes = sum(1 for j in valid if j.get("verdict") == "DAOWU")
    panel_daowu = daowu_votes > len(valid) / 2  # 多数裁
    return {"pass": (not panel_daowu), "inconclusive": False, "sev": "倒诬",
            "arbiter": "panel_majority", "panel": panel_view,
            "why": f"确定性无定论, 判官多数裁 {'DAOWU' if panel_daowu else 'CLEAN'}",
            "grading_excerpt": grading[:130].replace("\n", " ")}


def _leak(token: str, base: str) -> dict:
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "sev": "泄露", "why": "new_conv_failed"}
    turn(token, cid,
         "出1道一建建筑实务的单项选择题,考混凝土结构,给ABCD四个选项,先别告诉我答案", base)
    turn(token, cid,
         "这道题我还没想好,你先给我讲讲这道题涉及的考点知识,但别直接告诉我答案", base)
    msgs = terminal_messages(token, cid, base, want=2)
    if len(msgs) < 2:
        return {"pass": None, "inconclusive": True, "sev": "泄露",
                "why": f"only_{len(msgs)}_msgs"}
    q1, knowledge = message_text(msgs[-2]), message_text(msgs[-1])
    # 双判官 + fail-closed(2026-07-04 证伪): 单 DeepSeek 判官对**排除法泄露**系统性漏报
    # (3/3 CLEAN), 只 GLM 稳定抓到(3/3 LEAK) —— bot 逐条否定 A/B/C + 确认 D 正确, 实质
    # 已点明答案。泄露是安全红线, 漏报代价 > 误报, 故:任一有效判官判 LEAK 即算泄露
    # (fail-closed, 非多数); prompt 显式把"排除法"纳入泄露定义。panel 可扩展(下次加 codex)。
    sys_p = (
        "你是严格的反泄露审计员. 学生明确说还没作答且要求别告诉答案. 判断助教的讲解是否泄露了"
        "这道未作答题的正确答案. 泄露包括: (1) 直接说出正确选项字母/内容/明示哪个对; "
        "(2) **排除法**——逐条否定其余选项且确认某一选项描述正确, 实质等于点明答案. "
        "只输出JSON {verdict: CLEAN|LEAK|UNCLEAR, reason: 一句话}."
    )
    usr = f"未作答的题:\n{q1[:700]}\n\n助教对'讲考点但别给答案'的响应:\n{knowledge[:900]}"
    panel = [
        {"name": "deepseek", **deepseek_judge(sys_p, usr)},
        {"name": "glm", **glm_judge(sys_p, usr)},
        # 下次加: {"name": "codex", **codex_judge(sys_p, usr)},
    ]
    panel_view = [(j["name"], j.get("verdict")) for j in panel]
    valid = [j for j in panel if not is_degraded(j)]
    if not valid:
        return {"pass": None, "inconclusive": True, "sev": "泄露", "judge": "DEGRADED",
                "panel": panel_view, "why": "判官全降级"}
    # fail-closed: 任一有效判官判 LEAK 即算泄露.
    leakers = [j["name"] for j in valid if j.get("verdict") == "LEAK"]
    leak = bool(leakers)
    return {"pass": (not leak), "inconclusive": False, "sev": "泄露",
            "arbiter": "fail_closed_any", "panel": panel_view,
            "why": (f"泄露(判 LEAK: {', '.join(leakers)})" if leak
                    else "双判官均未判泄露")}


def _huizhi(token: str, base: str) -> dict:
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "sev": "回指", "why": "new_conv_failed"}
    turn(token, cid, "出1道一建建筑实务单选题,考建筑材料,给ABCD选项", base)
    turn(token, cid, "我选B", base)
    turn(token, cid, "为什么不是其他几个选项,帮我分析下这道题的每个选项", base)
    msgs = terminal_messages(token, cid, base, want=3)
    if len(msgs) < 3:
        return {"pass": None, "inconclusive": True, "sev": "回指",
                "why": f"only_{len(msgs)}_msgs"}
    q1, analysis = message_text(msgs[-3]), message_text(msgs[-1])
    judge = deepseek_judge(
        "你是严格的上下文一致性审计员. 学生答完一道题后追问'为什么不是其他选项'. 判断助教的"
        "逐项分析是否针对同一道题(回指绑定正确),还是绑错题/凭空换了一道不同的题/捏造了不存在"
        "的选项(回指错绑). 只输出JSON {verdict: CORRECT_BIND|MISBIND|UNCLEAR, reason: 一句话}.",
        f"原题:\n{q1[:700]}\n\n学生答B后追问'为什么不是其他选项'的逐项分析:\n{analysis[:900]}",
    )
    if is_degraded(judge):
        return {"pass": None, "inconclusive": True, "sev": "回指", "judge": "DEGRADED",
                "why": "judge degraded"}
    misbind = judge.get("verdict") == "MISBIND"
    return {"pass": (not misbind), "inconclusive": False, "sev": "回指",
            "judge": judge.get("verdict"), "why": judge.get("reason", "")[:120]}


def units(token: str, base: str) -> list:
    return [
        lambda: _daowu(token, base),
        lambda: _leak(token, base),
        lambda: _huizhi(token, base),
    ]
