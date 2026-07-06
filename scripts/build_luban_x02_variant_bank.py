#!/usr/bin/env python3
"""X02 变体池编译期预生成器（临设、道路、材料堆场布置——真题认证限缩池）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本沿 F16 先例
（`scripts/build_luban_f16_variant_bank.py`）同构——纯确定性枚举（零 LLM、零随机），
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

**限缩裁决（fail-closed 的核心决定，逐条对应 X02 pack 原文）**：
X02 §4 R4 封闭性自检明文声明——「『封闭成立』『越界即不妥』『漏其一=不全』等扣分
规则属 R7 评分边界范畴……这些扣分判断全部 🔴 待评分 artifact / 专家裁决（非机械
红线）。规范原文（JGJ146/GB50720 等）可能有更多并列规格情形……补真题/规范锚后再
收紧封闭域」。即：X02 的纯教材锚数值档（危险品仓库 15m / 道路宽度 4m·6m / 仓库
消防分区 500m²·30m²·20m² / 电气间距 / 灭火器配置率 / 材料验收保管 / 不合格材料
处置流程 / 工具式定型化临设）其「越界即不妥」二值判定被 pack 自己划为 🔴 待裁决，
**全部不入池**。

只保留 R4 表判分边界列**自带真题明锚**（即二值判定有真题 ground truth 认证）的
两个切片：
- **宿舍标准**：「每间>16人/通道<0.9m=不妥（真题 `{2020,案例五}` 明锚）」——真题
  correct_answer 直判「个别宿舍住18人→每间≤16人；通道宽度0.8m→不得小于0.9m」。
- **易燃材料仓库方向**：「设上风向=不妥（真题 `{2015,第30题}` 明锚）」——真题 D 选项
  「易燃材料仓库应设在上风方向」判错、应下风向。

其余诚实边界：
- **§8.2 C1**：`{2015,案例2}`（钢构件堆场条件·钢结构 territory）/`{2015,案例4}`
  （施工组织设计内容·X01 territory）已降 🔵 相邻——token 禁入池。
- **jury HI#1**：「疏散门≤10m」截断表述（仓库消防组本就整档不入池）——token 禁入。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，期望判定只有
  妥/不妥二值（且二值本身以真题明锚为 ground truth）。
- 宿舍标准取值域中床铺≤2层/净高≥2.5m/人均≥2.5m² 三项虽 🟢 教材锚，但其「越界即
  不妥」未被真题明锚认证（真题只判人数/通道两项）——**不入池**（同上限缩原则）。

用法::

    python3 scripts/build_luban_x02_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_x02_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_X02_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "X02_临设道路材料堆场布置.md"

SCHEMA_NAME = "luban-x02-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 X02 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼工地", "某厂房项目现场")

# 切片 1：宿舍标准（锚 kc:1A431011_012_0013:2 + {2020,案例五}——R4 判分边界真题明锚：
# 每间>16人/通道<0.9m=不妥）
_DORM_MAX_OCCUPANCY = 16
_DORM_OCCUPANCY_SURFACES = (12, 16, 17, 18, 20)  # 题面可出现的人数(封闭·皮)
_DORM_MIN_AISLE_M = 0.9
_DORM_AISLE_SURFACES_M = (0.8, 0.9, 1.0)  # 题面可出现的通道宽度(封闭·皮)
_ANCHOR_DORM = "kc:1A431011_012_0013:2 + {2020,案例五}"
_CORRECT_OCCUPANCY = "宿舍每间住宿人员不得超过16人（每间≤16人）"
_CORRECT_AISLE = "宿舍室内通道宽度不得小于0.9m"

# 切片 2：易燃材料仓库方向（锚 kc:1A437000_146_0235:0 + {2015,第30题}——R4 判分
# 边界真题明锚：设上风向=不妥，应设下风向、水源充足处）
_WIND_CORRECT = "下风方向"
_WIND_DIRECTIONS = ("下风方向", "上风方向")  # 封闭二值域
_ANCHOR_WIND = "kc:1A437000_146_0235:0 + {2015,第30题}"
_CORRECT_WIND = "易燃材料仓库应设在现场下风方向（下风向）、水源充足处"


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"X02-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：宿舍每间人数——皮×人数全枚举（真题明锚 18人→≤16人）
    for skin, n in itertools.product(_SITE_SKINS, _DORM_OCCUPANCY_SURFACES):
        add("A-dorm-occupancy", f"{skin}工人宿舍每间安排住宿 {n} 人",
            {"occupancy": n}, n <= _DORM_MAX_OCCUPANCY,
            _CORRECT_OCCUPANCY, _ANCHOR_DORM)

    # 组 A：宿舍通道宽度——皮×宽度全枚举（真题明锚 0.8m→不得小于0.9m）
    for skin, w in itertools.product(_SITE_SKINS, _DORM_AISLE_SURFACES_M):
        add("A-dorm-aisle", f"{skin}工人宿舍室内通道宽度为 {w}m",
            {"aisle_m": w}, w >= _DORM_MIN_AISLE_M,
            _CORRECT_AISLE, _ANCHOR_DORM)

    # 组 B：易燃材料仓库方向——皮×方向全枚举（真题明锚：上风方向=错）
    for skin, direction in itertools.product(_SITE_SKINS, _WIND_DIRECTIONS):
        add("B-flammable-wind", f"{skin}将易燃材料仓库设置在现场{direction}",
            {"direction": direction}, direction == _WIND_CORRECT,
            _CORRECT_WIND, _ANCHOR_WIND)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-dorm-occupancy":
        return p["occupancy"] <= _DORM_MAX_OCCUPANCY
    if g == "A-dorm-aisle":
        return p["aisle_m"] >= _DORM_MIN_AISLE_M
    if g == "B-flammable-wind":
        if p["direction"] not in _WIND_DIRECTIONS:
            return None  # 封闭二值域外不许出现
        return p["direction"] == _WIND_CORRECT
    return None


# 争议/🔵相邻/待裁决层 token，禁入题面与正确做法（fail-closed）：
# 钢构件/施工组织设计=§8.2 C1 相邻降🔵；疏散门=jury HI#1 截断表述所在组(整档不入池)；
# 其余为 pack 自检划 🔴 待裁决的纯教材锚数值档族 token 守门（防限缩池被绕开）
_CONTESTED_TOKENS = ("钢构件", "施工组织设计", "疏散门", "防火墙", "灭火器",
                     "碘钨灯", "回车场", "码放", "退场")


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
        "pack_id": "X02",
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
