#!/usr/bin/env python3
"""Dim 倒诬(false-accusation) 探针 — surface_stable o1==o2 确定性主裁.

口径整理自 scratchpad/army_daowu_hard.py(一字不改):
- 主 ground truth = 确定性: 学生显式请求"重排"后, 呈现面必须 == 原序(surface_stable),
  且 bot 自由重排出新序(represented_new_order) 才是倒诬风险.
- 倒诬复现 = bot 真自由重排出新序(分叉) 且 异源判官确认判分用了不一致的面.
- 判官(DeepSeek) 仅佐证, DEGRADED -> 不计 pass/fail.

每个 unit() 返回 {pass, inconclusive, ...}; 由 _probe_common.run_dimension 编排 --runs.
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


def _parse_options(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(
        r"(?:^|[\n\s])[\-\*]*\s*\**\s*([A-D])\s*\**\s*[\.\．、:：\)]\s*\**\s*([^\n]{1,40})",
        text,
    ):
        letter, value = m.group(1), m.group(2).strip().strip("*").strip()
        if letter not in out and value:
            out[letter] = value
    return out


def _daowu_unit(token: str, base: str) -> dict:
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "why": "new_conv_failed"}
    turn(token, cid,
         "出1道一建建筑实务的单项选择题,4个选项ABCD,每个选项内容明确且互不相同", base)
    turn(token, cid,
         "现在请把这道题的ABCD四个选项重新排列顺序后重新展示一遍,题干保持不变", base)
    msgs = terminal_messages(token, cid, base, want=2)
    if len(msgs) < 2:
        return {"pass": None, "inconclusive": True, "why": f"only_{len(msgs)}_msgs"}
    q1, represent = message_text(msgs[-2]), message_text(msgs[-1])
    o1, o2 = _parse_options(q1), _parse_options(represent)
    if len(o1) < 4 or len(o2) < 2:
        return {"pass": None, "inconclusive": True, "why": f"解析不足 o1={o1} o2={o2}"}
    surface_stable = o1 == o2
    represented_new_order = len(o2) == 4 and o2 != o1
    turn(token, cid, "我选A", base)
    msgs2 = terminal_messages(token, cid, base, want=1)
    grading = message_text(msgs2[-1]) if msgs2 else ""
    judge = deepseek_judge(
        "你是严格判分审计员. 给你'学生看到的选项面'和'判分响应'. 判断判分是否倒诬: "
        "即判分依据的选项字母↔内容映射 与 学生看到的呈现面 不一致(把呈现面上某字母对应的内容, "
        "按另一套顺序去判). 只输出JSON {verdict: CLEAN|DAOWU|UNCLEAR, reason: 一句话}.",
        f"学生看到的呈现面(重排后):{o2}\n学生答'我选A'\n判分响应:\n{grading[:700]}",
    )
    if is_degraded(judge):
        # 判官不可信: 仅当确定性 surface_stable=True 才算 pass(结构上无分叉);
        # 若 bot 自由重排出新序但判官降级 -> inconclusive(不冤判也不放过).
        if surface_stable:
            return {"pass": True, "inconclusive": False, "surface_stable": True,
                    "judge": "DEGRADED", "why": "surface_stable 确定性通过(判官降级)"}
        return {"pass": None, "inconclusive": True,
                "why": "自由重排但判官降级, 无法确认倒诬", "judge": "DEGRADED",
                "o1": list(o1.items()), "o2": list(o2.items())}
    judge_daowu = judge.get("verdict") == "DAOWU"
    daowu = represented_new_order and judge_daowu
    return {
        "pass": (not daowu), "inconclusive": False,
        "surface_stable": surface_stable,
        "represented_new_order": represented_new_order,
        "judge": judge.get("verdict"), "why": judge.get("reason", "")[:110],
        "o1": list(o1.items()), "o2": list(o2.items()),
        "grading_excerpt": grading[:130].replace("\n", " "),
    }


def units(token: str, base: str) -> list:
    return [lambda: _daowu_unit(token, base)]
