#!/usr/bin/env python3
"""变体池风格泄露审计（红队 2026-07-10 规格）——出题"不用懂也能得分"量尺。

背景：owner 实测抓获"整场点不妥当全对"。红队量化：一条口诀（看到
认为/无需/不属于→答错，其余答对）零知识打全网 63%；15/17 signed 池在
55% 及格线沦陷。病灶=编译端模板分派（True 套"列入"肯定壳 / False 套
"认为/无需"否定壳，`params.case` 与答案 100% 绑定）。

本脚本是**审计尺**（只读报告，不改任何 bank）：
- 每池 × 每风格线索的条件命中率（n≥5 才计），>65% 标记 LEAK；
- 傻瓜策略基线（全 False / 组合口诀）命中率；
- 供编译端"模板对偶补齐 + 重签发"返工前后对照（返工目标=全部线索
  条件命中率 ≤65%，组合口诀 ≤55%）。

用法：
    python scripts/audit_variant_style_tells.py            # 全部 signed 池
    python scripts/audit_variant_style_tells.py --gate     # 违规则 exit 1（供签发闸复用）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BANK_DIR = _REPO / "docs" / "原始数据" / "考点原料" / "成品"

# 风格线索（红队实测最泄露的句式壳；判定=题面含该模式）
CUES: dict[str, str] = {
    "认为/认定": r"认为|认定",
    "无需类": r"无需|不必|即可|可不|不再需要",
    "不属于": r"不属于",
    "列入/纳入": r"列入|纳入",
    "顺序箭头": r"→",
}
CUE_MAX_HIT = 0.65  # 任一 n≥5 线索的条件命中率上限（超过=LEAK）
COMBO_MAX = 0.55    # 组合口诀（认为|无需|不属于→F 否则 T）上限
MIN_N = 5


def _core_variants(bank: dict) -> list[dict]:
    return [v for v in bank.get("variants") or [] if not v.get("extension")]


def audit_pack(pack_id: str, variants: list[dict]) -> dict:
    n = len(variants)
    falses = [v for v in variants if not v.get("expected_ok")]
    leaks = []
    for name, pat in CUES.items():
        rx = re.compile(pat)
        hit = [v for v in variants if rx.search(str(v.get("surface") or ""))]
        if len(hit) < MIN_N:
            continue
        # 线索的最优单边命中率（判 F 或判 T 取高者）
        f_rate = sum(1 for v in hit if not v.get("expected_ok")) / len(hit)
        rate = max(f_rate, 1 - f_rate)
        if rate > CUE_MAX_HIT:
            leaks.append({"cue": name, "n": len(hit), "hit_rate": round(rate, 3),
                          "direction": "F" if f_rate >= 0.5 else "T"})
    combo_rx = re.compile(r"认为|认定|无需|不必|即可|可不|不属于")
    combo_correct = sum(
        1 for v in variants
        if (not v.get("expected_ok")) == bool(combo_rx.search(str(v.get("surface") or "")))
    )
    return {
        "pack_id": pack_id,
        "n_core": n,
        "p_true": round(1 - len(falses) / n, 3) if n else 0.0,
        "always_false": round(len(falses) / n, 3) if n else 0.0,
        "combo_rule": round(combo_correct / n, 3) if n else 0.0,
        "cue_leaks": leaks,
        "violations": (
            (["combo>%.0f%%" % (COMBO_MAX * 100)] if n and combo_correct / n > COMBO_MAX else [])
            + [f"cue:{d['cue']}={d['hit_rate']:.0%}" for d in leaks]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true", help="违规则 exit 1")
    parser.add_argument("--pack", help="只审计单个 pack_id")
    args = parser.parse_args()

    reports = []
    for path in sorted(_BANK_DIR.glob("_*_variant_bank.v0.json")):
        bank = json.loads(path.read_text(encoding="utf-8"))
        if bank.get("status") != "signed":
            continue
        pack_id = str(bank.get("pack_id") or path.name.split("_")[1])
        if args.pack and pack_id != args.pack.upper():
            continue
        reports.append(audit_pack(pack_id, _core_variants(bank)))

    bad = [r for r in reports if r["violations"]]
    for r in reports:
        flag = "  LEAK " if r["violations"] else "  ok   "
        print(f"{flag}{r['pack_id']:>4} n={r['n_core']:<4} P(T)={r['p_true']:.0%} "
              f"全F={r['always_false']:.0%} 口诀={r['combo_rule']:.0%} "
              f"{'; '.join(r['violations'])}")
    print(f"\n{len(bad)}/{len(reports)} 池存在风格泄露违规"
          f"（阈值: 单线索≤{CUE_MAX_HIT:.0%}, 口诀≤{COMBO_MAX:.0%}）")
    if args.gate and bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
