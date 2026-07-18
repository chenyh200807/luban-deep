#!/usr/bin/env python3
"""G03 变体池编译期预生成器（桩基施工与质量问题）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。先例：S05（`scripts/build_luban_s05_variant_bank.py`）、
F16（`scripts/build_luban_f16_variant_bank.py`，含 🔵/🔴 fail-closed 范式，本脚本以其为主模板）。
纯确定性枚举（零 LLM、零随机、零时间依赖），从 G03 Pack §4 R4 三个封闭规则组
（A 预制桩施工 / B 灌注桩施工质量 / C 桩基检测）+ §5 R5 #13 质量问题封闭集派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（数值/顺序/方法在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 G03 pack §8/§9 记录）：
- **jury #1（单源未裁决）**：「缺陷用低应变/声波透射」排他表述存疑（高应变亦可判
  完整性）——本池**不生成**任何"完整性只能由低应变/声波透射检测"方向的判定变体；
  只保留反向已锚事实「低应变不能定承载力，承载力须静载（甲级必静载）」
  （锚 `kc:1A413030_093_0174:0` + `{2021,第14题}`）。
- **jury #2（单源未裁决）**：`{2024,案例二}` 主体为基坑支护属邻接——不作本池锚。
- **jury #6（单源未裁决）+ §8.2 C2 条件层**：超灌「0.8~1.0m」只挂真题锚
  `{2016,案例1}`、「≥1m」只挂教材锚 `kc:1A413030_091_0169:0`，不混挂；两口径
  冲突带（如单值 0.8m 对教材 ≥1m 不达标）**不入池**，只用两口径一致的取值。
- **§8.2 C3 越界剔除**：CFG桩/排桩支护/地下连续墙非 G03 承载桩判分眼——争议 token
  门拦截，禁入题面与正确做法。
- **§8.2 C5 无锚通识**：泥浆比重 1.1~1.3 / 水头≥2m / 导管埋深 2~6m 编译库无锚
  （🔵 通识）——具体数值禁入池（"水头压力"作防坍孔四防枚举项本身有锚
  `kc:1A434000_071_0110:1`，保留）。
- **R4 判分边界只取显式点名项**：沉管成桩漏步只枚举 R4 点名的「漏边振边拔/漏复打
  反插」；人工挖孔只枚举点名的「相邻同时挖/间距<5m」——不外推其他漏步/排列。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_g03_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_g03_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_G03_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "G03_桩基施工与质量问题.md"

SCHEMA_NAME = "luban-g03-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 G03 Pack §4 R4 / §5 R5，锚随行）─────────────────
# 规则组 A：预制桩施工（锚 kc:1A413030_090_0165:0/:1、kc:1A413030_091_0166:0；
# 真题印证 {2015,第24题}/{2024,第9题}/{2017,第26题}）
_HOIST_THRESHOLD_PCT = {"起吊": 70, "运输打桩": 100}
_HOIST_SURFACE_PCTS = (50, 70, 90, 100)  # 题面可出现的强度百分比(封闭·皮)
_ANCHOR_A_HOIST = "kc:1A413030_090_0165:0"
_CORRECT_A_HOIST = "桩身混凝土强度达设计强度的70%方可起吊，达100%方可运输、打桩"

_ORDER_PAIRS = (  # (正确口诀, 写反口诀)——R4 判分边界「任一写反=不妥」
    ("先深后浅", "先浅后深"),
    ("先大后小", "先小后大"),
    ("先长后短", "先短后长"),
    ("先密后疏", "先疏后密"),
    ("密集桩群自中间向四周对称施打", "密集桩群自四周向中间施打"),
)
_ORDER_CORRECT_SET = frozenset(p[0] for p in _ORDER_PAIRS)
_ORDER_REVERSED_SET = frozenset(p[1] for p in _ORDER_PAIRS)
_ANCHOR_A_ORDER = "kc:1A413030_090_0165:0 + {2015,第24题} + {2024,第9题}"
_CORRECT_A_ORDER = (
    "沉桩顺序应先深后浅、先大后小、先长后短、先密后疏；密集桩群应自中间向四周对称施打"
)

_HAMMER_ALLOWED = frozenset({"重锤低击", "低锤重打"})
_HAMMER_SURFACES = ("重锤低击", "低锤重打", "重锤高击", "高锤重打", "低垂轻打")  # {2017,第26题} 五选项
_ANCHOR_A_HAMMER = "{2017,第26题}"
_CORRECT_A_HAMMER = "锤击法落锤方式宜为重锤低击（低锤重打）"

_TRIAL_PILE_MIN = 3
_TRIAL_PILE_SURFACES = (1, 2, 3, 5)
_ANCHOR_A_STATIC = "kc:1A413030_090_0165:1"
_CORRECT_A_STATIC_TRIAL = "静力压桩试压桩不应少于3根"
_CORRECT_A_STATIC_DIG = "静力压桩不得边压桩边开挖基坑（不得边压边挖）"

_STOP_PRIMARY = {"摩擦桩": "标高", "端承桩": "压力"}  # kc:1A413030_091_0166:0
_ANCHOR_A_STOP = "kc:1A413030_091_0166:0"
_CORRECT_A_STOP = "终止沉桩标准：摩擦桩以标高为主、压力为辅；端承桩以压力为主、标高为辅"

# 规则组 B：灌注桩施工质量（锚 kc:1A413030_091_0169:0/092_0170:0/092_0171:0/092_0172:0；
# 真题印证 {2016,案例1}/{2022,案例三}）
_SLAG_LIMITS_MM = {"端承型": 50, "摩擦型": 100, "抗拔/抗水平力": 200}
_SLAG_MEASURED_MM = (50, 100, 200)  # 只用三档锚定数值互相交叉，不发明新数
_ANCHOR_B_SLAG = "kc:1A413030_091_0169:0"
_CORRECT_B_SLAG = "孔底沉渣厚度：端承型≤50mm、摩擦型≤100mm、抗拔/抗水平力桩≤200mm"

_SLUMP_RANGE_MM = (180, 220)
_SLUMP_SURFACES_MM = (160, 180, 200, 220, 240)  # 题面可出现的坍落度(封闭·皮)
_ANCHOR_B_SLUMP = "kc:1A413030_091_0169:0"
_CORRECT_B_SLUMP = "水下混凝土坍落度宜为180~220mm"

# 超灌：条件层拆锚（jury#6 / §8.2 C2）——0.8~1.0m 只挂真题、≥1m 只挂教材
_OVERPOUR_ALLOWED = frozenset({"0.8~1.0m", "不小于1m"})
_OVERPOUR_CASES = (
    {"stated": "500mm", "surface": "水下灌注成桩后桩顶混凝土面仅超过设计标高500mm",
     "correct": "水下灌注时桩顶混凝土面标高至少要比设计标高超灌0.8~1.0m，仅超500mm不妥",
     "anchor": "{2016,案例1}"},
    {"stated": "0.8~1.0m", "surface": "水下灌注时按桩顶混凝土面比设计标高超灌0.8~1.0m控制",
     "correct": "水下灌注时桩顶混凝土面标高至少要比设计标高超灌0.8~1.0m",
     "anchor": "{2016,案例1}"},
    {"stated": "不小于1m", "surface": "泥浆护壁灌注桩按超灌高度不小于1m控制",
     "correct": "泥浆护壁灌注桩超灌高度≥1m（一般口径）",
     "anchor": "kc:1A413030_091_0169:0"},
)

_PIPE_SEQ_CANONICAL = ("桩机就位", "锤击沉管", "上料", "边振边拔", "下钢筋笼", "继续浇筑", "成桩")
_PIPE_METHODS_FULL = frozenset({"单打法", "复打法", "反插法"})
_ANCHOR_B_SEQ = "kc:1A413030_092_0171:0 + {2022,案例三}"
_CORRECT_B_SEQ = ("沉管灌注桩成桩流程应为：" + "→".join(_PIPE_SEQ_CANONICAL)
                  + "；工法除单打法外还包括复打法、反插法")

_DIG_MIN_GAP_M = 5.0
_DIG_GAP_SURFACES_M = (4.0, 5.0, 6.0)  # 题面可出现的间距值(封闭·皮)
_ANCHOR_B_DIG = "kc:1A413030_092_0172:0"
_CORRECT_B_DIG = ("人工挖孔桩桩距<2.5m时应间隔开挖浇筑、最小施工间距≥5m；挖土先中间后周边")

_ANCHOR_B_GROUT = "kc:1A413030_092_0170:0"
_CORRECT_B_GROUT = ("桩底注浆终止应以注浆量为主控制：注浆总量达设计值，或注浆量≥80%且压力>设计值")

# 规则组 C：桩基检测（锚 kc:1A413030_092_0173:0/093_0174:0/:1/:2、kc:1A434000_065_0096:0/:1；
# 真题印证 {2021,第14题}/{2018,第8题}/{2016,案例1}/{2023,办公楼案例}）
# 注意 jury#1 fail-closed：不建"完整性只能低应变/声波透射"方向变体
_PURPOSE_METHODS = {
    "判定桩端持力层岩土性状": frozenset({"钻芯法"}),
    "检验单桩竖向抗压承载力": frozenset({"静载试验", "高应变法"}),
}
_METHOD_CASES = (
    {"purpose": "判定桩端持力层岩土性状", "method": "钻芯法",
     "anchor": "kc:1A413030_093_0174:0 + {2021,第14题}"},
    {"purpose": "检验单桩竖向抗压承载力", "method": "低应变法",
     "anchor": "kc:1A413030_093_0174:0 + {2021,第14题}"},
    {"purpose": "检验单桩竖向抗压承载力", "method": "静载试验",
     "anchor": "kc:1A434000_065_0096:0"},
)
_CORRECT_C_METHOD = ("检测方法按目的匹配：持力层岩土性状用钻芯法；单桩竖向抗压承载力用静载试验"
                     "（甲级或地质复杂必用静载）或高应变法，低应变法不能确定承载力")

_TEST_PILE_PURPOSE = "确定单桩极限承载力"
_TEST_PILE_WRONG_PURPOSES = ("检测桩身完整性",)  # {2018,第8题} 干扰项方向
_ANCHOR_C_TESTPILE = "{2018,第8题}"
_CORRECT_C_TESTPILE = "为设计提供依据的试验桩检测应主要确定单桩极限承载力"

_PRECOND_CASES = (
    {"surface": "桩身混凝土强度达设计强度70%且不小于15MPa后进行低应变检测", "met": True},
    {"surface": "桩身混凝土强度未达设计强度70%即进行低应变检测", "met": False},
    {"surface": "受检桩混凝土龄期达28d后进行钻芯法检测", "met": True},
    {"surface": "受检桩混凝土龄期未达28d即进行钻芯法检测", "met": False},
)
_ANCHOR_C_PRECOND = "kc:1A413030_093_0174:0"
_CORRECT_C_PRECOND = ("低应变/声波透射检测要求桩身强度≥设计强度70%且≥15MPa；钻芯法要求龄期≥28d")

_INTEGRITY_MAP = {
    "Ⅰ类": "桩身完整",
    "Ⅱ类": "桩身有轻微缺陷、不影响桩身结构承载力",
    "Ⅲ类": "桩身有明显缺陷、对桩身结构承载力有影响",
    "Ⅳ类": "桩身存在严重缺陷",
}
_INTEGRITY_SWAPS = (  # R4 判分边界「分类对应错=不妥」——只枚举 Ⅱ↔Ⅲ 典型互换
    ("Ⅱ类", "桩身有明显缺陷、对桩身结构承载力有影响"),
    ("Ⅲ类", "桩身有轻微缺陷、不影响桩身结构承载力"),
)
_ANCHOR_C_CLASS = "kc:1A413030_093_0174:1"
_CORRECT_C_CLASS = ("桩身完整性分类：Ⅰ类完整；Ⅱ类轻微缺陷不影响承载力；"
                    "Ⅲ类明显缺陷影响承载力；Ⅳ类严重缺陷")

_DRILLHOLE_SURFACES = (  # (桩径m·封闭皮避开档界, 声称孔数)
    (1.0, 2), (1.0, 3), (1.4, 2), (1.4, 3), (1.8, 3), (1.8, 2),
)
_ANCHOR_C_DRILLHOLE = "kc:1A413030_093_0174:2"
_CORRECT_C_DRILLHOLE = "钻芯法钻孔数量：桩径<1.2m为1~2孔；1.2~1.6m为2孔；>1.6m为3孔"


def _drillhole_allowed(diam_m: float) -> frozenset[int]:
    if diam_m < 1.2:
        return frozenset({1, 2})
    if diam_m <= 1.6:
        return frozenset({2})
    return frozenset({3})


_SAMPLE_RULES = {  # (kind, cohort) -> 要求
    ("static_load", "甲级或地质复杂"): {"pct": 1, "min_n": 3},
    ("static_load", "总桩数<50根"): {"min_n": 2},
    ("integrity", "一般工程桩"): {"pct": 20, "min_n": 10},
    ("integrity", "甲级/地质复杂/成桩质量可靠性低的灌注桩"): {"pct": 30, "min_n": 20},
}
_SAMPLE_CASES = (
    {"kind": "static_load", "cohort": "甲级或地质复杂", "claimed": {"pct": 1, "min_n": 3},
     "surface": "设计等级甲级工程采用静载试验检验承载力，检验桩数按不少于总桩数1%且不少于3根控制",
     "anchor": "kc:1A434000_065_0096:0"},
    {"kind": "static_load", "cohort": "总桩数<50根", "claimed": {"min_n": 2},
     "surface": "总桩数少于50根的工程，静载检验桩数按不少于2根控制",
     "anchor": "kc:1A434000_065_0096:0"},
    {"kind": "integrity", "cohort": "一般工程桩", "claimed": {"pct": 20, "min_n": 10},
     "surface": "一般工程桩桩身完整性检验按不少于总桩数20%且不少于10根、每根柱子承台下不少于1根抽检",
     "anchor": "kc:1A434000_065_0096:1 + {2023,办公楼案例}"},
    {"kind": "integrity", "cohort": "甲级/地质复杂/成桩质量可靠性低的灌注桩",
     "claimed": {"pct": 20, "min_n": 10},
     "surface": "设计等级甲级、成桩质量可靠性低的灌注桩，桩身完整性按总桩数20%且10根抽检",
     "anchor": "{2016,案例1}"},
    {"kind": "integrity", "cohort": "甲级/地质复杂/成桩质量可靠性低的灌注桩",
     "claimed": {"pct": 30, "min_n": 20},
     "surface": "设计等级甲级、地质条件复杂、成桩质量可靠性低的灌注桩，完整性抽检按不少于总数30%且不少于20根控制",
     "anchor": "{2016,案例1}"},
)
_CORRECT_C_SAMPLE = ("承载力抽检：甲级或地质复杂用静载≥总桩数1%且≥3根（<50根时≥2根）；"
                     "完整性抽检：一般≥20%且≥10根、每承台≥1根；"
                     "甲级/地质复杂/成桩质量可靠性低的灌注桩≥30%且≥20根")

# 质量问题（§5 R5 #13 封闭集；锚 kc:1A434000_070_0109:0、kc:1A434000_071_0110:0/:1）
_BROKEN_CAUSES = ("桩身弯曲", "遇障碍物", "稳桩不直", "接桩偏心", "混凝土强度不足")
_ANCHOR_D_BROKEN = "kc:1A434000_070_0109:0"
_CORRECT_D_BROKEN = ("预制桩桩身断裂成因封闭集：桩身弯曲/遇障碍物/稳桩不直/接桩偏心/混凝土强度不足")

_LOOSE_SOIL_LIMIT_MM = 100
_ANCHOR_D_SOIL = "kc:1A434000_071_0110:0"
_CORRECT_D_SOIL = ("干作业成孔孔底虚土厚度应≤100mm，超过应二次投钻/勺钻清理/孔底压力灌浆处理")

_COLLAPSE_ITEMS = ("护壁效果", "水头压力", "钻进参数", "孔口处理")
_ANCHOR_D_COLLAPSE = "kc:1A434000_071_0110:1"
_CORRECT_D_COLLAPSE = "泥浆护壁防坍孔控制要点封闭集：护壁效果+水头压力+钻进参数+孔口处理"


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"G03-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A-hoist：强度-吊运阈值（百分比皮 × 两动作全枚举）
    for pct in _HOIST_SURFACE_PCTS:
        for action, thr in _HOIST_THRESHOLD_PCT.items():
            add("A-hoist",
                f"预制桩桩身混凝土强度达设计强度的{pct}%时开始{action}",
                {"pct": pct, "action": action}, pct >= thr,
                _CORRECT_A_HOIST, _ANCHOR_A_HOIST)

    # 组 A-order：沉桩顺序口诀——正确/写反成对枚举
    for correct_rule, reversed_rule in _ORDER_PAIRS:
        add("A-order", f"预制桩沉桩顺序安排为「{correct_rule}」",
            {"stated_rule": correct_rule}, True, _CORRECT_A_ORDER, _ANCHOR_A_ORDER)
        add("A-order", f"预制桩沉桩顺序安排为「{reversed_rule}」",
            {"stated_rule": reversed_rule}, False, _CORRECT_A_ORDER, _ANCHOR_A_ORDER)

    # 组 A-hammer：落锤方式（{2017,第26题} 五选项全枚举）
    for method in _HAMMER_SURFACES:
        add("A-hammer", f"锤击沉桩采用{method}方式施打",
            {"method": method}, method in _HAMMER_ALLOWED,
            _CORRECT_A_HAMMER, _ANCHOR_A_HAMMER)

    # 组 A-static：静压试压桩根数 + 边压边挖
    for n in _TRIAL_PILE_SURFACES:
        add("A-static", f"静力压桩施工前试压桩{n}根",
            {"trial_piles": n}, n >= _TRIAL_PILE_MIN,
            _CORRECT_A_STATIC_TRIAL, _ANCHOR_A_STATIC)
    add("A-static", "静力压桩施工与基坑开挖同时进行（边压桩边开挖）",
        {"simultaneous_dig": True}, False, _CORRECT_A_STATIC_DIG, _ANCHOR_A_STATIC)
    add("A-static", "静力压桩全部完成后再进行基坑开挖，未边压边挖",
        {"simultaneous_dig": False}, True, _CORRECT_A_STATIC_DIG, _ANCHOR_A_STATIC)

    # 组 A-stop：终止沉桩标准——桩型 × 主控互换全枚举
    for pile in _STOP_PRIMARY:
        for primary in ("标高", "压力"):
            aux = "压力" if primary == "标高" else "标高"
            add("A-stop", f"{pile}终止沉桩以{primary}控制为主、{aux}为辅",
                {"pile": pile, "primary": primary}, _STOP_PRIMARY[pile] == primary,
                _CORRECT_A_STOP, _ANCHOR_A_STOP)

    # 组 B-slag：孔底沉渣——桩型 × 三档锚定数值交叉（不发明新数）
    for pile_type, limit in _SLAG_LIMITS_MM.items():
        for measured in _SLAG_MEASURED_MM:
            add("B-slag",
                f"{pile_type}灌注桩清孔后实测孔底沉渣厚度{measured}mm，判定满足要求",
                {"pile_type": pile_type, "measured_mm": measured, "limit_mm": limit},
                measured <= limit, _CORRECT_B_SLAG, _ANCHOR_B_SLAG)

    # 组 B-slump：水下混凝土坍落度
    for slump in _SLUMP_SURFACES_MM:
        add("B-slump", f"灌注桩水下混凝土坍落度按{slump}mm控制",
            {"slump_mm": slump},
            _SLUMP_RANGE_MM[0] <= slump <= _SLUMP_RANGE_MM[1],
            _CORRECT_B_SLUMP, _ANCHOR_B_SLUMP)

    # 组 B-overpour：超灌高度（条件层拆锚，只用两口径一致取值）
    for case in _OVERPOUR_CASES:
        add("B-overpour", case["surface"], {"stated": case["stated"]},
            case["stated"] in _OVERPOUR_ALLOWED, case["correct"], case["anchor"])

    # 组 B-seq：沉管成桩流程——完整正序 + R4 点名漏步(边振边拔) + 工法全集/漏集
    add("B-seq", "沉管灌注桩成桩流程：" + "→".join(_PIPE_SEQ_CANONICAL),
        {"steps": list(_PIPE_SEQ_CANONICAL)}, True, _CORRECT_B_SEQ, _ANCHOR_B_SEQ)
    omitted = [s for s in _PIPE_SEQ_CANONICAL if s != "边振边拔"]
    add("B-seq", "沉管灌注桩成桩流程：" + "→".join(omitted),
        {"steps": omitted}, False, _CORRECT_B_SEQ, _ANCHOR_B_SEQ)
    add("B-seq", "认为沉管灌注桩成桩工法除单打法外，还包括复打法、反插法",
        {"methods_acknowledged": sorted(_PIPE_METHODS_FULL)}, True,
        _CORRECT_B_SEQ, _ANCHOR_B_SEQ)
    add("B-seq", "认为沉管灌注桩成桩工法只有单打法一种",
        {"methods_acknowledged": ["单打法"]}, False, _CORRECT_B_SEQ, _ANCHOR_B_SEQ)

    # 组 B-dig：人工挖孔——R4 点名违例（相邻同时挖/间距<5m）+ 正例
    add("B-dig", "人工挖孔桩桩距2.0m，相邻两孔同时开挖",
        {"pile_spacing_m": 2.0, "simultaneous_adjacent": True}, False,
        _CORRECT_B_DIG, _ANCHOR_B_DIG)
    add("B-dig", "人工挖孔桩桩距2.0m，采取间隔开挖、间隔浇筑",
        {"pile_spacing_m": 2.0, "simultaneous_adjacent": False}, True,
        _CORRECT_B_DIG, _ANCHOR_B_DIG)
    for gap in _DIG_GAP_SURFACES_M:
        add("B-dig", f"人工挖孔桩间隔开挖时同时开挖孔的最小施工间距按{gap}m控制",
            {"min_gap_m": gap}, gap >= _DIG_MIN_GAP_M, _CORRECT_B_DIG, _ANCHOR_B_DIG)
    add("B-dig", "人工挖孔桩挖土顺序为先中间后周边",
        {"dig_order": "先中间后周边"}, True, _CORRECT_B_DIG, _ANCHOR_B_DIG)

    # 组 B-grout：桩底注浆终止条件
    add("B-grout", "桩底注浆终止以注浆量为主控制",
        {"primary_control": "注浆量"}, True, _CORRECT_B_GROUT, _ANCHOR_B_GROUT)
    add("B-grout", "桩底注浆终止以注浆压力为单一主控指标",
        {"primary_control": "注浆压力"}, False, _CORRECT_B_GROUT, _ANCHOR_B_GROUT)
    add("B-grout", "注浆量已达设计值的80%且注浆压力超过设计值时终止注浆",
        {"primary_control": "注浆量", "ratio_pct": 80, "pressure_over_design": True}, True,
        _CORRECT_B_GROUT, _ANCHOR_B_GROUT)

    # 组 C-method：检测方法-目的匹配（jury#1 fail-closed：不建完整性方法排他变体）
    for case in _METHOD_CASES:
        add("C-method", f"采用{case['method']}{case['purpose']}",
            {"purpose": case["purpose"], "method": case["method"]},
            case["method"] in _PURPOSE_METHODS[case["purpose"]],
            _CORRECT_C_METHOD, case["anchor"])
    add("C-method", f"为设计提供依据的试验桩检测以{_TEST_PILE_PURPOSE}为主要目的",
        {"test_pile_purpose": _TEST_PILE_PURPOSE}, True,
        _CORRECT_C_TESTPILE, _ANCHOR_C_TESTPILE)
    for wrong in _TEST_PILE_WRONG_PURPOSES:
        add("C-method", f"为设计提供依据的试验桩检测以{wrong}为主要目的",
            {"test_pile_purpose": wrong}, False,
            _CORRECT_C_TESTPILE, _ANCHOR_C_TESTPILE)

    # 组 C-precond：检测前置条件
    for case in _PRECOND_CASES:
        add("C-precond", case["surface"], {"condition_met": case["met"]},
            case["met"], _CORRECT_C_PRECOND, _ANCHOR_C_PRECOND)

    # 组 C-class：完整性分类映射（4 正确对应 + Ⅱ↔Ⅲ 典型互换）
    for cls, desc in _INTEGRITY_MAP.items():
        add("C-class", f"将「{desc}」的桩判定为{cls}",
            {"cls": cls, "desc": desc}, True, _CORRECT_C_CLASS, _ANCHOR_C_CLASS)
    for cls, desc in _INTEGRITY_SWAPS:
        add("C-class", f"将「{desc}」的桩判定为{cls}",
            {"cls": cls, "desc": desc}, False, _CORRECT_C_CLASS, _ANCHOR_C_CLASS)

    # 组 C-drillhole：钻芯孔数（桩径皮避开档界值）
    for diam, holes in _DRILLHOLE_SURFACES:
        add("C-drillhole", f"桩径{diam}m的灌注桩钻芯法检测钻{holes}孔",
            {"diam_m": diam, "holes": holes}, holes in _drillhole_allowed(diam),
            _CORRECT_C_DRILLHOLE, _ANCHOR_C_DRILLHOLE)

    # 组 C-sample：抽检比例（条件层显式区分，§8.2 C1）
    for case in _SAMPLE_CASES:
        rule = _SAMPLE_RULES[(case["kind"], case["cohort"])]
        add("C-sample", case["surface"],
            {"kind": case["kind"], "cohort": case["cohort"], "claimed": case["claimed"]},
            case["claimed"] == rule, _CORRECT_C_SAMPLE, case["anchor"])

    # 组 D-broken：断桩成因封闭集——成员判断双极性
    for cause in _BROKEN_CAUSES:
        add("D-broken", f"分析预制桩桩身断裂原因时，将「{cause}」列为可能成因",
            {"cause": cause, "listed": True}, True, _CORRECT_D_BROKEN, _ANCHOR_D_BROKEN)
        add("D-broken", f"分析预制桩桩身断裂原因时，认为「{cause}」与桩身断裂无关",
            {"cause": cause, "listed": False}, False, _CORRECT_D_BROKEN, _ANCHOR_D_BROKEN)

    # 组 D-soil：干作业孔底虚土（阈值 + 点名处置）
    add("D-soil", "干作业成孔灌注桩孔底虚土厚度控制在100mm以内",
        {"over_limit": False, "action": "控制在限值内"}, True,
        _CORRECT_D_SOIL, _ANCHOR_D_SOIL)
    add("D-soil", "干作业成孔孔底虚土厚度超过100mm，未处理即浇筑混凝土",
        {"over_limit": True, "action": "不处理"}, False, _CORRECT_D_SOIL, _ANCHOR_D_SOIL)
    add("D-soil", "干作业成孔孔底虚土厚度超过100mm，采用二次投钻清理后再浇筑",
        {"over_limit": True, "action": "二次投钻清理"}, True,
        _CORRECT_D_SOIL, _ANCHOR_D_SOIL)

    # 组 D-collapse：防坍孔四防封闭集——成员判断双极性
    for item in _COLLAPSE_ITEMS:
        add("D-collapse", f"将「{item}」列入泥浆护壁灌注桩防坍孔控制要点",
            {"item": item, "listed": True}, True, _CORRECT_D_COLLAPSE, _ANCHOR_D_COLLAPSE)
        add("D-collapse", f"认为「{item}」与泥浆护壁灌注桩防坍孔无关",
            {"item": item, "listed": False}, False, _CORRECT_D_COLLAPSE, _ANCHOR_D_COLLAPSE)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-hoist":
        thr = _HOIST_THRESHOLD_PCT.get(p.get("action"))
        return None if thr is None else p["pct"] >= thr
    if g == "A-order":
        rule = p["stated_rule"]
        if rule in _ORDER_CORRECT_SET:
            return True
        if rule in _ORDER_REVERSED_SET:
            return False
        return None
    if g == "A-hammer":
        if p["method"] not in _HAMMER_SURFACES:
            return None  # 封闭域外落锤方式不许出现
        return p["method"] in _HAMMER_ALLOWED
    if g == "A-static":
        if "simultaneous_dig" in p:
            return not p["simultaneous_dig"]
        return p["trial_piles"] >= _TRIAL_PILE_MIN
    if g == "A-stop":
        expected = _STOP_PRIMARY.get(p.get("pile"))
        return None if expected is None else p["primary"] == expected
    if g == "B-slag":
        limit = _SLAG_LIMITS_MM.get(p.get("pile_type"))
        return None if limit is None else p["measured_mm"] <= limit
    if g == "B-slump":
        return _SLUMP_RANGE_MM[0] <= p["slump_mm"] <= _SLUMP_RANGE_MM[1]
    if g == "B-overpour":
        return p["stated"] in _OVERPOUR_ALLOWED
    if g == "B-seq":
        if "steps" in p:
            return p["steps"] == list(_PIPE_SEQ_CANONICAL)
        return set(p["methods_acknowledged"]) == _PIPE_METHODS_FULL
    if g == "B-dig":
        if "simultaneous_adjacent" in p:
            return not p["simultaneous_adjacent"]
        if "min_gap_m" in p:
            return p["min_gap_m"] >= _DIG_MIN_GAP_M
        return p.get("dig_order") == "先中间后周边"
    if g == "B-grout":
        return p["primary_control"] == "注浆量"
    if g == "C-method":
        if "test_pile_purpose" in p:
            return p["test_pile_purpose"] == _TEST_PILE_PURPOSE
        allowed = _PURPOSE_METHODS.get(p.get("purpose"))
        return None if allowed is None else p["method"] in allowed
    if g == "C-precond":
        return bool(p["condition_met"])
    if g == "C-class":
        return _INTEGRITY_MAP.get(p["cls"]) == p["desc"]
    if g == "C-drillhole":
        return p["holes"] in _drillhole_allowed(p["diam_m"])
    if g == "C-sample":
        rule = _SAMPLE_RULES.get((p.get("kind"), p.get("cohort")))
        return None if rule is None else p["claimed"] == rule
    if g == "D-broken":
        if p["cause"] not in _BROKEN_CAUSES:
            return None  # 枚举外成因不许出现(封闭域)
        return bool(p["listed"])
    if g == "D-soil":
        if not p["over_limit"]:
            return True
        return p["action"] != "不处理"
    if g == "D-collapse":
        if p["item"] not in _COLLAPSE_ITEMS:
            return None
        return bool(p["listed"])
    return None


# 争议/越界/无锚层 token，禁入题面与正确做法（fail-closed）：
# CFG/排桩/地下连续墙/强夯/复合地基=§8.2 C3 越界剔除；泥浆比重/导管埋深=§8.2 C5 无锚通识
_CONTESTED_TOKENS = ("CFG", "排桩", "地下连续墙", "强夯", "复合地基", "泥浆比重", "导管埋深")


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
        "pack_id": "G03",
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
