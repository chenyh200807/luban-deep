#!/usr/bin/env python3
"""F16 变体池编译期预生成器（双轮完整首站：成品教学卡 + 次日换皮复测）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本是该红线的第二个实证（S05 先例：
`scripts/build_luban_s05_variant_bank.py`）——纯确定性枚举（零 LLM、零随机），
从 F16 Pack §4 R4 封闭规则组派生变体，自带独立一致性检查门（生成器与校验器
从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（直径/工序/检查项在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 F16 pack 裁决）：
- **jury HI#2**：「排气孔/基层干燥 = 起鼓成因诊断 + 防复发根因」已降 🔵 工程推理
  ——组 C 变体只做**检查项枚举层**（🟢 锚 `kc:1A434000_068_0104:0`）的成员判断
  （在/不在必查项枚举内），任何成因/根因/诊断措辞禁入题面与正确做法。
- **§8.2 C2 编造防御**：「蓄水试验/淋水试验 + 时长」全 pack 源料无锚（🔴 编造），
  整族禁入池（含作为故意错误干扰项——争议 token 门拦截）。
- **jury 残留 #5**：组 B「漏其一即不全」为候选封闭、待多真题收敛——本池只枚举
  R4 判分边界**显式点名**的 4 个漏步（放气/擦干/清旧胶/重做保护层）+ 1 个显式
  点名的顺序违例（先贴后清），不外推其他排列/漏步组合。
- **组 D 区分锚为 🔵**（流淌 `kc:1A434000_076_0118:0` / 搭接 `kc:1A413030_131_0252:*`
  均为区分/相邻背景）——防混答变体标 `extension=true`（消费侧核心复测不发），
  其判定不依赖 🔵 锚，仅由 🟢 组 A 封闭方法域（起鼓治理方法 ∉ {抽气灌胶/割补}
  即不妥）推导；🔵 锚只作干扰项来源留痕。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。
- 镜头 D「养护」步无锚已删（§8.2 C6）——token 禁入池。

用法::

    python3 scripts/build_luban_f16_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_f16_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_F16_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "F16_屋面防水起鼓割补.md"

SCHEMA_NAME = "luban-f16-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 F16 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：工地上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼屋面工程", "某厂房项目屋面")

# 规则组 A：起鼓按直径分档（锚 kc:1A434000_076_0119:0 + ca:1A434000_076_0119；
# "斜十字形/新贴方形卷材"形状词出自 ca/EP grading_keywords，jury 单源#3 回真源核实有锚）
_DIAMETER_THRESHOLD_MM = 100
_DIAMETER_SURFACES_MM = (60, 80, 90, 100, 120, 150)  # 题面可出现的直径值(封闭·皮)
_METHOD_SMALL = "抽气灌胶法"
_METHOD_LARGE = "割补法（斜十字形割开、清理、吹干、重贴新贴方形卷材）"
_ANCHOR_A = "kc:1A434000_076_0119:0 + ca:1A434000_076_0119"
_CORRECT_A = (
    "应按直径分档处置：直径<100mm 用抽气灌胶法；≥100mm 斜十字形割开、清理、"
    "吹干、重贴新贴方形卷材"
)

# 规则组 B：割补工序（锚 {2017,案例二} + kc:1A434000_076_0119:0）
_SEQ_CANONICAL = (
    "割开鼓泡", "放出鼓内气体", "擦干水分", "清除旧胶结料",
    "喷灯烘烤槎口分层剥开", "重贴新卷材", "压实刮平", "重做保护层",
)
# R4 判分边界显式点名的漏步（jury 残留#5：候选封闭，只枚举点名项，不外推）
_SEQ_NAMED_OMISSIONS = ("放出鼓内气体", "擦干水分", "清除旧胶结料", "重做保护层")
_ANCHOR_B = "{2017,案例二} + kc:1A434000_076_0119:0"
_CORRECT_B = "割补工序应为：" + "→".join(_SEQ_CANONICAL) + "，不得漏步或颠倒"

# 规则组 C：屋面施工过程检查项枚举（锚 kc:1A434000_068_0104:0；
# 仅枚举层 🟢——成因/根因/诊断框定为 🔵 推理禁入，jury HI#2）
_CHECK_ITEMS = (
    "基层状况", "铺贴方向", "搭接长度", "泛水高度", "排气孔",
    "保护层", "材料相容性", "基层平整干燥", "防潮防火",
)
_ANCHOR_C = "kc:1A434000_068_0104:0 + ca:1A434000_068_0104"

# 外延（组 D 区分·防混答，区分锚 🔵 故标 extension）：判定只由 🟢 组 A 方法域推导
_MIX_CASES = (
    {"surface": "屋面卷材起鼓（直径 120mm），项目部采用钉钉子法处理",
     "wrong": "钉钉子法",
     "correct": "钉钉子法属卷材流淌治理方法；起鼓应按直径分档，≥100mm 走割补"
                "（斜十字形割开、清理、吹干、重贴）",
     "anchor": "kc:1A434000_076_0119:0（本体方法域）+ kc:1A434000_076_0118:0（区分背景🔵）"},
    {"surface": "屋面卷材起鼓（直径 120mm），项目部按流淌病害采用局部切除重铺处理",
     "wrong": "局部切除重铺",
     "correct": "局部切除重铺属卷材流淌治理方法；起鼓应按直径分档，≥100mm 走割补"
                "（斜十字形割开、清理、吹干、重贴）",
     "anchor": "kc:1A434000_076_0119:0（本体方法域）+ kc:1A434000_076_0118:0（区分背景🔵）"},
    {"surface": "对屋面卷材起鼓的治理，主答案写为「卷材应顺流水方向搭接、附加层伸入 250mm」",
     "wrong": "搭接方向/附加层当主答案",
     "correct": "搭接方向/附加层为相邻施工背景，起鼓治理主答案应为按直径分档 + 割补工序",
     "anchor": "kc:1A434000_076_0119:0（本体方法域）+ kc:1A413030_131_0252:*（相邻背景🔵）"},
)
_MIX_WRONGS = tuple(c["wrong"] for c in _MIX_CASES)


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"F16-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：直径分档——直径皮 × 两法全枚举
    for d, method in itertools.product(_DIAMETER_SURFACES_MM, (_METHOD_SMALL, _METHOD_LARGE)):
        ok = (d < _DIAMETER_THRESHOLD_MM) == (method == _METHOD_SMALL)
        add("A-diameter", f"屋面卷材起鼓，直径 {d}mm，项目部采用{method}处理",
            {"diameter_mm": d, "method": method}, ok, _CORRECT_A, _ANCHOR_A)
    # 组 A：不分档政策（一律 X = 不妥）
    for uniform in (_METHOD_SMALL, "割开重贴"):
        add("A-policy", f"项目部规定：屋面卷材起鼓不论直径大小，一律采用{uniform}处理",
            {"uniform_method": uniform}, False, _CORRECT_A, _ANCHOR_A)

    # 组 B：割补工序——完整正序 + 显式点名漏步 + 显式点名顺序违例（先贴后清）
    seq_cases: list[tuple[str, list[str]]] = [("complete", list(_SEQ_CANONICAL))]
    for omit in _SEQ_NAMED_OMISSIONS:
        seq_cases.append((f"omit:{omit}", [s for s in _SEQ_CANONICAL if s != omit]))
    swapped = list(_SEQ_CANONICAL)
    i_paste, i_clean = swapped.index("重贴新卷材"), swapped.index("清除旧胶结料")
    swapped[i_paste], swapped[i_clean] = swapped[i_clean], swapped[i_paste]
    seq_cases.append(("order:先贴后清", swapped))
    for skin, (kind, steps) in itertools.product(_SITE_SKINS, seq_cases):
        add("B-seq", f"{skin}对起鼓卷材（直径 120mm）实施割补，工序为：{'→'.join(steps)}",
            {"steps": steps, "case": kind}, steps == list(_SEQ_CANONICAL),
            _CORRECT_B, _ANCHOR_B)

    # 组 C：检查项枚举——成员判断双极性（纯枚举层，无成因/诊断措辞）
    for item in _CHECK_ITEMS:
        add("C-check", f"屋面施工过程检查中，项目部将「{item}」列入必查项",
            {"item": item, "listed_as_required": True}, True,
            f"「{item}」属于屋面施工过程检查项枚举，应列入检查", _ANCHOR_C)
        add("C-check", f"项目部认为「{item}」无需列入屋面施工过程检查项",
            {"item": item, "listed_as_required": False}, False,
            f"「{item}」属于屋面施工过程检查项枚举，应列入检查", _ANCHOR_C)

    # 外延：组 D 防混答（extension=true, 区分锚 🔵；判定由 🟢 组 A 方法域推导）
    for case in _MIX_CASES:
        add("X-mix", case["surface"], {"wrong_method_or_answer": case["wrong"]},
            False, case["correct"], case["anchor"], extension=True)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-diameter":
        if p["method"] == _METHOD_SMALL:
            return p["diameter_mm"] < _DIAMETER_THRESHOLD_MM
        if p["method"] == _METHOD_LARGE:
            return p["diameter_mm"] >= _DIAMETER_THRESHOLD_MM
        return None
    if g == "A-policy":
        return False if p.get("uniform_method") else None  # 不分档一律不妥
    if g == "B-seq":
        return p["steps"] == list(_SEQ_CANONICAL)
    if g == "C-check":
        if p["item"] not in _CHECK_ITEMS:
            return None  # 枚举外条目不许出现(封闭域)
        return bool(p["listed_as_required"])
    if g == "X-mix":
        # 起鼓治理方法域封闭(🟢 组 A)：非{抽气灌胶/割补}的方法/主答案一律不妥
        return False if p.get("wrong_method_or_answer") in _MIX_WRONGS else None
    return None


# 争议/🔵推理/🔴编造层 token，禁入题面与正确做法（fail-closed）：
# 蓄水/淋水=§8.2 C2 编造防御；成因/根因/复发/诊断=jury HI#2 降🔵推理层；养护=§8.2 C6 无锚已删
_CONTESTED_TOKENS = ("蓄水", "淋水", "成因", "根因", "复发", "诊断", "养护")


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
        "pack_id": "F16",
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
