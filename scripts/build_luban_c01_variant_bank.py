#!/usr/bin/env python3
"""C01 变体池编译期预生成器（施工缝留置与处理）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。先例：S05（`scripts/build_luban_s05_variant_bank.py`）
与 F16（`scripts/build_luban_f16_variant_bank.py`，fail-closed 主模板）。纯确定性
枚举（零 LLM、零随机、零时间依赖），从 C01 Pack §4 R4 四个封闭规则组派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（构件/工序/参数在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药。

诚实边界（fail-closed，逐条对应 C01 pack 裁决）：
- **§8.2 C4 + jury(§9) HI#2（已裁决）**：后浇带模板"独立支设/独立设置"教材
  （`kc:1A413030_098_0184:0`）与真题（{2018,案例三问题3}）表述相反，教材锚已降
  🔵冲突锚、不直接参与采分——**模板独立支设族整档不入池**（含作为干扰项），
  "独立支设/独立设置" token 争议门拦截。
- **§8.2 C2**：镜头 A 无锚外推（跳仓法 5-7d / 微膨胀率 0.02-0.03% / 钙矾石 /
  收缩 80%）已降 🔵 讲解性表述——整族禁入池，token 拦截。
- **jury(§9)#9 单源存疑未裁决**：柱/墙水平缝"0~100/0~300mm"表达可能让"柱也可
  0~300mm"误入判分——组 A 位置变体**不带该数值档**（token 拦截），只用 R4 组 A
  表格的位置表述（顶面/短边/1/3/交接处等）。
- **jury(§9)#4 单源候选（回真源已证伪）**：其声称教材 quote 为"应按施工缝要求
  进行处理"；直读 `_C01_compiled_source.json` scoring_points quote 实为
  "……否则，应留置施工缝"——组 B 正确做法逐字对齐编译源 quote。
- **§8.2 C5 / jury HI#1（已裁决 + D2 批回源补全）**：1.2N/mm²/凿毛/30mm 砂浆为
  EP grading_keywords 关键词级锚，已回源 2026教材P103 `CET_1A413030_P0103_001`
  证据链闭合——组 C 按 R4 组 C 封闭工序建池，锚标注 EP关键词级+回源。
- **jury(§9)#3 单源候选**：≥28d 封闭教材 quote 未提及——28d 变体锚**只挂真题**
  `{2018,案例三问题3}`（verify_exam_anchors.py PASS），不冒教材锚。
- **jury(§9)#8 单源候选**：14d 养护语境混淆——14d 只出现在后浇带养护与防水混凝土
  养护两个 🟢 语境，不进普通施工缝语境。
- **jury(§9)#11 单源候选**：`kc:1A434000_074_0116:0` 不支持防水混凝土浇筑规则——
  组 E 防水混凝土变体锚**只挂真题** `{2015,第26题}`。
- **§0/§8.3 污染绕开**：止水带/止水条/防水设防/桩基/大体积跳仓等跨考点 chunk
  已在挖矿层绕开——token 拦截，不入池。
- **R7 边界候选全 🔴 待真人裁决**——不作变体判定依据，期望判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_c01_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_c01_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_C01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "C01_施工缝留置与处理.md"

SCHEMA_NAME = "luban-c01-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 C01 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼工地", "某厂房项目现场")

# 规则组 A：施工缝留置位置（锚 kc:1A413030_103_0196:0 + {2021,第8题}；
# 正确位置与"= 不妥"违例均逐字取自 R4 组 A 封闭表；0~100/0~300mm 数值档不入题面）
_POSITION_RULES: dict[str, dict[str, str]] = {
    "柱": {"correct": "基础、楼板、梁的顶面", "wrong": "柱中段（受剪力较大处）"},
    "单向板": {"correct": "平行于板短边的任意位置", "wrong": "平行于板长边的位置"},
    "有主次梁的楼板": {"correct": "次梁跨中 1/3 范围内", "wrong": "次梁支座处"},
    "墙": {"correct": "门洞口过梁跨中 1/3 范围内或墙纵横交接处", "wrong": "墙上任意位置"},
    "楼梯梯段": {"correct": "端部 1/3 范围内", "wrong": "梯段中部"},
    "双向受力板": {"correct": "按设计要求确定的位置", "wrong": "施工单位自行确定的位置"},
}
_ANCHOR_POS = "kc:1A413030_103_0196:0 + {2021,第8题}"

# 规则组 B：留设时机（锚 cc:1A413030_103_0196:2 + :3；正确做法对齐编译源逐字 quote
# "……并应在前层混凝土初凝之前，将次层混凝土浇筑完毕；否则，应留置施工缝"——
# jury(§9)#4 的措辞质疑经回 `_C01_compiled_source.json` 直读证伪，quote 即"留置施工缝"）
_ANCHOR_TIMING = "cc:1A413030_103_0196:2 + cc:1A413030_103_0196:3"
_CORRECT_TIMING = (
    "混凝土浇筑宜连续进行；当必须间歇时，其间歇时间宜尽量缩短，并应在前层混凝土"
    "初凝之前，将次层混凝土浇筑完毕；否则，应留置施工缝"
)

# 规则组 C：施工缝处理工序（锚 ca:1A413030_103_0196 EP关键词级，
# 回源 2026教材P103 CET_1A413030_P0103_001 证据链闭合——§8.2 C5/D2 裁决）
_SEQ_CANONICAL = ("已浇混凝土强度达 1.2N/mm²", "凿毛处理", "清理松动石子浮浆",
                  "铺 30mm 砂浆", "浇筑振捣养护")
_ANCHOR_SEQ = "ca:1A413030_103_0196（EP关键词级·回源 CET_1A413030_P0103_001）"
_CORRECT_SEQ = ("施工缝处理工序应为：" + "→".join(_SEQ_CANONICAL) +
                "，不得先浇后凿或未达强度即接")

# 规则组 D：后浇带技术措施（锚 kc:1A413030_103_0196:1 + {2018,案例三问题3}；
# ≥28d 封闭与钢丝网只挂真题锚；收口网锚 kc:1A413030_094_0176:0）
_ANCHOR_POSTPOUR = "kc:1A413030_103_0196:1 + {2018,案例三问题3}"
_ANCHOR_2018 = "{2018,案例三问题3}"
_ANCHOR_MESH_NET = "kc:1A413030_094_0176:0"
_POSTPOUR_CURING_MIN_D = 14
_POSTPOUR_CLOSURE_MIN_D = 28
_CONCRETE_DOMAIN = ("微膨胀混凝土", "与原结构同强度等级的普通混凝土")
_GRADE_DOMAIN = ("比原结构提高一级", "与原结构同级", "比原结构降低一级")

# 规则组 E：防水混凝土施工缝（锚只挂真题 {2015,第26题}——jury(§9)#11）
_ANCHOR_WATERPROOF = "{2015,第26题}"
_WATERPROOF_PRACTICES: tuple[tuple[str, str, bool], ...] = (
    ("地下防水混凝土连续浇筑、宜少留施工缝", "连续浇筑宜少留缝", True),
    ("防水混凝土施工缝留在剪力最大处", "留在剪力最大处", False),
    ("防水混凝土施工缝留在底板与侧墙交接处", "留在底板与侧墙交接处", False),
)
_WATERPROOF_PRACTICE_DOMAIN = tuple(p[1] for p in _WATERPROOF_PRACTICES)
_CORRECT_WATERPROOF = ("防水混凝土应连续浇筑、宜少留施工缝；留缝时不应留在剪力最大处"
                       "或底板与侧墙交接处")
_WATERPROOF_CURING_MIN_D = 14


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"C01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：留置位置——每构件 正确位置(妥) + R4 点名违例(不妥)，双极性
    for member, spec in _POSITION_RULES.items():
        add("A-position", f"{member}的施工缝留置在{spec['correct']}",
            {"member": member, "position": spec["correct"]}, True,
            f"{member}的施工缝应留置在{spec['correct']}", _ANCHOR_POS)
        add("A-position", f"{member}的施工缝留置在{spec['wrong']}",
            {"member": member, "position": spec["wrong"]}, False,
            f"{member}的施工缝应留置在{spec['correct']}", _ANCHOR_POS)

    # 组 B：留设时机——初凝前浇完(妥) / 超初凝未处理直接续浇(不妥)（皮×2）
    for skin in _SITE_SKINS:
        add("B-timing",
            f"{skin}混凝土浇筑需短时间歇，间歇时间尽量缩短，并在前层混凝土初凝之前"
            f"浇筑完次层混凝土",
            {"poured_before_initial_set": True}, True, _CORRECT_TIMING, _ANCHOR_TIMING)
        add("B-timing",
            f"{skin}混凝土浇筑间歇超过前层混凝土初凝时间，未作处理即继续浇筑次层混凝土",
            {"poured_before_initial_set": False}, False, _CORRECT_TIMING, _ANCHOR_TIMING)

    # 组 C：处理工序——完整正序 + R4 点名违例（先浇后凿/未达强度即接）（皮×2）
    seq_cases: list[tuple[str, list[str]]] = [("complete", list(_SEQ_CANONICAL))]
    swapped = list(_SEQ_CANONICAL)
    i_chisel, i_pour = swapped.index("凿毛处理"), swapped.index("浇筑振捣养护")
    swapped[i_chisel], swapped[i_pour] = swapped[i_pour], swapped[i_chisel]
    seq_cases.append(("order:先浇后凿", swapped))
    seq_cases.append(("omit:未达强度即接",
                      [s for s in _SEQ_CANONICAL if s != "已浇混凝土强度达 1.2N/mm²"]))
    for skin, (kind, steps) in itertools.product(_SITE_SKINS, seq_cases):
        add("C-seq", f"{skin}对既有施工缝接缝处理，工序为：{'→'.join(steps)}",
            {"steps": steps, "case": kind}, steps == list(_SEQ_CANONICAL),
            _CORRECT_SEQ, _ANCHOR_SEQ)

    # 组 D：后浇带技术措施——R4 组 D 封闭清单逐项（含正例防"见题就挑错"）
    for concrete in _CONCRETE_DOMAIN:
        add("D-postpour", f"后浇带浇筑采用{concrete}",
            {"concrete": concrete}, concrete == "微膨胀混凝土",
            "后浇带应采用微膨胀混凝土（补偿收缩）", _ANCHOR_POSTPOUR)
    for grade in _GRADE_DOMAIN:
        add("D-postpour", f"后浇带混凝土强度等级{grade}",
            {"grade": grade}, grade == "比原结构提高一级",
            "后浇带混凝土强度等级应比原结构提高一级", _ANCHOR_POSTPOUR)
    for days in (14, 10):
        add("D-postpour", f"后浇带混凝土浇筑后保持 {days}d 湿润养护",
            {"curing_d": days, "min_d": _POSTPOUR_CURING_MIN_D},
            days >= _POSTPOUR_CURING_MIN_D,
            "后浇带应保持不少于 14d 湿润养护", _ANCHOR_POSTPOUR)
    for days in (28, 10):
        add("D-postpour", f"底板后浇带在两侧主体完成 {days}d 后封闭",
            {"closure_d": days, "min_d": _POSTPOUR_CLOSURE_MIN_D},
            days >= _POSTPOUR_CLOSURE_MIN_D,
            "底板后浇带应在 ≥28d 后封闭，待两侧主体完成初期收缩", _ANCHOR_2018)
    add("D-postpour", "后浇带接缝按施工缝要求处理（整理钢筋、冲洗松动部分）",
        {"joint_treated_as_construction_joint": True}, True,
        "后浇带接缝应按施工缝处理（整理钢筋/冲洗松动部分）", _ANCHOR_POSTPOUR)
    add("D-postpour", "后浇带接缝未作处理直接浇筑混凝土",
        {"joint_treated_as_construction_joint": False}, False,
        "后浇带接缝应按施工缝处理（整理钢筋/冲洗松动部分）", _ANCHOR_POSTPOUR)
    add("D-postpour", "后浇带两侧钢丝网予以保留",
        {"mesh": "钢丝网", "action": "保留"}, True,
        "后浇带钢丝网应保留，不得剔除", _ANCHOR_2018)
    add("D-postpour", "后浇带两侧钢丝网在浇筑前全部剔除",
        {"mesh": "钢丝网", "action": "剔除"}, False,
        "后浇带钢丝网应保留，不得剔除", _ANCHOR_2018)
    add("D-postpour", "后浇带采用快易收口网，浇筑前拆除并凿毛",
        {"mesh": "快易收口网", "action": "浇筑前拆除并凿毛"}, True,
        "后浇带快易收口网应在浇筑前拆除并凿毛", _ANCHOR_MESH_NET)

    # 组 E：防水混凝土施工缝——真题锚 {2015,第26题} 封闭做法 + 养护 14d
    for surface, practice, ok in _WATERPROOF_PRACTICES:
        add("E-waterproof", surface, {"practice": practice}, ok,
            _CORRECT_WATERPROOF, _ANCHOR_WATERPROOF)
    for days in (14, 7):
        add("E-waterproof", f"防水混凝土浇筑后养护 {days}d",
            {"curing_d": days, "min_d": _WATERPROOF_CURING_MIN_D},
            days >= _WATERPROOF_CURING_MIN_D,
            "防水混凝土养护时间不少于 14d", _ANCHOR_WATERPROOF)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-position":
        spec = _POSITION_RULES.get(p["member"])
        if spec is None or p["position"] not in (spec["correct"], spec["wrong"]):
            return None  # 封闭域外的构件/位置不许出现
        return p["position"] == spec["correct"]
    if g == "B-timing":
        return bool(p["poured_before_initial_set"])
    if g == "C-seq":
        return p["steps"] == list(_SEQ_CANONICAL)
    if g == "D-postpour":
        if "concrete" in p:
            if p["concrete"] not in _CONCRETE_DOMAIN:
                return None
            return p["concrete"] == "微膨胀混凝土"
        if "grade" in p:
            if p["grade"] not in _GRADE_DOMAIN:
                return None
            return p["grade"] == "比原结构提高一级"
        if "curing_d" in p:
            return p["curing_d"] >= p["min_d"]
        if "closure_d" in p:
            return p["closure_d"] >= p["min_d"]
        if "joint_treated_as_construction_joint" in p:
            return bool(p["joint_treated_as_construction_joint"])
        if p.get("mesh") == "钢丝网":
            return p["action"] == "保留"
        if p.get("mesh") == "快易收口网":
            return p["action"] == "浇筑前拆除并凿毛"
        return None
    if g == "E-waterproof":
        if "practice" in p:
            if p["practice"] not in _WATERPROOF_PRACTICE_DOMAIN:
                return None
            return p["practice"] == "连续浇筑宜少留缝"
        if "curing_d" in p:
            return p["curing_d"] >= p["min_d"]
        return None
    return None


# 争议/🔵推理/污染层 token，禁入题面与正确做法（fail-closed）：
# 独立支设/独立设置=§8.2 C4 教材真题冲突锚(HI#2 降🔵)；跳仓/钙矾石/膨胀率=§8.2 C2
# 无锚外推降🔵；止水带/止水条=§0/§8.3 防水跨考点污染绕开；0~100/0~300=jury§9#9 单源存疑
_CONTESTED_TOKENS = ("独立支设", "独立设置", "跳仓", "钙矾石", "膨胀率",
                     "止水带", "止水条", "0~100", "0~300")


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
        "pack_id": "C01",
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
