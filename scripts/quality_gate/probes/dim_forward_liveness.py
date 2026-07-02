#!/usr/bin/env python3
"""Dim 拒判(forward liveness) 探针 — 确定性主裁, 无判官.

口径(按 owner 重建规格):
  bot inline 出 2-3 题 -> 学员批量作答 -> 终态必须含逐题判分(对/错/正确答案),
  且 *无* "你还没作答/未提交/请带题号" 类拒判. 命中拒判 = forward liveness 破 = fail.

含 **Dim1 已知 bug** (门要能跑出它红, 不为绿改口径):
  同会话先出 3 题, 再出 **单** 题, 学员 bare "我选B" ->
  *陈旧多题 active-set 没替换* 导致被 "你这轮有多道题请带题号" 拒判.
  断言: 终态含判分 且 无拒判. 当前部署(686fe37bb)预期 fail(真 bug 未修).

两个 unit:
  U1 batch_grade   — 批量作答必判(回归基线, 当前部署应 PASS).
  U2 stale_set_bug — Dim1 陈旧多题 active-set bug(当前部署应 FAIL=复现).
"""
from __future__ import annotations

import re

from _probe_common import (
    message_text,
    new_conv,
    terminal_messages,
    turn,
)

# 确定性: 判分发生的信号(逐题对/错/正确答案/得分/阅卷结论). markdown 粗体不挡匹配:
# 先剥 ** 再扫. 覆盖 TutorBot 真实判分形态: "你选B，正确"/"阅卷结论"/"判断依据"/"得分N/M".
_GRADED = re.compile(
    r"(正确答案|参考答案|阅卷结论|判断依据|回答正确|答对|答错|选错|不正确|判[你卷]"
    r"|你选\s*[A-D]?\s*[，,。]?\s*(正确|错误|对了|错了)"
    r"|judged|得\s*\d+\s*分|\d+\s*/\s*\d+\s*分|本题(正确|错误|得分)"
    r"|第\s*[一二三1-9]\s*题.*(对|错|正确|错误)|✓|✗"
    r"|你(答|选)的?\s*[A-D].*(正确|错误)|这道?题.*(答对|答错|选对|选错|正确|错误))"
)
# 确定性: 拒判信号(还没作答/未提交/请带题号/这轮有多道题).
_REFUSAL = re.compile(
    r"(你还没作答|还没有作答|未作答|未提交|没有提交|请(先)?作答|请带题号|带上题号"
    r"|这轮有多道题|有多道题.*题号|是哪一道|哪一题|先选(一个|个)答案|你还没.*选)"
)


def _graded_and_not_refused(text: str) -> dict:
    # 剥 markdown 粗体标记, 避免 **正确** 挡住判分信号匹配.
    clean = text.replace("*", "")
    graded = bool(_GRADED.search(clean))
    refused = bool(_REFUSAL.search(clean))
    refusal_hit = _REFUSAL.search(clean)
    return {
        "graded": graded,
        "refused": refused,
        "refusal_marker": refusal_hit.group(0) if refusal_hit else None,
    }


def _batch_grade_unit(token: str, base: str) -> dict:
    """U1: inline 多题 -> 批量作答 -> 必逐题判分, 无拒判."""
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "sub": "U1批量判分", "why": "new_conv_failed"}
    turn(token, cid,
         "连续出2道一建建筑实务单选题,每道都给ABCD四个选项,一次性都列出来", base)
    turn(token, cid, "第1题选A，第2题选B", base)
    msgs = terminal_messages(token, cid, base, want=2)
    if len(msgs) < 1:
        return {"pass": None, "inconclusive": True, "sub": "U1批量判分",
                "why": f"only_{len(msgs)}_msgs"}
    grading = message_text(msgs[-1])
    det = _graded_and_not_refused(grading)
    # 批量判分: 必须判分 且 不拒判.
    ok = det["graded"] and not det["refused"]
    return {
        "pass": ok, "inconclusive": False, "sub": "U1批量判分",
        "graded": det["graded"], "refused": det["refused"],
        "refusal_marker": det["refusal_marker"],
        "excerpt": grading[:160].replace("\n", " "),
    }


def _stale_set_bug_unit(token: str, base: str) -> dict:
    """U2: Dim1 已知 bug — 先出3题再出单题, bare 答案被陈旧多题 active-set 拒判.

    确定性断言: 单题作答后终态含判分 且 无 '请带题号/有多道题' 拒判.
    当前部署(686fe37bb) 预期 FAIL(陈旧 active-set 未替换 -> 拒判复现). 不为绿改口径.
    """
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "sub": "U2陈旧多题set", "why": "new_conv_failed"}
    # 先出多题 -> 建立 active 多题 set.
    turn(token, cid,
         "一次性连续出3道一建建筑实务单选题,每道都给ABCD四个选项,都列出来", base)
    # 再出单题 -> 新单题应完整替换旧多题 active-set.
    turn(token, cid, "再单独出1道一建建筑实务的单选题,给ABCD四个选项", base)
    # bare 单题作答 -> 陈旧多题计数残留 => 被 '请带题号' 拒判(bug).
    turn(token, cid, "我选B", base)
    msgs = terminal_messages(token, cid, base, want=3)
    if len(msgs) < 1:
        return {"pass": None, "inconclusive": True, "sub": "U2陈旧多题set",
                "why": f"only_{len(msgs)}_msgs"}
    grading = message_text(msgs[-1])
    det = _graded_and_not_refused(grading)
    # 单题 bare 作答: 必须判分 且 不被陈旧多题 active-set 拒判.
    ok = det["graded"] and not det["refused"]
    return {
        "pass": ok, "inconclusive": False, "sub": "U2陈旧多题set(Dim1 known bug)",
        "graded": det["graded"], "refused": det["refused"],
        "refusal_marker": det["refusal_marker"],
        "excerpt": grading[:200].replace("\n", " "),
    }


def units(token: str, base: str) -> list:
    return [
        lambda: _batch_grade_unit(token, base),
        lambda: _stale_set_bug_unit(token, base),
    ]
