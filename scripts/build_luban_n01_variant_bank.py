#!/usr/bin/env python3
"""N01 变体池编译期预生成器（计算/判读型首站：网络计划关键线路/总时差）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本沿 S05/F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`），
纯确定性枚举（零 LLM、零随机），从 N01 Pack §4 R4 封闭判读边界派生变体，自带独立
一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

计算型考点约束（任务硬门）：N01 是计算/判读型，本池**不生成**需要读图求解
关键线路/总工期数值的题面——只枚举 R4 显式给出的**判读边界二值判定**
（线路是否全列/表达是否落到具体线路/延误≤总时差是否影响总工期/方法与监测
内容是否在封闭清单内/程序顺序是否违例），数值判定只用 pack 内逐字锚定的
真题数值单元（延误 vs 总时差整数比较，params 内独立复核）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（判读形态在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 N01 pack 裁决）：
- **jury 单源#6/#7（未裁决）**：「工期索赔成立」结论降 🔵（需责任归属/K01 锚共同
  支撑）——本池组 C 只做「延误是否影响总工期」二值判读（jury#6 明示该层保 🟢），
  「索赔」措辞整族禁入题面与正确做法（争议 token 门拦截）。
- **jury 单源#8（未裁决）**：「救总工期只能压缩关键工作」表述过硬——组 D 只做
  五类调整方法的封闭清单成员判断，不生成「压非关键=不妥」类判定。
- **jury 单源#5（未裁决）**：虚工作「只表达逻辑、不耗时间/资源」定义锚不足——
  组 G 只用保 🟢 的「补虚工作/调节点」动作层（{2015,案例1} 直读锚），
  「不耗时间/不消耗资源」措辞禁入池。
- **§8.2 C1/C4 邻接**：优化/赶工/压缩费率归 N02、流水施工归 N03——token 禁入池。
- **§8.2 C2 编造防御**：2015 案例1 的「C 工作总时差 1 月/E 总时差 4 月」为虚构
  已删——组 C 数值单元只用证据包直读核真的 {2018}(3月/1月)、{2020,问题3}(3天/2天)、
  {2018}(管道 TF=0) 三个真题数值单元，不外推其他数值组合。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值（「漏列并列关键线路=不妥」由 §3 R2 不变量 jury HI#1 已采纳
  措辞「线路漏一条…即丢分/三者缺一即不妥」+ {2015,案例1}/{2020,案例二问题2} 支撑）。
- **§4 S7（MCQ 场景）真题暂未直命标 🔴**——pack 明示「可作变题备料，不充真题锚」，
  组 E/F 只挂 🟢 教材锚（kc:1A433000_061_0091:0 / kc:1A433000_055_0084:0），
  不冒充真题锚。

用法::

    python3 scripts/build_luban_n01_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_n01_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_N01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "N01_网络计划关键线路.md"

SCHEMA_NAME = "luban-n01-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 N01 Pack §4 R4 / §5 / §6，锚随行）────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼工程", "某厂房工程")

# 规则组 A：关键线路识别/表达（锚 kc:1A433000_056_0085:1；多条印证 {2015,案例1}、
# {2020,案例二问题2}；单条印证 {2017,案例一}）
_ANCHOR_A_MULTI = "kc:1A433000_056_0085:1 + {2015,案例1} + {2020,案例二问题2}"
_ANCHOR_A_EXPR = "kc:1A433000_056_0085:1 + {2017,案例一}"
_CORRECT_A = (
    "并列最长路径必须全部列出（2015/2020 均两条）；线路须落到具体线路且节点"
    "连续无跳号；关键工作按「总时差最小」判据判定并落到具体工作"
)

# 规则组 B：总工期表达（锚 {2015,案例1}(T=5+7+5+4+4=25 个月)、{2017,案例一}；
# 「沿非关键线路求和/只写数字不给线路」为 §6 M4 锚定误区）
_ANCHOR_B = "{2015,案例1} + {2017,案例一} + kc:1A433000_056_0085:1"
_CORRECT_B = "总工期 = 关键线路上各工作持续时间之和，答案须「线路 + 算式 + 单位」三件齐全"

# 规则组 C：延误影响判读（封闭判定树，锚 {2018,案例分析(二)问题1-4}、
# {2020,案例二问题3}；数值单元逐字来自证据包直读核真的真题，不外推）
_DELAY_CELLS = (
    {"name": "甲供电缆安装", "tf": 3, "delay": 1, "unit": "个月", "on_critical": False,
     "anchor": "{2018,案例分析(二)问题1-4}"},
    {"name": "D 工作", "tf": 3, "delay": 2, "unit": "天", "on_critical": False,
     "anchor": "{2020,案例二问题3}"},
)
_CRITICAL_CELL = {"name": "管道安装", "tf": 0, "unit": "个月",
                  "anchor": "{2018,案例分析(二)问题1-4} + kc:1A433000_056_0085:1"}
_CORRECT_C = (
    "延误 ≤ 该工作总时差则不影响总工期；延误工作在关键线路上（总时差为 0）"
    "或延误超过总时差则影响总工期，必须比较「延误 vs 总时差」后下结论"
)

# 规则组 D：进度调整方法（封闭方法集，锚 kc:1A433000_061_0092:0 + {2025,参考答案(二)}）
_ADJUST_METHODS = ("关键工作调整", "逻辑关系调整", "重新编制计划", "非关键工作调整", "资源调整")
_ANCHOR_D = "kc:1A433000_061_0092:0 + {2025,参考答案(二)}"
_CORRECT_D = ("进度计划调整方法为封闭五类：关键工作调整（重点）/逻辑关系调整/"
              "重新编制计划/非关键工作调整/资源调整")

# 规则组 E：进度监测内容（封闭枚举，锚 kc:1A433000_061_0091:0；S7 真题未直命标 🔴，
# pack 明示「作变题备料」——只挂教材锚）
_MONITOR_ITEMS = ("记录实际时间", "观测关键线路", "检查非关键工作", "核查逻辑关系", "收集变更")
_ANCHOR_E = "kc:1A433000_061_0091:0"
_CORRECT_E = ("进度监测内容为封闭枚举：记录实际时间/观测关键线路/检查非关键工作/"
              "核查逻辑关系/收集变更")

# 规则组 F：应用程序顺序（锚 kc:1A433000_055_0084:0 + kc:LEC_1A433000_P0018_001:0；
# 错误步骤示例逐字来自 §6 M8（jury HI#2 已采纳补入））
_ANCHOR_F = "kc:1A433000_055_0084:0 + kc:LEC_1A433000_P0018_001:0"
_CORRECT_F = ("应按「绘图（含补虚工作）→ 计算时间参数（各路径长/时差）→ 确定关键线路"
              "→ 编制/实施」顺序进行，顺序不可乱")

# 规则组 G：网络逻辑修正/虚工作（锚 {2015,案例1} 直读「3—4 之间增加一个虚工作」+
# kc:LEC_1A433000_P0018_001:0；只用「补虚工作/调节点」动作层，jury#5 争议定义禁入）
_ANCHOR_G = "{2015,案例1} + kc:LEC_1A433000_P0018_001:0"
_CORRECT_G = ("题干紧前逻辑不全应先补虚工作/调节点（2015：3—4 之间增加一个虚工作），"
              "再在正确的网络图上计算关键线路")


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"N01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：关键线路识别/表达（R4 组 A 显式判分边界逐条，不外推其他表达缺陷）
    add("A-line", "网络计划有两条并列关键线路，项目部将两条线路全部列出，节点连续无跳号",
        {"lines_total": 2, "lines_listed": 2, "concrete_path": True, "nodes_continuous": True},
        True, _CORRECT_A, _ANCHOR_A_MULTI)
    add("A-line", "网络计划有两条并列关键线路，项目部只列出其中一条",
        {"lines_total": 2, "lines_listed": 1, "concrete_path": True, "nodes_continuous": True},
        False, _CORRECT_A, _ANCHOR_A_MULTI)
    add("A-line", "项目部答题只写「最长的线路就是关键线路」，未写出具体线路",
        {"lines_total": 1, "lines_listed": 1, "concrete_path": False, "nodes_continuous": True},
        False, _CORRECT_A, _ANCHOR_A_EXPR)
    add("A-line", "项目部写出的关键线路节点跳号、前后不连续",
        {"lines_total": 1, "lines_listed": 1, "concrete_path": True, "nodes_continuous": False},
        False, _CORRECT_A, _ANCHOR_A_EXPR)
    add("A-line", "网络计划关键线路为单条，项目部完整写出该线路，节点连续无跳号",
        {"lines_total": 1, "lines_listed": 1, "concrete_path": True, "nodes_continuous": True},
        True, _CORRECT_A, _ANCHOR_A_EXPR)
    add("A-line", "项目部以「总时差最小」作为关键工作判定依据，并落到具体工作",
        {"criterion": "总时差最小", "grounded": True},
        True, _CORRECT_A, "kc:1A433000_056_0085:1")
    add("A-line", "项目部只写「关键工作 = 总时差最小的工作」，未落到本网络图的具体工作",
        {"criterion": "总时差最小", "grounded": False},
        False, _CORRECT_A, "kc:1A433000_056_0085:1")

    # 组 B：总工期表达（完整三件 + §6 M4 两个锚定误区，不外推其他表达缺陷）
    add("B-expr", "项目部按「关键线路 + 算式 + 单位」给出总工期：T=5+7+5+4+4=25 个月",
        {"sum_along": "critical", "has_path": True, "has_formula": True, "has_unit": True},
        True, _CORRECT_B, _ANCHOR_B)
    add("B-expr", "项目部计算总工期时，沿一条非关键线路将各工作持续时间求和",
        {"sum_along": "noncritical", "has_path": True, "has_formula": True, "has_unit": True},
        False, _CORRECT_B, _ANCHOR_B)
    add("B-expr", "项目部的总工期答案只写一个数字，不给出线路与算式",
        {"sum_along": "critical", "has_path": False, "has_formula": False, "has_unit": True},
        False, _CORRECT_B, _ANCHOR_B)

    # 组 C：延误影响判读——真题数值单元 × 双极性判定（只判「影响总工期」，索赔结论
    # jury#6/#7 未裁决禁入）
    for cell in _DELAY_CELLS:
        base = (f"{cell['name']}有 {cell['tf']} {cell['unit']}总时差（非关键工作），"
                f"实际延误 {cell['delay']} {cell['unit']}")
        add("C-delay", f"{base}，项目部判定该延误不影响总工期",
            {"on_critical": cell["on_critical"], "tf": cell["tf"], "delay": cell["delay"],
             "claim_affects": False}, True, _CORRECT_C, cell["anchor"])
        add("C-delay", f"{base}，项目部据此判定总工期将被拖延",
            {"on_critical": cell["on_critical"], "tf": cell["tf"], "delay": cell["delay"],
             "claim_affects": True}, False, _CORRECT_C, cell["anchor"])
    add("C-delay", "管道安装位于关键线路上（总时差为 0），项目部判定其延误将影响总工期",
        {"on_critical": True, "tf": 0, "delay": None, "claim_affects": True},
        True, _CORRECT_C, _CRITICAL_CELL["anchor"])
    add("C-delay", "管道安装位于关键线路上（总时差为 0），项目部认为其仍有机动时间，延误不影响总工期",
        {"on_critical": True, "tf": 0, "delay": None, "claim_affects": False},
        False, _CORRECT_C, _CRITICAL_CELL["anchor"])

    # 组 D：进度调整方法——封闭五类 × 成员判断双极性
    for method in _ADJUST_METHODS:
        add("D-adjust", f"进度检查发现偏差需调整计划，项目部将「{method}」列为可用的调整方法",
            {"method": method, "listed_as_method": True}, True, _CORRECT_D, _ANCHOR_D)
        add("D-adjust", f"项目部认为「{method}」不属于进度计划的调整方法",
            {"method": method, "listed_as_method": False}, False, _CORRECT_D, _ANCHOR_D)

    # 组 E：进度监测内容——封闭枚举 × 成员判断双极性（纯枚举层，只挂教材锚）
    for item in _MONITOR_ITEMS:
        add("E-monitor", f"进度计划实施监测中，项目部将「{item}」列入监测内容",
            {"item": item, "listed_as_content": True}, True, _CORRECT_E, _ANCHOR_E)
        add("E-monitor", f"项目部认为「{item}」不属于进度计划实施监测的内容",
            {"item": item, "listed_as_content": False}, False, _CORRECT_E, _ANCHOR_E)

    # 组 F：应用程序顺序——正序 + §6 M8 显式点名的两个顺序违例（不外推其他乱序）
    add("F-procedure", "项目部按「绘图（含补虚工作）→ 计算时间参数 → 确定关键线路 → 编制/实施」"
        "顺序应用网络计划", {"violation": None}, True, _CORRECT_F, _ANCHOR_F)
    add("F-procedure", "项目部未绘图、未补全网络逻辑，就直接套公式计算时间参数",
        {"violation": "未绘图先算参数"}, False, _CORRECT_F, _ANCHOR_F)
    add("F-procedure", "项目部跳过「计算时间参数」阶段，直接确定关键线路",
        {"violation": "跳过计算参数"}, False, _CORRECT_F, _ANCHOR_F)

    # 组 G：网络逻辑修正/虚工作——2015 锚定情节 × 处理/不处理 × 皮×2
    logic_cases = (
        ("项目部在 3—4 节点间增设虚工作补全逻辑后，再计算关键线路", True),
        ("项目部未调整网络图，直接在原图上计算关键线路", False),
    )
    for skin, (action, adjusted) in itertools.product(_SITE_SKINS, logic_cases):
        add("G-logic", f"{skin}双代号网络计划中新增紧前关系：工作 F 须 B、C 均完成后"
            f"方可开始。{action}",
            {"logic_added": True, "graph_adjusted": adjusted}, adjusted,
            _CORRECT_G, _ANCHOR_G)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-line":
        if "criterion" in p:
            return p["criterion"] == "总时差最小" and bool(p["grounded"])
        return (bool(p["concrete_path"]) and bool(p["nodes_continuous"])
                and p["lines_listed"] == p["lines_total"])
    if g == "B-expr":
        return (p["sum_along"] == "critical" and bool(p["has_path"])
                and bool(p["has_formula"]) and bool(p["has_unit"]))
    if g == "C-delay":
        affects = bool(p["on_critical"]) or (p["delay"] is not None and p["delay"] > p["tf"])
        return p["claim_affects"] == affects
    if g == "D-adjust":
        if p["method"] not in _ADJUST_METHODS:
            return None  # 枚举外方法不许出现(封闭域)
        return bool(p["listed_as_method"])
    if g == "E-monitor":
        if p["item"] not in _MONITOR_ITEMS:
            return None  # 枚举外条目不许出现(封闭域)
        return bool(p["listed_as_content"])
    if g == "F-procedure":
        return p["violation"] is None
    if g == "G-logic":
        return bool(p["graph_adjusted"])
    return None


# 争议/🔵推理/邻接层 token，禁入题面与正确做法（fail-closed）：
# 索赔=jury#6/#7 未裁决(结论降🔵)；优化/赶工/费率=N02 邻接(§8.2 C1)；流水=N03 邻接(C4)；
# 不耗时间/不消耗=jury#5 虚工作定义锚不足；满分/压线=R7 🔴 档位措辞
_CONTESTED_TOKENS = ("索赔", "优化", "赶工", "费率", "流水", "不耗时间", "不消耗", "满分", "压线")


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
        "pack_id": "N01",
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
