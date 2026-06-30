#!/usr/bin/env python3
"""Dim content-truth(规范条文不抑制 + hedge) 探针 — 确定性主裁, GLM/DeepSeek 仅附加.

口径(按 owner 重建规格): bot 出规范条文/具体数值条款时 ->
  ① 永远输出, 不抑制(非空 且 非拒答) —— 抑制/拒答 = fail.
  ② 核不到权威源时 hedge present(以教材为准/AI生成/请以现行规范为准/不保证100%) ——
     给了具体条文数值却无 hedge = 过度自信 = fail.
  ③ (可选) 低置信 claim 进 TurnEventLog —— 仅 observability, 不阻断.

  GLM/DeepSeek 仅附加盲点检测(是否给了像规范条文的具体声称), DEGRADED 不计 pass/fail.

falsifiable: 拒答/空响应 = ① fail; 出具体数值条文但全程无 hedge = ② fail.
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

# 拒答/抑制信号(确定性): 不能回答/无法提供/建议查阅(无任何实质内容).
_REFUSAL = re.compile(
    r"(我?无法(回答|提供|确定)|不能(回答|提供|告诉)|没有(相关|该)信息"
    r"|抱歉.*(无法|不能|没有)|建议(您)?(自行)?查阅(相关)?(规范|资料)$"
    r"|超出.*范围.*无法)"
)
# hedge 信号(确定性): 不确定性免责 / 以教材或现行规范为准 / AI 生成不保证.
_HEDGE = re.compile(
    r"(以(现行)?(教材|规范|标准|官方)为准|请(以|参考).*(规范|标准|教材).*(为准|核对)"
    r"|AI\s*生成|不保证(100%|完全|绝对)?(准确|正确)|可能(存在)?(误差|偏差|不准确)"
    r"|仅供参考|请(以|二次)?核(对|实)|具体(以|请以).*(规范|标准|文件)"
    r"|建议(再)?核对|最终以.*为准|如有出入)"
)
# 具体规范条文/数值条款信号(确定性): 出现了像条款编号/具体数值时长/规范代号.
_SPECIFIC_CLAIM = re.compile(
    r"(\d+\s*(年|个月|天|小时|米|mm|MPa|kN|%|‰|级|度)"
    r"|第\s*[\d一二三四五六七八九十]+\s*(条|款|项)"
    r"|GB\s*\d+|JGJ\s*\d+|《[^》]{2,30}》)"
)

TOPICS = [
    "工程质量保修期的具体年限规定",
    "建筑工程施工合同价款支付的相关规范条款",
    "建设工程施工现场消防安全的具体规范要求",
]


def _content_truth_unit(token: str, base: str, idx: int) -> dict:
    topic = TOPICS[idx % len(TOPICS)]
    cid = new_conv(token, base)
    if not cid:
        return {"pass": None, "inconclusive": True, "why": "new_conv_failed"}
    turn(token, cid,
         f"请直接告诉我关于{topic}的具体规范条文和数值,要给出明确的条款和数字", base)
    msgs = terminal_messages(token, cid, base, want=1)
    if len(msgs) < 1:
        return {"pass": None, "inconclusive": True, "why": "no_assistant_msg"}
    answer = message_text(msgs[-1]).strip()
    # ① 永远输出: 非空 且 非拒答.
    non_empty = len(answer) >= 20
    refused = bool(_REFUSAL.search(answer))
    suppressed = (not non_empty) or refused
    # ② 给了具体条文数值 -> 必须有 hedge.
    has_specific = bool(_SPECIFIC_CLAIM.search(answer))
    has_hedge = bool(_HEDGE.search(answer))
    hedge_ok = (not has_specific) or has_hedge
    det_pass = (not suppressed) and hedge_ok
    # 附加: 异源判官只佐证"是否给了像规范条文的具体声称", 不主裁.
    judge = deepseek_judge(
        "你是事实声称审计员. 判断这段助教回答是否给出了关于规范/法规的具体条文或数值声称"
        "(具体年限/条款编号/规范代号), 以及是否带了'以教材或现行规范为准/AI生成不保证'类免责. "
        "只输出JSON {has_specific_claim:true|false, has_hedge:true|false, reason:一句话}.",
        f"助教回答:\n{answer[:900]}",
    )
    judge_note = "DEGRADED" if is_degraded(judge) else (
        f"specific={judge.get('has_specific_claim')} hedge={judge.get('has_hedge')}")
    why = []
    if suppressed:
        why.append("抑制/拒答(违反①永远输出)")
    if not hedge_ok:
        why.append("出具体条文数值却无hedge(违反②)")
    return {
        "pass": det_pass, "inconclusive": False,
        "non_empty": non_empty, "refused": refused,
        "has_specific": has_specific, "has_hedge": has_hedge,
        "judge": judge_note, "why": "; ".join(why) or "ok",
        "excerpt": answer[:160].replace("\n", " "),
    }


def units(token: str, base: str) -> list:
    return [lambda: _content_truth_unit(token, base, 0)]
