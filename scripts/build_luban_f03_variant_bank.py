#!/usr/bin/env python3
"""F03 变体池编译期预生成器（防水构造层次：屋面/地下）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本承接 S05/F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`）
——纯确定性枚举（零 LLM、零随机），从 F03 Pack §4 R4 三个封闭规则组派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（等级/道数/层序/数值/种数在封闭取值域内代换）+ 期望判定
  （妥/不妥）+ 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 F03 pack 裁决）：
- **jury §9 #11 争议档整档不入**（单源存疑·汇编层"留残留待专家裁决"未收）：
  「坡度、胶凝用量、坍落度等'宜/不宜'措辞被硬化为越界即错」——种植排水坡度
  （≥2%/≥1%）、胶凝材料 ≥320kg/m³、入泵坍落度 120~160mm 三档**双极性均不入池**
  （token 门拦截）。水胶比 ≤0.50 为「不得大于」强制措辞（§8.2 C5 直读 quote），
  不在 #11 争议范围，保留。
- **jury §9 #10 争议负例不入**：「地下三级写 P8 未必错（工程提高等级需看题干）」
  ——三级档只入 R4 封闭取值正例（≥1道/防水混凝土应选/外设不作要求/P6），
  「写P8=不妥」「外设强加要求=不妥」两个负例不入池。
- **屋面道数"写多"不外推**：R4 判分边界只点名「道数写少/漏卷材≥1道=不妥」——
  道数网格只枚举 claimed≤canon 的格（写多档无判分边界，不入）。
- **种植屋面层序只枚举点名违例**：R4 判分边界点名「漏耐根穿刺层」；"层序错"
  未点名具体排列，不外推其他置换（照 F16 组 B jury 残留#5 范式）。
- **不在 R4 三组内的判分眼不入池**：室内防水翻起高度（≥2000/1200/250mm）、
  管道穿楼板、墙体防潮（`{2023,第22题}`）为 §0/§5 本体但 **R4 未建组**——
  本池严格以 R4 组为变量权威，不外溢（token 门拦截）。
- **🔵/🔴 禁入**：保温层选材（`kc:1A413030_125_0238:1` 🔵 保温隔热邻接）、
  卷材铺贴/搭接工艺与 2025 卷材性能题（🔵 F02 territory，§8.2 C2）、外墙防水
  （🔵 外延）、机理讲解词（容错/湿迁移/毛细孔）、镜头 A/C 自造真题锚所涉
  女儿墙泛水节点（§8.2 C1/C3 已删）——token 禁入题面与正确做法。
- **真题锚仅 3 条**（`{2019,第12题}`/`{2020,第12题}`/`{2023,第22题}`，直读核真）
  ——本池只引前两条（第三条墙体防潮不在 R4 组内），证据包外年题号禁入。
- **R7 边界档位全 🔴 待裁决**——不作变体判定依据，本池期望判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_f03_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_f03_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_F03_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "F03_防水构造层次屋面地下.md"

SCHEMA_NAME = "luban-f03-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 F03 Pack §4 R4 / §5，锚随行）─────────────────
# 规则组 A：屋面防水设防（封闭等级↔道数表）— 锚 kc:1A413030_122_0230:0/:2
_ANCHOR_A_GRADE = "kc:1A413030_122_0230:0"
_ANCHOR_A_BASIC = "kc:1A413030_122_0230:2"
_ROOF_LEVELS_CANON = 3          # 屋面防水等级分三级（地下才四级——R4 判分边界）
_ROOF_LEVEL_CLAIMS = (3, 4)
_CORRECT_A_LEVEL = "屋面防水等级分三级（一/二/三级）；地下工程防水等级才分四级，禁混"
_ROOF_GRADE_MIN = {"一级": 3, "二级": 2, "三级": 1}
_ROOF_LAYER_CLAIMS = (3, 2, 1)
_CORRECT_A_GRADE = ("屋面防水等级↔道数：一级≥3道(卷材≥1道)；二级≥2道(卷材≥1道)；"
                    "三级≥1道(可任选卷材/涂料)")
_MEMBRANE_CASES = (  # 「漏卷材≥1道=不妥」判分边界（一/二级卷材≥1道）
    {"grade": "一级", "total": 3, "membrane": 1,
     "surface": "屋面一级防水设防3道，其中卷材防水层1道"},
    {"grade": "一级", "total": 3, "membrane": 0,
     "surface": "屋面一级防水设防3道，全部采用涂料防水层、未设卷材防水层"},
    {"grade": "二级", "total": 2, "membrane": 1,
     "surface": "屋面二级防水设防2道，其中卷材防水层1道"},
)
_ROOF_BASIC_RULES: dict[str, dict[str, Any]] = {
    "防排方针": {"ok": ("屋面防水坚持以防为主、以排为辅",), "bad": (),
             "correct": "屋面防水应以防为主、以排为辅"},
    "设计年限": {"ok": ("屋面防水设计使用年限不低于20年",), "bad": (),
             "correct": "屋面防水设计使用年限≥20年"},
    "附加层": {"ok": ("天沟、檐沟、变形缝和泛水部位增设附加层",),
            "bad": ("泛水部位未增设附加层",),
            "correct": "天沟/檐沟/变形缝/泛水部位应增设附加层（漏附加层=不妥）"},
}

# 规则组 B：构造层次顺序（封闭层序表）
# 锚 kc:1A413030_127_0240:0/:1、kc:1A413030_125_0238:0；真题印证 {2020,第12题}
_INVERTED_SEQ = ("结构层", "找坡层", "找平层", "防水层", "保温层", "保护层")
_ANCHOR_B_INV = "{2020,第12题}(真题锚🟢·ans=B)"
_CORRECT_B_INV = ("倒置式屋面构造层次自下而上：结构层→找坡层→找平层→防水层→保温层→"
                  "保护层（口诀「结构找坡再找平，防水保温后保护」），保温层在防水层之上")
_GREEN_SEQ = ("基层", "绝热层", "找平层", "普通防水层", "耐根穿刺防水层",
              "保护层", "排(蓄)水层", "过滤层", "种植土层", "植被层")
_ANCHOR_B_GREEN = "kc:1A413030_127_0240:1"
_CORRECT_B_GREEN = "种植屋面构造层次共10层：" + "→".join(_GREEN_SEQ) + "，不得漏耐根穿刺防水层"
_VAPOR_RISE_MIN_MM = 150
_ANCHOR_B_VAPOR = "kc:1A413030_125_0238:0"
_CORRECT_B_VAPOR = ("隔汽层应设在结构层之上、保温层之下，气密性好，"
                    "沿周边墙面向上连续铺设、高出保温层不小于150mm")
_VAPOR_POS_RULES: dict[str, dict[str, Any]] = {
    "位置": {"ok": ("隔汽层设置在结构层之上、保温层之下",),
           "bad": ("隔汽层设置在防水层之上",)},
}
_ROOT_LIMITS_MM = {  # 耐根穿刺材料厚度（封闭数字）— 锚 kc:1A413030_127_0240:0
    "改性沥青类耐根穿刺防水卷材": 4.0,
    "PVC/TPO/HDPE/EPDM耐根穿刺防水卷材": 1.2,
    "喷涂聚脲防水层": 2.0,
}
_ROOT_SURFACES_MM = (4.0, 1.2, 2.0)  # 题面可出现的厚度值（封闭·全部来自 pack）
_ANCHOR_B_ROOT = "kc:1A413030_127_0240:0"
_CORRECT_B_ROOT = ("耐根穿刺材料厚度：改性沥青类≥4mm；PVC/TPO/HDPE/EPDM≥1.2mm；"
                   "喷涂聚脲≥2mm（厚度写少=不妥）")

# 规则组 C：地下防水设防 + 结构自防水（封闭表）
# 锚 kc:1A413030_130_0247:0/:1、kc:1A413030_130_0248:0/:1、kc:1A413030_130_0249:0/:1/:2、
#    kc:1A413030_131_0250:0/:1；真题印证 {2019,第12题}
_UG_LEVELS_CANON = 4
_UG_LEVEL_CLAIMS = (4, 5, 3)  # 「写五级/总数错=不妥」
_ANCHOR_C_LEVEL = "{2019,第12题}(真题锚🟢·ans=C)"
_CORRECT_C_LEVEL = "地下工程防水等级分四级（一/二/三/四级）；屋面防水等级才分三级，禁混"
_ANCHOR_C_G1 = "kc:1A413030_130_0247:0"
_CORRECT_C_G1 = ("地下一级防水：防水做法≥3道；防水混凝土1道(应选)；外设防水层≥2道"
                 "(卷材或涂料≥1道)；抗渗等级≥P8，缺一不可")
_UG_GRADE1_CASES = (
    {"surface": "地下工程防水等级一级：防水做法3道，防水混凝土1道（应选），"
                "外设防水层2道（其中卷材或涂料防水层1道），防水混凝土抗渗等级P8",
     "total": 3, "concrete": 1, "external": 2, "imperm": "P8"},
    {"surface": "地下工程防水等级一级：仅采用抗渗等级P8的防水混凝土，不再外设防水层",
     "total": 1, "concrete": 1, "external": 0, "imperm": "P8"},
    {"surface": "地下工程防水等级一级：防水做法3道，外设防水层仅1道，防水混凝土抗渗等级P8",
     "total": 3, "concrete": 1, "external": 1, "imperm": "P8"},
    {"surface": "地下工程防水等级一级：防水做法3道，防水混凝土1道、外设防水层2道，"
                "防水混凝土抗渗等级P6",
     "total": 3, "concrete": 1, "external": 2, "imperm": "P6"},
)
_ANCHOR_C_G3 = "kc:1A413030_130_0247:1"
_CORRECT_C_G3 = ("地下三级防水：防水做法≥1道；防水混凝土1道(应选)；外设防水层不作要求；"
                 "抗渗等级≥P6（负例档 jury#10 争议不入，仅正例）")
_ANCHOR_C_CONCRETE = {"imperm_floor": "kc:1A413030_130_0249:0",
                      "trial": "kc:1A413030_130_0249:0",
                      "ratio": "kc:1A413030_130_0249:1",
                      "layer": "kc:1A413030_130_0249:2"}
_CORRECT_C_CONCRETE = ("防水混凝土：抗渗等级≥P6；试配抗渗比设计提高0.2MPa(设计P8则试配P10)；"
                       "水胶比不得大于0.50；分层连续浇筑、分层厚度≤500mm")
_CONCRETE_CASES = (
    {"kind": "imperm_floor", "value": "P6",
     "surface": "防水混凝土抗渗等级不低于P6"},
    {"kind": "trial", "design": "P8", "trial": "P10",
     "surface": "防水混凝土设计抗渗等级P8，试配抗渗等级按P10"},
    {"kind": "trial", "design": "P8", "trial": "P8",
     "surface": "防水混凝土设计抗渗等级P8，试配抗渗等级仍按P8"},
    {"kind": "ratio", "relation": "不大于0.50",
     "surface": "防水混凝土水胶比不大于0.50"},
    {"kind": "ratio", "relation": "大于0.50",
     "surface": "防水混凝土水胶比大于0.50"},
    {"kind": "layer", "layer_mm": 500,
     "surface": "防水混凝土分层连续浇筑，分层厚度500mm"},
)
_JOINT_KINDS_MIN = {"施工缝": 2, "后浇带": 1}
_ANCHOR_C_JOINT_KINDS = {"施工缝": "kc:1A413030_130_0248:0", "后浇带": "kc:1A413030_130_0248:1"}
_CORRECT_C_JOINT_KINDS = ("接缝防水设防种数：施工缝≥2种、后浇带≥1种"
                          "（中埋式止水带/遇水膨胀止水条胶/预埋注浆管/外贴卷材外涂涂料/"
                          "补偿收缩混凝土等，施工缝写1种=不妥）")
_JOINT_KINDS_CASES = (
    {"joint": "施工缝", "kinds": 2,
     "surface": "地下工程施工缝防水设防采用2种防水措施（遇水膨胀止水条+中埋式止水带）"},
    {"joint": "施工缝", "kinds": 1,
     "surface": "地下工程施工缝防水设防仅采用1种防水措施"},
    {"joint": "后浇带", "kinds": 1,
     "surface": "地下工程后浇带防水设防采用1种防水措施（补偿收缩混凝土）"},
)
_H_RISE_MIN_MM, _HOLE_DIST_MIN_MM, _SWELL_MIN_PCT = 300, 300, 220
_ANCHOR_C_JOINT_POS = {"h_rise": "kc:1A413030_131_0250:0",
                       "hole_dist": "kc:1A413030_131_0250:0",
                       "swell": "kc:1A413030_131_0250:1"}
_CORRECT_C_JOINT_POS = ("施工缝设置：水平缝应高出底板表面≥300mm、距孔洞边缘≥300mm；"
                        "遇水膨胀止水条最终膨胀率≥220%（7d净膨胀率≤60%最终）")
_JOINT_POS_CASES = (
    {"kind": "h_rise", "rise_mm": 300,
     "surface": "墙体水平施工缝留置在高出底板表面300mm的墙体上"},
    {"kind": "h_rise", "rise_mm": 0,
     "surface": "墙体水平施工缝设在底板表面以下"},
    {"kind": "hole_dist", "dist_mm": 300,
     "surface": "施工缝距孔洞边缘300mm"},
    {"kind": "swell", "rate_pct": 220,
     "surface": "采用遇水膨胀止水条，最终膨胀率220%"},
)


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"F03-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：屋面设防——等级分级数
    for n in _ROOF_LEVEL_CLAIMS:
        add("A-roof-grade", f"作答：屋面防水等级分为{'三' if n == 3 else '四'}级",
            {"item": "分级数", "claimed_levels": n}, n == _ROOF_LEVELS_CANON,
            _CORRECT_A_LEVEL, _ANCHOR_A_GRADE)
    # 组 A：等级↔道数网格（只枚举 claimed<=canon 的格——写多档无判分边界不外推）
    for grade, claimed in itertools.product(_ROOF_GRADE_MIN, _ROOF_LAYER_CLAIMS):
        if claimed > _ROOF_GRADE_MIN[grade]:
            continue
        add("A-roof-grade", f"作答：屋面{grade}防水设防道数不少于{claimed}道",
            {"item": "道数", "grade": grade, "claimed_min": claimed},
            claimed == _ROOF_GRADE_MIN[grade], _CORRECT_A_GRADE, _ANCHOR_A_GRADE)
    # 组 A：卷材≥1道判分边界
    for case in _MEMBRANE_CASES:
        ok = case["total"] >= _ROOF_GRADE_MIN[case["grade"]] and case["membrane"] >= 1
        add("A-roof-grade", case["surface"],
            {"item": "卷材道数", "grade": case["grade"],
             "total": case["total"], "membrane": case["membrane"]},
            ok, _CORRECT_A_GRADE, _ANCHOR_A_GRADE)
    # 组 A：基本要求
    for item, rule in _ROOF_BASIC_RULES.items():
        for practice in rule["ok"] + rule["bad"]:
            add("A-roof-basic", f"屋面防水工程中，{practice}",
                {"item": item, "practice": practice}, practice in rule["ok"],
                rule["correct"], _ANCHOR_A_BASIC)

    # 组 B：构造层次——倒置式层序（完整正序 + 点名违例「保温写在防水之下」）
    seq_cases: list[tuple[str, list[str]]] = [("complete", list(_INVERTED_SEQ))]
    swapped = list(_INVERTED_SEQ)
    i_wp, i_ins = swapped.index("防水层"), swapped.index("保温层")
    swapped[i_wp], swapped[i_ins] = swapped[i_ins], swapped[i_wp]
    seq_cases.append(("order:保温在防水之下", swapped))
    for kind, steps in seq_cases:
        add("B-layer-seq", f"倒置式屋面构造层次自下而上为：{'→'.join(steps)}",
            {"seq": "倒置式", "steps": steps, "case": kind},
            steps == list(_INVERTED_SEQ), _CORRECT_B_INV, _ANCHOR_B_INV)
    # 组 B：种植屋面 10 层（完整 + 点名漏步「耐根穿刺防水层」，不外推其他置换）
    green_cases: list[tuple[str, list[str]]] = [
        ("complete", list(_GREEN_SEQ)),
        ("omit:耐根穿刺防水层", [s for s in _GREEN_SEQ if s != "耐根穿刺防水层"]),
    ]
    for kind, steps in green_cases:
        add("B-layer-seq", f"种植屋面构造层次自下而上为：{'→'.join(steps)}",
            {"seq": "种植屋面", "steps": steps, "case": kind},
            steps == list(_GREEN_SEQ), _CORRECT_B_GREEN, _ANCHOR_B_GREEN)
    # 组 B：隔汽层位置 + 高出保温层数值
    for item, rule in _VAPOR_POS_RULES.items():
        for practice in rule["ok"] + rule["bad"]:
            add("B-vapor", f"屋面保温工程中，{practice}",
                {"kind": "位置", "practice": practice}, practice in rule["ok"],
                _CORRECT_B_VAPOR, _ANCHOR_B_VAPOR)
    add("B-vapor", "隔汽层沿周边墙面向上连续铺设，高出保温层150mm",
        {"kind": "rise", "rise_mm": 150}, True, _CORRECT_B_VAPOR, _ANCHOR_B_VAPOR)
    add("B-vapor", "隔汽层仅铺至保温层底面周边，未沿周边墙面向上铺设高出保温层",
        {"kind": "rise", "rise_mm": 0}, False, _CORRECT_B_VAPOR, _ANCHOR_B_VAPOR)
    # 组 B：耐根穿刺厚度——材料 × 题面厚度全枚举（数值全部来自 pack）
    for material, mm in itertools.product(_ROOT_LIMITS_MM, _ROOT_SURFACES_MM):
        add("B-root-thickness", f"种植屋面采用{material}，厚度 {mm:g}mm",
            {"material": material, "thickness_mm": mm},
            mm >= _ROOT_LIMITS_MM[material], _CORRECT_B_ROOT, _ANCHOR_B_ROOT)

    # 组 C：地下设防——等级分级数
    for n in _UG_LEVEL_CLAIMS:
        add("C-underground", f"作答：地下工程防水等级分为{('四', '五', '三')[_UG_LEVEL_CLAIMS.index(n)]}级",
            {"item": "分级数", "claimed_levels": n}, n == _UG_LEVELS_CANON,
            _CORRECT_C_LEVEL, _ANCHOR_C_LEVEL)
    # 组 C：地下一级做法（含 R4 点名负例：漏外设/外设道数错/抗渗写P6）
    for case in _UG_GRADE1_CASES:
        ok = (case["total"] >= 3 and case["concrete"] >= 1
              and case["external"] >= 2 and case["imperm"] == "P8")
        add("C-underground", case["surface"],
            {"item": "一级做法", "total": case["total"], "concrete": case["concrete"],
             "external": case["external"], "imperm": case["imperm"]},
            ok, _CORRECT_C_G1, _ANCHOR_C_G1)
    # 组 C：地下三级——仅正例（负例档 jury#10 争议不入）
    add("C-underground",
        "地下工程防水等级三级：防水做法1道，防水混凝土1道（应选），"
        "外设防水层不作要求，防水混凝土抗渗等级P6",
        {"item": "三级做法", "total": 1, "concrete": 1,
         "external_required": False, "imperm": "P6"},
        True, _CORRECT_C_G3, _ANCHOR_C_G3)
    # 组 C：结构自防水·防水混凝土（胶凝/坍落度档 jury#11 争议不入）
    for case in _CONCRETE_CASES:
        params = {k: v for k, v in case.items() if k != "surface"}
        if case["kind"] == "imperm_floor":
            ok = case["value"] == "P6"
        elif case["kind"] == "trial":
            ok = int(case["trial"][1:]) == int(case["design"][1:]) + 2
        elif case["kind"] == "ratio":
            ok = case["relation"] == "不大于0.50"
        else:  # layer
            ok = case["layer_mm"] <= 500
        add("C-concrete", case["surface"], params, ok,
            _CORRECT_C_CONCRETE, _ANCHOR_C_CONCRETE[case["kind"]])
    # 组 C：接缝防水设防种数
    for case in _JOINT_KINDS_CASES:
        add("C-joint", case["surface"],
            {"item": "设防种数", "joint": case["joint"], "kinds": case["kinds"]},
            case["kinds"] >= _JOINT_KINDS_MIN[case["joint"]],
            _CORRECT_C_JOINT_KINDS, _ANCHOR_C_JOINT_KINDS[case["joint"]])
    # 组 C：施工缝设置位置 + 止水条性能（封闭数字）
    for case in _JOINT_POS_CASES:
        params = {k: v for k, v in case.items() if k != "surface"}
        if case["kind"] == "h_rise":
            ok = case["rise_mm"] >= _H_RISE_MIN_MM
        elif case["kind"] == "hole_dist":
            ok = case["dist_mm"] >= _HOLE_DIST_MIN_MM
        else:  # swell
            ok = case["rate_pct"] >= _SWELL_MIN_PCT
        add("C-joint", case["surface"], params, ok,
            _CORRECT_C_JOINT_POS, _ANCHOR_C_JOINT_POS[case["kind"]])

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-roof-grade":
        if p["item"] == "分级数":
            return p["claimed_levels"] == _ROOF_LEVELS_CANON
        if p["item"] == "道数":
            if p["claimed_min"] > _ROOF_GRADE_MIN.get(p["grade"], -1):
                return None  # 写多档无判分边界，不许出现
            return p["claimed_min"] == _ROOF_GRADE_MIN[p["grade"]]
        if p["item"] == "卷材道数":
            return p["total"] >= _ROOF_GRADE_MIN[p["grade"]] and p["membrane"] >= 1
        return None
    if g == "A-roof-basic":
        rule = _ROOF_BASIC_RULES.get(p["item"])
        if rule is None:
            return None
        if p["practice"] in rule["ok"]:
            return True
        if p["practice"] in rule["bad"]:
            return False
        return None
    if g == "B-layer-seq":
        canon = {"倒置式": list(_INVERTED_SEQ), "种植屋面": list(_GREEN_SEQ)}.get(p["seq"])
        if canon is None:
            return None
        return p["steps"] == canon
    if g == "B-vapor":
        if p["kind"] == "位置":
            rule = _VAPOR_POS_RULES["位置"]
            if p["practice"] in rule["ok"]:
                return True
            if p["practice"] in rule["bad"]:
                return False
            return None
        if p["kind"] == "rise":
            return p["rise_mm"] >= _VAPOR_RISE_MIN_MM
        return None
    if g == "B-root-thickness":
        limit = _ROOT_LIMITS_MM.get(p["material"])
        if limit is None or p["thickness_mm"] not in _ROOT_SURFACES_MM:
            return None  # 封闭域外材料/厚度不许出现
        return p["thickness_mm"] >= limit
    if g == "C-underground":
        if p["item"] == "分级数":
            return p["claimed_levels"] == _UG_LEVELS_CANON
        if p["item"] == "一级做法":
            return (p["total"] >= 3 and p["concrete"] >= 1
                    and p["external"] >= 2 and p["imperm"] == "P8")
        if p["item"] == "三级做法":
            return (p["total"] >= 1 and p["concrete"] >= 1
                    and not p["external_required"] and p["imperm"] == "P6")
        return None
    if g == "C-concrete":
        if p["kind"] == "imperm_floor":
            return p["value"] == "P6"
        if p["kind"] == "trial":
            return int(p["trial"][1:]) == int(p["design"][1:]) + 2  # 提高0.2MPa: P8→P10
        if p["kind"] == "ratio":
            if p["relation"] not in ("不大于0.50", "大于0.50"):
                return None
            return p["relation"] == "不大于0.50"
        if p["kind"] == "layer":
            return p["layer_mm"] <= 500
        return None
    if g == "C-joint":
        if p.get("item") == "设防种数":
            floor = _JOINT_KINDS_MIN.get(p["joint"])
            return None if floor is None else p["kinds"] >= floor
        if p["kind"] == "h_rise":
            return p["rise_mm"] >= _H_RISE_MIN_MM
        if p["kind"] == "hole_dist":
            return p["dist_mm"] >= _HOLE_DIST_MIN_MM
        if p["kind"] == "swell":
            return p["rate_pct"] >= _SWELL_MIN_PCT
        return None
    return None


# 争议/🔵邻接/越 R4 边界层 token，禁入题面与正确做法（fail-closed）：
# 坡度/胶凝/坍落度=jury#11 争议档；翻起/淋浴/盥洗=室内防水不在 R4 组内；
# 女儿墙=镜头A/C 自造泛水节点已删(§8.2 C1/C3)；搭接/铺贴/满粘=F02 卷材施工 territory
# (§8.2 C2)；吸水率/导热系数=保温层选材 🔵 邻接；容错/湿迁移/毛细孔=🔵 机理讲解词
_CONTESTED_TOKENS = ("坡度", "胶凝", "坍落度", "翻起", "淋浴", "盥洗", "女儿墙",
                     "搭接", "铺贴", "满粘", "吸水率", "导热系数",
                     "容错", "湿迁移", "毛细孔")


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
        "pack_id": "F03",
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
