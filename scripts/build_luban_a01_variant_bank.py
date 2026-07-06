#!/usr/bin/env python3
"""A01 变体池编译期预生成器（检验批/分部分项工程质量验收程序）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。先例：S05（`scripts/build_luban_s05_variant_bank.py`）
与 F16（`scripts/build_luban_f16_variant_bank.py`，fail-closed 主模板）。纯确定性
枚举（零 LLM、零随机、零时间依赖），从 A01 Pack §4.3 R4 封闭变量轴派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（层级/依据/项目/阈值在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药。

诚实边界（fail-closed，逐条对应 A01 pack 裁决）：
- **jury(§10) 高可信#1（已裁决降级）**：「主控项目100%/一般项目合格率≥80%」合格
  标准锚 `kc:1A422000_045_0071:1` 为防火章语境 🟡（普适性待 GB50300 §3.0.x 补锚）
  ——该合格标准档**整档不入池**；「主控/一般项目」token 争议门拦截。
- **jury(§10) 高可信#2/#4 + §8.1 🔴-1**：「逐级下合格才能上」普适阶梯已降 🔵、
  完整逐级判定阶梯为 🔴 缺口——组 A 只判**层级顺序/方向**（🟢 `kc:1A422000_021_0029:1`
  四级层级 + 验收方向自下而上，§2.2 表第 1 行），违例只枚举 R8-2 显式点名两例
  （"分部→分项→检验批"倒装 / 从分项起步漏检验批），不出"逐级合格前提"判定，
  "逐级" token 禁入。
- **§8.1 🔴-2**：让步接收四档完整流程源料/真题均无——组 E-redline 只收 🟢 锚档
  （返修加固后仍不满足安全→严禁验收 / 资料缺→委托实体检验，`kc:1A434020_088_0146:1`）；
  "让步接收" token 禁入。
- **R7-2 数值边界硬争议 🔴**：{2017·案例二·问4} 平均值 30.8=35×88% 为临界、
  ≥/> 取舍歧义待教研核原卷——强度数据变体题面值全部避开阈值等值点
  （85/90/92 × 75/85，无 88、无 80），不替教研裁决临界。
- **§8.2 数据张力①（原样保留禁改判）**：{2016·第28题} 型钢混凝土/铝合金子分部
  的答案-解析张力——组 C 子分部成员枚举**剔除该两项**（token 门拦截），只枚举
  无张力 5 项（混凝土/砌体/钢/钢管混凝土/木，🟢 `kc:1A434020_083_0134:0`）。
- **R4 V6 行自带 🔴**（"谁组织哪一级"逐条教材原文待 GB50300 §6 取证）+ R7-3
  待裁（2015·第28题 E 项需教研核）——分部/单位验收组织与参加人员档整档不入池；
  仅保留结构实体检验组织（🟢 `kc:1A434020_085_0136:1` 独立锚，非 V6 范围）。
- **jury(§9)#7 外墙 1000㎡ / #8+§10#10 检查方法（看摸敲照/靠量吊套）** 单源存疑
  未裁决——整档不入池，token 禁入。"三检"源料侧 🔴（仅真题）——不入池。
- **R7 边界档位（满分/压线/0分）全 🔴 待教研裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_a01_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_a01_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_A01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "A01_检验批验收程序.md"

SCHEMA_NAME = "luban-a01-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 A01 Pack §4.3 R4 / §5，锚随行）─────────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼工地", "某办公楼项目现场")

# 组 A：验收层级顺序（锚 kc:1A422000_021_0029:1，四级层级+验收方向自下而上 🟢；
# 违例只枚举 R8-2 显式点名两例，不外推其他排列——阶梯普适前提 🔵/🔴-1 不入池）
_LEVEL_CANONICAL = ("检验批", "分项工程", "分部工程", "单位工程")
_LEVEL_CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("complete", _LEVEL_CANONICAL),
    ("order:自上而下倒装", ("分部工程", "分项工程", "检验批")),   # R8-2 "写成分部→分项→检验批"
    ("order:漏检验批", ("分项工程", "分部工程", "单位工程")),     # R8-2 "从分项起步漏掉检验批"
)
_ANCHOR_ORDER = "kc:1A422000_021_0029:1"
_CORRECT_ORDER = (
    "质量验收应自下而上按 检验批→分项工程→分部工程→单位工程 进行，"
    "不得自上而下倒装，也不得跳过检验批"
)

# 组 B：划分依据成员枚举（锚 R4-V3 + C1-2/C1-3，🟢；🔴禁新增"按班组"等未锚依据，
# 故负极性只做"认为不可作为依据"的成员判断，不发明枚举外依据）
_BASIS_SETS: dict[str, dict[str, Any]] = {
    "检验批": {"items": ("工程量", "楼层", "施工段", "变形缝"),
             "anchor": "m35:Q18-1A434000:P6 + kc:1A422000_021_0029:1"},
    "分项工程": {"items": ("主要工种", "材料", "施工工艺", "设备类别"),
              "anchor": "kc:1A422000_021_0029:1"},
}

# 组 C：主体结构子分部成员枚举（锚 kc:1A434020_083_0134:0 🟢；
# 型钢混凝土/铝合金因 §8.2 数据张力① 整项剔除，见 docstring）
_SUBDIV_ITEMS = ("混凝土", "砌体", "钢", "钢管混凝土", "木")
_ANCHOR_SUBDIV = "kc:1A434020_083_0134:0"

# 组 D：结构实体检验（簇 C4 全 🟢）
_ENTITY_CHECK_ITEMS = ("混凝土强度", "钢筋保护层厚度", "结构位置与尺寸偏差", "合同约定项目")
_ANCHOR_ENTITY_CONTENT = "kc:1A434020_085_0136:0 + {2020·案例二·问4}"
_ANCHOR_ENTITY_ORG = "kc:1A434020_085_0136:1"
_CORRECT_ENTITY_ORG = "结构实体检验应由监理单位组织、施工单位实施、监理见证全过程"
_ANCHOR_ENTITY_METHOD = "kc:1A434020_085_0136:2 + {2017·案例二·问4}"
_CORRECT_ENTITY_METHOD = "混凝土强度检验应优先采用同条件养护试件法；试件不足时方可采用回弹—取芯法"
# 强度判定阈值（锚 真题 {2017·案例二·问4} 🟢）；题面数据值避开 88/80 临界（R7-2 🔴）
_STRENGTH_AVG_THRESHOLD = 88
_STRENGTH_MIN_THRESHOLD = 80
_STRENGTH_AVG_SURFACES = (85, 90, 92)
_STRENGTH_MIN_SURFACES = (75, 85)
_ANCHOR_STRENGTH = "{2017·案例二·问4}"
_CORRECT_STRENGTH = "实体混凝土强度合格判定：平均值≥设计值×88% 且 最小值≥设计值×80%"

# 组 E：单位工程合格五条（锚 kc:1A434020_088_0146:0 🟢）
_UNIT_FIVE_ITEMS = ("分部工程全部合格", "质量控制资料完整",
                    "安全、节能、环保和主要使用功能资料完整",
                    "主要功能抽查符合要求", "观感质量达标")
_ANCHOR_UNIT_FIVE = "kc:1A434020_088_0146:0"
# 组 E：不合格处理红线（仅 🟢 锚档，锚 kc:1A434020_088_0146:1；其余四档 🔵/🔴-2 不入池）
_ANCHOR_REDLINE = "kc:1A434020_088_0146:1"


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"A01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：验收层级顺序——正序 + R8-2 显式点名两违例（皮×2）
    for skin, (kind, levels) in itertools.product(_SITE_SKINS, _LEVEL_CASES):
        add("A-order", f"{skin}质量验收按以下层级顺序推进：{'→'.join(levels)}",
            {"order": list(levels), "case": kind}, levels == _LEVEL_CANONICAL,
            _CORRECT_ORDER, _ANCHOR_ORDER)

    # 组 B：划分依据——成员判断双极性（枚举内条目，不发明枚举外依据）
    for category, spec in _BASIS_SETS.items():
        domain = "/".join(spec["items"])
        for item in spec["items"]:
            add("B-basis", f"项目部将「{item}」列为{category}的划分依据",
                {"category": category, "item": item, "listed": True}, True,
                f"「{item}」属于{category}划分依据（{domain}）", spec["anchor"])
            add("B-basis", f"项目部认为「{item}」不可作为{category}的划分依据",
                {"category": category, "item": item, "listed": False}, False,
                f"「{item}」属于{category}划分依据（{domain}）", spec["anchor"])

    # 组 C：主体结构子分部——成员判断双极性（无张力 5 项）
    for item in _SUBDIV_ITEMS:
        add("C-subdiv", f"项目部将「{item}」列为主体结构分部的子分部",
            {"item": item, "listed": True}, True,
            f"「{item}」属于主体结构分部的子分部", _ANCHOR_SUBDIV)
        add("C-subdiv", f"项目部认为「{item}」不属于主体结构分部的子分部",
            {"item": item, "listed": False}, False,
            f"「{item}」属于主体结构分部的子分部", _ANCHOR_SUBDIV)

    # 组 D：实体检验内容四件套——成员判断双极性
    for item in _ENTITY_CHECK_ITEMS:
        add("D-content", f"结构实体检验方案中将「{item}」列入检验内容",
            {"item": item, "listed": True}, True,
            f"「{item}」属于结构实体检验内容（混凝土强度/钢筋保护层厚度/"
            f"结构位置与尺寸偏差/合同约定项目）", _ANCHOR_ENTITY_CONTENT)
        add("D-content", f"项目部认为「{item}」无需列入结构实体检验内容",
            {"item": item, "listed": False}, False,
            f"「{item}」属于结构实体检验内容（混凝土强度/钢筋保护层厚度/"
            f"结构位置与尺寸偏差/合同约定项目）", _ANCHOR_ENTITY_CONTENT)

    # 组 D：实体检验组织主体（R8-4 显式点名违例）
    for surface, organizer, implementer, ok in (
        ("结构实体检验由监理单位组织、施工单位实施，监理见证全过程", "监理单位", "施工单位", True),
        ("结构实体检验由施工单位自行组织并实施", "施工单位", "施工单位", False),
        ("结构实体检验由建设单位组织、施工单位实施", "建设单位", "施工单位", False),
    ):
        add("D-org", surface, {"organizer": organizer, "implementer": implementer}, ok,
            _CORRECT_ENTITY_ORG, _ANCHOR_ENTITY_ORG)

    # 组 D：强度检验方法优先级（R8-5 显式点名违例）
    for surface, first, ok in (
        ("实体混凝土强度检验优先采用同条件养护试件法", "同条件养护试件法", True),
        ("实体混凝土强度检验不留同条件试件，直接采用回弹—取芯法", "回弹—取芯法", False),
        ("同条件养护试件不足时，实体强度检验采用回弹—取芯法兜底", "同条件养护试件法", True),
    ):
        add("D-method", surface, {"first_method": first}, ok,
            _CORRECT_ENTITY_METHOD, _ANCHOR_ENTITY_METHOD)

    # 组 D：强度判定——数据点（避开临界值）+ 判定规则方向
    for avg, mn in itertools.product(_STRENGTH_AVG_SURFACES, _STRENGTH_MIN_SURFACES):
        add("D-strength",
            f"结构实体检验实测混凝土强度平均值为设计值的 {avg}%、最小值为设计值的 {mn}%，"
            f"项目部判定实体强度合格",
            {"avg_pct": avg, "min_pct": mn,
             "avg_threshold": _STRENGTH_AVG_THRESHOLD, "min_threshold": _STRENGTH_MIN_THRESHOLD},
            avg >= _STRENGTH_AVG_THRESHOLD and mn >= _STRENGTH_MIN_THRESHOLD,
            _CORRECT_STRENGTH, _ANCHOR_STRENGTH)
    for rule_avg, rule_min in ((88, 80), (80, 88)):
        add("D-strength",
            f"项目部按「平均值≥设计值×{rule_avg}% 且 最小值≥设计值×{rule_min}%」"
            f"判定实体混凝土强度合格",
            {"rule_avg_pct": rule_avg, "rule_min_pct": rule_min},
            (rule_avg, rule_min) == (_STRENGTH_AVG_THRESHOLD, _STRENGTH_MIN_THRESHOLD),
            _CORRECT_STRENGTH, _ANCHOR_STRENGTH)

    # 组 E：单位工程合格五条——成员判断双极性
    for item in _UNIT_FIVE_ITEMS:
        add("E-five", f"单位工程验收时将「{item}」列为合格条件之一",
            {"item": item, "listed": True}, True,
            f"「{item}」属于单位工程验收合格五条", _ANCHOR_UNIT_FIVE)
        add("E-five", f"项目部认为「{item}」不属于单位工程验收合格条件",
            {"item": item, "listed": False}, False,
            f"「{item}」属于单位工程验收合格五条", _ANCHOR_UNIT_FIVE)

    # 组 E：不合格处理红线（仅 🟢 锚档）
    add("E-redline", "某单位工程经返修加固后仍不满足安全要求，项目部仍将其组织验收通过",
        {"after_repair_meets_safety": False, "action": "验收通过"}, False,
        "经返修或加固后仍不满足安全或重要使用要求的，严禁验收", _ANCHOR_REDLINE)
    add("E-redline", "某单位工程经返修加固后仍不满足安全或重要使用要求，被判定严禁验收",
        {"after_repair_meets_safety": False, "action": "严禁验收"}, True,
        "经返修或加固后仍不满足安全或重要使用要求的，严禁验收", _ANCHOR_REDLINE)
    add("E-redline", "某单位工程质量控制资料缺失，委托有资质机构进行实体检验/抽样试验补证",
        {"situation": "质量控制资料缺失", "action": "委托有资质机构实体检验"}, True,
        "质量控制资料缺失时，应委托有资质机构做实体检验/抽样试验补证", _ANCHOR_REDLINE)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-order":
        return tuple(p["order"]) == _LEVEL_CANONICAL
    if g == "B-basis":
        spec = _BASIS_SETS.get(p["category"])
        if spec is None or p["item"] not in spec["items"]:
            return None  # 枚举外条目不许出现(封闭域)
        return bool(p["listed"])
    if g == "C-subdiv":
        if p["item"] not in _SUBDIV_ITEMS:
            return None
        return bool(p["listed"])
    if g == "D-content":
        if p["item"] not in _ENTITY_CHECK_ITEMS:
            return None
        return bool(p["listed"])
    if g == "D-org":
        return p["organizer"] == "监理单位" and p["implementer"] == "施工单位"
    if g == "D-method":
        return p["first_method"] == "同条件养护试件法"
    if g == "D-strength":
        if "rule_avg_pct" in p:
            return (p["rule_avg_pct"], p["rule_min_pct"]) == (
                _STRENGTH_AVG_THRESHOLD, _STRENGTH_MIN_THRESHOLD)
        if p["avg_pct"] in (_STRENGTH_AVG_THRESHOLD,) or p["min_pct"] in (_STRENGTH_MIN_THRESHOLD,):
            return None  # 临界等值点禁入（R7-2 🔴 取舍歧义待教研）
        return p["avg_pct"] >= p["avg_threshold"] and p["min_pct"] >= p["min_threshold"]
    if g == "E-five":
        if p["item"] not in _UNIT_FIVE_ITEMS:
            return None
        return bool(p["listed"])
    if g == "E-redline":
        if "after_repair_meets_safety" in p:
            if p["after_repair_meets_safety"]:
                return None  # 满足安全后的分支属 🔵/🔴-2 缺口，不许出现
            return p["action"] == "严禁验收"
        if p.get("situation") == "质量控制资料缺失":
            return p["action"] == "委托有资质机构实体检验"
        return None
    return None


# 争议/🟡降级/🔴缺口层 token，禁入题面与正确做法（fail-closed）：
# 主控/一般项目=jury§10 HI#1 防火章🟡整档不入；让步接收=🔴-2；逐级=HI#2/#4 普适阶梯🔵；
# 型钢混凝土/铝合金=§8.2 数据张力①；三检=源料🔴；1000=jury§9#7 单源存疑；
# 看摸敲照/靠量吊套=jury§9#8+§10#10 检查方法单源存疑
_CONTESTED_TOKENS = ("主控", "一般项目", "让步接收", "逐级", "型钢混凝土", "铝合金",
                     "三检", "1000", "看摸敲照", "靠量吊套")


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
        "pack_id": "A01",
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
