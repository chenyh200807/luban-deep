#!/usr/bin/env python3
"""S05 变体池编译期预生成器（阶段 1 P0-② 变体产能实测 spike）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本是该红线的第一个实证——纯确定性
枚举（零 LLM、零随机），从 S05 Pack §4 R4 六个封闭规则组派生变体，自带独立
一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（数值/主体/场景在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed）：
- S05 §1 行3 与 §4 规则组C 对「潮湿/隧道/人防」档位记载互相矛盾（jury 单源存疑
  #5 未裁决）——该争议档位**整档不入池**，只用无争议档（金属容器/锅炉 ≤12V 有
  真题锚 {2016,第13题}；手持灯具 ≤36V 有 kc:1A436000_130_0209:0）。
- 30m 间距/碘钨灯为综合纠错外延（jury 高可信#1 降级），入池但标 extension=true，
  消费侧可按核心/外延过滤。

用法::

    python3 scripts/build_luban_s05_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_s05_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_S05_variant_bank.v0.json"

SCHEMA_NAME = "luban-s05-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 S05 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼工地", "某办公楼项目现场", "某厂房施工现场", "某学校教学楼工地")

# 规则组 B：停送电顺序（锚 kc:1A431011_015_0016:1 + {2017,第2题} 语义锚）
_SEND_CORRECT = ("总配电箱", "分配电箱", "开关箱")
_STOP_CORRECT = ("开关箱", "分配电箱", "总配电箱")

# 规则组 C（无争议档 only）：金属容器/锅炉 ≤12V（锚 kc:1A431011_015_0016:2 + {2016,第13题}）
#                          手持灯具 ≤36V（锚 kc:1A436000_130_0209:0）
_VOLTAGE_CELLS = (
    {"place": "金属容器内", "limit_v": 12, "anchor": "kc:1A431011_015_0016:2 + {2016,第13题}"},
    {"place": "锅炉内", "limit_v": 12, "anchor": "kc:1A431011_015_0016:2"},
    {"place": "手持灯具", "limit_v": 36, "anchor": "kc:1A436000_130_0209:0"},
)
_VOLTAGE_SURFACES = (6, 12, 24, 36, 48, 220)  # 题面可出现的电压值(封闭)

# 规则组 D：一机一闸（锚 kc:1A431011_014_0015:2 + {2023,第1题}）
_MACHINES = ("电锯", "钢筋切断机", "混凝土搅拌机", "电焊机")
_SHARE_COUNTS = (1, 2, 3)  # 1=专用(妥), ≥2=共用(不妥)

# 规则组 E：电缆埋深 ≥0.7m（锚 kc:1A431011_014_0015:0）
_BURY_DEPTHS_M = (0.4, 0.5, 0.6, 0.7, 0.8, 1.0)
# 规则组 E：标识色（锚 kc:1A431011_014_0015:1 + {2019,第14题}）N=蓝, PE=黄绿
_COLOR_ASSIGN = (("蓝色", "黄绿双色"), ("黄绿双色", "蓝色"), ("蓝色", "蓝色"))

# 规则组 F：管理制度（锚 kc:1A431011_014_0015:4 + {2018,第17题}/{2023,第1题}）
_MGMT_CASES = (
    {"surface": "电工张某未取得职业资格证即上岗接线", "ok": False,
     "correct": "电工须经职业资格考试合格后持证上岗", "anchor": "kc:1A431011_014_0015:4 + {2018,第17题}"},
    {"surface": "用电设备拆除由安全员完成", "ok": False,
     "correct": "用电设备拆除应由电工完成", "anchor": "{2018,第17题}"},
    {"surface": "现场用电总容量 60kW，未编制用电组织设计", "ok": False,
     "correct": "总容量 50kW 及以上应编制用电组织设计", "anchor": "{2018,第17题}"},
    {"surface": "现场用电总容量 40kW，编制了安全用电和电气防火措施", "ok": True,
     "correct": "50kW 以下编制安全用电和电气防火措施即可", "anchor": "{2018,第17题}"},
    {"surface": "进入装饰装修阶段未补充编制单项施工用电方案", "ok": False,
     "correct": "装饰装修阶段应补充编制单项施工用电方案", "anchor": "{2023,第1题}"},
)

# 外延（综合纠错补充，jury 高可信#1 降级——标 extension）：间距≤30m（{2017,第2题}）
_DIST_SURFACES_M = (25.0, 28.0, 30.0, 30.5, 32.0, 35.0)


def _permutations3(triple: tuple[str, str, str]) -> list[tuple[str, ...]]:
    return [p for p in itertools.permutations(triple)]


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"S05-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 B：停送电顺序——全排列枚举，只有正序为妥
    for skin in _SITE_SKINS[:2]:  # 皮×2 足以换脸, 不为凑数全乘
        for perm in _permutations3(("总配电箱", "分配电箱", "开关箱")):
            add("B-send", f"{skin}送电操作顺序：{'→'.join(perm)}",
                {"order": list(perm), "op": "send"}, perm == _SEND_CORRECT,
                f"送电顺序应为{'→'.join(_SEND_CORRECT)}",
                "kc:1A431011_015_0016:1")
            add("B-stop", f"{skin}停电操作顺序：{'→'.join(perm)}",
                {"order": list(perm), "op": "stop"}, perm == _STOP_CORRECT,
                f"停电顺序应为{'→'.join(_STOP_CORRECT)}",
                "kc:1A431011_015_0016:1 + {2017,第2题}")

    # 组 C：安全电压（无争议档）——场所×题面电压
    for cell, volt in itertools.product(_VOLTAGE_CELLS, _VOLTAGE_SURFACES):
        add("C-voltage", f"{cell['place']}使用 {volt}V 照明",
            {"place": cell["place"], "surface_v": volt, "limit_v": cell["limit_v"]},
            volt <= cell["limit_v"],
            f"{cell['place']}照明电压不得大于 {cell['limit_v']}V",
            cell["anchor"])

    # 组 D：一机一闸——设备×共用台数 + 插头插座
    for machine, count in itertools.product(_MACHINES, _SHARE_COUNTS):
        surface = (f"{machine}单独设置专用开关箱" if count == 1
                   else f"{count} 台{machine}共用一个开关箱")
        add("D-one-switch", surface, {"machine": machine, "share_count": count},
            count == 1, "每台用电设备必须有各自专用的开关箱，严禁 2 台及以上共用",
            "kc:1A431011_014_0015:2 + {2023,第1题}")
    add("D-one-switch", "配电箱电源进线端采用插头插座做活动连接",
        {"plug_socket_inlet": True}, False,
        "配电箱、开关箱电源进线端严禁采用插头插座做活动连接", "{2023,第1题}")

    # 组 E：埋深阈值 + 标识色
    for depth in _BURY_DEPTHS_M:
        add("E-bury", f"电缆直接埋地敷设，埋深 {depth}m",
            {"depth_m": depth, "threshold_m": 0.7}, depth >= 0.7,
            "电缆直接埋地敷设深度不应小于 0.7m", "kc:1A431011_014_0015:0")
    for n_color, pe_color in _COLOR_ASSIGN:
        ok = (n_color, pe_color) == ("蓝色", "黄绿双色")
        add("E-color", f"五芯电缆 N 线采用{n_color}、PE 线采用{pe_color}",
            {"n": n_color, "pe": pe_color}, ok,
            "N 线必须为蓝色、PE 线必须为黄绿双色，不得混用",
            "kc:1A431011_014_0015:1 + {2019,第14题}")

    # 组 F：管理制度（离散案例，含正例防"见题就挑错"）
    for case in _MGMT_CASES:
        add("F-mgmt", case["surface"], {"raw": case["surface"]}, case["ok"],
            case["correct"], case["anchor"])

    # 外延：间距 ≤30m（extension=true, 综合纠错补充）
    for dist in _DIST_SURFACES_M:
        add("X-distance", f"电锯开关箱距堆场配电箱 {dist}m",
            {"dist_m": dist, "threshold_m": 30.0}, dist <= 30.0,
            "开关箱与配电箱的间距不得大于 30m", "{2017,第2题}", extension=True)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "B-send":
        return p["order"] == list(_SEND_CORRECT)
    if g == "B-stop":
        return p["order"] == list(_STOP_CORRECT)
    if g == "C-voltage":
        return p["surface_v"] <= p["limit_v"]
    if g == "D-one-switch":
        if p.get("plug_socket_inlet"):
            return False
        return p["share_count"] == 1
    if g == "E-bury":
        return p["depth_m"] >= p["threshold_m"]
    if g == "E-color":
        return (p["n"], p["pe"]) == ("蓝色", "黄绿双色")
    if g == "F-mgmt":
        raw = p["raw"]
        if "40kW" in raw:
            return True
        return False  # 其余管理反例均为不妥（封闭集内逐条构造）
    if g == "X-distance":
        return p["dist_m"] <= p["threshold_m"]
    return None


_CONTESTED_TOKENS = ("潮湿", "隧道", "人防", "易触及")  # jury 存疑#5 争议档, 禁入池


def run_gate(variants: list[dict[str, Any]]) -> dict[str, Any]:
    mismatches, contested, dup = [], [], []
    seen: set[str] = set()
    for v in variants:
        iv = _independent_verdict(v)
        if iv is None or iv != v["expected_ok"]:
            mismatches.append(v["variant_id"])
        if any(t in v["surface"] for t in _CONTESTED_TOKENS):
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
    print(f"variants={gate['total']} gate_pass={gate['passed']} rate={gate['pass_rate']:.2%} "
          f"gen={gen_ms:.1f}ms gate={gate_ms:.1f}ms -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(json.dumps({k: gate[k] for k in
                          ('verdict_mismatches', 'contested_leaks', 'duplicate_surfaces')},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    if args.check:
        return 0

    payload = {
        "schema_version": SCHEMA_NAME,
        "pack_id": "S05",
        "status": "candidate",  # 教研审核+判分内核回路核验后方可签发入池
        "source_pack_sha256": hashlib.sha256(
            (REPO / "docs/原始数据/考点原料/成品/S05_临时用电三级配电.md").read_bytes()).hexdigest(),
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
