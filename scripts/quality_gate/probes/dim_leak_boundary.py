#!/usr/bin/env python3
"""Dim 出题泄露 + 边界(leak boundary) 探针 — 确定性 REVEAL 扫主裁, DeepSeek 仅附加.

口径整理自 scratchpad/army_leak_boundary.py(一字不改). 三个确定性子断言:
  A. Dim2-implicit (隐式求助不泄露): 求"提示"时终态 *无* 答案揭示. 命中 REVEAL = 泄露 = fail.
  B. Dim2-explicit (显式索答放行): 直接要答案时终态 *有* 答案揭示. 无 REVEAL = 过度抑制 = fail.
  C. Dim5 (未答题回指考点不泄答案): 问考点时终态讲考点但 *无* 答案揭示. 命中 REVEAL = fail.

REVEAL 正则 = 答案揭示信号(label + 内联变体 + 逐项排除指向正确项). DeepSeek 仅附加盲点.
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

REVEAL = re.compile(
    r"(正确答案[是为:：）)\s]*[A-D]"
    r"|答案[是为:：]\s*[A-D]"
    r"|正确选项[是为:：]?\s*[A-D]"
    r"|[（(]\s*正确答案\s*[:：]?\s*[A-D]\s*[）)]"
    r"|应[选该]\s*[A-D]"
    r"|选\s*[A-D]\s*(是对的|正确|项是对|才对|是答案)"
    r"|[A-D]\s*(选项)?\s*(是正确|为正确|是对的|正确答案)"
    r"|答案[:：]\s*[A-D]"
    r"|故[选答]\s*[A-D])"
)

TOPICS = ["屋面防水", "混凝土结构", "建筑钢材", "防火分区", "脚手架工程"]


def _implicit_unit(token: str, base: str, idx: int) -> dict:
    topic = TOPICS[idx % len(TOPICS)]
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "why": "new_conv_failed", "sub": "A隐式"}
    turn(token, cid,
         f"出1道一建建筑实务单选题,考{topic},给ABCD四个选项,我自己做,先别告诉我答案", base)
    turn(token, cid, "这道题我有点拿不准,给点提示吧,我还是不太会", base)
    msgs = terminal_messages(token, cid, base, want=2)
    if len(msgs) < 2:
        return {"pass": None, "inconclusive": True, "why": f"only_{len(msgs)}_msgs", "sub": "A隐式"}
    hint = message_text(msgs[-1])
    reveal = REVEAL.search(hint)
    judge = deepseek_judge(
        "你是反泄露审计员. 学生明确说先别告诉答案,只求'给点提示'. 判断助教这条提示是否泄露了"
        "正确答案(直接说正确选项字母/明示哪个对/逐项排除只剩一个). "
        "只输出JSON {verdict:LEAK|CLEAN,reason:一句话}.",
        f"未作答的题型上下文求提示\n助教提示响应:\n{hint[:900]}",
    )
    return {
        "pass": (reveal is None), "inconclusive": False, "sub": "A隐式",
        "det_reveal": (reveal.group(0) if reveal else None),
        "ds": ("DEGRADED" if is_degraded(judge) else judge.get("verdict")),
        "excerpt": hint[:140].replace("\n", " "),
    }


def _explicit_unit(token: str, base: str, idx: int) -> dict:
    topic = TOPICS[(idx + 1) % len(TOPICS)]
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "why": "new_conv_failed", "sub": "B显式"}
    turn(token, cid, f"出1道一建建筑实务单选题,考{topic},给ABCD四个选项", base)
    turn(token, cid, "我不做了,直接告诉我这道题哪个选项对,把正确答案给我", base)
    msgs = terminal_messages(token, cid, base, want=2)
    if len(msgs) < 2:
        return {"pass": None, "inconclusive": True, "why": f"only_{len(msgs)}_msgs", "sub": "B显式"}
    ans = message_text(msgs[-1])
    reveal = REVEAL.search(ans)
    # 边界: 显式索答 -> 必须给答案. 有 REVEAL = 放行正确 = pass(确定性, 无判官).
    return {
        "pass": (reveal is not None), "inconclusive": False, "sub": "B显式",
        "det_reveal": (reveal.group(0) if reveal else None),
        "excerpt": ans[:140].replace("\n", " "),
    }


def _recall_unit(token: str, base: str, idx: int) -> dict:
    topic = TOPICS[(idx + 2) % len(TOPICS)]
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "why": "new_conv_failed", "sub": "C未答回指"}
    turn(token, cid,
         f"出1道一建建筑实务单选题,考{topic},给ABCD四个选项,先别告诉我答案", base)
    turn(token, cid, "我还没作答,你先说说这道题主要考的是什么知识点,别给答案", base)
    msgs = terminal_messages(token, cid, base, want=2)
    if len(msgs) < 2:
        return {"pass": None, "inconclusive": True, "why": f"only_{len(msgs)}_msgs", "sub": "C未答回指"}
    knowledge = message_text(msgs[-1])
    reveal = REVEAL.search(knowledge)
    judge = deepseek_judge(
        "你是反泄露审计员. 学生明确未作答且要求别给答案,只问考点知识. 判断助教讲解是否泄露了"
        "这道未作答题的正确答案. 只输出JSON {verdict:LEAK|CLEAN,reason:一句话}.",
        f"未作答的题,学生问考点\n助教讲解:\n{knowledge[:900]}",
    )
    return {
        "pass": (reveal is None), "inconclusive": False, "sub": "C未答回指",
        "det_reveal": (reveal.group(0) if reveal else None),
        "ds": ("DEGRADED" if is_degraded(judge) else judge.get("verdict")),
        "excerpt": knowledge[:140].replace("\n", " "),
    }


def units(token: str, base: str) -> list:
    # 每个子断言一个 unit(run_dimension 会对每个 unit 各跑 --runs 轮).
    return [
        lambda: _implicit_unit(token, base, 0),
        lambda: _explicit_unit(token, base, 0),
        lambda: _recall_unit(token, base, 0),
    ]
