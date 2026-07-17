#!/usr/bin/env python3
"""D13 变体池编译期预生成器（幕墙防火/防雷/层间封堵构造）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本承接 S05 / F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`），
纯确定性枚举（零 LLM、零随机、零时间依赖），从 D13 Pack §4 R4 三个封闭规则组
（A 防火构造尺寸 / B 层间封堵材料 / C 防雷连接）派生变体，自带独立一致性检查门
（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（尺寸/材料/环节在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 D13 pack 裁决）：
- **jury HI#1**：有机防火堵料特性已降 🔵 材料外延（非幕墙防火防雷封堵构造本体）
  ——整组不入池（含作干扰项，争议 token 门拦截「堵料」）。
- **§0 邻接①②③④**：幕墙分类体系 / 成品保护清洗 / 防火涂料·防火玻璃·防火板材
  材料层 / 幕墙面板安装（开启窗角度/背栓/云石胶/硅酮结构胶，§8.2 C3 越界已删）
  全部 🔵 邻接——禁入题面与正确做法。
- **§8.2 C1**：「柔性铜导线」的"铜"限定无锚——token 禁入，统一教材原文"柔性导线"。
- **§2 机理解释（烟囱效应/铝熔点 660℃）为 🔵 讲解性**——禁入题面与正确做法。
- **R4 组 C "宜"的强制力与"≤10m"端点严谨度留 R7 待规范锚**——本池只做
  「全程无柔性导线连通 = 不妥」的显式边界，不生成"间距 12m 设不设"类端点判定。
- **jury #4/#5 拆锚**："每三层与均压环连接"与"隐蔽工程验收"只挂真题锚
  `{2020,第23题}`（教材 quote 无"每三层"，2019 无隐蔽验收支撑）。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_d13_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_d13_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_D13_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "D13_幕墙防火防雷层间封堵.md"

SCHEMA_NAME = "luban-d13-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 D13 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：幕墙工程上下文的封闭集合（换皮不换判分点，≤2 照先例）
_SITE_SKINS = ("某高层办公楼幕墙工程", "某商业综合体幕墙工程")

# 规则组 A：防火构造尺寸（锚 kc:1A413030_148_0286:0 + {2019,第29题}/{2017,第12题}）
# 题面数值全部 pack 内：1.2m 实体墙下限 / 1.0m 挑檐宽度下限 / 200mm 空腔填塞 /
# 100mm 楼板缝隙(混部位=不妥, R4 显式) / 1.5mm 承托板(1.5m=真题单位陷阱)
_WALL_MIN_M = 1.2
_CANOPY_MIN_M = 1.0
_CAVITY_MIN_MM = 200
_BOARD_SPEC_OK = "1.5mm"
_ANCHOR_A = "kc:1A413030_148_0286:0 + {2019,第29题}"
_ANCHOR_A_BOARD = "kc:1A413030_148_0286:0 + {2019,第29题} + {2017,第12题}"
_CORRECT_A_WALL = (
    "上下层开口间应设高度不小于1.2m的实体墙；或设防火挑檐，宽度不小于1.0m且长度不小于开口宽度"
)
_CORRECT_A_CAVITY = "窗槛墙空腔上下沿矿物棉填塞高度不应小于200mm（楼板缝隙封堵100mm为不同部位尺寸）"
_CORRECT_A_BOARD = "钢质承托板厚度不小于1.5mm（不得写成1.5m，不得用铝板）"
_CORRECT_A_ZONE = "同一幕墙玻璃单元不应跨越两个防火分区"

# 规则组 B：层间封堵（真题锚 {2015,案例2}；铝板另有 {2017,第12题}）
# 全要素清单逐字来自 {2015,案例2} 官方答案口径（pack §3 场景3 直读）
_SEAL_CANONICAL = (
    "采用不燃材料封堵", "填充材料采用岩棉或矿棉", "厚度不小于100mm",
    "满足设计的耐火极限要求", "楼层间形成水平防火烟带",
    "防火层采用厚度不小于1.5mm的镀锌钢板承托", "承托板缝隙采用防火密封胶密封",
)
# R4 组 B 判分边界显式点名的缺陷（漏项/错材料），不外推其他组合
_SEAL_NAMED_DEFECTS = (
    ("omit:水平防火烟带", "楼层间形成水平防火烟带", None),
    ("omit:防火密封胶", "承托板缝隙采用防火密封胶密封", None),
    ("omit:耐火极限", "满足设计的耐火极限要求", None),
    ("swap:铝板承托", "防火层采用厚度不小于1.5mm的镀锌钢板承托", "防火层采用铝板承托"),
    ("swap:可燃材料", "采用不燃材料封堵", "采用可燃材料封堵"),
)
_ANCHOR_B = "{2015,案例2}"
_ANCHOR_B_ALU = "{2015,案例2} + {2017,第12题}"
_CORRECT_B = (
    "层间缝隙应采用不燃材料（岩棉或矿棉）封堵，厚度不小于100mm并满足设计耐火极限，"
    "楼层间形成水平防火烟带；防火层用不小于1.5mm镀锌钢板承托（不得用铝板），"
    "承托板缝隙用防火密封胶密封"
)

# 规则组 C：防雷连接（锚 kc:1A413030_148_0287:0；每三层/除镀膜/隐蔽验收=真题侧
# {2020,第23题}，jury #4/#5 拆锚后不混挂 2019/教材）
_ANCHOR_C_TEXT = "kc:1A413030_148_0287:0"
_ANCHOR_C_EXAM = "{2020,第23题}"
_C_CASES = (
    {"aspect": "frame", "ok_surface": "幕墙金属框架与主体结构防雷体系可靠连接",
     "bad_surface": "幕墙金属框架未与主体结构防雷体系连接",
     "correct": "幕墙金属框架应与主体结构防雷体系可靠连接",
     "anchor": "kc:1A413030_148_0287:0 + {2019,第29题} + {2020,第23题}"},
    {"aspect": "wire", "ok_surface": "铝合金立柱每 10m 范围内用一根柔性导线连通上下柱",
     "bad_surface": "铝合金立柱全程未设柔性导线连通上下柱",
     "correct": "铝合金立柱≤10m范围内宜一根柔性导线连通上下柱（全程不设即漏防雷连通要点）",
     "anchor": _ANCHOR_C_TEXT},
    {"aspect": "ring", "ok_surface": "有均压环楼层的预埋件用圆钢与均压环焊接连通",
     "bad_surface": "有均压环楼层的预埋件未与均压环焊接连通",
     "correct": "有均压环楼层预埋件应用圆钢/扁钢与均压环焊接连通",
     "anchor": _ANCHOR_C_TEXT},
    {"aspect": "coating", "ok_surface": "有镀膜的构件上做防雷连接前除去其镀膜层",
     "bad_surface": "有镀膜的构件上直接做防雷连接，未除去镀膜层",
     "correct": "有镀膜构件防雷连接应除去镀膜层",
     "anchor": _ANCHOR_C_EXAM},
    {"aspect": "concealed", "ok_surface": "防雷构造连接完成后进行隐蔽工程验收",
     "bad_surface": "项目部认为防雷构造连接不必进行隐蔽工程验收",
     "correct": "防雷构造连接必须做隐蔽工程验收",
     "anchor": _ANCHOR_C_EXAM},
)
_C_ASPECTS = tuple(c["aspect"] for c in _C_CASES)


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"D13-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：实体墙高度（1.0m 为 pack 内错值皮·低于 1.2m 下限，题面注明未设挑檐替代）
    for h in (1.2, 1.0):
        add("A-wall", f"幕墙上下层开口之间设置高度 {h}m 的实体墙，未另设防火挑檐",
            {"wall_height_m": h, "has_canopy": False}, h >= _WALL_MIN_M,
            _CORRECT_A_WALL, _ANCHOR_A)
    # 组 A：防火挑檐（宽度 1.0m 封闭下限；长度与开口宽度关系为 R4 显式边界）
    add("A-canopy", "实体墙高度不足时设防火挑檐，宽度 1.0m 且长度不小于开口宽度",
        {"canopy_width_m": 1.0, "length_ge_opening": True}, True,
        _CORRECT_A_WALL, _ANCHOR_A)
    add("A-canopy", "实体墙高度不足时设防火挑檐，宽度 1.0m 但长度小于开口宽度",
        {"canopy_width_m": 1.0, "length_ge_opening": False}, False,
        _CORRECT_A_WALL, _ANCHOR_A)
    # 组 A：窗槛墙空腔填塞（100mm=楼板缝隙尺寸，混部位=不妥，R4 显式边界）
    for mm in (200, 100):
        add("A-cavity", f"窗槛墙内幕墙与墙体间空腔的上下沿用矿物棉填塞，填塞高度 {mm}mm",
            {"cavity_fill_mm": mm}, mm >= _CAVITY_MIN_MM,
            _CORRECT_A_CAVITY, _ANCHOR_A)
    # 组 A：承托板（1.5m=真题单位陷阱 {2019,第29题}A；铝板=材料陷阱 {2017,第12题}）
    for material, spec in (("镀锌钢板", "1.5mm"), ("钢板", "1.5m"), ("铝板", "1.5mm")):
        add("A-board", f"防火层采用厚度 {spec} 的{material}承托",
            {"material": material, "thickness_spec": spec},
            "钢" in material and spec == _BOARD_SPEC_OK,
            _CORRECT_A_BOARD, _ANCHOR_A_BOARD)
    # 组 A：防火分区
    add("A-zone", "幕墙玻璃单元按防火分区分格，同一玻璃单元不跨越两个防火分区",
        {"crosses_zones": False}, True, _CORRECT_A_ZONE, _ANCHOR_A)
    add("A-zone", "同一幕墙玻璃单元跨越了两个防火分区",
        {"crosses_zones": True}, False, _CORRECT_A_ZONE, _ANCHOR_A)

    # 组 B：层间封堵——完整全要素 + R4 显式点名缺陷（漏烟带/漏密封胶/漏耐火极限/
    # 铝板承托/可燃材料），不外推其他排列组合
    seal_cases: list[tuple[str, list[str], str]] = [
        ("complete", list(_SEAL_CANONICAL), _ANCHOR_B)]
    for kind, target, replacement in _SEAL_NAMED_DEFECTS:
        elements = [replacement if s == target and replacement else s
                    for s in _SEAL_CANONICAL if not (s == target and replacement is None)]
        seal_cases.append((kind, elements, _ANCHOR_B_ALU if kind == "swap:铝板承托" else _ANCHOR_B))
    for skin, (kind, elements, anchor) in itertools.product(_SITE_SKINS, seal_cases):
        add("B-seal",
            f"{skin}对幕墙与各层楼板、隔墙外沿间缝隙实施层间封堵，做法：{'；'.join(elements)}",
            {"elements": elements, "case": kind},
            elements == list(_SEAL_CANONICAL), _CORRECT_B, anchor)

    # 组 C：防雷连接——五环节双极性
    for case in _C_CASES:
        add("C-lightning", case["ok_surface"],
            {"aspect": case["aspect"], "done": True}, True,
            case["correct"], case["anchor"])
        add("C-lightning", case["bad_surface"],
            {"aspect": case["aspect"], "done": False}, False,
            case["correct"], case["anchor"])
    # 组 C：每三层接均压环（真题侧正例，锚只挂 {2020,第23题}，jury#5 拆锚）
    add("C-lightning", "避雷接地一般每三层与均压环连接",
        {"aspect": "ring_every_three_floors", "done": True}, True,
        "避雷接地一般每三层与均压环连接（真题侧口径）", _ANCHOR_C_EXAM)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-wall":
        if p.get("has_canopy"):
            return None  # 实体墙不足+设挑檐的组合归 A-canopy，不在本组封闭域
        return p["wall_height_m"] >= _WALL_MIN_M
    if g == "A-canopy":
        return p["canopy_width_m"] >= _CANOPY_MIN_M and bool(p["length_ge_opening"])
    if g == "A-cavity":
        return p["cavity_fill_mm"] >= _CAVITY_MIN_MM
    if g == "A-board":
        return "钢" in p["material"] and p["thickness_spec"] == _BOARD_SPEC_OK
    if g == "A-zone":
        return not p["crosses_zones"]
    if g == "B-seal":
        return p["elements"] == list(_SEAL_CANONICAL)
    if g == "C-lightning":
        if p["aspect"] in _C_ASPECTS or p["aspect"] == "ring_every_three_floors":
            return bool(p["done"])
        return None  # 环节封闭域外禁入
    return None


# 争议/🔵邻接/🔴无锚层 token，禁入题面与正确做法（fail-closed）：
# 堵料=jury HI#1 降🔵材料外延；铜=§8.2 C1 无锚限定；熔点/烟囱=§2 机理🔵；
# 开启窗/背栓/云石胶/硅酮结构胶=§8.2 C3 越界(幕墙面板安装 territory)；
# 防火涂料/防火玻璃/膨胀型=§1 #12-14 材料层🔵(与承托板 1.5mm 数字撞车陷阱)；
# 保护膜/清洗=成品保护🔵；人造板/火烧石=幕墙分类背景🔵
_CONTESTED_TOKENS = ("堵料", "铜", "熔点", "烟囱", "开启窗", "背栓", "云石胶",
                     "硅酮结构胶", "防火涂料", "防火玻璃", "膨胀型", "保护膜",
                     "清洗", "人造板", "火烧石")


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
        "pack_id": "D13",
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
