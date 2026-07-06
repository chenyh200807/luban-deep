#!/usr/bin/env python3
"""C02 变体池编译期预生成器（进度款与计量计价）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。先例：S05（`scripts/build_luban_s05_variant_bank.py`）
与 F16（`scripts/build_luban_f16_variant_bank.py`，fail-closed 主模板）。纯确定性
枚举（零 LLM、零随机、零时间依赖），从 C02 Pack §4 R4 六维封闭变量集派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

计算型 pack 的建池口径（照任务红线）：C02 的核心真题是多步算术整题（逐月进度款表/
综合单价重算 5453/调值公式 14250 例），**多步算术求值题面一律不入池**；本池只收
R4 给出封闭公式/钉死常数后可机械二值裁决的三类判断——法定阈值方向（≤3%/≤10%/
≥80%）、公式结构方向（起扣点/预付款基数/税口径）、封闭集合成员与责任归类
（五要素/不得竞争性/指定/维度6 扰动事件），判定均可由整数比较或封闭映射在
params 内独立复核。

诚实边界（fail-closed，逐条对应 C02 pack 裁决）：
- **jury(§10) 高可信#3（已裁决）**：安全生产费「开工后一个月内付≥50%」已从 R4
  维度5 封闭集移出（证据包 74 条 0 命中，属安全科目 🔵 邻接）——整档不入池，
  "安全生产费" token 争议门拦截。
- **jury(§10)#9 单源存疑未裁决**：挣值法「🟢本体但非直接判分」定位矛盾——挣值
  族（BCWP/CV/SV/CPI/SPI）整档不入池，token 拦截；HI#4（已裁决）SV<0 推论降 🔵
  按合同约定——同族一并不入。
- **jury(§10) 高可信#5（已裁决）**：主要材料所占比重为**题面给定变量、非常数**
  （60%/65%/70% 皆为例值）——起扣点公式变体不带占比数值，correct_statement 附
  变量声明；G-4"固定 60% 起扣"编造已剔，不复现。
- **jury(§10)#13 单源存疑未裁决**：起扣点公式"合同价"含/不含暂列口径——公式
  变体只判**公式结构方向**（错误结构在任一口径下均错），不判基数含/不含暂列；
  预付款基数扣暂列另有 🟢 多真题锚（2015案例4/2019第1题/2021案例四）独立成组。
- **G-2/G-3 真题误挂已剔**：2025第1题（实为资格预审/工程总承包）不作任何锚，
  token 拦截；指定供应商/分包锚统一 2022第(四)题。
- **索赔时限 28 天档**：错因码映射争议（jury HI#2 系错因码层裁决）且属程序时点
  记忆点——不入池，"28天" token 拦截。
- **多步算术族不入池**：逐月进度款表（2019第1题）、综合单价重算（2020案例四
  4433→5453）、调值公式（`ca:1A435000_045_0064` 14250 例）、索赔金额逐层计提
  ——均需多步算术求值，超出机械二值判定边界；"调值" token 拦截。
- **R7 六边界候选全 🔴 待真人/专家裁决**——不作变体判定依据，本池期望判定只有
  妥/不妥二值。

用法::

    python3 scripts/build_luban_c02_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_c02_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_C02_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "C02_进度款与计量计价.md"

SCHEMA_NAME = "luban-c02-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 C02 Pack §4 R4 / §5，锚随行）─────────────────
# 场景皮：项目上下文的封闭集合（换皮不换判分点）
_SITE_SKINS = ("某住宅楼项目", "某厂房项目")

# 组 A：法定阈值（R4 维度5 封闭钉死常数；题面百分比为封闭皮值，阈值本身不变）
_RETENTION_CAP_PCT = 3      # 质保金 ≤ 结算总价 3%（kc:1A435000_044_0059:0）
_RETENTION_SURFACES = (2, 3, 5)   # 5% = 2022第(四)题 故意设错值
_ANCHOR_RETENTION = "kc:1A435000_044_0059:0 + 2022第(四)题"
_CORRECT_RETENTION = "累计预留质量保证金（或保函）不得超过工程结算总价的 3%"
_BOND_CAP_PCT = 10          # 履约保证金 ≤ 中标价 10%
_BOND_SURFACES = (8, 10, 15)      # 15% = 2022第(四)题 故意设错值
_ANCHOR_BOND = "2022第(四)题"
_CORRECT_BOND = "履约保证金不得超过中标价的 10%"
_PAY_FLOOR_PCT = 80         # 未约定支付比例 ≥80%（kc:1A435000_042_0056:1）
_PAY_SURFACES = (70, 80, 90)
_ANCHOR_PAY_FLOOR = "kc:1A435000_042_0056:1"
_CORRECT_PAY_FLOOR = "合同未约定支付比例的，进度款不宜低于累计完成工程总值的 80%"

# 组 B：质保金计算基数（R5 采分点8：以结算总价为基数，不得按合同价/当期进度款/预付款）
_RETENTION_BASE_CORRECT = "工程结算总价"
_RETENTION_BASE_DOMAIN = ("工程结算总价", "签约合同价", "当期进度款", "预付款")
_ANCHOR_RETENTION_BASE = "kc:1A435000_044_0059:0"
_CORRECT_RETENTION_BASE = ("质保金上限应以工程结算总价为基数，不得按合同价/当期进度款/"
                           "预付款计算")

# 组 C：不得作为竞争性费用（锚 m35:Q19-1A432000:P4 + 2018第3题）
_NONCOMPETE_ITEMS = ("安全文明施工费", "规费", "税金")
_ANCHOR_NONCOMPETE = "m35:Q19-1A432000:P4 + 2018第3题"

# 组 D：工程量清单五要素（锚 m35:Q19-1A432000:P4）
_LIST_ELEMENTS = ("项目编码", "项目名称", "项目特征", "计量单位", "工程量")
_ANCHOR_ELEMENTS = "m35:Q19-1A432000:P4"

# 组 E：起扣点公式结构（锚 kc:1A435000_043_0058:1；错误结构逐字取自因果链②易错/
# R7 边界2 点名，不外推其他变形；主要材料所占比重=题面变量非常数——jury HI#5）
_QIKOU_CORRECT_FORMULA = "合同价 − 预付款 ÷ 主要材料所占比重"
_QIKOU_FORMULA_DOMAIN = (
    "合同价 − 预付款 ÷ 主要材料所占比重",
    "合同价 × 主要材料所占比重 − 预付款",
    "预付款 ÷ 合同价",
)
_ANCHOR_QIKOU = "kc:1A435000_043_0058:1"
_CORRECT_QIKOU = ("起扣点＝合同价 − 预付款 ÷ 主要材料所占比重；主要材料所占比重为"
                  "题面给定变量、非常数")
# 组 E：预付款基数先扣暂列金额（锚 kc:1A435000_043_0058:0 + 2015案例4）
_ANCHOR_ADVANCE = "kc:1A435000_043_0058:0 + 2015案例4"
_CORRECT_ADVANCE = "预付款＝合同价（扣除暂列金额后）×预付款比例"

# 组 F：综合单价/税口径（锚 kc:1A432002_035_0046:0；双重计税 + 2020案例四）
_ANCHOR_PRICE = "kc:1A432002_035_0046:0"
_ANCHOR_PRICE_TAX = "kc:1A432002_035_0046:0 + 2020案例四"
_CORRECT_PRICE = ("综合单价＝不含增值税的税前全费用价（含人/材/机/管/利+一定风险）；"
                  "增值税只在结算最末整体计提一次，不得双重计税")

# 组 G：不得指定供应商/分包（锚 2022第(四)题）
_ANCHOR_DESIGNATE = "2022第(四)题"
_CORRECT_DESIGNATE = "建设单位不得指定供应商/品牌、不得指定分包人"

# 组 H：索赔成立性（R4 维度6 封闭 3 类扰动事件；锚随案例行）
_CLAIM_CAUSE_OWNER = "发包人责任"
_CLAIM_CAUSE_SELF = "承包人自身原因"
_CLAIM_CAUSE_FORCE = "不可抗力"


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"C02-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：法定阈值三条（钉死常数，题面值封闭皮）
    for pct in _RETENTION_SURFACES:
        add("A-retention", f"合同约定按工程结算总价累计预留 {pct}% 质量保证金",
            {"pct": pct, "cap_pct": _RETENTION_CAP_PCT}, pct <= _RETENTION_CAP_PCT,
            _CORRECT_RETENTION, _ANCHOR_RETENTION)
    for pct in _BOND_SURFACES:
        add("A-bond", f"招标文件要求中标人提交中标价 {pct}% 的履约保证金",
            {"pct": pct, "cap_pct": _BOND_CAP_PCT}, pct <= _BOND_CAP_PCT,
            _CORRECT_BOND, _ANCHOR_BOND)
    for pct in _PAY_SURFACES:
        add("A-floor", f"合同未约定进度款支付比例，发包人按累计完成工程总值的 {pct}% 支付",
            {"pct": pct, "floor_pct": _PAY_FLOOR_PCT}, pct >= _PAY_FLOOR_PCT,
            _CORRECT_PAY_FLOOR, _ANCHOR_PAY_FLOOR)

    # 组 B：质保金计算基数（封闭 4 取值，只有结算总价为妥）
    for base in _RETENTION_BASE_DOMAIN:
        add("B-base", f"项目按{base}的 3% 控制质量保证金累计预留上限",
            {"base": base}, base == _RETENTION_BASE_CORRECT,
            _CORRECT_RETENTION_BASE, _ANCHOR_RETENTION_BASE)

    # 组 C：不得竞争性费用——成员判断双极性
    for item in _NONCOMPETE_ITEMS:
        add("C-noncompete", f"投标报价时将「{item}」作为竞争性费用予以下浮",
            {"item": item, "competitive": True}, False,
            f"「{item}」不得作为竞争性费用", _ANCHOR_NONCOMPETE)
        add("C-noncompete", f"「{item}」按规定计取，不作为竞争性费用参与报价竞争",
            {"item": item, "competitive": False}, True,
            f"「{item}」不得作为竞争性费用", _ANCHOR_NONCOMPETE)

    # 组 D：工程量清单五要素——成员判断双极性
    domain = "/".join(_LIST_ELEMENTS)
    for element in _LIST_ELEMENTS:
        add("D-elements", f"招标人将「{element}」列为分部分项工程量清单的必备要素",
            {"element": element, "listed": True}, True,
            f"「{element}」属于工程量清单五要素（{domain}）", _ANCHOR_ELEMENTS)
        add("D-elements", f"招标人认为「{element}」不属于工程量清单五要素",
            {"element": element, "listed": False}, False,
            f"「{element}」属于工程量清单五要素（{domain}）", _ANCHOR_ELEMENTS)

    # 组 E：起扣点公式结构（1 正 + 2 个点名错误结构）
    for formula in _QIKOU_FORMULA_DOMAIN:
        add("E-qikou", f"项目按「起扣点 ＝ {formula}」计算预付款起扣点",
            {"formula": formula}, formula == _QIKOU_CORRECT_FORMULA,
            _CORRECT_QIKOU, _ANCHOR_QIKOU)
    # 组 E：预付款基数先扣暂列金额（皮×2）
    for skin in _SITE_SKINS:
        add("E-advance", f"{skin}以扣除暂列金额后的签约合同价乘以预付款比例计算工程预付款",
            {"deduct_provisional_sum": True}, True, _CORRECT_ADVANCE, _ANCHOR_ADVANCE)
        add("E-advance", f"{skin}以含暂列金额的签约合同价直接乘以预付款比例计算工程预付款",
            {"deduct_provisional_sum": False}, False, _CORRECT_ADVANCE, _ANCHOR_ADVANCE)

    # 组 F：综合单价/税口径（含正例防"见题就挑错"）
    for surface, tax_in_unit, tax_end_once, anchor in (
        ("综合单价按不含增值税的税前全费用价（含人工费/材料费/机械费/管理费/利润及"
         "一定风险费用）确定", False, True, _ANCHOR_PRICE),
        ("综合单价中计入增值税再参与计价", True, False, _ANCHOR_PRICE_TAX),
        ("增值税在结算最末按整体计提一次，综合单价内不含税", False, True, _ANCHOR_PRICE),
        ("综合单价内已含增值税，结算时再整体乘以(1+增值税率)", True, True, _ANCHOR_PRICE_TAX),
    ):
        add("F-price", surface,
            {"tax_in_unit_price": tax_in_unit, "tax_applied_once_at_end": tax_end_once},
            (not tax_in_unit) and tax_end_once, _CORRECT_PRICE, anchor)

    # 组 G：不得指定供应商/分包（2022第(四)题 判不妥；含承包人自主采购正例）
    for surface, designates in (
        ("建设单位在合同中指定钢材供应商", True),
        ("建设单位指定专业工程分包人", True),
        ("主要材料由承包人按合同约定标准自行采购选择供应商", False),
    ):
        add("G-designate", surface, {"owner_designates": designates}, not designates,
            _CORRECT_DESIGNATE, _ANCHOR_DESIGNATE)

    # 组 H：索赔成立性（R4 维度6 封闭 3 类扰动事件，成立性只看事件归类）
    add("H-claim", "因发包人图纸延误造成停工，承包人就工期和费用提出索赔",
        {"cause": _CLAIM_CAUSE_OWNER, "claim_item": "工期和费用"}, True,
        "发包人责任（图纸延误/甲供材不合格/甲方指令）造成的损失可索赔工期和费用",
        "2018第4题 + 2021案例四（R4维度6·发包人责任档）")
    add("H-claim", "承包人自有设备故障造成停工，承包人向发包人索赔停工费用",
        {"cause": _CLAIM_CAUSE_SELF, "claim_item": "费用"}, False,
        "承包人自身原因（自有设备故障）造成的损失不可索赔",
        "2018第4题（R4维度6·承包人自身原因档）")
    add("H-claim", "不可抗力造成承包人机具损失，承包人向发包人索赔机具损失",
        {"cause": _CLAIM_CAUSE_FORCE, "claim_item": "机具损失"}, False,
        "不可抗力造成的承包人机具损失由承包人自担",
        "kc:1A432000_047_0067:0")
    add("H-claim", "不可抗力造成工期延误，承包人提出工期顺延",
        {"cause": _CLAIM_CAUSE_FORCE, "claim_item": "工期顺延"}, True,
        "不可抗力造成的工期延误可顺延工期",
        "kc:1A432000_047_0067:0 + R4维度6（不可抗力→工期可顺延）")

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-retention" or g == "A-bond":
        return p["pct"] <= p["cap_pct"]
    if g == "A-floor":
        return p["pct"] >= p["floor_pct"]
    if g == "B-base":
        if p["base"] not in _RETENTION_BASE_DOMAIN:
            return None  # 封闭域外的基数不许出现
        return p["base"] == _RETENTION_BASE_CORRECT
    if g == "C-noncompete":
        if p["item"] not in _NONCOMPETE_ITEMS:
            return None
        return not p["competitive"]
    if g == "D-elements":
        if p["element"] not in _LIST_ELEMENTS:
            return None
        return bool(p["listed"])
    if g == "E-qikou":
        if p["formula"] not in _QIKOU_FORMULA_DOMAIN:
            return None
        return p["formula"] == _QIKOU_CORRECT_FORMULA
    if g == "E-advance":
        return bool(p["deduct_provisional_sum"])
    if g == "F-price":
        return (not p["tax_in_unit_price"]) and p["tax_applied_once_at_end"]
    if g == "G-designate":
        return not p["owner_designates"]
    if g == "H-claim":
        if p["cause"] == _CLAIM_CAUSE_OWNER:
            return p["claim_item"] in ("工期和费用", "工期", "费用")
        if p["cause"] == _CLAIM_CAUSE_SELF:
            return False
        if p["cause"] == _CLAIM_CAUSE_FORCE:
            if p["claim_item"] == "工期顺延":
                return True
            if p["claim_item"] == "机具损失":
                return False
            return None  # 清理可赔等其余分支未入池，不许出现
        return None
    return None


# 争议/移出封闭集/误挂已剔层 token，禁入题面与正确做法（fail-closed）：
# 安全生产费=jury HI#3 已移出维度5；挣值/BCWP/CV/SPI/CPI=jury#9 定位矛盾单源未裁决
# +HI#4 SV推论降🔵；调值=多步算术族不入池；28天=索赔时限档不入池；2025第1题=G-2 误挂已剔
_CONTESTED_TOKENS = ("安全生产费", "挣值", "BCWP", "BCWS", "ACWP", "CPI", "SPI",
                     "调值", "28天", "2025第1题")


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
        "pack_id": "C02",
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
