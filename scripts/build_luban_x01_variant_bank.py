#!/usr/bin/env python3
"""X01 变体池编译期预生成器（施工平面布置原则）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本沿 F16 先例
（`scripts/build_luban_f16_variant_bank.py`）同构——纯确定性枚举（零 LLM、零随机），
从 X01 Pack §4 R4 六个封闭规则组（A~F）派生变体，自带独立一致性检查门
（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（清单成员/数量/高度/顺序在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 X01 pack 裁决）：
- **jury 单源#3 未裁决**：施工升降机因素「围栏」无 quote 支撑（真题侧增补）——
  升降机封闭因素域**剔除「围栏」**，token 禁入池。
- **jury 单源#5 未裁决**：「路口 20m 内 0.8m 以上通透性围挡」的 quote 实为冲洗设施、
  未覆盖该数字——组 E **整档剔除路口通透档**（只保留 2.5m/1.8m 两个路段档），
  「通透」「0.8m」token 禁入池。
- **§8.2 C2/C4 镜头 A 自造情节**：「木工堆场火灾/电杆 7.5m/碘钨灯」「钢构件堆场
  基本条件」均证据包外核真证伪已删——token（7.5m/碘钨灯/钢构件）禁入池。
- **§8.2 C3/C5**：「五牌一图内侧」无据断言已删、「空间心理学」等机理外推降 🔵——
  token（内侧/心理学）禁入池；环保/扬尘管理属 X03 territory，「扬尘」禁入。
- **R3 场景 S6/S7（塔吊/大门）标 🔴 = 真题暂未直命**（非编造、非取值域存疑）：
  其 R4 因素域 `kc:1A431011_011_0012:2/:3` 为 🟢 教材锚且 pack 封闭性自检明示
  「判分边界全部可机械裁决」——入池为核心（教材锚 🟢），报告已留痕。
- **组 F 垂直运输设备辨识**（jury 单源#4）：支撑=真题锚直接（{2020,第27题} 已核真）、
  教材锚间接——锚只挂真题锚，不冒充教材直推。
- **组 D 布置步骤**：R4 只给封闭顺序、无点名漏步——只枚举完整正序 + 顺序违例（相邻
  对调），**不外推漏步组合**（照 F16 jury 残留#5 的"只枚举点名项"纪律）。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望判定
  只有妥/不妥二值。

用法::

    python3 scripts/build_luban_x01_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_x01_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_X01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "X01_施工平面布置原则.md"

SCHEMA_NAME = "luban-x01-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 X01 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼工地", "某厂房项目现场")

# 规则组 A：施工总平面图内容六项（锚 kc:1A431011_011_0012:0 + ca:1A431011_011_0012）
_CONTENT_ITEMS = (
    "地形状况", "拟建建构筑物位置", "加工运输储存设施",
    "临时道路办公生活用房", "安全消防环保设施", "周边既有建筑环境",
)
_ANCHOR_A = "kc:1A431011_011_0012:0 + ca:1A431011_011_0012"
_CORRECT_A = ("施工总平面布置图内容应含六项：地形状况、拟建建构筑物位置、加工运输"
              "储存设施、临时道路办公生活用房、安全消防环保设施、周边既有建筑环境，"
              "漏项即不全")

# 规则组 B：设计原则七条（锚 kc:1A431011_011_0012:1；判分边界：只写「合理布置/
# 科学规划」=口号化不得分）
_PRINCIPLES = (
    "占地少", "运输合理(减少二次搬运)", "减少干扰", "利用既有设施",
    "分区设置", "环保安全", "遵守规定",
)
_ANCHOR_B = "kc:1A431011_011_0012:1"
_CORRECT_B = ("施工总平面图设计原则七条：占地少、运输合理(减少二次搬运)、减少干扰、"
              "利用既有设施、分区设置、环保安全、遵守规定；布置理由须落到这七条的"
              "因果句，只写「合理布置/科学规划」=口号化不得分")

# 规则组 C：各设施布置考虑因素（封闭因素表，禁混搭别设施）
# 升降机域按 jury 单源#3 fail-closed 剔除「围栏」（无 quote 支撑未裁决）
_FACILITY_FACTORS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "大门": (("路网", "转弯半径", "坡度", "车辆运输"),
             "kc:1A431011_011_0012:2",
             "大门宜设≥2个，考虑路网、转弯半径、坡度，满足车辆运输"),
    "塔吊": (("基础", "环境", "覆盖范围", "吊重", "运输堆放", "附墙位置",
              "拆除运输", "群塔防撞"),
             "kc:1A431011_011_0012:3",
             "塔吊布置八因素：基础、环境、覆盖范围、吊重、运输堆放、附墙位置、"
             "拆除运输、群塔防撞，缺项即不全"),
    "混凝土泵": (("泵管输送距离", "罐车停靠", "立管固定", "泵车可流动"),
                 "kc:1A431011_011_0012:4",
                 "混凝土泵布置考虑泵管输送距离、罐车停靠、立管固定牢固，泵车可流动"),
    "施工升降机": (("地基承载力", "平整度", "排水", "附墙位置", "楼层通道", "防护门"),
                   "kc:1A431011_011_0012:5 + {2021,案例二} + {2025,案例二}",
                   "施工升降机布置考虑地基承载力、平整度、排水、附墙位置、楼层通道、"
                   "防护门"),
}

# 规则组 C 数量档：大门宜设 ≥2 个（锚 kc:1A431011_011_0012:2）
_GATE_MIN = 2
_GATE_COUNTS = (1, 2, 3)  # 题面可出现的大门数量(封闭·皮)
_CORRECT_GATE = "现场宜设置≥2个大门（考虑路网、转弯半径、坡度，满足车辆运输）"

# 规则组 D：临时设施平面布置步骤（封闭顺序，锚 ca:1A431011_012_0013 + {2021,案例二}）
_STEPS_CANONICAL = (
    "布置仓库堆场", "布置加工厂", "布置场内临时运输道路",
    "布置临时房屋", "布置临时水电管网",
)
_ANCHOR_D = "ca:1A431011_012_0013 + {2021,案例二}"
_CORRECT_D = "临时设施平面布置步骤应为：" + "→".join(_STEPS_CANONICAL) + "，顺序不得错乱"

# 规则组 E：围挡高度分路段（锚 kc:1A431011_013_0014:0；路口 20m/0.8m 通透档因
# jury 单源#5 未裁决整档剔除）
_FENCE_THRESHOLDS_M = {"市区主要路段": 2.5, "一般路段": 1.8}
_FENCE_SURFACES_M = {"市区主要路段": (1.8, 2.0, 2.5, 3.0),  # 题面可出现的高度(封闭·皮)
                     "一般路段": (1.5, 1.8, 2.5)}
_ANCHOR_E = "kc:1A431011_013_0014:0 + ca:1A431011_013_0014"
_CORRECT_E = "围挡高度：市区主要路段≥2.5m、一般路段≥1.8m，不得混淆路段档位"

# 规则组 E：五牌一图六项（锚 kc:1A431011_013_0014:1 + {2017,案例三}）
_BOARD_ITEMS = (
    "工程概况牌", "消防保卫牌", "安全生产牌", "文明施工牌",
    "管理人员名单及监督电话牌", "施工现场总平面图",
)
_ANCHOR_BOARDS = "kc:1A431011_013_0014:1 + {2017,案例三}"
_CORRECT_BOARDS = ("主要出入口五牌一图应含：工程概况牌、消防保卫牌、安全生产牌、"
                   "文明施工牌、管理人员名单及监督电话牌 + 施工现场总平面图，漏项不全")

# 规则组 F：垂直运输设备辨识（锚 {2020,第27题}——jury 单源#4：支撑=真题锚直接，
# 教材锚间接，故只挂真题锚）
_VERT_EQUIPMENT = ("塔式起重机", "施工电梯", "物料提升架", "混凝土泵")
_NON_VERT = "吊篮"
_ANCHOR_F = "{2020,第27题}"
_CORRECT_F = ("垂直运输设备 = 塔式起重机/施工电梯/物料提升架/混凝土泵；"
              "吊篮属高处作业设备，不属垂直运输设备")


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"X01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：图内容六项——成员判断双极性（照 F16 组 C 范式）
    for item in _CONTENT_ITEMS:
        add("A-content", f"项目部将「{item}」列入施工总平面布置图内容",
            {"item": item, "listed": True}, True, _CORRECT_A, _ANCHOR_A)
        add("A-content", f"项目部认为「{item}」不属于施工总平面布置图内容",
            {"item": item, "listed": False}, False, _CORRECT_A, _ANCHOR_A)

    # 组 B：设计原则七条——成员判断双极性
    for item in _PRINCIPLES:
        add("B-principle", f"项目部将「{item}」列为施工总平面图设计原则",
            {"item": item, "listed": True}, True, _CORRECT_B, _ANCHOR_B)
        add("B-principle", f"项目部认为「{item}」不属于施工总平面图设计原则",
            {"item": item, "listed": False}, False, _CORRECT_B, _ANCHOR_B)
    # 组 B：口号化（R4 判分边界显式点名：只写「合理布置/科学规划」不得分）
    for skin in _SITE_SKINS:
        add("B-slogan",
            f"{skin}平面布置方案对各设施布置理由统一只写「合理布置、科学规划」",
            {"slogan_only": True}, False, _CORRECT_B, _ANCHOR_B)

    # 组 C：各设施布置考虑因素——(设施×因素)成员判断双极性（禁混搭别设施）
    for fac, (factors, anchor, correct) in _FACILITY_FACTORS.items():
        for factor in factors:
            add("C-factor", f"布置{fac}时，项目部将「{factor}」列入考虑因素",
                {"facility": fac, "factor": factor, "listed": True}, True,
                correct, anchor)
            add("C-factor", f"项目部认为布置{fac}无需考虑「{factor}」",
                {"facility": fac, "factor": factor, "listed": False}, False,
                correct, anchor)

    # 组 C：大门数量档（宜设 ≥2 个）
    for n in _GATE_COUNTS:
        add("C-gate-count", f"施工现场共设置 {n} 个大门",
            {"gate_count": n}, n >= _GATE_MIN, _CORRECT_GATE,
            "kc:1A431011_011_0012:2")

    # 组 D：布置步骤——完整正序 + 顺序违例（相邻对调，不外推漏步组合）
    seq_cases: list[tuple[str, list[str]]] = [("complete", list(_STEPS_CANONICAL))]
    swap1 = list(_STEPS_CANONICAL)
    swap1[0], swap1[1] = swap1[1], swap1[0]          # 先加工厂后仓库堆场
    seq_cases.append(("order:先加工厂后仓库堆场", swap1))
    swap2 = list(_STEPS_CANONICAL)
    swap2[2], swap2[3] = swap2[3], swap2[2]          # 先临时房屋后运输道路
    seq_cases.append(("order:先临时房屋后运输道路", swap2))
    for skin, (kind, steps) in itertools.product(_SITE_SKINS, seq_cases):
        add("D-steps", f"{skin}临时设施平面布置步骤为：{'→'.join(steps)}",
            {"steps": steps, "case": kind}, steps == list(_STEPS_CANONICAL),
            _CORRECT_D, _ANCHOR_D)

    # 组 E：围挡高度分路段——路段×题面高度（路口通透档已 fail-closed 剔除）
    for road, heights in _FENCE_SURFACES_M.items():
        for h in heights:
            add("E-fence", f"{road}施工现场围挡高度设为 {h}m",
                {"road": road, "height_m": h}, h >= _FENCE_THRESHOLDS_M[road],
                _CORRECT_E, _ANCHOR_E)
    # 组 E：不分路段政策（统一 1.8m 违反市区主要路段 ≥2.5m 档）
    add("E-fence", "项目部规定：围挡高度不分路段统一按 1.8m 设置",
        {"uniform_height_m": 1.8}, False, _CORRECT_E, _ANCHOR_E)

    # 组 E：五牌一图六项——成员判断双极性
    for item in _BOARD_ITEMS:
        add("E-boards", f"项目部将「{item}」列入主要出入口的五牌一图",
            {"item": item, "listed": True}, True, _CORRECT_BOARDS, _ANCHOR_BOARDS)
        add("E-boards", f"项目部认为主要出入口五牌一图无需包含「{item}」",
            {"item": item, "listed": False}, False, _CORRECT_BOARDS, _ANCHOR_BOARDS)

    # 组 F：垂直运输设备辨识——封闭集合成员判断（真题锚直接）
    for eq in _VERT_EQUIPMENT:
        add("F-vert", f"备考笔记称「{eq}」属于垂直运输设备",
            {"equipment": eq, "claimed_vertical": True}, True, _CORRECT_F, _ANCHOR_F)
        add("F-vert", f"备考笔记称「{eq}」不属于垂直运输设备",
            {"equipment": eq, "claimed_vertical": False}, False, _CORRECT_F, _ANCHOR_F)
    add("F-vert", f"备考笔记称「{_NON_VERT}」属于垂直运输设备",
        {"equipment": _NON_VERT, "claimed_vertical": True}, False,
        _CORRECT_F, _ANCHOR_F)
    add("F-vert", f"备考笔记称「{_NON_VERT}」属高处作业设备、不属垂直运输设备",
        {"equipment": _NON_VERT, "claimed_vertical": False}, True,
        _CORRECT_F, _ANCHOR_F)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-content":
        if p["item"] not in _CONTENT_ITEMS:
            return None  # 枚举外条目不许出现(封闭域)
        return bool(p["listed"])
    if g == "B-principle":
        if p["item"] not in _PRINCIPLES:
            return None
        return bool(p["listed"])
    if g == "B-slogan":
        return False if p.get("slogan_only") else None  # 口号化不得分
    if g == "C-factor":
        entry = _FACILITY_FACTORS.get(p["facility"])
        if entry is None or p["factor"] not in entry[0]:
            return None  # 跨设施因素不混搭(封闭域外)
        return bool(p["listed"])
    if g == "C-gate-count":
        return p["gate_count"] >= _GATE_MIN
    if g == "D-steps":
        return p["steps"] == list(_STEPS_CANONICAL)
    if g == "E-fence":
        if p.get("uniform_height_m") is not None:
            # 不分路段统一档：须同时满足所有路段阈值，否则不妥
            return all(p["uniform_height_m"] >= t
                       for t in _FENCE_THRESHOLDS_M.values())
        if p["road"] not in _FENCE_THRESHOLDS_M:
            return None
        return p["height_m"] >= _FENCE_THRESHOLDS_M[p["road"]]
    if g == "E-boards":
        if p["item"] not in _BOARD_ITEMS:
            return None
        return bool(p["listed"])
    if g == "F-vert":
        eq = p["equipment"]
        if eq not in _VERT_EQUIPMENT and eq != _NON_VERT:
            return None
        return (eq in _VERT_EQUIPMENT) == bool(p["claimed_vertical"])
    return None


# 争议/🔴编造/未裁决层 token，禁入题面与正确做法（fail-closed）：
# 通透/0.8m=jury#5 未裁决路口档；围栏=jury#3 未裁决升降机因素；
# 碘钨灯/7.5m=§8.2 C2 镜头A自造；内侧=C3 无据断言；钢构件=C4 自造情节；
# 心理学=C5 机理外推降🔵；扬尘=X03 territory 邻接
_CONTESTED_TOKENS = ("通透", "0.8m", "围栏", "碘钨灯", "7.5m", "内侧",
                     "钢构件", "心理学", "扬尘")


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
        "pack_id": "X01",
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
