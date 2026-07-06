#!/usr/bin/env python3
"""J01 变体池编译期预生成器（危大工程范围 + 专项方案 + 专家论证）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。先例：S05（`scripts/build_luban_s05_variant_bank.py`）、
F16（`scripts/build_luban_f16_variant_bank.py`，含 🔵/🔴 fail-closed 范式，本脚本以其为主模板）。
纯确定性枚举（零 LLM、零随机、零时间依赖），从 J01 Pack §4 R4 六个封闭规则组
（A 危大档阈值 / B 超规模阈值 / C 编制主体 / D 方案必含内容 / E 论证程序与专家组 /
F 现场管理）派生变体，自带独立一致性检查门（生成器与校验器从同一规则表**分别**
推导判定，互证）。Pack §4 封闭性自检明示「判分边界全部可机械裁决，规则封闭成立」。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（参数/主体/条目在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 J01 pack §8/§9.1 裁决）：
- **jury #5（§9.1 采纳·微调）**：「审核先于审查不可颠倒」的顺序绝对性为讲解层
  ——本池**不生成**判定"施工单位审核 vs 总监理工程师审查"内部先后的变体；只判定
  已锚事实「论证前须经施工单位审核 + 总监理工程师审查」（缺任一 / 论证前置于二者
  之前 = 不妥，锚 `cc:1A437000_010_0013:3` + `kc:1A437000_010_0013:0`）。
- **§8.2 C4 越界剔除**：起拱 1/1000、浇筑高度等模板施工工艺数字属 C04 territory，
  非 J01 判分眼——争议 token 门拦截；`{2015,案例1}` 的"编案梁跨度 10m"档不在 R4
  A 表（A 表模板档只有搭设高度≥5m），**不入池**（token「梁跨度」拦截）。
- **§1 #15 法律后果外延（🔵）**：「未编/未审=重大事故隐患」为邻接外延，禁入池
  （token「重大事故隐患」拦截）。
- **§4 S7 真题锚 🔴（§9.1 HI#1 维持）**：危大六项现场管理无独立直命真题——组 F
  变体只挂 🟢 教材锚（`kc:1A436000_010_0011:0`、`cc:1A436000_010_0011:2/:3`），
  不冒充真题锚。
- **jury #4（§9.1 驳回后口径）**：论证主要内容三项强锚主挂真题 `{2023,第28题}`，
  `ca:1A437000_010_0013` 作教材佐证——组 G 锚按此挂。
- **R7 边界档位（满分/压线/0分）全 🔴 待裁决**——不作变体判定依据，本池期望
  判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_j01_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_j01_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_J01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "J01_危大工程专项方案专家论证.md"

SCHEMA_NAME = "luban-j01-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 J01 Pack §4 R4 / §5 R5，锚随行）─────────────────
# 规则组 A：危大工程范围(一般档)阈值（锚 kc:1A436000_008_0011:0）
# (类型标签, 阈值, 单位, 题面参数皮·封闭)
_HAZARD_RULES = (
    ("基坑工程开挖深度", 3.0, "m", (2.0, 3.0, 4.0)),
    ("模板工程搭设高度", 5.0, "m", (4.0, 5.0, 6.0)),
    ("起重吊装单件起吊重量", 10.0, "kN", (8.0, 10.0, 15.0)),
    ("脚手架搭设高度", 24.0, "m", (20.0, 24.0, 30.0)),
)
_HAZARD_THRESHOLDS = {label: thr for label, thr, _, _ in _HAZARD_RULES}
_ANCHOR_A = "kc:1A436000_008_0011:0"
_CORRECT_A = ("达一般危大档阈值（基坑开挖≥3m/模板搭设≥5m/起重单件≥10kN/脚手架≥24m）"
              "即属危大工程，须编制专项施工方案")

# 规则组 B：超过一定规模危大工程阈值（锚 kc:1A436000_009_0012:0 + cc:1A436000_009_0012:1；
# 真题印证 {2021,第5题}(6m基坑/60m幕墙)、{2022,第19题}(8m基坑)）
_SUPER_RULES = (
    ("深基坑开挖深度", 5.0, "m", (3.0, 4.0, 5.0, 6.0, 8.0)),
    ("模板支撑搭设高度", 8.0, "m", (5.0, 8.0, 9.0)),
    ("模板支撑跨度", 18.0, "m", (12.0, 18.0)),
    ("承重支撑单点荷载", 7.0, "kN", (5.0, 7.0)),
    ("起重吊装单件起吊重量", 100.0, "kN", (10.0, 100.0, 120.0)),
    ("落地脚手架搭设高度", 50.0, "m", (24.0, 50.0, 60.0)),
    ("附着式脚手架架体高度", 150.0, "m", (100.0, 150.0)),
    ("悬挑脚手架搭设高度", 20.0, "m", (15.0, 20.0)),
    ("建筑幕墙安装高度", 50.0, "m", (40.0, 50.0, 60.0)),
    ("钢结构安装跨度", 36.0, "m", (30.0, 36.0)),
    ("网架安装跨度", 60.0, "m", (50.0, 60.0)),
    ("人工挖孔桩开挖深度", 16.0, "m", (12.0, 16.0)),
    ("大型结构整体提升重量", 1000.0, "kN", (800.0, 1000.0)),
)
_SUPER_THRESHOLDS = {label: thr for label, thr, _, _ in _SUPER_RULES}
_ANCHOR_B_BASE = "kc:1A436000_009_0012:0 + cc:1A436000_009_0012:1"
_ANCHOR_B_EXTRA = {  # 真题侧印证只挂已核真条目
    "深基坑开挖深度": " + {2021,第5题} + {2022,第19题}",
    "建筑幕墙安装高度": " + {2021,第5题}",
}
_CORRECT_B = ("达超规模档阈值（深基坑≥5m/模板支撑高≥8m或跨≥18m/承重支撑单点≥7kN/"
              "起重单件≥100kN/落地脚手架≥50m/附着≥150m/悬挑≥20m/幕墙≥50m/"
              "钢结构跨≥36m/网架≥60m/挖孔桩≥16m/大型结构≥1000kN）须组织专家论证")
_CORRECT_BAND = ("基坑开挖深度≥3m须编制专项施工方案，≥5m方须组织专家论证；"
                 "3m≤深度<5m 只需编案、不需论证")

# 规则组 C：专项方案编制主体（锚 cc:1A436000_008_0011:3、cc:1A436000_008_0011:4）
_AUTHOR_ALLOWED = {
    "总承包工程": frozenset({"施工总承包单位"}),
    "专业分包工程": frozenset({"专业承包单位"}),
}
_SPECIALIST_SUB_KINDS = ("起重机械安拆", "深基坑", "附着式升降脚手架")  # cc:...:4 点名分包情形
_ANCHOR_C = "cc:1A436000_008_0011:3 + cc:1A436000_008_0011:4"
_CORRECT_C = ("实行施工总承包的，专项方案由施工总承包单位组织编制；起重机械安拆/深基坑/"
              "附着式升降脚手架等专业分包工程可由专业承包单位组织编制")

# 规则组 D：专项方案必含内容（锚 kc:1A431000_008_0008:0 基坑8项 / kc:1A431000_009_0009:0 模板支撑）
_PIT_PLAN_ITEMS = ("工程概况", "编制依据", "施工计划", "施工工艺技术", "施工保证措施",
                   "施工管理及人员配备", "验收要求", "应急处置措施")
_FORMWORK_PLAN_ITEMS = ("工程概况", "技术参数", "工艺流程", "施工方法", "检查要求",
                        "计算书及相关施工图纸")
_ANCHOR_D_PIT = "kc:1A431000_008_0008:0"
_ANCHOR_D_FORMWORK = "kc:1A431000_009_0009:0"
_CORRECT_D_PIT = "基坑专项方案八项内容：" + "/".join(_PIT_PLAN_ITEMS) + "，缺项应补全"
_CORRECT_D_FORMWORK = ("模板支撑专项方案内容：" + "/".join(_FORMWORK_PLAN_ITEMS)
                       + "（计算书及相关施工图纸为模板支撑特有、补全题易漏）")

# 规则组 E：专家论证程序与专家组（锚 cc:1A437000_010_0013:1/:2/:3、kc:1A437000_010_0013:0、
# ca:1A437000_010_0013；真题 {2019,案例二}）
# jury#5 fail-closed：不判"审核 vs 审查"内部先后，只判"论证前二者齐备"
_PROC_CASES = (
    {"surface": "专项方案经施工单位审核和总监理工程师审查后，再召开专家论证会",
     "contractor_review": True, "supervisor_review": True, "before_panel": True},
    {"surface": "专项方案未经总监理工程师审查即召开专家论证会",
     "contractor_review": True, "supervisor_review": False, "before_panel": True},
    {"surface": "专项方案未经施工单位审核即召开专家论证会",
     "contractor_review": False, "supervisor_review": True, "before_panel": True},
    {"surface": "专项方案先召开专家论证会，再报总监理工程师审查",
     "contractor_review": True, "supervisor_review": True, "before_panel": False},
)
_ANCHOR_E_PROC = "cc:1A437000_010_0013:3 + kc:1A437000_010_0013:0"
_CORRECT_E_PROC = "专家论证前专项方案应经施工单位审核和总监理工程师审查"

_ORGANIZER_ALLOWED = frozenset({"施工总承包单位"})
_ORGANIZER_SURFACES = ("施工总承包单位", "建设单位", "监理单位")  # R4 E 判分边界点名主体
_ANCHOR_E_ORG = "cc:1A437000_010_0013:2 + kc:1A437000_010_0013:0"
_CORRECT_E_ORG = "实行施工总承包的，专家论证会由施工总承包单位组织召开"

_PANEL_MIN = 5
_PANEL_SIZE_SURFACES = (3, 4, 5, 7)
_ANCHOR_E_PANEL = "ca:1A437000_010_0013 + kc:1A437000_010_0013:0"
_ANCHOR_E_PANEL_EXAM = "ca:1A437000_010_0013 + {2019,案例二}"
_CORRECT_E_PANEL_SIZE = "专家组成人员应为5人以上"
_CORRECT_E_PANEL_AVOID = ("专家不得与工程有利害关系，本项目参建各方的人员不得以专家身份参加专家论证")
_CORRECT_E_PANEL_SIGN = "专家论证报告需经专家签字确认"

# 规则组 G：论证主要内容（强锚 {2023,第28题}，ca 作教材佐证——jury#4 口径）
_REVIEW_CONTENT_ITEMS = ("方案内容是否完整、可行", "计算书和验算依据、施工图是否符合标准规范",
                         "是否满足现场实际并确保施工安全")
_REVIEW_CONTENT_DISTRACTORS = ("方案经济性", "分包单位资质")  # {2023,第28题} D/E 干扰项
_ANCHOR_G = "{2023,第28题} + ca:1A437000_010_0013"
_CORRECT_G = ("专家论证主要内容三项：方案内容是否完整、可行；计算书和验算依据、施工图"
              "是否符合标准规范；是否满足现场实际并确保施工安全（方案经济性、分包单位"
              "资质不属论证内容）")

# 规则组 F：危大六项现场管理（锚 kc:1A436000_010_0011:0、cc:1A436000_010_0011:1/:2/:3；
# S7 真题锚 🔴 故只挂教材锚）
_SITE_MGMT_ITEMS = ("公示", "方案交底", "严禁擅自修改方案", "人员登记与监督",
                    "监测与巡视", "第三方监测")
_ANCHOR_F = "kc:1A436000_010_0011:0"
_CORRECT_F = "危大六项现场管理要求封闭集：" + "/".join(_SITE_MGMT_ITEMS)
_ANCHOR_F_MODIFY = "cc:1A436000_010_0011:3"
_CORRECT_F_MODIFY = "应严格按照专项施工方案组织施工，不得擅自修改"
_BRIEFING_ALLOWED = frozenset({"方案编制人员", "项目技术负责人"})
_ANCHOR_F_BRIEF = "cc:1A436000_010_0011:2"
_CORRECT_F_BRIEF = "方案实施前应由方案编制人员或项目技术负责人向施工现场管理人员进行方案交底"


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"J01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：危大档判定——类型×参数皮全枚举（题面主张"属危大须编案"，按阈值互证）
    for label, thr, unit, values in _HAZARD_RULES:
        for val in values:
            v_txt = f"{val:g}{unit}"
            add("A-hazard",
                f"某工程{label}为{v_txt}，项目部认定其属于危险性较大的分部分项工程并编制专项施工方案",
                {"label": label, "value": val, "claim": "hazardous"}, val >= thr,
                _CORRECT_A, _ANCHOR_A)

    # 组 B：超规模判定——类型×参数皮全枚举（题面主张"需专家论证"，按超规模阈值互证）
    for label, thr, unit, values in _SUPER_RULES:
        anchor = _ANCHOR_B_BASE + _ANCHOR_B_EXTRA.get(label, "")
        for val in values:
            v_txt = f"{val:g}{unit}"
            add("B-super",
                f"某工程{label}为{v_txt}，项目部认为该工程需组织专家论证",
                {"label": label, "value": val, "claim": "super"}, val >= thr,
                _CORRECT_B, anchor)

    # 组 B-band：编案/论证双档带（基坑 3≤深度<5 只编案，R4 B 判分边界原文）
    for val, in ((4.0,), (6.0,)):
        add("B-band",
            f"某基坑工程开挖深度{val:g}m，项目部认为不需组织专家论证、只需编制专项施工方案",
            {"label": "基坑工程开挖深度", "value": val, "claim": "only_plan"},
            3.0 <= val < 5.0, _CORRECT_BAND,
            "kc:1A436000_008_0011:0 + kc:1A436000_009_0012:0")

    # 组 C：编制主体——情形×主体（R4 C 封闭枚举 + R7 点名错误主体）
    add("C-author", "实行施工总承包，专项施工方案由施工总承包单位组织编制",
        {"scenario": "总承包工程", "author": "施工总承包单位"}, True, _CORRECT_C, _ANCHOR_C)
    for wrong in ("建设单位", "监理单位"):
        add("C-author", f"实行施工总承包，专项施工方案由{wrong}组织编制",
            {"scenario": "总承包工程", "author": wrong}, False, _CORRECT_C, _ANCHOR_C)
    for kind in _SPECIALIST_SUB_KINDS:
        add("C-author", f"{kind}工程实行专业分包，专项施工方案由专业承包单位组织编制",
            {"scenario": "专业分包工程", "author": "专业承包单位", "kind": kind}, True,
            _CORRECT_C, _ANCHOR_C)

    # 组 D：方案必含内容——成员判断双极性（基坑8项 + 模板支撑6项）
    for item in _PIT_PLAN_ITEMS:
        add("D-content", f"基坑工程专项施工方案中编入「{item}」",
            {"plan": "基坑", "item": item, "listed": True}, True,
            _CORRECT_D_PIT, _ANCHOR_D_PIT)
        add("D-content", f"认为「{item}」无需编入基坑工程专项施工方案",
            {"plan": "基坑", "item": item, "listed": False}, False,
            _CORRECT_D_PIT, _ANCHOR_D_PIT)
    for item in _FORMWORK_PLAN_ITEMS:
        add("D-content", f"模板支撑工程专项施工方案中编入「{item}」",
            {"plan": "模板支撑", "item": item, "listed": True}, True,
            _CORRECT_D_FORMWORK, _ANCHOR_D_FORMWORK)
        add("D-content", f"认为「{item}」无需编入模板支撑工程专项施工方案",
            {"plan": "模板支撑", "item": item, "listed": False}, False,
            _CORRECT_D_FORMWORK, _ANCHOR_D_FORMWORK)

    # 组 E-proc：论证前置程序（jury#5：不判审核/审查内部先后）
    for case in _PROC_CASES:
        ok = case["contractor_review"] and case["supervisor_review"] and case["before_panel"]
        add("E-proc", case["surface"],
            {"contractor_review": case["contractor_review"],
             "supervisor_review": case["supervisor_review"],
             "before_panel": case["before_panel"]},
            ok, _CORRECT_E_PROC, _ANCHOR_E_PROC)

    # 组 E-org：论证组织主体
    for org in _ORGANIZER_SURFACES:
        add("E-org", f"实行施工总承包的项目，专家论证会由{org}组织召开",
            {"organizer": org}, org in _ORGANIZER_ALLOWED, _CORRECT_E_ORG, _ANCHOR_E_ORG)

    # 组 E-panel：专家组人数 / 回避 / 签字
    for n in _PANEL_SIZE_SURFACES:
        add("E-panel", f"专家论证会组织{n}名专家进行论证",
            {"panel_size": n}, n >= _PANEL_MIN, _CORRECT_E_PANEL_SIZE, _ANCHOR_E_PANEL)
    add("E-panel", "组织包括本项目总承包单位技术负责人在内的5名专家进行论证",
        {"panel_size": 5, "includes_project_party": True}, False,
        _CORRECT_E_PANEL_AVOID, _ANCHOR_E_PANEL_EXAM)
    add("E-panel", "邀请本项目监理单位人员以专家身份参加专家论证",
        {"includes_project_party": True}, False, _CORRECT_E_PANEL_AVOID, _ANCHOR_E_PANEL_EXAM)
    add("E-panel", "论证专家均与本工程无利害关系，且非本项目参建各方人员",
        {"includes_project_party": False}, True, _CORRECT_E_PANEL_AVOID, _ANCHOR_E_PANEL_EXAM)
    add("E-panel", "专家论证报告经全体专家签字确认",
        {"report_signed": True}, True, _CORRECT_E_PANEL_SIGN, _ANCHOR_E_PANEL)
    add("E-panel", "专家论证报告未经专家签字确认即归档",
        {"report_signed": False}, False, _CORRECT_E_PANEL_SIGN, _ANCHOR_E_PANEL)

    # 组 G：论证主要内容——成员判断双极性 + 真题干扰项双极性
    for item in _REVIEW_CONTENT_ITEMS + _REVIEW_CONTENT_DISTRACTORS:
        member = item in _REVIEW_CONTENT_ITEMS
        add("G-review", f"将「{item}」列入专家论证会的论证主要内容",
            {"item": item, "listed": True}, member, _CORRECT_G, _ANCHOR_G)
        add("G-review", f"认为「{item}」不属于专家论证会的论证主要内容",
            {"item": item, "listed": False}, not member, _CORRECT_G, _ANCHOR_G)

    # 组 F：现场管理——六项成员判断双极性 + 擅自修改点名违例 + 交底主体
    for item in _SITE_MGMT_ITEMS:
        add("F-site", f"将「{item}」列入危大工程现场管理要求并落实",
            {"item": item, "listed": True}, True, _CORRECT_F, _ANCHOR_F)
        add("F-site", f"认为「{item}」不属于危大工程现场管理要求",
            {"item": item, "listed": False}, False, _CORRECT_F, _ANCHOR_F)
    add("F-site", "施工中现场管理人员根据现场实际情况擅自修改专项施工方案",
        {"unauthorized_modify": True}, False, _CORRECT_F_MODIFY, _ANCHOR_F_MODIFY)
    add("F-site", "施工中严格按照专项施工方案组织施工，未擅自修改",
        {"unauthorized_modify": False}, True, _CORRECT_F_MODIFY, _ANCHOR_F_MODIFY)
    for who in ("方案编制人员", "项目技术负责人"):
        add("F-site", f"方案实施前由{who}向施工现场管理人员进行方案交底",
            {"briefing_by": who}, True, _CORRECT_F_BRIEF, _ANCHOR_F_BRIEF)

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-hazard":
        thr = _HAZARD_THRESHOLDS.get(p.get("label"))
        if thr is None or p.get("claim") != "hazardous":
            return None
        return p["value"] >= thr
    if g == "B-super":
        thr = _SUPER_THRESHOLDS.get(p.get("label"))
        if thr is None or p.get("claim") != "super":
            return None
        return p["value"] >= thr
    if g == "B-band":
        if p.get("label") != "基坑工程开挖深度" or p.get("claim") != "only_plan":
            return None
        return (p["value"] >= _HAZARD_THRESHOLDS["基坑工程开挖深度"]
                and p["value"] < _SUPER_THRESHOLDS["深基坑开挖深度"])
    if g == "C-author":
        allowed = _AUTHOR_ALLOWED.get(p.get("scenario"))
        return None if allowed is None else p["author"] in allowed
    if g == "D-content":
        enum = _PIT_PLAN_ITEMS if p.get("plan") == "基坑" else (
            _FORMWORK_PLAN_ITEMS if p.get("plan") == "模板支撑" else None)
        if enum is None or p["item"] not in enum:
            return None  # 枚举外条目不许出现(封闭域)
        return bool(p["listed"])
    if g == "E-proc":
        return (bool(p["contractor_review"]) and bool(p["supervisor_review"])
                and bool(p["before_panel"]))
    if g == "E-org":
        if p["organizer"] not in _ORGANIZER_SURFACES:
            return None
        return p["organizer"] in _ORGANIZER_ALLOWED
    if g == "E-panel":
        if p.get("includes_project_party") is not None:
            return not p["includes_project_party"]
        if "report_signed" in p:
            return bool(p["report_signed"])
        return p["panel_size"] >= _PANEL_MIN
    if g == "G-review":
        universe = set(_REVIEW_CONTENT_ITEMS) | set(_REVIEW_CONTENT_DISTRACTORS)
        if p["item"] not in universe:
            return None
        return (p["item"] in _REVIEW_CONTENT_ITEMS) == bool(p["listed"])
    if g == "F-site":
        if "unauthorized_modify" in p:
            return not p["unauthorized_modify"]
        if "briefing_by" in p:
            return p["briefing_by"] in _BRIEFING_ALLOWED
        if p["item"] not in _SITE_MGMT_ITEMS:
            return None
        return bool(p["listed"])
    return None


# 争议/越界/外延层 token，禁入题面与正确做法（fail-closed）：
# 起拱=§8.2 C4 模板工艺越界；梁跨度=编案10m档不在 R4 A 表({2015,案例1}语境专用)；
# 重大事故隐患=§1 #15 法律后果外延🔵
_CONTESTED_TOKENS = ("起拱", "梁跨度", "重大事故隐患")


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
        "pack_id": "J01",
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
