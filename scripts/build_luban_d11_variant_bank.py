#!/usr/bin/env python3
"""D11 变体池编译期预生成器（抹灰工序与质量控制）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本承接 S05 / F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`），
纯确定性枚举（零 LLM、零随机、零时间依赖），从 D11 Pack §4 R4 四个封闭规则组
（A 厚度与加强 / B 交接处防裂 / C 基层含水率 / D 环境温度与材料）派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（数值/对象/部位在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 D11 pack 裁决）：
- **§8.3 编译库覆盖薄**：砂浆配合比 / 底中面三层工序 / 护角阳角 / 墙面抹灰层
  空鼓防治程序**零专用锚（🔴 待补 GB50210 编译）**——整族禁入池（争议 token 门拦截）。
- **jury #7**：「<35mm 仍强行加强 = 不妥」反向规则过封闭、缺教材依据——本池
  **不生成** "<35mm 却加强" 的判定变体（独立校验器对该组合返回 None，fail-closed）。
- **jury #6**：「分层+挂网」措施展开无 quote 支撑，降讲解性——禁入题面与正确
  做法，加强措施只用教材原文「应采取加强措施」。
- **jury HI#1**：层厚用真题原文「平均总厚度」（非"底中面单层"），层厚(≤20/≤25mm)
  与温度(≥5℃) 仅真题单锚 `{2023,第26题}`，锚如实标真题侧不冒充教材锚。
- **§5 E1 涂饰工序衔接为 🔵 外延（涂饰 territory）**——不入池（其判定无法由
  D11 🟢 锚规则推导，无 F16 组 D 式安全外延路径）。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_d11_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_d11_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_D11_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "D11_抹灰工序与质量控制.md"

SCHEMA_NAME = "luban-d11-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 D11 Pack §4 R4 / §5 / §6，锚随行）───────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点，≤2 照先例）
_SITE_SKINS = ("某住宅楼工地", "某办公楼项目")

# 规则组 A：抹灰厚度与加强（锚 kc:1A422000_042_0068:0 + {2023,第26题}）
# 题面厚度值全部 pack 内：20/25mm=R4 层厚封闭值、35mm=R4 加强阈值、40mm=§6 M1 误区值
_REINFORCE_THRESHOLD_MM = 35
_THICK_SURFACES_MM = (20, 35, 40)
_ANCHOR_A_THICK = "kc:1A422000_042_0068:0 + {2023,第26题}"
_CORRECT_A_THICK = "抹灰总厚度≥35mm时应采取加强措施"
# 规则组 A：层厚上限（真题锚 {2023,第26题}D/E，真题原文"平均总厚度"·教材库缺卡）
_LAYER_LIMITS = ({"grade": "普通", "limit_mm": 20}, {"grade": "高级", "limit_mm": 25})
_LAYER_SURFACES_MM = (20, 25, 30)  # 20/25=R4 封闭值；30=§6 M4 误区值（pack 内）
_ANCHOR_A_LAYER = "{2023,第26题}"
_CORRECT_A_LAYER = "内墙普通抹灰层平均总厚度不大于20mm；高级抹灰层平均总厚度不大于25mm"

# 规则组 B：不同材料基体交接处防裂（锚 kc:1A422000_042_0068:0 +
# kc:1A422000_043_0069:0 + {2023,第26题}C；搭接错值 50/80mm=R4 判分边界点名）
_LAP_THRESHOLD_MM = 100
_LAP_SURFACES_MM = (50, 80, 100)
_ANCHOR_B = "kc:1A422000_042_0068:0 + kc:1A422000_043_0069:0 + {2023,第26题}C"
_CORRECT_B = "不同材料基体交接处应设加强网，加强网与各基体搭接宽度不应小于100mm"

# 规则组 C：基层含水率（封闭·分对象，锚 kc:1A422000_043_0069:1）
_MOIST_CELLS = (
    {"base": "混凝土墙面基层拟涂刷溶剂型涂料", "obj": "溶剂型涂料基层", "limit_pct": 8},
    {"base": "抹灰基层拟涂刷乳液型涂料", "obj": "乳液型涂料基层", "limit_pct": 10},
    {"base": "木材基层", "obj": "木材基层", "limit_pct": 12},
)
_MOIST_SURFACES_PCT = (8, 10, 12)  # 题面可出现的含水率值(封闭，全部来自 R4 组 C)
_ANCHOR_C = "kc:1A422000_043_0069:1"
_CORRECT_C = "基层含水率分对象控制：混凝土/抹灰基层用溶剂型涂料≤8%、乳液型涂料≤10%、木材基层≤12%"

# 规则组 D：室内抹灰环境温度（真题锚 {2023,第26题}A；0℃=真题错值、5℃=下限）
_TEMP_THRESHOLD_C = 5
_TEMP_SURFACES_C = (0, 5)
_ANCHOR_D_TEMP = "{2023,第26题}A"
_CORRECT_D_TEMP = "室内抹灰环境温度一般不低于5℃"

# 规则组 D：耐水腻子部位（锚 kc:1A422000_043_0069:2 + {2018,第24题} + {2022,第21题}）
_WET_PLACES = ("厨房", "卫生间", "地下室")  # {2018,第24题}ABE/{2022,第21题}BCE 封闭部位
_GENERAL_PLACES = ("卧室", "客厅")  # 真题干扰项部位（一般环境）
_ANCHOR_D_PUTTY = "kc:1A422000_043_0069:2 + {2018,第24题} + {2022,第21题}"
_CORRECT_D_WET = "厨房/卫生间/地下室等潮湿部位墙面找平层应使用耐水腻子"
_CORRECT_D_GENERAL = (
    "耐水腻子用于厨房/卫生间/地下室等潮湿部位；卧室/客厅等一般环境可用普通腻子，"
    "强行要求耐水腻子属过度"
)


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"D11-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：总厚度加强——厚度×(加强/未加强)；"<35mm 却加强"组合按 jury#7 过封闭裁定
    # 整档不生成（fail-closed），只枚举 R4 显式边界「≥35mm 不加强 = 不妥」两个方向
    for t in _THICK_SURFACES_MM:
        if t >= _REINFORCE_THRESHOLD_MM:
            add("A-thick", f"墙面抹灰总厚度 {t}mm，项目部采取了加强措施",
                {"thickness_mm": t, "reinforced": True}, True,
                _CORRECT_A_THICK, _ANCHOR_A_THICK)
        add("A-thick", f"墙面抹灰总厚度 {t}mm，项目部未采取加强措施",
            {"thickness_mm": t, "reinforced": False},
            t < _REINFORCE_THRESHOLD_MM, _CORRECT_A_THICK, _ANCHOR_A_THICK)
    # 组 A：不分档政策（一律不加强 = 不妥，照 S05/F16 policy 先例）
    add("A-policy", "项目部规定：墙面抹灰不论总厚度大小，一律不采取加强措施",
        {"uniform_no_reinforce": True}, False, _CORRECT_A_THICK, _ANCHOR_A_THICK)

    # 组 A：层厚上限——等级×题面层厚全枚举（真题原文"平均总厚度"）
    for cell, mm in itertools.product(_LAYER_LIMITS, _LAYER_SURFACES_MM):
        add("A-layer",
            f"内墙{cell['grade']}抹灰工程，抹灰层平均总厚度做到 {mm}mm",
            {"grade": cell["grade"], "layer_mm": mm, "limit_mm": cell["limit_mm"]},
            mm <= cell["limit_mm"], _CORRECT_A_LAYER, _ANCHOR_A_LAYER)

    # 组 B：交接处防裂——不设网 + (皮×搭接宽度)枚举
    add("B-mesh", "混凝土柱与砖墙交接处抹灰，项目部未设加强网",
        {"has_mesh": False, "lap_mm": None}, False, _CORRECT_B, _ANCHOR_B)
    for skin, lap in itertools.product(_SITE_SKINS, _LAP_SURFACES_MM):
        add("B-lap",
            f"{skin}混凝土柱与砖墙交接处抹灰设加强网，加强网与各基体搭接宽度 {lap}mm",
            {"has_mesh": True, "lap_mm": lap}, lap >= _LAP_THRESHOLD_MM,
            _CORRECT_B, _ANCHOR_B)

    # 组 C：基层含水率——对象×题面含水率全枚举
    for cell, pct in itertools.product(_MOIST_CELLS, _MOIST_SURFACES_PCT):
        add("C-moist", f"{cell['base']}，实测基层含水率 {pct}%，随即进行下道施工",
            {"obj": cell["obj"], "surface_pct": pct, "limit_pct": cell["limit_pct"]},
            pct <= cell["limit_pct"], _CORRECT_C, _ANCHOR_C)

    # 组 D：环境温度——皮×温度枚举
    for skin, c in itertools.product(_SITE_SKINS, _TEMP_SURFACES_C):
        add("D-temp", f"{skin}室内抹灰在环境温度 {c}℃ 条件下施工",
            {"temp_c": c, "threshold_c": _TEMP_THRESHOLD_C}, c >= _TEMP_THRESHOLD_C,
            _CORRECT_D_TEMP, _ANCHOR_D_TEMP)

    # 组 D：耐水腻子——潮湿部位×材料双极性 + 一般环境双极性
    for place in _WET_PLACES:
        add("D-putty", f"{place}墙面找平层使用耐水腻子",
            {"place": place, "material": "耐水腻子", "mandate_waterproof": False},
            True, _CORRECT_D_WET, _ANCHOR_D_PUTTY)
        add("D-putty", f"{place}墙面找平层使用普通腻子",
            {"place": place, "material": "普通腻子", "mandate_waterproof": False},
            False, _CORRECT_D_WET, _ANCHOR_D_PUTTY)
    for place in _GENERAL_PLACES:
        add("D-putty", f"{place}墙面找平层使用普通腻子",
            {"place": place, "material": "普通腻子", "mandate_waterproof": False},
            True, _CORRECT_D_GENERAL, _ANCHOR_D_PUTTY)
        add("D-putty", f"项目部规定：{place}墙面找平层必须使用耐水腻子",
            {"place": place, "material": "耐水腻子", "mandate_waterproof": True},
            False, _CORRECT_D_GENERAL, _ANCHOR_D_PUTTY)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-thick":
        if p["reinforced"]:
            # jury#7：<35mm 却加强 属过封闭档，禁入池 → None 触发 gate FAIL
            return True if p["thickness_mm"] >= _REINFORCE_THRESHOLD_MM else None
        return p["thickness_mm"] < _REINFORCE_THRESHOLD_MM
    if g == "A-policy":
        return False if p.get("uniform_no_reinforce") else None
    if g == "A-layer":
        limit = {"普通": 20, "高级": 25}.get(p["grade"])
        return None if limit is None else p["layer_mm"] <= limit
    if g in ("B-mesh", "B-lap"):
        if not p["has_mesh"]:
            return False
        return p["lap_mm"] is not None and p["lap_mm"] >= _LAP_THRESHOLD_MM
    if g == "C-moist":
        limit = {"溶剂型涂料基层": 8, "乳液型涂料基层": 10, "木材基层": 12}.get(p["obj"])
        return None if limit is None else p["surface_pct"] <= limit
    if g == "D-temp":
        return p["temp_c"] >= _TEMP_THRESHOLD_C
    if g == "D-putty":
        if p["place"] in _WET_PLACES:
            return p["material"] == "耐水腻子"
        if p["place"] in _GENERAL_PLACES:
            if p.get("mandate_waterproof"):
                return False  # 一般环境强行要求耐水腻子 = 过度(R4 组 D 判分边界)
            return p["material"] == "普通腻子"
        return None  # 部位封闭域外禁入
    return None


# 争议/🔵外延/🔴无锚层 token，禁入题面与正确做法（fail-closed）：
# 砂浆配比/底中面/护角/阳角/空鼓=§8.3 编译库零锚待补 GB50210；分层/挂网=jury#6 无 quote
# 措施展开；薄抹灰/外保温=§0 邻接①外保温系统；地面板块=D14/填充墙=C06 territory(§8.2 C3)；
# 涂饰=🔵外延 territory(§5 E1)；养护=R7 0分示例空泛措辞，无 D11 锚
_CONTESTED_TOKENS = ("砂浆", "配合比", "底中面", "护角", "阳角", "空鼓", "分层", "挂网",
                     "薄抹灰", "外保温", "地面板块", "填充墙", "涂饰", "养护")


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
        "pack_id": "D11",
        "status": "candidate",  # 教研审核+判分内核回路核验后方可签发入池
        "source_pack_sha256": hashlib.sha256(PACK_PATH.read_bytes()).hexdigest(),
        "generation_ms": round(gen_ms, 2),
        "gate": gate,
        "per_group_counts": {g: sum(1 for v in variants if v["rule_group"] == g)
                             for g in sorted({v["rule_group"] for v in variants})},
        "variants": variants,
    }
    # 重建保留合并：按 variant_id + content_sha256 原位保留已签 decision 块，
    # 内容/pack 漂移的条目置回 pending + stale（绝不静默保留旧签名）——镜像
    # practice publisher `_load_practice_review_records` 的人审保留模式。
    # 惰性导入：--check 门保持零依赖（promote gate 重跑不受服务层影响）。
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from deeptutor.services.luban_lesson.variant_eligibility import (
        carry_variant_bank_decisions,
    )

    carried = carry_variant_bank_decisions(OUT_PATH, payload)
    if any(carried.values()):
        print(f"decision blocks: preserved={carried['preserved']} "
              f"stale_reset={carried['stale']} dropped={carried['dropped']}")
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {OUT_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
