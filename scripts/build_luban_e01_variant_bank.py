#!/usr/bin/env python3
"""E01 变体池编译期预生成器（工程量清单计价）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本承接 S05 / F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`），
纯确定性枚举（零 LLM、零随机、零时间依赖），从 E01 Pack §4 R4 三个封闭规则组
（A 计价方式与综合单价 / B 清单造价组成汇总 / C 缺陷与风险责任归属）派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

计算型 pack 的机械可裁决边界（照任务判据）：
- E01 是「制度 + 计算」混合考点。R4 给出的是**封闭定义 + 结构/方向判读边界**
  （计价方式分流、综合单价构成要素、汇总项不漏不重、增值税基数方向、责任分流），
  这些**构成要素/方向的二值判断可机械裁决**，本池只做这一层。
- **不生成任何需要多步算术求值的题面**（教材母题 408.64 万 / 2020 结算 5453 元/t
  等逐步计算归判分内核与教学层，不入变体池）。

变体形状（只换皮不换判分锚——红线 9：变题只能换事件/方式/归属，不能换计价
规则结构与责任分流原则）：
- 每个变体 = 情境题面（方式/构成/事件/归属在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药。

诚实边界（fail-closed，逐条对应 E01 pack 裁决）：
- **jury #2/#5（已应用进正文）**：「五项必含规费」为过强通用化——本池规费变体
  显式带 `fee_given` 参数（题给规费才要求纳入；题未给时四项+税=妥），增值税基数
  用 pack 统一口径「全部税前计价项之和，题给规费时再加规费，不含已计增值税」。
- **§8.2 C3**：2015 案例4 真题锚已被汇编层删除（非清单计价本体）——禁引；真题
  锚只用经确定性核验的年份案例（2016/2020/2023/2024/2025 案例四），且不写
  「某年第 N 题」级断言。
- **§0 邻接①②③**：进度款/计量（C02 territory）、造价八部分/六阶段、招投标程序/
  索赔（K01）全部 🔵 邻接——禁入题面与正确做法（争议 token 门拦截）。
- **合同类型选择（工程量不确定→单价等，§1 #6）与编制依据清单（R5 B）不在 R4
  规则组内**——不入池（变体只能在 R4 封闭域内换皮）。
- **R6 🔵 主体规范**：表述用「发包人/承包人」，禁"甲方/乙方"（token 门拦截）。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_e01_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_e01_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_E01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "E01_工程量清单计价.md"

SCHEMA_NAME = "luban-e01-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 E01 Pack §4 R4 / §5，锚随行）─────────────────
# 规则组 A：计价方式分流（锚 kc:1A432002_035_0046:0）
_PRICING_CORRECT = {"分部分项工程": "单价计价", "措施项目": "总价计价"}
_PRICING_MODES = ("单价计价", "总价计价")
_ANCHOR_A = "kc:1A432002_035_0046:0"
_CORRECT_A_MODE = "分部分项工程宜采用单价计价；措施项目宜采用总价计价"

# 规则组 A：综合单价构成（不含增值税的税前全费用价=人材机+管理+利润+风险费）
_CORRECT_A_PRICE = (
    "综合单价是不含增值税的税前全费用价，含人工费+材料费+机具费+管理费+利润+风险费"
)
_UNITPRICE_CASES = (
    {"surface": "投标人综合单价按人工费、材料费、机具费、管理费、利润组价并考虑风险费，不含增值税",
     "includes_vat": False, "includes_risk": True, "includes_overhead_profit": True},
    {"surface": "投标人认为综合单价中应包含增值税",
     "includes_vat": True, "includes_risk": True, "includes_overhead_profit": True},
    {"surface": "投标人综合单价只按人工费、材料费、机具费、管理费、利润组价，不考虑风险费",
     "includes_vat": False, "includes_risk": False, "includes_overhead_profit": True},
    {"surface": "投标人综合单价只按人工费、材料费、机具费直接成本组价",
     "includes_vat": False, "includes_risk": False, "includes_overhead_profit": False},
)

# 规则组 B：清单造价组成汇总（锚 kc:1A435000_038_0050:1/2 + kc:1A435000_039_0053:0
# + kc:1A435000_040_0054:2；规费口径按 jury#2 收口=题给才纳入）
_ANCHOR_B_SUM = "kc:1A435000_040_0054:2 + kc:1A435000_039_0053:0"
_ANCHOR_B_ITEM = "kc:1A435000_038_0050:1"
_ANCHOR_B_MEASURE = "kc:1A435000_038_0050:2"
_CORRECT_B_FEE = (
    "清单造价逐项汇总：分部分项工程费+措施项目费+其他项目费+（题给/规范要求时）规费+增值税，"
    "项数随题给清单结构，不漏项不重复"
)
_CORRECT_B_VAT = (
    "增值税基数=全部税前计价项之和（分部分项费+措施费+其他费，题给规费时再加规费），"
    "不含已计的增值税本身"
)
_CORRECT_B_TOTAL = "投标总价应与各组成合计一致；不一致时保持总价不变、调整已标价工程量清单"
_CORRECT_B_ITEM = "分部分项工程费=Σ(分部分项工程量×综合单价)，综合单价含人材机+管理费+利润"
_CORRECT_B_MEASURE = "措施项目费按单价计量=Σ(工程量×综合单价)、按总价计量=Σ(计算基数×费率)，计量方式应与题给一致"
_MEASURE_MODES = ("单价计量", "总价计量")

# 规则组 C：缺陷/风险责任归属（锚 kc:1A432002_036_0047:0 + kc:1A432002_037_0048:1）
_ANCHOR_C_DEFECT = "kc:1A432002_037_0048:1"
_ANCHOR_C_RISK = "kc:1A432002_036_0047:0"
_ANCHOR_C_BID = "kc:1A435000_040_0054:0"
_CORRECT_C_DEFECT = "清单缺陷按合同类型归责：单价合同缺陷发包人负责；总价合同缺陷承包人负责"
_CORRECT_C_RISK = (
    "计价风险按来源归属：发包人承担清单缺陷/数据错误/变更/赶工；"
    "承包人承担措施清单准确性/自身方案变更/施工效率"
)
_CORRECT_C_BID = "投标报价不得低于成本价、不得高于最高投标限价"
_PARTIES = ("发包人", "承包人")
_DEFECT_CORRECT = {"单价合同": "发包人", "总价合同": "承包人"}
_EMPLOYER_EVENTS = ("招标工程量清单数据错误", "工程变更", "发包人要求赶工")
_CONTRACTOR_EVENTS = ("措施项目清单的准确性", "承包人自身施工方案变更", "承包人施工效率")


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"E01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：计价方式——项目类型×方式全枚举
    for item, mode in itertools.product(_PRICING_CORRECT, _PRICING_MODES):
        add("A-mode", f"招标工程量清单中，{item}采用{mode}方式",
            {"item": item, "mode": mode}, _PRICING_CORRECT[item] == mode,
            _CORRECT_A_MODE, _ANCHOR_A)

    # 组 A：综合单价构成——构成要素封闭案例（正例+三类错误内涵）
    for case in _UNITPRICE_CASES:
        ok = (not case["includes_vat"]) and case["includes_risk"] and case["includes_overhead_profit"]
        add("A-unitprice", case["surface"],
            {"includes_vat": case["includes_vat"], "includes_risk": case["includes_risk"],
             "includes_overhead_profit": case["includes_overhead_profit"]},
            ok, _CORRECT_A_PRICE, _ANCHOR_A)

    # 组 B：规费口径（jury#2 收口：题给才纳入；母题可四项+税）
    add("B-fee", "题目给出规费计算规定，投标人按分部分项工程费+措施项目费+其他项目费+规费+增值税逐项汇总总造价",
        {"fee_given": True, "fee_in_sum": True}, True, _CORRECT_B_FEE, _ANCHOR_B_SUM)
    add("B-fee", "题目给出规费计算规定，投标人只按分部分项工程费+措施项目费+其他项目费+增值税汇总总造价",
        {"fee_given": True, "fee_in_sum": False}, False, _CORRECT_B_FEE, _ANCHOR_B_SUM)
    add("B-fee", "题目未给规费，投标人按分部分项工程费+措施项目费+其他项目费+增值税汇总总造价",
        {"fee_given": False, "fee_in_sum": False}, True, _CORRECT_B_FEE, _ANCHOR_B_SUM)

    # 组 B：增值税基数方向（不含已计增值税；题给项不漏）
    add("B-vat", "题目未给规费，增值税以分部分项工程费+措施项目费+其他项目费之和为基数乘以税率",
        {"includes_levied_vat": False, "omits_given_item": False}, True,
        _CORRECT_B_VAT, _ANCHOR_B_SUM)
    add("B-vat", "投标人计算增值税时，基数中包含了已计的增值税",
        {"includes_levied_vat": True, "omits_given_item": False}, False,
        _CORRECT_B_VAT, _ANCHOR_B_SUM)
    add("B-vat", "题目给出规费，投标人计算增值税时基数漏掉了规费",
        {"includes_levied_vat": False, "omits_given_item": True}, False,
        _CORRECT_B_VAT, _ANCHOR_B_SUM)

    # 组 B：投标总价一致性（发现不一致的两种处置）
    add("B-total", "投标总价与各组成合计不一致，投标人保持总价不变、调整已标价工程量清单",
        {"action": "保持总价调整清单"}, True, _CORRECT_B_TOTAL, _ANCHOR_B_SUM)
    add("B-total", "投标总价与各组成合计不一致，投标人直接修改投标总价",
        {"action": "直接改总价"}, False, _CORRECT_B_TOTAL, _ANCHOR_B_SUM)

    # 组 B：措施费计量方式与题给一致性——要求×实际全枚举
    for required, used in itertools.product(_MEASURE_MODES, _MEASURE_MODES):
        add("B-measure", f"题目要求措施项目按{required}，投标人按{used}计算措施项目费",
            {"required": required, "used": used}, required == used,
            _CORRECT_B_MEASURE, _ANCHOR_B_MEASURE)

    # 组 B：分部分项费构成层级（含管理费/利润 vs 只按人材机）
    add("B-item", "分部分项工程费按Σ(工程量×综合单价)计算，综合单价含人材机、管理费和利润",
        {"includes_overhead_profit": True}, True, _CORRECT_B_ITEM, _ANCHOR_B_ITEM)
    add("B-item", "分部分项工程费只按人工费、材料费、机具费汇总，不含管理费和利润",
        {"includes_overhead_profit": False}, False, _CORRECT_B_ITEM, _ANCHOR_B_ITEM)

    # 组 C：清单缺陷归责——合同类型×判给主体全枚举
    for contract, liable in itertools.product(_DEFECT_CORRECT, _PARTIES):
        add("C-defect", f"{contract}履行中发现招标工程量清单缺陷，判由{liable}负责",
            {"contract": contract, "liable": liable},
            _DEFECT_CORRECT[contract] == liable, _CORRECT_C_DEFECT, _ANCHOR_C_DEFECT)

    # 组 C：计价风险归属——事件×判给主体全枚举
    for event, liable in itertools.product(_EMPLOYER_EVENTS, _PARTIES):
        add("C-risk", f"因{event}产生的计价风险，判由{liable}承担",
            {"event": event, "liable": liable}, liable == "发包人",
            _CORRECT_C_RISK, _ANCHOR_C_RISK)
    for event, liable in itertools.product(_CONTRACTOR_EVENTS, _PARTIES):
        add("C-risk", f"因{event}产生的计价风险，判由{liable}承担",
            {"event": event, "liable": liable}, liable == "承包人",
            _CORRECT_C_RISK, _ANCHOR_C_RISK)

    # 组 C：投标报价合法边界（方向判断，无数值算术）
    add("C-bid", "投标报价低于成本价，评标时仍判该报价有效",
        {"below_cost": True, "above_ceiling": False, "judged_valid": True}, False,
        _CORRECT_C_BID, _ANCHOR_C_BID)
    add("C-bid", "投标报价高于最高投标限价，评标时仍判该报价有效",
        {"below_cost": False, "above_ceiling": True, "judged_valid": True}, False,
        _CORRECT_C_BID, _ANCHOR_C_BID)
    add("C-bid", "投标报价不低于成本价且不高于最高投标限价，评标时判该报价有效",
        {"below_cost": False, "above_ceiling": False, "judged_valid": True}, True,
        _CORRECT_C_BID, _ANCHOR_C_BID)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-mode":
        correct = _PRICING_CORRECT.get(p["item"])
        return None if correct is None else p["mode"] == correct
    if g == "A-unitprice":
        return ((not p["includes_vat"]) and p["includes_risk"]
                and p["includes_overhead_profit"])
    if g == "B-fee":
        return p["fee_in_sum"] == p["fee_given"]  # 题给才纳入；未给四项+税=妥
    if g == "B-vat":
        return (not p["includes_levied_vat"]) and (not p["omits_given_item"])
    if g == "B-total":
        if p["action"] == "保持总价调整清单":
            return True
        if p["action"] == "直接改总价":
            return False
        return None  # 处置封闭域外禁入
    if g == "B-measure":
        if p["required"] not in _MEASURE_MODES or p["used"] not in _MEASURE_MODES:
            return None
        return p["required"] == p["used"]
    if g == "B-item":
        return bool(p["includes_overhead_profit"])
    if g == "C-defect":
        correct = _DEFECT_CORRECT.get(p["contract"])
        return None if correct is None else p["liable"] == correct
    if g == "C-risk":
        if p["event"] in _EMPLOYER_EVENTS:
            return p["liable"] == "发包人"
        if p["event"] in _CONTRACTOR_EVENTS:
            return p["liable"] == "承包人"
        return None  # 事件封闭域外禁入
    if g == "C-bid":
        legal = (not p["below_cost"]) and (not p["above_ceiling"])
        return p["judged_valid"] == legal
    return None


# 争议/🔵邻接/🔴删锚层 token，禁入题面与正确做法（fail-closed）：
# 进度款/预付款=C02 territory(§0 邻接①)；索赔=K01(§0 邻接③)；概算/估算/决算=
# 造价八部分/六阶段邻接(§0 邻接②)；甲方/乙方=R6 🔵 主体规范禁用表述；
# 2015案例=汇编层已删真题锚(§8.2 C3)
_CONTESTED_TOKENS = ("进度款", "预付款", "索赔", "概算", "估算", "决算",
                     "甲方", "乙方", "2015案例", "2015 案例")


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
        "pack_id": "E01",
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
