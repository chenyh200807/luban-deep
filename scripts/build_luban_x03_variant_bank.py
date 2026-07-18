#!/usr/bin/env python3
"""X03 变体池编译期预生成器（文明/绿色/环保施工措施）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本沿 F16 先例
（`scripts/build_luban_f16_variant_bank.py`）同构——纯确定性枚举（零 LLM、零随机），
从 X03 Pack §4 R4 六个封闭规则组（A~F）派生变体，自带独立一致性检查门
（生成器与校验器从同一规则表**分别**推导判定，互证）。

可建性依据：X03 §4 封闭性自检明示「取值域/归类边界（"哪些项""归哪一节""哪类污染"）
可机械裁决……规则封闭成立」；🔴 只指「逐档扣多少分」（R7 范畴，本池本就不作判定
依据，期望判定只有妥/不妥二值）。

诚实边界（fail-closed，逐条对应 X03 pack 裁决）：
- **§8.3 双源缺口（jury HI#2 语境化）**：围挡高度 1.8m（本源料）vs 2.5m（X01 场容
  侧市区主路段）两数字分属不同规范/语境——**围挡高度档整档不入池**（1.8m/2.5m
  token 禁入），只保留围挡材料类型档（真题 `{2024,第27题}` 明锚、无争议）。
- **组 D 堆放高度用柔性原文（jury 单源#10 已应用）**：「不宜高于3m，超过3m须堆体和
  地基稳定性验算」——只生成 ≤3m（妥）与 >3m 且未验算（不妥）两类；「>3m 且已验算」
  情形因「不宜」柔性边界**不生成**（不可机械二值）。
- **§8.2 C1/C6 + §0 邻接边界**：职业病/振捣（安全卫生 territory）、消防/动火/灭火器
  （R01 territory）NOISE 已剔——token 禁入池。
- **§8.2 C2**：镜头 A 自造 node_code 前缀 `1910438001` 已删——token 禁入。
- **「降低机械满载率」**（{2015,第29题} 干扰项）只出现在 R7/§6 误区层、不在 R4/R5
  封闭取值域表内——不入池（本池数值/术语只取 R4/R5），token 禁入。
- **建筑节能工程验收 ≠ 四节「节能」**为 R4 组 B 判分边界显式点名的归类陷阱，但
  「建筑节能工程验收」本身是 🔵 邻接（§0 边界③）——照 F16 组 D 范式做**防混答
  外延变体（extension=true）**，其判定只由 🟢 组 B 封闭节能措施域推导
  （建筑节能工程验收 ∉ {节能设备/最低照度/可再生能源} 即不妥）。
- **组 F 绿色施工评价顺序**：R3 场景 S8 标 🔴 = 真题暂未直命（教材锚
  `kc:1A437000_139_0222:0` 为 🟢，非编造/存疑）——入池为核心，报告留痕；
  违例只枚举「漏中间层级」（判分边界显式措辞），不外推排列组合。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据。

用法::

    python3 scripts/build_luban_x03_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_x03_variant_bank.py --check  # 只跑一致性门(CI 可挂)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_X03_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "X03_文明绿色环保施工措施.md"

SCHEMA_NAME = "luban-x03-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 X03 Pack §4 R4 / §5，锚随行）─────────────────
# 规则组 A：文明施工「六化」+ 隔离/严禁住人（锚 kc:1A437000_143_0229:0/:1 +
# ca:1A437000_143_0229；判分边界：漏项/口号即不全）
_CIVIL_ITEMS: dict[str, str] = {
    "围挡大门标牌标准化": "kc:1A437000_143_0229:0 + ca:1A437000_143_0229",
    "材料码放整齐化": "kc:1A437000_143_0229:0 + ca:1A437000_143_0229",
    "安全设施规范化": "kc:1A437000_143_0229:0 + ca:1A437000_143_0229",
    "生活设施整洁化": "kc:1A437000_143_0229:0 + ca:1A437000_143_0229",
    "职工行为文明化": "kc:1A437000_143_0229:0 + ca:1A437000_143_0229",
    "工作生活秩序化": "kc:1A437000_143_0229:0 + ca:1A437000_143_0229",
    "施工区与办公生活区划分清晰并隔离防护": "kc:1A437000_143_0229:1 + {2016,第18题}",
    "在建工程内严禁住人": "kc:1A437000_143_0229:1 + {2016,第18题}",
}
_CORRECT_CIVIL = ("文明施工基本要求：围挡/大门/标牌标准化、材料码放整齐化、安全设施"
                  "规范化、生活设施整洁化、职工行为文明化、工作生活秩序化；施工区与"
                  "办公生活区划分清晰并隔离防护，在建工程内严禁住人")

# 规则组 B：绿色施工四节归类（锚 kc:1A437000_140_0223:0/1/2 + kc:1A437000_141_0224:0；
# 判分边界：归类必须准确——绿化代硬化=节地(非节材)；四节"节能"≠建筑节能工程验收）
_FOUR_SAVES: dict[str, tuple[tuple[str, ...], str]] = {
    "节材与材料资源利用": (
        ("商品混凝土", "预拌砂浆", "高强钢筋", "非木质材料替代木质板材",
         "外墙保温板替代混凝土模板"),
        "kc:1A437000_140_0223:0 + {2015,第29题}"),
    "节水与水资源利用": (
        ("冲洗用水设循环装置", "抽水量>50万m³须回灌地下水"),
        "kc:1A437000_140_0223:1"),
    "节能与能源利用": (
        ("优先使用节能设备", "临时照明按最低照度设置", "优先利用太阳能地热等可再生能源"),
        "kc:1A437000_140_0223:2"),
    "节地与施工用地保护": (
        ("临时设施占用最小面积", "红线外优先使用荒地废地", "道路永临结合",
         "利用绿化代替场地硬化"),
        "kc:1A437000_141_0224:0 + {2017,第16题}"),
}
_CORRECT_CLASSIFY = ("四节归类必须准确：节材(商混/预拌砂浆/高强钢筋/非木质替代/外墙"
                     "保温板替代模板)、节水(循环装置/抽水>50万m³回灌)、节能(节能设备/"
                     "最低照度/可再生能源)、节地(临设最小面积/红线外荒地/道路永临结合/"
                     "绿化代替场地硬化)")
_CORRECT_GREEN_LAND = "「利用绿化代替场地硬化」属「节地与施工用地保护」，不是节材"
# 外延（防混答，🔵 邻接借归类陷阱——判定只由 🟢 节能封闭措施域推导）
_MIX_ITEM = "建筑节能工程验收(围护保温)"
_CORRECT_MIX = ("四节「节能与能源利用」=节能设备/最低照度/可再生能源等施工措施；"
                "建筑节能工程验收属别章验收内容，与四节「节能」同字不同考")
_ANCHOR_MIX = "kc:1A437000_140_0223:2（四节节能封闭域🟢）+ §0 边界③（邻接🔵留痕）"

# 规则组 C：环境保护污染分级封闭措施域（禁混搭别污染）
_POLLUTION: dict[str, tuple[tuple[str, ...], str]] = {
    "扬尘控制": (
        ("自动喷淋", "雾炮除尘", "车辆冲洗", "地面硬化", "裸土覆盖固化或绿化",
         "物料篷盖", "出口设冲洗池和沉淀池", "定期洒水抑尘"),
        "kc:1A437000_149_0293:0 + kc:1A437000_141_0225:1"),
    "噪声控制": (
        ("低噪声设备", "隔声屏/隔声罩", "封闭木工房", "优化施工工艺"),
        "kc:1A437000_149_0294:0"),
    "夜间施工光污染控制": (
        ("办理许可证并公告居民", "照明灯加灯罩使透光方向集中", "电焊作业遮挡防弧光外泄"),
        "kc:1A437000_139_0222:2"),
    "污水泥浆控制": (
        ("泥浆经泥浆池或封闭容器收集存放", "未经处理的泥浆不得随意排放",
         "雨水回收用于冲厕洗车洒水降尘"),
        "kc:1A437000_013_0019:1 + kc:1A437000_149_0290:0"),
}

# 规则组 D：建筑垃圾（柔性原文：不宜高于3m，超3m须稳定性验算；分类计量台账；
# 资源化路径封闭顺序）
_WASTE_HEIGHT_SOFT_M = 3.0
_ANCHOR_WASTE_HEIGHT = "kc:1A437000_013_0019:0"
_CORRECT_WASTE_HEIGHT = ("建筑垃圾堆放不宜高于3m；超过3m须进行堆体和地基稳定性验算")
_ANCHOR_WASTE_SORT = "kc:1A437000_013_0019:4 + {2025,案例三}"
_CORRECT_WASTE_SORT = "建筑垃圾应分类计量、建立台账；未分类的建筑垃圾不得运输出场"
_WASTE_PATH_CANONICAL = ("分类收集", "分类堆放", "级配回填/就地粉碎", "再生骨料")
_ANCHOR_WASTE_PATH = "kc:1A437000_149_0291:0 + {2025,案例三}"
_CORRECT_WASTE_PATH = ("建筑垃圾资源化路径：" + "→".join(_WASTE_PATH_CANONICAL) +
                       "，缺项即不全")

# 规则组 E：围挡材料类型（锚 kc:1A437000_141_0225:0 + {2024,第27题}；
# 高度档因 §8.3 双源缺口整档不入池）
_FENCE_MATERIALS = ("可循环", "可拆卸", "标准化")
_FENCE_WRONG_MATERIALS = ("有机类", "无机类")  # 真题 {2024,第27题} 干扰项
_ANCHOR_FENCE = "kc:1A437000_141_0225:0 + {2024,第27题}"
_CORRECT_FENCE = ("生活区围挡应采用可循环、可拆卸、标准化定型材料；"
                  "「有机类/无机类」为按成分分类的干扰项")

# 规则组 F：绿色施工评价流程（封闭顺序，锚 kc:1A437000_139_0222:0；
# 判分边界：漏中间层级即顺序错）
_EVAL_CANONICAL = ("基本规定", "指标", "要素", "批次", "阶段", "单位工程")
_EVAL_MIDDLE = ("指标", "要素", "批次", "阶段")  # "中间层级"（首尾外）
_ANCHOR_EVAL = "kc:1A437000_139_0222:0"
_CORRECT_EVAL = ("绿色施工评价流程：" + "→".join(_EVAL_CANONICAL) + "，漏中间层级即顺序错")


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"X03-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：文明施工封闭清单——成员判断双极性（照 F16 组 C 范式）
    for item, anchor in _CIVIL_ITEMS.items():
        add("A-civil", f"项目部将「{item}」列入现场文明施工管理要求",
            {"item": item, "listed": True}, True, _CORRECT_CIVIL, anchor)
        add("A-civil", f"项目部认为「{item}」不属于现场文明施工管理要求",
            {"item": item, "listed": False}, False, _CORRECT_CIVIL, anchor)

    # 组 B：四节归类——每项归对节（妥）+ R4 显式点名的归类陷阱（不妥）
    for node, (items, anchor) in _FOUR_SAVES.items():
        for item in items:
            add("B-classify", f"项目部将「{item}」归入绿色施工「{node}」措施",
                {"item": item, "claimed_node": node}, True, _CORRECT_CLASSIFY, anchor)
    # R4 判分边界显式点名：绿化代硬化=节地(非节材)
    add("B-classify", "项目部将「利用绿化代替场地硬化」归入绿色施工「节材与材料资源利用」措施",
        {"item": "利用绿化代替场地硬化", "claimed_node": "节材与材料资源利用"},
        False, _CORRECT_GREEN_LAND, "kc:1A437000_141_0224:0 + {2017,第16题}")
    # 外延：四节"节能"≠建筑节能工程验收（防混答，extension=true；判定只由 🟢 节能域推导）
    add("B-classify", f"项目部将「{_MIX_ITEM}」列为绿色施工四节中「节能与能源利用」措施",
        {"item": _MIX_ITEM, "claimed_node": "节能与能源利用"},
        False, _CORRECT_MIX, _ANCHOR_MIX, extension=True)

    # 组 C：污染分级封闭措施域——(污染类×措施)成员判断双极性（禁混搭别污染）
    for cls, (measures, anchor) in _POLLUTION.items():
        correct = f"「{cls}」封闭措施域：{('、'.join(measures))}，漏项即不全"
        for m in measures:
            add("C-pollution", f"针对{cls}，项目部采取「{m}」措施",
                {"pollution_class": cls, "measure": m, "listed": True}, True,
                correct, anchor)
            add("C-pollution", f"项目部认为「{m}」不属于{cls}措施、无需采取",
                {"pollution_class": cls, "measure": m, "listed": False}, False,
                correct, anchor)

    # 组 D：建筑垃圾堆放高度——柔性原文：≤3m(妥)/>3m且未验算(不妥)；
    # >3m且已验算因「不宜」柔性边界不生成
    for h in (2.0, 3.0):
        add("D-waste-height", f"现场建筑垃圾堆放高度 {h}m",
            {"height_m": h, "stability_verified": None}, True,
            _CORRECT_WASTE_HEIGHT, _ANCHOR_WASTE_HEIGHT)
    for h in (3.5, 4.0):
        add("D-waste-height",
            f"现场建筑垃圾堆放高度 {h}m，未对堆体和地基进行稳定性验算",
            {"height_m": h, "stability_verified": False}, False,
            _CORRECT_WASTE_HEIGHT, _ANCHOR_WASTE_HEIGHT)
    # 组 D：分类计量台账（含正例防"见题就挑错"）
    add("D-waste-sort", "现场建筑垃圾分类计量、建立台账后运输出场",
        {"sorted_and_logged": True}, True, _CORRECT_WASTE_SORT, _ANCHOR_WASTE_SORT)
    add("D-waste-sort", "现场建筑垃圾未经分类即运输出场",
        {"sorted_and_logged": False}, False, _CORRECT_WASTE_SORT, _ANCHOR_WASTE_SORT)
    # 组 D：资源化路径——完整正序 + 逐项缺项（判分边界：缺项即不全）
    add("D-waste-path", f"建筑垃圾资源化路径为：{'→'.join(_WASTE_PATH_CANONICAL)}",
        {"steps": list(_WASTE_PATH_CANONICAL)}, True,
        _CORRECT_WASTE_PATH, _ANCHOR_WASTE_PATH)
    for omit in _WASTE_PATH_CANONICAL:
        steps = [s for s in _WASTE_PATH_CANONICAL if s != omit]
        add("D-waste-path", f"建筑垃圾资源化路径为：{'→'.join(steps)}",
            {"steps": steps, "case": f"omit:{omit}"}, False,
            _CORRECT_WASTE_PATH, _ANCHOR_WASTE_PATH)

    # 组 E：围挡材料类型——正确定型材料（妥）+ 真题点名干扰项（不妥）
    for m in _FENCE_MATERIALS:
        add("E-fence-material", f"生活区围挡采用「{m}」定型材料",
            {"material": m}, True, _CORRECT_FENCE, _ANCHOR_FENCE)
    for m in _FENCE_WRONG_MATERIALS:
        add("E-fence-material", f"项目部按材料成分将生活区围挡定型材料选为「{m}」",
            {"material": m}, False, _CORRECT_FENCE, _ANCHOR_FENCE)

    # 组 F：绿色施工评价顺序——完整正序 + 逐个漏中间层级（判分边界显式措辞）
    add("F-eval-order", f"绿色施工评价流程为：{'→'.join(_EVAL_CANONICAL)}",
        {"steps": list(_EVAL_CANONICAL)}, True, _CORRECT_EVAL, _ANCHOR_EVAL)
    for omit in _EVAL_MIDDLE:
        steps = [s for s in _EVAL_CANONICAL if s != omit]
        add("F-eval-order", f"绿色施工评价流程为：{'→'.join(steps)}",
            {"steps": steps, "case": f"omit:{omit}"}, False,
            _CORRECT_EVAL, _ANCHOR_EVAL)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-civil":
        if p["item"] not in _CIVIL_ITEMS:
            return None  # 枚举外条目不许出现(封闭域)
        return bool(p["listed"])
    if g == "B-classify":
        node = p["claimed_node"]
        if node not in _FOUR_SAVES:
            return None
        # 归类可机械裁决：条目 ∈ 该节封闭措施域 ⇔ 妥（外延防混答同由此推导）
        return p["item"] in _FOUR_SAVES[node][0]
    if g == "C-pollution":
        entry = _POLLUTION.get(p["pollution_class"])
        if entry is None or p["measure"] not in entry[0]:
            return None  # 跨污染类措施不混搭(封闭域外)
        return bool(p["listed"])
    if g == "D-waste-height":
        if p["height_m"] <= _WASTE_HEIGHT_SOFT_M:
            return True
        if p["stability_verified"] is False:
            return False  # 超3m未验算即不妥
        return None  # 超3m且已验算=「不宜」柔性边界，不可机械二值(不生成)
    if g == "D-waste-sort":
        return bool(p["sorted_and_logged"])
    if g == "D-waste-path":
        return p["steps"] == list(_WASTE_PATH_CANONICAL)
    if g == "E-fence-material":
        if p["material"] not in _FENCE_MATERIALS + _FENCE_WRONG_MATERIALS:
            return None
        return p["material"] in _FENCE_MATERIALS
    if g == "F-eval-order":
        return p["steps"] == list(_EVAL_CANONICAL)
    return None


# 争议/🔵邻接/双源/自造层 token，禁入题面与正确做法（fail-closed）：
# 职业病/振捣=§8.2 C1 安全卫生邻接已删；消防/动火/灭火器=C6 R01 territory NOISE 剔；
# 1910438001=C2 镜头A自造前缀；满载率=R4/R5 表外(只在 R7/误区层)；
# 1.8m/2.5m=§8.3 围挡高度双源缺口整档不入池
_CONTESTED_TOKENS = ("职业病", "振捣", "消防", "动火", "灭火器",
                     "1910438001", "满载率", "1.8m", "2.5m")


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
        "pack_id": "X03",
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
