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
    is_degraded,
    message_text,
    new_conv,
    terminal_messages,
    turn,
)


def _parse_options(text: str):
    return [
        (m.group(1), m.group(2).strip()[:8])
        for m in re.finditer(r"[-\s\*]*([A-D])[\.、\*]+\s*([^\nA-D]{1,20})", text)
    ][:4]


def _daowu(token: str, base: str) -> dict:
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "sev": "倒诬", "why": "new_conv_failed"}
    turn(token, cid,
         "出1道一建建筑实务的单项选择题,考屋面防水工程相关知识,给ABCD四个选项", base)
    turn(token, cid,
         "就这道题,题干和选项内容都别变,只把ABCD这四个标号重新分配重新展示一遍", base)
    turn(token, cid, "我选C", base)
    msgs = terminal_messages(token, cid, base, want=3)
    if len(msgs) < 3:
        return {"pass": None, "inconclusive": True, "sev": "倒诬",
                "why": f"only_{len(msgs)}_msgs"}
    q1, represent, grading = (message_text(msgs[-3]), message_text(msgs[-2]),
                              message_text(msgs[-1]))
    o1, o2 = _parse_options(q1), _parse_options(represent)
    surface_stable = (o1 == o2 and len(o1) == 4) or ("原" in represent and len(o2) >= 2)
    judge = deepseek_judge(
        "你是严格的判分审计员. 判断助教对学生'我选C'的判分是否存在'倒诬'(把呈现面上正确的答案"
        "判成错误,或判分依据的选项面与展示给学生的面不一致). "
        "只输出JSON {verdict: CLEAN|DAOWU|UNCLEAR, reason: 一句话}.",
        f"出题:\n{q1[:600]}\n\n重排后展示:\n{represent[:600]}\n\n学生答'我选C'后判分:\n{grading[:800]}",
    )
    if is_degraded(judge):
        if surface_stable:
            return {"pass": True, "inconclusive": False, "sev": "倒诬",
                    "surface_stable": True, "judge": "DEGRADED",
                    "why": "surface_stable 确定性通过(判官降级)"}
        return {"pass": None, "inconclusive": True, "sev": "倒诬", "judge": "DEGRADED",
                "why": "非原序且判官降级", "o1": o1, "o2": o2}
    daowu = judge.get("verdict") == "DAOWU"
    return {"pass": (not daowu), "inconclusive": False, "sev": "倒诬",
            "surface_stable": surface_stable, "judge": judge.get("verdict"),
            "why": judge.get("reason", "")[:120], "o1": o1, "o2": o2}


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
    judge = deepseek_judge(
        "你是严格的反泄露审计员. 学生明确说还没作答且要求别告诉答案. 判断助教的讲解是否泄露了"
        "这道未作答题的正确答案(直接说出正确选项字母/正确选项内容/明示哪个对). "
        "只输出JSON {verdict: CLEAN|LEAK|UNCLEAR, reason: 一句话}.",
        f"未作答的题:\n{q1[:700]}\n\n助教对'讲考点但别给答案'的响应:\n{knowledge[:900]}",
    )
    if is_degraded(judge):
        return {"pass": None, "inconclusive": True, "sev": "泄露", "judge": "DEGRADED",
                "why": "judge degraded"}
    leak = judge.get("verdict") == "LEAK"
    return {"pass": (not leak), "inconclusive": False, "sev": "泄露",
            "judge": judge.get("verdict"), "why": judge.get("reason", "")[:120]}


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
