#!/usr/bin/env python3
"""Dim 回指(back-reference binding) 探针 — 确定性 binding-check 主裁, GLM 仅附加.

口径整理自 scratchpad/army_huizhi_closure.py(一字不改):
- binding-check: T3 逐项分析提到的选项值是否匹配 T1 原题 4 选项(=绑定正确),
  与"哪个答案对"(content-truth 轴)确定性分离, 别让内容分歧污染绑定 SEV 判定.
- >=3/4 原题选项值命中分析 = 绑定正确. GLM 仅附加盲点检测.
"""
from __future__ import annotations

import re

from _probe_common import (
    glm_judge,
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


def _value_token(value: str) -> str:
    nums = re.findall(r"\d+\.?\d*\s*[年月%‰mm米个级度]?", value)
    if nums:
        return nums[0].strip()
    words = re.findall(r"[一-龥]{2,}", value)
    return max(words, key=len) if words else value[:4]


def _binding_check(o1: dict[str, str], analysis: str):
    if len(o1) < 4:
        return None, "原题选项解析不足"
    hits = []
    for letter, value in o1.items():
        tok = _value_token(value)
        if tok and tok in analysis:
            hits.append(letter)
    bind = len(hits) >= 3
    return bind, f"原题选项{len(hits)}/4命中分析({''.join(hits)})"


def _huizhi_unit(token: str, base: str) -> dict:
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "why": "new_conv_failed"}
    turn(token, cid,
         "出1道一建建筑实务单选题,考建筑材料,给ABCD四个选项,内容明确互不相同", base)
    turn(token, cid, "我选B", base)
    turn(token, cid,
         "为什么不是其他几个选项,帮我把这道题的ABCD每个选项逐项分析一下", base)
    msgs = terminal_messages(token, cid, base, want=3)
    if len(msgs) < 3:
        return {"pass": None, "inconclusive": True, "why": f"only_{len(msgs)}_msgs"}
    q1, analysis = message_text(msgs[-3]), message_text(msgs[-1])
    o1 = _parse_options(q1)
    bind, det_reason = _binding_check(o1, analysis)
    glm = glm_judge(
        "你是上下文一致性审计员. 只判一件事: 助教的逐项分析针对的是不是学生原题的那4个选项"
        "(=绑定正确), 与'哪个选项是正确答案'(内容对错)无关. "
        "只输出JSON {bind: CORRECT|MISBIND|UNCLEAR, reason: 一句话}.",
        f"原题选项:{o1}\n助教逐项分析:\n{analysis[:700]}",
    )
    glm_bind = None if is_degraded(glm) else (glm.get("bind") or glm.get("verdict"))
    if bind is None:
        return {"pass": None, "inconclusive": True, "why": det_reason,
                "o1": list(o1.items())}
    return {
        "pass": bool(bind), "inconclusive": False, "det_reason": det_reason,
        "glm_bind": glm_bind or "DEGRADED",
        "glm_reason": (glm.get("reason", "") if not is_degraded(glm) else "")[:90],
        "o1": list(o1.items()),
        "analysis_excerpt": analysis[:120].replace("\n", " "),
    }


def units(token: str, base: str) -> list:
    return [lambda: _huizhi_unit(token, base)]
