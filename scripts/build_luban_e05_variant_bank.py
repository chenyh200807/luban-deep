#!/usr/bin/env python3
"""E05 变体池编译期预生成器（挣值法/偏差分析·纯计算考点）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本承接 S05/F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`）
——纯确定性枚举（零 LLM、零随机），从 E05 Pack §4 R4 封闭规则组派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（参数构成/公式写法/方向判读在封闭取值域内代换）+ 期望判定
  （妥/不妥）+ 正确做法 + 采分锚（pack 内 point_id，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 E05 pack 裁决）：
- **E05 无任何 🟢 真题锚**（§0/§8.2 C3：STRICT 术语直读 2015–2025 建筑实务真题
  =0 命中）——本池全部锚为教材编译源 point_id（kc:/ca:），任何「某年第 N 题」
  真题锚禁入（🔴 编造）。
- **R4 组 C「作答表达边界」为 🔵 工程通识**（§4 组 C 自标 🔵；jury §9 #7：
  `kc:1A435020_097_0160:1` quote 仅含四公式、不含成组表达细节）——整组不入池，
  单位/无量纲等表达格式不作变体判定。
- **jury #3 已裁决**：「BCWP 居中/居于 ACWP 与 BCWS 之间」为事实错误已删——
  「居中」类三线曲线断言 token 禁入。
- **邻接噪声**（§0 边界①②③：成本考核指标/成本分析方法学/进度监测比较法/
  网络计划）token 禁入题面与正确做法。
- **R7 边界档位全 🔴 待裁决**——不作变体判定依据，本池期望判定只有妥/不妥二值。
- **计算型注意**（R4 封闭性自检：「出题人只能换三个数，不能换公式结构」）：
  组 D 母题数值变体只用 pack 自带教材例题三值（BCWP=6370/ACWP=6240/BCWS=5340，
  `ca:1A435020_095_0156`/`ca:1A435020_097_0160`），判定由整数/两位小数算术在
  params 内独立复核；不发明任何 pack 外数值。

用法::

    python3 scripts/build_luban_e05_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_e05_variant_bank.py --check  # 只跑一致性门(CI 可挂)
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_E05_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "E05_挣值法偏差分析.md"

SCHEMA_NAME = "luban-e05-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 E05 Pack §4 R4 / §5，锚随行）─────────────────
# 规则组 A：三个基本参数构成（封闭定义，禁互换）
# 锚 kc:1A435020_095_0156:0 + kc:1A435020_096_0158:0
_PARAM_CANON = {
    "BCWP": ("已完成工程量", "预算单价"),
    "BCWS": ("计划工程量", "预算单价"),
    "ACWP": ("已完成工程量", "实际单价"),
}
_PARAM_TITLES = {
    "BCWP": "已完成工作预算成本(挣值)",
    "BCWS": "计划完成工作预算成本",
    "ACWP": "已完成工作实际成本",
}
_QTY_DOMAIN = ("已完成工程量", "计划工程量")
_PRICE_DOMAIN = ("预算单价", "实际单价")
_ANCHOR_A = "kc:1A435020_095_0156:0 + kc:1A435020_096_0158:0"
_CORRECT_A = (
    "三个基本参数构成不得互换：BCWP=已完成工程量×预算单价；"
    "BCWS=计划工程量×预算单价；ACWP=已完成工程量×实际单价"
)

# 规则组 B：四个评价指标公式（封闭公式，禁颠倒）
# 锚 kc:1A435020_095_0156:1/2 + kc:1A435020_097_0160:1 + kc:1A435020_096_0157:0
_INDICATORS = ("CV", "SV", "CPI", "SPI")
_INDICATOR_NAMES = {"CV": "成本偏差", "SV": "进度偏差",
                    "CPI": "成本绩效指数", "SPI": "进度绩效指数"}
_FORMULA_CANON = {"CV": "BCWP−ACWP", "SV": "BCWP−BCWS",
                  "CPI": "BCWP/ACWP", "SPI": "BCWP/BCWS"}
_FORMULA_WRONG = {"CV": "ACWP−BCWP", "SV": "BCWS−BCWP",
                  "CPI": "ACWP/BCWP", "SPI": "BCWS/BCWP"}
_ANCHOR_IND = {
    "CV": "kc:1A435020_095_0156:1 + kc:1A435020_097_0160:1",
    "SV": "kc:1A435020_095_0156:1 + kc:1A435020_097_0160:1",
    "CPI": "kc:1A435020_095_0156:2 + kc:1A435020_097_0160:1",
    "SPI": "kc:1A435020_096_0157:0 + kc:1A435020_097_0160:1",
}
_CORRECT_B = {
    "CV": "CV=BCWP−ACWP；CV>0 成本节支、CV<0 成本超支；写成 ACWP−BCWP 即方向反，不妥",
    "SV": "SV=BCWP−BCWS；SV>0 进度提前、SV<0 进度延误；写成 BCWS−BCWP 即方向反，不妥",
    "CPI": "CPI=BCWP/ACWP；CPI>1 成本节支、CPI<1 成本超支；分子分母颠倒不妥",
    "SPI": "SPI=BCWP/BCWS；SPI>1 进度提前、SPI<1 进度延误；分子分母颠倒不妥",
}

# 规则组 C（本池组名 C-reading）：偏差方向判读（封闭判别表，R4 组 B 判分边界列）
_READING_CANON = {
    ("CV", "CV>0"): "成本节支", ("CV", "CV<0"): "成本超支",
    ("SV", "SV>0"): "进度提前", ("SV", "SV<0"): "进度延误",
    ("CPI", "CPI>1"): "成本节支", ("CPI", "CPI<1"): "成本超支",
    ("SPI", "SPI>1"): "进度提前", ("SPI", "SPI<1"): "进度延误",
}
_READING_OPPOSITE = {"成本节支": "成本超支", "成本超支": "成本节支",
                     "进度提前": "进度延误", "进度延误": "进度提前"}

# 规则组 D：母题数值组（pack 自带教材例题三值，禁外数值）
# 锚 ca:1A435020_095_0156 + ca:1A435020_097_0160（第20周末 6370/6240/5340）
_MOTHER_BCWP, _MOTHER_ACWP, _MOTHER_BCWS = 6370, 6240, 5340
_ANCHOR_D = "ca:1A435020_095_0156 + ca:1A435020_097_0160"
_CORRECT_D = (
    "母题四指标（R6 骨架）：CV=BCWP−ACWP=6370−6240=130万元(节支)；"
    "SV=BCWP−BCWS=6370−5340=1030万元(提前)；CPI=6370/6240≈1.02(节支)；"
    "SPI=6370/5340≈1.19(提前)——本项目第20周末成本节支、进度提前"
)


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"E05-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：三值构成——参数 × 量 × 价 全枚举（3×2×2=12）
    for param, qty, price in itertools.product(_PARAM_CANON, _QTY_DOMAIN, _PRICE_DOMAIN):
        ok = (qty, price) == _PARAM_CANON[param]
        add("A-param",
            f"某项目用挣值法做偏差分析，作答将 {param}（{_PARAM_TITLES[param]}）"
            f"取为「{qty}×{price}」",
            {"param": param, "qty": qty, "price": price}, ok, _CORRECT_A, _ANCHOR_A)

    # 组 B：四公式写法——正式 + R4 点名的颠倒式（4×2=8）
    for ind in _INDICATORS:
        for written in (_FORMULA_CANON[ind], _FORMULA_WRONG[ind]):
            add("B-formula",
                f"作答将{_INDICATOR_NAMES[ind]}公式写为 {ind}={written}",
                {"indicator": ind, "written": written},
                written == _FORMULA_CANON[ind], _CORRECT_B[ind], _ANCHOR_IND[ind])

    # 组 C：方向判读——判别表逐格 × 正读/反读（8×2=16）
    for (ind, cond), canon in _READING_CANON.items():
        for claim in (canon, _READING_OPPOSITE[canon]):
            add("C-reading",
                f"某项目挣值分析算得 {cond}，作答判读为「{claim}」",
                {"indicator": ind, "condition": cond, "claim": claim},
                claim == canon, _CORRECT_B[ind], _ANCHOR_IND[ind])

    # 组 D：母题数值——pack 教材例题三值 + R6 骨架结果逐字（全正例，4）
    header = (f"第20周末 BCWP={_MOTHER_BCWP}万元、ACWP={_MOTHER_ACWP}万元、"
              f"BCWS={_MOTHER_BCWS}万元，作答 ")
    mother_cases = (
        ("CV", f"CV=BCWP−ACWP={_MOTHER_BCWP}−{_MOTHER_ACWP}=130万元，判读成本节支",
         {"indicator": "CV", "value": 130, "claim": "成本节支"}),
        ("SV", f"SV=BCWP−BCWS={_MOTHER_BCWP}−{_MOTHER_BCWS}=1030万元，判读进度提前",
         {"indicator": "SV", "value": 1030, "claim": "进度提前"}),
        ("CPI", f"CPI=BCWP/ACWP={_MOTHER_BCWP}/{_MOTHER_ACWP}≈1.02，判读成本节支",
         {"indicator": "CPI", "value_2dp": 1.02, "claim": "成本节支"}),
        ("SPI", f"SPI=BCWP/BCWS={_MOTHER_BCWP}/{_MOTHER_BCWS}≈1.19，判读进度提前",
         {"indicator": "SPI", "value_2dp": 1.19, "claim": "进度提前"}),
    )
    for _, expr, params in mother_cases:
        add("D-mother", header + expr,
            {**params, "bcwp": _MOTHER_BCWP, "acwp": _MOTHER_ACWP, "bcws": _MOTHER_BCWS},
            True, _CORRECT_D, _ANCHOR_D)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-param":
        if p["param"] not in _PARAM_CANON:
            return None
        return (p["qty"], p["price"]) == _PARAM_CANON[p["param"]]
    if g == "B-formula":
        canon = _FORMULA_CANON.get(p["indicator"])
        if canon is None or p["written"] not in (canon, _FORMULA_WRONG[p["indicator"]]):
            return None  # 封闭域外写法不许出现
        return p["written"] == canon
    if g == "C-reading":
        canon = _READING_CANON.get((p["indicator"], p["condition"]))
        if canon is None:
            return None
        return p["claim"] == canon
    if g == "D-mother":
        b, a, s = p["bcwp"], p["acwp"], p["bcws"]
        if (b, a, s) != (_MOTHER_BCWP, _MOTHER_ACWP, _MOTHER_BCWS):
            return None  # 只允许 pack 自带母题三值（禁外数值）
        if p["indicator"] == "CV":
            return p["value"] == b - a and p["claim"] == ("成本节支" if b - a > 0 else "成本超支")
        if p["indicator"] == "SV":
            return p["value"] == b - s and p["claim"] == ("进度提前" if b - s > 0 else "进度延误")
        if p["indicator"] == "CPI":
            return p["value_2dp"] == round(b / a, 2) and \
                p["claim"] == ("成本节支" if b > a else "成本超支")
        if p["indicator"] == "SPI":
            return p["value_2dp"] == round(b / s, 2) and \
                p["claim"] == ("进度提前" if b > s else "进度延误")
        return None
    return None


# 争议/🔵通识/🔴编造层 token，禁入题面与正确做法（fail-closed）：
# 真题=E05 零真题命中禁编造(§8.2 C3)；居中=jury#3 已删的三线曲线事实错误；
# 无量纲=R4 组 C 表达边界 🔵(jury#7) 整组不入池；
# 其余=§0 邻接噪声①成本考核 ②成本分析方法学 ③进度监测/网络计划
_CONTESTED_TOKENS = (
    "真题", "居中", "无量纲",
    "劳动生产率", "成本降低率", "因素分析法", "差额计算法", "比率法",
    "前锋线", "横道", "S曲线", "关键线路",
)


def run_gate(variants: list[dict[str, Any]]) -> dict[str, Any]:
    mismatches, contested, dup = [], [], []
    seen: set[str] = set()
    for v in variants:
        iv = _independent_verdict(v)
        if iv is None or iv != v["expected_ok"]:
            mismatches.append(v["variant_id"])
        if any(t in v["surface"] or t in v["correct_statement"] for t in _CONTESTED_TOKENS):
            contested.append(v["variant_id"])
        key = v["surface"]
        if key in seen:
            dup.append(v["variant_id"])
        seen.add(key)
    total = len(variants)
    passed = total - len(set(mismatches + contested + dup))
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "verdict_mismatches": mismatches,
        "contested_leaks": contested,
        "duplicate_surfaces": dup,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    t0 = time.perf_counter()
    variants = build_variants()
    gen_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    gate = run_gate(variants)
    gate_ms = (time.perf_counter() - t1) * 1000

    ok = not (gate["verdict_mismatches"] or gate["contested_leaks"] or gate["duplicate_surfaces"])
    core = sum(1 for v in variants if not v["extension"])
    print(f"variants={gate['total']} (core={core}) gate_pass={gate['passed']} "
          f"rate={gate['pass_rate']:.2%} gen={gen_ms:.1f}ms gate={gate_ms:.1f}ms "
          f"-> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(json.dumps({k: gate[k] for k in
                          ('verdict_mismatches', 'contested_leaks', 'duplicate_surfaces')},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    if args.check:
        return 0

    payload = {
        "schema_version": SCHEMA_NAME,
        "pack_id": "E05",
        "status": "candidate",  # 教研审核+判分内核回路核验后方可签发入池
        "source_pack_sha256": hashlib.sha256(PACK_PATH.read_bytes()).hexdigest(),
        "generation_ms": round(gen_ms, 2),
        "gate": gate,
        "per_group_counts": {g: sum(1 for v in variants if v["rule_group"] == g)
                             for g in sorted({v["rule_group"] for v in variants})},
        "variants": variants,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {OUT_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
