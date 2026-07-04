#!/usr/bin/env python3
"""N03 变体池编译期预生成器（计算/判读型：流水施工参数与工期）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本沿 S05/F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`），
纯确定性枚举（零 LLM、零随机），从 N03 Pack §4 R4 五个封闭规则组派生变体，自带独立
一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

计算型考点约束（任务硬门）：本池**不生成**开放数值求解题面——判型/取 K/队数/
工期判定全部落在 R4 封闭判分边界（判型是否对/K 是否取最大公约数/队数是否=节拍÷K/
工期是否体现搭接），数值单元只用 pack 内逐字锚定的真题算例
（{2019,第2题} 3、3、9、6、6 天→1、1、3、2、2=9 队；{2023,第2题} K=3 个月、
队数 5、总工期 (2+5-1)×3=18 个月），判定可由简单整数算术在 params 内独立复核。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（判读形态在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 N03 pack 裁决）：
- **jury 单源#2（未裁决）**：施工段划分「劳动量差异≤15%」普适性未验证——
  规则组 E（施工段划分）**整组不入池**，「劳动量」「≤15%」token 禁入。
- **jury 单源#6（未裁决）**：「无节奏/异步距用大差法」现有引用仅支持异节奏场景
  ——大差法三动作保 🟢 入池（组 B2），但题面**不预设「无节奏」场景**，
  只做三动作完备性判定（R5#8「缺一不可」+ R4 组 B 显式点名「只写方法名无过程」）。
- **jury 单源#9（未裁决）**：「机械加所有节拍=0分」档位降 🔴——本池只取
  「机械相加不体现搭接=语义错误」🟢 层（§6 M4 + {2023,第2题}），不出评分档位。
- **jury 单源#7（已给收窄措辞）**：拆队表述按「节拍成倍数时」收窄，
  正确做法不写「节拍不等即增队」。
- **§0/§8.2 C4 题号共享坑**：{2019}/{2023} 多问案例的 N01 子问（关键线路/
  总工期 21 个月）**不作 N03 锚**——「关键线路」「总时差」「21 个月」token 禁入。
- **§8.2 C2 编造防御**：闭式公式 `T=(M+N-1)t` 等无编译锚降 🔵、「潘特考夫斯基法」
  别名已删——工期数值只用 {2023} correct_answer 逐字算式 (2+5-1)×3=18 个月，
  「潘特」token 禁入。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。
- **§4 S5/S6 真题暂未直命标 🔴**——pack 明示「作变题备料，不充真题锚」：
  组 B2（大差法）只挂 🟢 教材锚 kc:1A433000_054_0081:0；S6（施工段划分）因
  jury#2 争议整组不入池（见上）。

用法::

    python3 scripts/build_luban_n03_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_n03_variant_bank.py --check  # 只跑一致性门(CI 可挂)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_N03_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "N03_流水施工参数与工期.md"

SCHEMA_NAME = "luban-n03-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 N03 Pack §4 R4 / §5 / §6，锚随行）────────────
# 规则组 A：类型判别（锚 kc:1A433000_052_0077:0 / 053_0078:0 / 052_0076:0）
_TYPE_EQUAL = "等节奏流水施工"
_TYPE_MULTIPLE = "等步距异节奏流水施工"
_TYPE_UNRHYTHMIC = "无节奏流水施工"
_PATTERN_CELLS = (
    ("全部相等", "equal", _TYPE_EQUAL),
    ("不全相等但互为倍数关系", "multiple", _TYPE_MULTIPLE),
    ("无规律（不全相等且不成倍数）", "unrhythmic", _TYPE_UNRHYTHMIC),
)
_PATTERN_TO_TYPE = {"equal": _TYPE_EQUAL, "multiple": _TYPE_MULTIPLE,
                    "unrhythmic": _TYPE_UNRHYTHMIC}
_ANCHOR_A = "kc:1A433000_052_0077:0 + kc:1A433000_053_0078:0 + kc:1A433000_052_0076:0"
_CORRECT_A = ("节拍全部相等→等节奏；节拍不全相等但成倍数关系→等步距异节奏（成倍节拍）；"
              "节拍无规律→无节奏，判型须写理由（节拍关系）")

# 规则组 B：流水步距 K（锚 kc:1A433000_053_0078:1、kc:1A433000_054_0081:0；
# 数值单元逐字来自 {2019,第2题}(3、3、9、6、6 天)、{2023,第2题}(3 个月/6 个月, K=3)）
_ANCHOR_B_GCD_2023 = "kc:1A433000_053_0078:1 + {2023,第2题}"
_ANCHOR_B_GCD_2019 = "kc:1A433000_053_0078:1 + {2019,第2题}"
_CORRECT_B = ("等节奏 K=流水节拍 t；等步距异节奏（成倍节拍）K=各节拍最大公约数"
              "（2023：gcd(3,6)=3 个月），K 取成最大/平均节拍即错")

# 规则组 B2：大差法三动作（锚 kc:1A433000_054_0081:0；R5#8「缺一不可」；
# 题面不预设「无节奏」场景，jury#6 fail-closed）
_DACHA_STEPS = ("列各施工过程累加数列", "错位相减", "取差值的最大值定为流水步距")
_ANCHOR_B2 = "kc:1A433000_054_0081:0"
_CORRECT_B2 = "大差法三动作缺一不可：列累加数列 → 错位相减 → 取最大值 = 流水步距"

# 规则组 C：专业队数 + 总工期（锚 {2019,第2题}、{2023,第2题}、kc:1A433000_055_0083:0）
_ANCHOR_C_2019 = "{2019,第2题} + kc:1A433000_053_0078:1"
_ANCHOR_C_2023 = "{2023,第2题} + kc:1A433000_055_0083:0"
_CORRECT_C_CREWS = ("成倍节拍各过程专业队数 = 节拍÷步距后求和（2019：3、3、9、6、6÷3="
                    "1、1、3、2、2，合计 9 队），专业队数大于施工过程数")
_CORRECT_C_T = ("总工期须体现搭接（2023：(2+5-1)×3=18 个月，带过程与单位），"
                "不是机械相加所有节拍")

# 规则组 D：参数定义与三分类 + 组织方式（锚 kc:1A433000_052_0075:0/:1/:2、
# kc:1A433000_051_0074:0、{2021,案例二}）
_TERM_DEFS = {
    "流水节拍": "one_segment_time",     # 某专业队在一个施工段上的施工时间(:0)
    "流水步距": "adjacent_interval",    # 相邻两专业队进入流水作业的时间间隔(:1)
    "流水施工工期": "first_in_last_out",  # 首队投入流水→末队完成最后一段并退出(:2)
}
_DEF_TEXTS = {
    "one_segment_time": "某专业队在一个施工段上的施工时间",
    "adjacent_interval": "相邻两专业队进入流水作业的时间间隔",
    "first_in_last_out": "第一个专业队投入流水到最后一个专业队完成最后一段并退出的持续时间",
}
_PARAM_CLASS = {
    "流水节拍": "时间参数", "流水步距": "时间参数", "施工工期": "时间参数",
    "施工段": "空间参数", "施工层": "空间参数",
    "施工过程数": "工艺参数", "流水强度": "工艺参数",
}
_ANCHOR_D_DEF = "kc:1A433000_052_0075:0、kc:1A433000_052_0075:1、kc:1A433000_052_0075:2"
_ANCHOR_D_CLASS = ("{2021,案例二} + kc:1A433000_051_0074:0 + "
                   "kc:1A433000_052_0075:0、kc:1A433000_052_0075:1、kc:1A433000_052_0075:2")
_CORRECT_D_DEF = ("流水节拍 t=某专业队在一个施工段上的施工时间；流水步距 K=相邻两专业队"
                  "进入流水作业的时间间隔；工期 T=首队投入流水到末队完成最后一段并退出，"
                  "t 与 K 不同维度不得互换")
_CORRECT_D_CLASS = ("参数三体系：工艺参数（施工过程数/流水强度）/时间参数（流水节拍/"
                    "流水步距/施工工期）/空间参数（施工段/施工层）；三大组织方式为"
                    "依次施工、平行施工、流水施工")

# 规则组 E：类型特点辨析（锚 {2015,第16题}、kc:1A433000_052_0077:0 / 052_0076:0 /
# 053_0078:1；特点→所属类型为封闭映射，逐字来自 §1#6/#7/#9）
_FEATURE_OWNERS: dict[str, tuple[str, ...]] = {
    "各专业工作队在各施工段上能够连续作业": (_TYPE_EQUAL, _TYPE_MULTIPLE),
    "各专业工作队不能连续作业": (),
    "流水步距等于流水节拍": (_TYPE_EQUAL,),
    "流水步距等于各节拍的最大公约数": (_TYPE_MULTIPLE,),
    "各施工过程的流水节拍互为倍数关系": (_TYPE_MULTIPLE,),
    "专业工作队数大于施工过程数": (_TYPE_MULTIPLE,),
    "专业工作队数等于施工过程数": (_TYPE_EQUAL, _TYPE_UNRHYTHMIC),
    "施工过程之间可能有间隔时间": (_TYPE_UNRHYTHMIC,),
    "流水节拍不全相等、流水步距不尽相等": (_TYPE_UNRHYTHMIC,),
}
_ANCHOR_E_EQUAL = "{2015,第16题} + kc:1A433000_052_0077:0"
_ANCHOR_E_MULTIPLE = "kc:1A433000_053_0078:1"
_ANCHOR_E_UNRHYTHMIC = "kc:1A433000_052_0076:0"


def _feature_correct(feature: str) -> str:
    owners = _FEATURE_OWNERS[feature]
    if not owners:
        return ("各专业工作队在各施工段上能够连续作业，「不能连续作业」不属于任何"
                "流水施工方式的特点（2015 第16题 D 项即此错误）")
    return f"「{feature}」是{'、'.join(owners)}的特点"


def _feature_anchor(claimed: str) -> str:
    return {_TYPE_EQUAL: _ANCHOR_E_EQUAL, _TYPE_MULTIPLE: _ANCHOR_E_MULTIPLE,
            _TYPE_UNRHYTHMIC: _ANCHOR_E_UNRHYTHMIC}[claimed]


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"N03-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：类型判别——节拍关系 × 判型 全枚举（3×3 封闭矩阵）
    for desc, pattern, _true_type in _PATTERN_CELLS:
        for claimed in (_TYPE_EQUAL, _TYPE_MULTIPLE, _TYPE_UNRHYTHMIC):
            add("A-type", f"某工程各施工段各施工过程的流水节拍{desc}，项目部判定为{claimed}",
                {"pattern": pattern, "claimed_type": claimed},
                _PATTERN_TO_TYPE[pattern] == claimed, _CORRECT_A, _ANCHOR_A)

    # 组 B：流水步距 K——类型 × 取法（取法只枚举 R4/意图① 显式点名项，不外推）
    add("B-step", "某工程各施工段各施工过程流水节拍均相等，项目部取流水步距 K=流水节拍 t",
        {"pattern": "equal", "k_choice": "t"}, True, _CORRECT_B,
        "kc:1A433000_052_0077:0")
    add("B-step", "基础工程流水节拍 3 个月、上部结构 6 个月（成倍数关系），"
        "项目部取流水步距 K=各节拍最大公约数 3 个月",
        {"pattern": "multiple", "k_choice": "gcd", "takts": [3, 6], "k_value": 3},
        True, _CORRECT_B, _ANCHOR_B_GCD_2023)
    add("B-step", "基础工程流水节拍 3 个月、上部结构 6 个月（成倍数关系），"
        "项目部取最大节拍 6 个月作为流水步距",
        {"pattern": "multiple", "k_choice": "max", "takts": [3, 6], "k_value": 6},
        False, _CORRECT_B, _ANCHOR_B_GCD_2023)
    add("B-step", "各施工过程流水节拍成倍数关系，项目部取各节拍的平均值作为流水步距",
        {"pattern": "multiple", "k_choice": "avg"}, False, _CORRECT_B,
        _ANCHOR_B_GCD_2023)
    add("B-step", "各施工过程流水节拍分别为 3、3、9、6、6 天，"
        "项目部取流水步距 K=各节拍最大公约数 3 天",
        {"pattern": "multiple", "k_choice": "gcd", "takts": [3, 3, 9, 6, 6], "k_value": 3},
        True, _CORRECT_B, _ANCHOR_B_GCD_2019)

    # 组 B2：大差法三动作——完整 + 逐动作点名漏步 + 只报方法名（R5#8 缺一不可，不外推乱序）
    add("B2-dacha", "采用大差法确定流水步距，项目部依次完成："
        + "→".join(_DACHA_STEPS), {"steps": list(_DACHA_STEPS)},
        True, _CORRECT_B2, _ANCHOR_B2)
    for omit in _DACHA_STEPS:
        kept = [s for s in _DACHA_STEPS if s != omit]
        add("B2-dacha", f"采用大差法确定流水步距，项目部只做了：{'→'.join(kept)}，缺少「{omit}」",
            {"steps": kept}, False, _CORRECT_B2, _ANCHOR_B2)
    add("B2-dacha", "项目部只在答案里写「用大差法计算流水步距」，未展示累加数列与错位相减过程",
        {"steps": []}, False, _CORRECT_B2, _ANCHOR_B2)

    # 组 C：专业队数 + 总工期——真题算例数值单元（简单整数算术独立复核）
    add("C-crew", "各施工过程流水节拍 3、3、9、6、6 天，流水步距 3 天，项目部按节拍÷步距"
        "组织专业工作队：1、1、3、2、2，合计 9 个",
        {"takts": [3, 3, 9, 6, 6], "k": 3, "crews": [1, 1, 3, 2, 2], "total": 9},
        True, _CORRECT_C_CREWS, _ANCHOR_C_2019)
    add("C-crew", "各施工过程流水节拍 3、3、9、6、6 天组织成倍节拍流水，"
        "项目部为每个施工过程只配 1 个专业工作队",
        {"takts": [3, 3, 9, 6, 6], "k": 3, "crews": [1, 1, 1, 1, 1], "total": 5},
        False, _CORRECT_C_CREWS, _ANCHOR_C_2019)
    add("C-crew", "基础流水节拍 3 个月、上部结构 6 个月，流水步距 3 个月，"
        "专业队数=1+1+2+1=5 个，项目部算总工期=（2+5-1）×3=18 个月",
        {"m": 2, "n_crews": 5, "k": 3, "claimed_T": 18},
        True, _CORRECT_C_T, _ANCHOR_C_2023)
    add("C-crew", "计算流水施工总工期时，项目部把所有施工过程的节拍机械相加",
        {"claim": "sum_all_takts"}, False, _CORRECT_C_T, _ANCHOR_C_2023)
    add("C-crew", "组织成倍节拍（等步距异节奏）流水施工时，项目部认为专业工作队数"
        "必然等于施工过程数",
        {"claim": "crews_equal_processes"}, False, _CORRECT_C_CREWS,
        "kc:1A433000_053_0078:1 + {2019,第2题}")

    # 组 D：参数定义（正误双极性）+ 三分类 + 组织方式
    for term, def_key in _TERM_DEFS.items():
        add("D-param", f"项目部把「{term}」定义为{_DEF_TEXTS[def_key]}",
            {"term": term, "definition": def_key}, True, _CORRECT_D_DEF, _ANCHOR_D_DEF)
    add("D-param", f"项目部把「流水节拍」定义为{_DEF_TEXTS['adjacent_interval']}",
        {"term": "流水节拍", "definition": "adjacent_interval"},
        False, _CORRECT_D_DEF, _ANCHOR_D_DEF)
    add("D-param", f"项目部把「流水步距」定义为{_DEF_TEXTS['one_segment_time']}",
        {"term": "流水步距", "definition": "one_segment_time"},
        False, _CORRECT_D_DEF, _ANCHOR_D_DEF)
    add("D-param", "项目部将流水节拍、流水步距、施工工期归入时间参数",
        {"items": ["流水节拍", "流水步距", "施工工期"], "claimed_class": "时间参数"},
        True, _CORRECT_D_CLASS, _ANCHOR_D_CLASS)
    add("D-param", "项目部将施工段、施工层归入空间参数",
        {"items": ["施工段", "施工层"], "claimed_class": "空间参数"},
        True, _CORRECT_D_CLASS, _ANCHOR_D_CLASS)
    add("D-param", "项目部将施工过程数、流水强度归入工艺参数",
        {"items": ["施工过程数", "流水强度"], "claimed_class": "工艺参数"},
        True, _CORRECT_D_CLASS, _ANCHOR_D_CLASS)
    add("D-param", "项目部将流水节拍归入工艺参数",
        {"items": ["流水节拍"], "claimed_class": "工艺参数"},
        False, _CORRECT_D_CLASS, _ANCHOR_D_CLASS)
    add("D-param", "项目部将流水步距归入工艺参数",
        {"items": ["流水步距"], "claimed_class": "工艺参数"},
        False, _CORRECT_D_CLASS, _ANCHOR_D_CLASS)
    add("D-param", "项目部答「施工组织方式有依次施工、平行施工、流水施工三种」",
        {"claim": "three_modes"}, True, _CORRECT_D_CLASS,
        "kc:1A433000_051_0074:0 + {2021,案例二}")

    # 组 E：类型特点辨析——(声称类型, 特点) 锚定配对（含 2015 第16题 D 项原型），
    # 不做 3×9 全乘（只取有锚配对，防注水）
    feature_pairs: tuple[tuple[str, str], ...] = (
        (_TYPE_EQUAL, "各专业工作队在各施工段上能够连续作业"),
        (_TYPE_EQUAL, "各专业工作队不能连续作业"),          # {2015,第16题} D 项错误原型
        (_TYPE_EQUAL, "流水步距等于流水节拍"),
        (_TYPE_EQUAL, "流水步距等于各节拍的最大公约数"),      # 意图② K=t 与 K=公约数混淆
        (_TYPE_EQUAL, "专业工作队数等于施工过程数"),
        (_TYPE_EQUAL, "施工过程之间可能有间隔时间"),          # M1：「可能有间隔」是无节奏特点
        (_TYPE_MULTIPLE, "流水步距等于各节拍的最大公约数"),
        (_TYPE_MULTIPLE, "各施工过程的流水节拍互为倍数关系"),
        (_TYPE_MULTIPLE, "专业工作队数大于施工过程数"),
        (_TYPE_MULTIPLE, "专业工作队数等于施工过程数"),        # M3：成倍节拍要拆队
        (_TYPE_UNRHYTHMIC, "施工过程之间可能有间隔时间"),
        (_TYPE_UNRHYTHMIC, "流水节拍不全相等、流水步距不尽相等"),
        (_TYPE_UNRHYTHMIC, "专业工作队数等于施工过程数"),
    )
    for claimed, feature in feature_pairs:
        add("E-feature", f"项目部认为「{feature}」是{claimed}的特点",
            {"claimed_type": claimed, "feature": feature},
            claimed in _FEATURE_OWNERS[feature],
            _feature_correct(feature), _feature_anchor(claimed))

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-type":
        if p["pattern"] not in _PATTERN_TO_TYPE:
            return None
        return _PATTERN_TO_TYPE[p["pattern"]] == p["claimed_type"]
    if g == "B-step":
        required = {"equal": "t", "multiple": "gcd"}.get(p["pattern"])
        if required is None:
            return None
        ok = p["k_choice"] == required
        if "takts" in p and p["k_choice"] == "gcd":
            ok = ok and math.gcd(*p["takts"]) == p["k_value"]
        return ok
    if g == "B2-dacha":
        return p["steps"] == list(_DACHA_STEPS)
    if g == "C-crew":
        if p.get("claim") in ("sum_all_takts", "crews_equal_processes"):
            return False  # 机械相加/队数=过程数 均为锚定误区(§6 M3/M4)
        if "crews" in p:
            want = [t // p["k"] for t in p["takts"]]
            return p["crews"] == want and p["total"] == sum(want)
        if "n_crews" in p:
            return (p["m"] + p["n_crews"] - 1) * p["k"] == p["claimed_T"]
        return None
    if g == "D-param":
        if p.get("claim") == "three_modes":
            return True  # 三大组织方式为封闭清单(kc:1A433000_051_0074:0)
        if "definition" in p:
            if p["term"] not in _TERM_DEFS:
                return None
            return _TERM_DEFS[p["term"]] == p["definition"]
        if any(i not in _PARAM_CLASS for i in p.get("items", [])):
            return None  # 枚举外参数不许出现(封闭域)
        return all(_PARAM_CLASS[i] == p["claimed_class"] for i in p["items"])
    if g == "E-feature":
        if p["feature"] not in _FEATURE_OWNERS:
            return None
        return p["claimed_type"] in _FEATURE_OWNERS[p["feature"]]
    return None


# 争议/🔵推理/邻接层 token，禁入题面与正确做法（fail-closed）：
# 关键线路/总时差/虚工作/网络=N01 邻接+题号共享坑(§0/§8.2 C4)；21 个月=同题 N01 子问；
# 优化/赶工=N02 邻接；劳动量/15%=jury#2 未裁决；潘特=§8.2 C2 无锚别名已删；
# 横道图=§1#12 🔵 外延；满分/压线=R7 🔴 档位措辞
_CONTESTED_TOKENS = ("关键线路", "总时差", "虚工作", "网络", "21 个月", "21个月",
                     "优化", "赶工", "劳动量", "15%", "潘特", "横道图", "满分", "压线")


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
        "pack_id": "N03",
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
