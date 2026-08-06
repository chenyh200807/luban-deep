#!/usr/bin/env python3
"""E06 变体池编译期预生成器（工程量清单与合同价款约定·2026 GB/T50500-2024 新规）。

承接 E01/S05/F16 先例（`scripts/build_luban_e01_variant_bank.py` 等）：双轮设计
v3.2 §8 红线——R4 变体在**编译期**按封闭规则预生成、过 gate、（双签后）签发入池；
runtime 只抽取，禁运行时 LLM 现编。纯确定性枚举（零 LLM、零随机、零时间依赖），
从 E06 Pack §4 R4 六个封闭规则组派生变体，生成器与校验器从同一规则表**分别**推导
判定互证。

2026 新增点纪律（照任务硬约束）：
- 所有 anchor 指向 `_E06_compiled_source.json` 中经 `mine_E06.py` 原文闸核验的
  cc:/kc: 采分点（教材溯源=2026 块 chunk_id）；本脚本启动时**直读源料核验全部
  anchor 存在**（fail-closed），杜绝锚漂移。
- 题面禁用 OCR 存疑短语（「有害身体健康 的环境」「生活生活垃圾」——见 pack §8.4
  待核对清单）；禁用邻接 territory token（E01 计价计算 / C02 进度款 / K01 索赔）。
- status 恒 `candidate` + `review_track: pending_dual_sign(teaching+scoring)`；
  签发唯一入口 = `docs/原始数据/考点原料/promote_variant_bank.py`（双签工单
  `2026-08-06-E06-Z01-双签工单.md` 走完前不得 promote）。

机械可裁决边界：本池只做**责任主体/规定动作/处置分流/程序时点**的二值判断，
无任何多步算术题面。

用法::

    python3 scripts/build_luban_e06_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_e06_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_E06_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "E06_工程量清单与合同价款约定2026.md"
SRC_PATH = REPO / "docs" / "原始数据" / "考点原料" / "_E06_compiled_source.json"

SCHEMA_NAME = "luban-e06-variant-bank"

# ── 锚（全部指向 _E06_compiled_source.json 采分点，启动时核验存在）──────────
_A_STRUCT = "cc:1A432002_035_0046:0"
_A_RATE = "cc:1A432002_035_0046:1"
_B_RESP = "cc:1A432002_035_0046:2"
_C_LIST = "cc:1A432002_035_0046:6"
_C_FEE = "cc:1A432002_035_0046:7"
_C_PROV = "cc:1A432002_035_0046:8"
_C_MEASURE = "cc:1A432002_035_0046:4"
_D_TYPE = "cc:1A432002_036_0047:3"
_D_TYPE_KC = "kc:1A432002_036_0047:1"
_D_SUBST = "cc:1A432002_036_0047:4"
_D_COST = "cc:1A432002_036_0047:7"
_E_UNIT = "cc:1A432002_036_0047:5"
_E_LUMP = "cc:1A432002_036_0047:6"
_E_FLOW = "cc:1A432002_037_0048:0"
_E_PROV_U = "cc:1A432002_037_0048:1"
_E_PROV_L = "cc:1A432002_037_0048:2"
_F_CLAR = "cc:1A432002_036_0047:8"

_ALL_ANCHORS = [_A_STRUCT, _A_RATE, _B_RESP, _C_LIST, _C_FEE, _C_PROV, _C_MEASURE,
                _D_TYPE, _D_TYPE_KC, _D_SUBST, _D_COST, _E_UNIT, _E_LUMP, _E_FLOW,
                _E_PROV_U, _E_PROV_L, _F_CLAR]

# ── 封闭取值域（逐字对齐 E06 Pack §4 R4 / 2026 块原文）──────────────────────
_CORRECT_A = "工程量清单应按分部分项工程项目清单、措施项目清单、其他项目清单和增值税分别编制及计价；不宜采用单价、总价计价方式的清单项目也可采用费率计价等其他计价方式"
_CORRECT_B = "分部分项清单：单价合同归发包人、总价合同（已标价）归承包人；措施项目清单：无论单价或总价合同，其完整性及准确性均由承包人负责"
_CORRECT_C = "其他项目清单含暂列金额、专业工程暂估价、计日工、总承包服务费及合同约定的其他项目；总承包服务费采用费率或总价计价，计日工采用标准规定的单价计价，暂列金额与专业工程暂估价应按招标工程量清单提供金额填报"
_CORRECT_D_TYPE = "工程量不确定宜单价合同、工程量明确宜总价合同、紧急抢险救灾或特别复杂工程宜成本加酬金合同"
_CORRECT_D_SUBST = "实行招标的工程，合同约定价格不得背离招标文件中工程范围、工期、价款、质量等实质性内容"
_CORRECT_D_COST = "成本加酬金合同总价为暂定价，应按实计算工程成本并按约定计算酬金及增值税后调整合同总价"
_CORRECT_E_DEFECT = "清单缺陷处置分流：单价合同按计价标准调整合同价格；总价合同价格视为已含合同总价、承包人补充完善且不做调整"
_CORRECT_E_PROV = "单价合同分部分项清单量为暂定量、履行中重新计量；总价合同内说明为暂定数量的清单项目按单价计价规定重新计量并调整合同价格及总价"
_CORRECT_F = "投标报价澄清应在开标后至定标前进行；算术误差及细微偏差可按计价标准修正但投标总价不得做任何调整；报价合理性疑问或漏报未报可要求澄清或说明"

_CONTRACTS = ("单价合同", "总价合同")
_PARTIES = ("发包人", "承包人")
# 分部分项清单责任随合同类型分流；措施项目清单恒归承包人
_ITEMLIST_RESP = {"单价合同": "发包人", "总价合同": "承包人"}
_MEASURELIST_RESP = {"单价合同": "承包人", "总价合同": "承包人"}

_TYPE_CORRECT = {"工程量不确定的工程": "单价合同",
                 "工程量明确的工程": "总价合同",
                 "紧急抢险救灾工程": "成本加酬金合同"}
_TYPE_MODES = ("单价合同", "总价合同", "成本加酬金合同")

_SUBST_ITEMS = ("工程范围", "工期", "价款", "质量")

_DEFECT_CORRECT = {"单价合同": "按计价标准的规定调整合同价格",
                   "总价合同": "价格视为已包含在合同总价中，不做调整"}
_DEFECT_ACTIONS = ("按计价标准的规定调整合同价格", "价格视为已包含在合同总价中，不做调整")

_CLAR_TIMING_OK = "开标后至定标前"
_CLAR_TIMINGS = ("开标前", "开标后至定标前", "定标后")


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"E06-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：清单结构与费率计价兜底
    add("A-structure", "招标人将工程量清单按分部分项工程项目清单、措施项目清单、其他项目清单和增值税分别编制及计价",
        {"parts": 4, "separate": True}, True, _CORRECT_A, _A_STRUCT)
    add("A-structure", "招标人只编制分部分项工程项目清单和措施项目清单两部分，其他项目并入措施项目清单计价",
        {"parts": 2, "separate": False}, False, _CORRECT_A, _A_STRUCT)
    add("A-structure", "编制清单时将增值税并入各清单项目价款合并计价、不再单独列出",
        {"parts": 3, "separate": False}, False, _CORRECT_A, _A_STRUCT)
    add("A-structure", "某些清单项目不宜采用单价计价、总价计价方式，招标人采用费率计价方式确定价款",
        {"rate_pricing": True, "judged_valid": True}, True, _CORRECT_A, _A_RATE)
    add("A-structure", "投标人认为清单项目价款只能采用单价计价或总价计价两种方式，费率计价不合规",
        {"rate_pricing": True, "judged_valid": False}, False, _CORRECT_A, _A_RATE)

    # 组 B：清单责任三分流——清单类别×合同类型×判给主体全枚举
    for contract, party in itertools.product(_CONTRACTS, _PARTIES):
        add("B-resp", f"{contract}履行中发现分部分项工程项目清单不完整，判其准确性、完整性由{party}负责",
            {"list": "分部分项", "contract": contract, "liable": party},
            _ITEMLIST_RESP[contract] == party, _CORRECT_B, _B_RESP)
    for contract, party in itertools.product(_CONTRACTS, _PARTIES):
        add("B-resp", f"{contract}履行中发现按项编制的措施项目清单漏项，判其完整性及准确性由{party}负责",
            {"list": "措施项目", "contract": contract, "liable": party},
            _MEASURELIST_RESP[contract] == party, _CORRECT_B, _B_RESP)

    # 组 C：其他项目清单规定动作
    add("C-other", "投标人对总承包服务费以计价基础乘以费率的方式计价",
        {"item": "总承包服务费", "mode": "费率"}, True, _CORRECT_C, _C_FEE)
    add("C-other", "投标人对总承包服务费以项计算清单项目价格（总价计价）",
        {"item": "总承包服务费", "mode": "总价"}, True, _CORRECT_C, _C_FEE)
    add("C-other", "投标人认为总承包服务费必须逐项按综合单价组价，费率计价不妥",
        {"item": "总承包服务费", "mode": "综合单价组价"}, False, _CORRECT_C, _C_FEE)
    add("C-other", "投标人对计日工采用标准规定的单价计价方式计价",
        {"item": "计日工", "mode": "单价"}, True, _CORRECT_C, _C_FEE)
    add("C-other", "投标人按招标工程量清单提供的相应金额填报暂列金额和专业工程暂估价",
        {"item": "暂列金额暂估价", "action": "按招标清单金额填报"}, True, _CORRECT_C, _C_PROV)
    add("C-other", "投标人认为某专业工程暂估价偏低，自行调高该暂估价后填入投标价",
        {"item": "暂列金额暂估价", "action": "自行调整"}, False, _CORRECT_C, _C_PROV)
    add("C-other", "投标人不采用招标工程量清单提供的暂列金额，按自身测算另行确定金额填报",
        {"item": "暂列金额暂估价", "action": "自行测算"}, False, _CORRECT_C, _C_PROV)
    add("C-other", "招标人把夜间施工增加费列入其他项目清单",
        {"item": "夜间施工增加", "action": "错列其他项目"}, False,
        "夜间施工增加属措施项目清单列举内容；其他项目清单为暂列金额、专业工程暂估价、计日工、总承包服务费及合同约定的其他项目", _C_MEASURE)
    add("C-other", "招标人在其他项目清单中列明暂列金额、专业工程暂估价、计日工和总承包服务费",
        {"item": "五项内容", "action": "正确列示"}, True, _CORRECT_C, _C_LIST)

    # 组 D：合同价款约定——类型选择全枚举 + 实质性内容 + 成本加酬金
    for scene, mode in itertools.product(_TYPE_CORRECT, _TYPE_MODES):
        add("D-agree", f"{scene}，发承包双方选用{mode}",
            {"scene": scene, "mode": mode}, _TYPE_CORRECT[scene] == mode,
            _CORRECT_D_TYPE, f"{_D_TYPE} + {_D_TYPE_KC}")
    for item in _SUBST_ITEMS:
        add("D-agree", f"某实行招标的工程，签约时双方协商变更招标文件中约定的{item}后写入合同",
            {"subst_item": item, "deviate": True}, False, _CORRECT_D_SUBST, _D_SUBST)
    add("D-agree", "某实行招标的工程，签订的合同价格与招标文件中工程范围、工期、价款、质量等实质性内容保持一致",
        {"subst_item": "全部", "deviate": False}, True, _CORRECT_D_SUBST, _D_SUBST)
    add("D-agree", "成本加酬金合同履行中，发包人按实计算合同工程成本并按约定计算酬金及增值税后调整合同总价",
        {"cost_plus_adjust": True}, True, _CORRECT_D_COST, _D_COST)
    add("D-agree", "成本加酬金合同履行中，发包人以「合同总价已约定」为由拒绝按实调整合同总价",
        {"cost_plus_adjust": False}, False, _CORRECT_D_COST, _D_COST)

    # 组 E：缺陷处置与暂定量分流——合同类型×处置动作全枚举 + 暂定量机制
    for contract, action in itertools.product(_CONTRACTS, _DEFECT_ACTIONS):
        add("E-defect", f"{contract}履行中发现工程量清单缺陷，处置为：{action}",
            {"contract": contract, "action": action},
            _DEFECT_CORRECT[contract] == action, _CORRECT_E_DEFECT,
            f"{_E_UNIT if contract == '单价合同' else _E_LUMP} + {_E_FLOW}")
    add("E-defect", "总价合同清单缺陷出现后，承包人承担工程量清单缺陷的补充完善责任",
        {"contract": "总价合同", "action": "承包人补充完善"}, True, _CORRECT_E_DEFECT, _E_FLOW)
    add("E-defect", "单价合同的分部分项工程项目清单工程数量为暂定工程量，合同履行中重新计量确定",
        {"contract": "单价合同", "prov_qty": "重新计量"}, True, _CORRECT_E_PROV, _E_PROV_U)
    add("E-defect", "单价合同履行中，发包人要求按招标工程量清单载明的暂定工程量直接结算、不再重新计量",
        {"contract": "单价合同", "prov_qty": "不重新计量"}, False, _CORRECT_E_PROV, _E_PROV_U)
    add("E-defect", "总价合同清单内说明为暂定数量的清单项目，按单价计价规定重新计量并调整合同价格及合同总价",
        {"contract": "总价合同", "prov_qty": "重新计量"}, True, _CORRECT_E_PROV, _E_PROV_L)
    add("E-defect", "总价合同清单内说明为暂定数量的清单项目实际数量增大，发包人以总价包干为由不予调整",
        {"contract": "总价合同", "prov_qty": "不重新计量"}, False, _CORRECT_E_PROV, _E_PROV_L)

    # 组 F：投标报价澄清程序——时点全枚举 + 算术误差 + 漏报
    for t in _CLAR_TIMINGS:
        add("F-clarify", f"招标人在{t}要求投标人对投标报价作出澄清或说明",
            {"timing": t}, t == _CLAR_TIMING_OK, _CORRECT_F, _F_CLAR)
    add("F-clarify", "投标文件存在算术误差，按计价标准规定修正，投标总价保持不变",
        {"arith_fix": True, "total_adjusted": False}, True, _CORRECT_F, _F_CLAR)
    add("F-clarify", "投标文件存在算术误差，修正的同时相应调整投标总价",
        {"arith_fix": True, "total_adjusted": True}, False, _CORRECT_F, _F_CLAR)
    add("F-clarify", "投标人未按要求完整填写投标报价（漏报），招标人要求其作出澄清或说明",
        {"missing_price": True, "clarify": True}, True, _CORRECT_F, _F_CLAR)

    return variants


# ── 独立一致性检查门（不复用生成分支，从 params 重新推导）────────────────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-structure":
        if "rate_pricing" in p:
            return bool(p["judged_valid"])  # 费率计价兜底合法
        return p.get("parts") == 4 and bool(p.get("separate"))
    if g == "B-resp":
        table = _ITEMLIST_RESP if p["list"] == "分部分项" else _MEASURELIST_RESP
        correct = table.get(p["contract"])
        return None if correct is None else p["liable"] == correct
    if g == "C-other":
        item, mode, action = p.get("item"), p.get("mode"), p.get("action")
        if item == "总承包服务费":
            return mode in ("费率", "总价")
        if item == "计日工":
            return mode == "单价"
        if item == "暂列金额暂估价":
            return action == "按招标清单金额填报"
        if item == "夜间施工增加":
            return False  # 属措施项目清单，错列其他项目
        if item == "五项内容":
            return action == "正确列示"
        return None
    if g == "D-agree":
        if "mode" in p:
            correct = _TYPE_CORRECT.get(p["scene"])
            return None if correct is None else p["mode"] == correct
        if "deviate" in p:
            return not p["deviate"]
        if "cost_plus_adjust" in p:
            return bool(p["cost_plus_adjust"])
        return None
    if g == "E-defect":
        if "prov_qty" in p:
            return p["prov_qty"] == "重新计量"
        if p.get("action") == "承包人补充完善":
            return p["contract"] == "总价合同"
        correct = _DEFECT_CORRECT.get(p["contract"])
        return None if correct is None else p.get("action") == correct
    if g == "F-clarify":
        if "timing" in p:
            return p["timing"] == _CLAR_TIMING_OK
        if "arith_fix" in p:
            return not p["total_adjusted"]
        if "missing_price" in p:
            return bool(p["clarify"])
        return None
    return None


# 争议/邻接/OCR 存疑 token，禁入题面与正确做法（fail-closed）：
# E01 territory(计价计算/风险费/五项汇总)；C02(进度款/预付款)；K01(索赔)；
# 造价阶段邻接(概算/估算/决算)；主体规范(甲方/乙方)；OCR 存疑(pack §8.4)
_CONTESTED_TOKENS = ("进度款", "预付款", "索赔", "概算", "估算", "决算",
                     "甲方", "乙方", "风险费", "挣值",
                     "有害身体健康", "生活生活", "运及清纳")


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


def _verify_anchors() -> None:
    """启动闸：全部 anchor 必须存在于 _E06_compiled_source.json（教材溯源铁律）。"""
    d = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    valid = {sp["point_id"] for u in d.get("units", []) for sp in u.get("scoring_points", [])}
    missing = [a for a in _ALL_ANCHORS if a not in valid]
    if missing:
        raise SystemExit(f"FAIL: anchor 不存在于源料: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    _verify_anchors()

    t0 = time.perf_counter()
    variants = build_variants()
    gen_ms = (time.perf_counter() - t0) * 1000

    gate = run_gate(variants)

    ok = not (gate["verdict_mismatches"] or gate["contested_leaks"] or gate["duplicate_surfaces"])
    core = sum(1 for v in variants if not v["extension"])
    print(f"variants={gate['total']} (core={core}) gate_pass={gate['passed']} "
          f"rate={gate['pass_rate']:.2%} gen={gen_ms:.1f}ms -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(json.dumps({k: gate[k] for k in
                          ('verdict_mismatches', 'contested_leaks', 'duplicate_surfaces')},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    if args.check:
        return 0

    payload = {
        "schema_version": SCHEMA_NAME,
        "pack_id": "E06",
        "status": "candidate",  # 双签(teaching+scoring)后经 promote_variant_bank.py 方可签发
        "review_track": "pending_dual_sign(teaching+scoring)·工单=2026-08-06-E06-Z01-双签工单.md",
        "production_basis": "官方《2026教材对比明细》变化#56–#64(GB/T50500-2024 整目变动)·2026 教材块原文锚",
        "source_pack_sha256": hashlib.sha256(PACK_PATH.read_bytes()).hexdigest(),
        "generation_ms": round(gen_ms, 2),
        "gate": gate,
        "per_group_counts": {g: sum(1 for v in variants if v["rule_group"] == g)
                             for g in sorted({v["rule_group"] for v in variants})},
        "variants": variants,
    }
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
