#!/usr/bin/env python3
"""Z01 变体池编译期预生成器（智能建造/智能施工/建筑机器人·2026 新增导则）。

承接 E01/E06 先例：编译期确定性枚举（零 LLM、零随机、零时间依赖），从 Z01 Pack
§4 R4 五个封闭规则组派生变体，生成器与校验器分别推导判定互证。anchor 全部指向
`_Z01_compiled_source.json`（`mine_Z01.py` cc: 原文闸核验），启动时直读源料核验
anchor 存在（fail-closed）。

2026 新增点纪律：
- 题面禁用 OCR/增强存疑短语（「自适应力」「变形控制力」——pack §8.4）与跨领域
  重复环节判别项（测量放线/放样、抹灰、喷涂笼统词——双解风险）；
- 禁绿色建造导则 territory token（实名制/门禁/智慧工地——M8 混淆源）；
- membership 反例（如「施工日志∈数字化交付内容」）是题面干扰项构造，判定真值与
  correct_statement 始终锚教材封闭清单，不构成对教材的编造；
- status 恒 `candidate` + pending_dual_sign；签发唯一入口 promote_variant_bank.py。

用法::

    python3 scripts/build_luban_z01_variant_bank.py          # 生成 + 门 + 写产物
    python3 scripts/build_luban_z01_variant_bank.py --check  # 只跑一致性门
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_Z01_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "Z01_智能建造与建筑机器人2026.md"
SRC_PATH = REPO / "docs" / "原始数据" / "考点原料" / "_Z01_compiled_source.json"

SCHEMA_NAME = "luban-z01-variant-bank"

# ── 锚 ──────────────────────────────────────────────────────────────────────
_A_GOAL = "cc:1A422000_052_0078:0"
_A_SURVEY = "cc:1A422000_052_0078:2"
_A_PROD = "cc:1A422000_052_0078:3"
_B_PLAN = "cc:1A422000_053_0079:0"
_B_BIM = "cc:1A422000_053_0079:1"
_B_FOUND = "cc:1A422000_053_0079:3"
_B_MAIN = "cc:1A422000_053_0079:4"
_B_PLATFORM = "cc:1A422000_053_0079:5"
_B_GROUT = "cc:1A422000_053_0079:6"
_B_ENVEL = "cc:1A422000_053_0079:8"
_B_DECOR_SYS = "cc:1A422000_053_0079:9"
_B_DECOR = "cc:1A422000_053_0079:10"
_C_OVERALL = "cc:1A422000_054_0080:0"
_C_BIMBASE = "cc:1A422000_054_0080:1"
_C_DRONE = "cc:1A422000_054_0080:2"
_C_TIER = "cc:1A422000_054_0080:3"
_C_CARRY = "cc:1A422000_054_0080:4"
_C_SPRAY = "cc:1A422000_054_0080:5"
_E_DELIVER = "cc:1A422000_054_0080:6"
_E_OPS = "cc:1A422000_054_0080:7"

_ALL_ANCHORS = [_A_GOAL, _A_SURVEY, _A_PROD, _B_PLAN, _B_BIM, _B_FOUND, _B_MAIN,
                _B_PLATFORM, _B_GROUT, _B_ENVEL, _B_DECOR_SYS, _B_DECOR,
                _C_OVERALL, _C_BIMBASE, _C_DRONE, _C_TIER, _C_CARRY, _C_SPRAY,
                _E_DELIVER, _E_OPS]

# ── 封闭取值域（逐字对齐 Z01 Pack §4 R4 / 2026 块原文）──────────────────────
_CORRECT_A = ("《智能建造技术导则（试行）》以「提品质、降成本」为目标，集成数字勘察、数字设计、"
              "智能生产、智能施工、智慧运维五阶段关键技术；智能生产在工厂、智能施工在现场")
_STAGES = ("数字勘察", "智能生产", "智能施工", "智慧运维")
_STAGE_CORRECT = {
    "工程勘察全过程数据的快速准确采集与共享": ("数字勘察", _A_SURVEY),
    "建筑部品部件智能生产线与标准部品部件生产体系": ("智能生产", _A_PROD),
    "施工现场智能建造装备及建筑机器人辅助作业": ("智能施工", _B_MAIN),
    "建筑结构健康监测与末端设备自动控制": ("智慧运维", _E_OPS),
}

_DOMAINS = ("数据驱动施工管理", "地基基础智能施工", "主体结构智能施工",
            "围护结构智能施工", "装饰装修工程智能施工")
# 仅取教材单一领域独有判别项（跨领域重复项禁入，见 pack §8.4）
_DOMAIN_CORRECT = {
    "桩基施工机器人辅助作业": ("地基基础智能施工", _B_FOUND),
    "构件吊装与混凝土布料机器人辅助作业": ("主体结构智能施工", _B_MAIN),
    "预制构件灌浆套筒自动灌浆": ("主体结构智能施工", _B_MAIN),
    "实测实量机器人实体质量检测": ("围护结构智能施工", _B_ENVEL),
    "地坪打磨与乳胶漆喷涂机器人作业": ("装饰装修工程智能施工", _B_DECOR),
    "BIM 施工总平面布置规划与工序模拟优化": ("数据驱动施工管理", _B_BIM),
}
# 指定混淆域（core）；其余组合入池但标 extension
_DOMAIN_CONFUSER = {
    "桩基施工机器人辅助作业": "主体结构智能施工",
    "构件吊装与混凝土布料机器人辅助作业": "地基基础智能施工",
    "预制构件灌浆套筒自动灌浆": "装饰装修工程智能施工",
    "实测实量机器人实体质量检测": "装饰装修工程智能施工",
    "地坪打磨与乳胶漆喷涂机器人作业": "围护结构智能施工",
    "BIM 施工总平面布置规划与工序模拟优化": "主体结构智能施工",
}

_EQUIP_USES = {
    "无人机": ("航拍自动化测算场地平整、基坑开挖及填筑土方量，生成三维实景模型展示进度", _C_DRONE),
    "手持式智能钢筋捆扎机": ("辅助人工进行钢筋捆扎作业", _C_TIER),
    "搬运机器人": ("物料自动化运输，与智能升降机数据联网实现垂直与水平运输联动", _C_CARRY),
    "喷涂机器人": ("建筑外立面墙漆喷涂，自动规划路径并自动喷涂底漆、中涂、面漆、罩光漆", _C_SPRAY),
    "智能化灌浆装备": ("对预制构件的灌浆套筒进行连接并自动检测灌浆质量", _B_GROUT),
}
_EQUIPS = tuple(_EQUIP_USES)

_CORRECT_C = ("装备用途按教材配对：无人机=土方量测算与三维实景进度；钢筋捆扎机=辅助人工捆扎；"
              "搬运机器人=物料运输与升降机联动；喷涂机器人=外立面墙漆四层自动喷涂；"
              "智能化灌浆装备=灌浆套筒连接与灌浆质量自动检测")
_CORRECT_D_PLAN = ("智能施工应编制专项实施方案明确应用计划，依据方案对施工过程跟踪指导，"
                   "并在施工完成后对方案实施效果进行评估")
_CORRECT_D_OVERALL = ("装备应用应统筹考虑技术适用性、成本投入、效益产出三因素，明确应用需求及进场计划")
_CORRECT_E_DELIVER = ("数字化交付内容为四项：模型（建筑/结构/机电/装饰/幕墙）、图纸、工程量清单、"
                      "工程所处环境信息")
_DELIVER_TRUE = ("模型", "图纸", "工程量清单", "工程所处环境信息")
_DELIVER_FALSE = ("施工日志", "成本核算台账")
_CORRECT_E_DECOR = ("装配式装修部品集成六系统：集成卫浴、集成厨房、架空楼面、隔墙和墙面、"
                    "集成吊顶、设备和管线系统")
_DECOR_TRUE = ("集成卫浴系统", "集成厨房系统", "架空楼面系统", "集成吊顶系统")
_DECOR_FALSE = ("现浇楼面系统", "外脚手架系统")
_CORRECT_E_PLATFORM = ("智能顶升集成建造平台集成：智能塔吊、智能施工电梯、智能运输车、悬挂式布料机、"
                       "水平运输设备、隔音降噪装置、物联感知与通信设备、建筑机器人、设备控制与监测平台")
_PLATFORM_TRUE = ("智能塔吊", "智能施工电梯", "悬挂式布料机", "设备控制与监测平台")
_PLATFORM_FALSE = ("无人机", "实测实量机器人")
_CORRECT_E_OPS = ("智慧运维平台提供人员管理、设备监控、能耗监测等管理能力，用于建筑结构健康监测、"
                  "建筑功能运行维护、安全风险应急管理")
_OPS_TRUE = ("人员管理", "设备监控", "能耗监测")
_OPS_FALSE = ("工程量清单编制",)


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"Z01-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：五阶段框架归属——事项×阶段全枚举
    add("A-stage", "项目部提出智能建造应以「提品质、降成本」为目标，集成五阶段关键技术产品",
        {"goal": "提品质降成本"}, True, _CORRECT_A, _A_GOAL)
    for item, stage in itertools.product(_STAGE_CORRECT, _STAGES):
        true_stage, anch = _STAGE_CORRECT[item]
        add("A-stage", f"技术交底中把「{item}」归入{stage}阶段",
            {"item": item, "stage": stage}, stage == true_stage,
            _CORRECT_A, anch, extension=(stage != true_stage and stage not in ("智能生产", "智能施工")))

    # 组 B：五大领域环节配对——判别项×领域（真值+指定混淆域=core，其余=extension）
    for item, domain in itertools.product(_DOMAIN_CORRECT, _DOMAINS):
        true_domain, anch = _DOMAIN_CORRECT[item]
        core = domain in (true_domain, _DOMAIN_CONFUSER[item])
        add("B-domain", f"智能施工方案把「{item}」列入{domain}部分",
            {"item": item, "domain": domain}, domain == true_domain,
            f"「{item}」属{true_domain}（教材领域清单）", anch, extension=not core)

    # 组 C：装备↔用途配对——装备×用途全枚举（对角=妥；错配 core 取相邻一位，其余 extension）
    uses = [(_EQUIP_USES[e][0], e) for e in _EQUIPS]
    for i, equip in enumerate(_EQUIPS):
        for j, (use_text, use_owner) in enumerate(uses):
            core = (i == j) or (j == (i + 1) % len(_EQUIPS))
            add("C-equip", f"项目部安排{equip}承担：{use_text}",
                {"equip": equip, "use_owner": use_owner},
                equip == use_owner, _CORRECT_C, _EQUIP_USES[equip][1],
                extension=not core)

    # 组 D：程序与统筹
    add("D-proc", "项目编制智能施工专项实施方案明确应用计划，过程跟踪指导，完工后对实施效果评估",
        {"steps": ["编制", "跟踪", "评估"]}, True, _CORRECT_D_PLAN, _B_PLAN)
    add("D-proc", "项目未编制智能施工专项实施方案，直接采购建筑机器人进场作业",
        {"steps": ["跟踪"]}, False, _CORRECT_D_PLAN, _B_PLAN)
    add("D-proc", "项目编制了专项实施方案并跟踪指导，但施工完成后未对方案实施效果进行评估",
        {"steps": ["编制", "跟踪"]}, False, _CORRECT_D_PLAN, _B_PLAN)
    add("D-proc", "项目先组织机器人施工、完工后补编智能施工专项实施方案",
        {"steps": ["跟踪", "编制"]}, False, _CORRECT_D_PLAN, _B_PLAN)
    add("D-proc", "装备选型综合考虑技术适用性、成本投入、效益产出，明确应用需求及进场计划",
        {"factors": ["技术", "成本", "效益"]}, True, _CORRECT_D_OVERALL, _C_OVERALL)
    add("D-proc", "装备选型只比较各厂家技术先进性即确定进场计划",
        {"factors": ["技术"]}, False, _CORRECT_D_OVERALL, _C_OVERALL)
    add("D-proc", "以 BIM 模型作为智能建造装备及建筑机器人协同作业、路径规划、导航及调度的基础",
        {"bim_base": True}, True, "BIM 模型是装备协同作业、路径规划、导航及调度的基础", _C_BIMBASE)

    # 组 E：列举完整性（多选形态候选池）——membership 断言
    for item in _DELIVER_TRUE:
        add("E-member", f"数字化交付方案将「{item}」列入交付内容",
            {"kind": "deliver", "member": item}, True, _CORRECT_E_DELIVER, _E_DELIVER)
    for item in _DELIVER_FALSE:
        add("E-member", f"技术交底称「{item}」属于导则规定的数字化交付内容",
            {"kind": "deliver", "member": item}, False, _CORRECT_E_DELIVER, _E_DELIVER)
    for item in _DECOR_TRUE:
        add("E-member", f"把「{item}」列为装配式装修部品集成技术的组成系统",
            {"kind": "decor", "member": item}, True, _CORRECT_E_DECOR, _B_DECOR_SYS)
    for item in _DECOR_FALSE:
        add("E-member", f"技术交底称「{item}」属于装配式装修部品集成六系统",
            {"kind": "decor", "member": item}, False, _CORRECT_E_DECOR, _B_DECOR_SYS)
    for item in _PLATFORM_TRUE:
        add("E-member", f"把「{item}」列为智能顶升集成建造平台的集成装备",
            {"kind": "platform", "member": item}, True, _CORRECT_E_PLATFORM, _B_PLATFORM)
    for item in _PLATFORM_FALSE:
        add("E-member", f"技术交底称「{item}」是智能顶升集成建造平台的集成装备",
            {"kind": "platform", "member": item}, False, _CORRECT_E_PLATFORM, _B_PLATFORM)
    for item in _OPS_TRUE:
        add("E-member", f"智慧运维平台方案将「{item}」列为平台管理能力",
            {"kind": "ops", "member": item}, True, _CORRECT_E_OPS, _E_OPS)
    for item in _OPS_FALSE:
        add("E-member", f"技术交底称「{item}」是智慧运维平台的管理能力",
            {"kind": "ops", "member": item}, False, _CORRECT_E_OPS, _E_OPS)

    return variants


# ── 独立一致性检查门（从 params 重新推导，不复用生成分支）────────────────────
_MEMBER_TABLES = {
    "deliver": (set(_DELIVER_TRUE), set(_DELIVER_FALSE)),
    "decor": (set(_DECOR_TRUE), set(_DECOR_FALSE)),
    "platform": (set(_PLATFORM_TRUE), set(_PLATFORM_FALSE)),
    "ops": (set(_OPS_TRUE), set(_OPS_FALSE)),
}


def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g == "A-stage":
        if "goal" in p:
            return p["goal"] == "提品质降成本"
        rec = _STAGE_CORRECT.get(p["item"])
        return None if rec is None else p["stage"] == rec[0]
    if g == "B-domain":
        rec = _DOMAIN_CORRECT.get(p["item"])
        return None if rec is None else p["domain"] == rec[0]
    if g == "C-equip":
        if p["equip"] not in _EQUIP_USES or p["use_owner"] not in _EQUIP_USES:
            return None
        return p["equip"] == p["use_owner"]
    if g == "D-proc":
        if "steps" in p:
            return p["steps"] == ["编制", "跟踪", "评估"]
        if "factors" in p:
            return set(p["factors"]) == {"技术", "成本", "效益"}
        if "bim_base" in p:
            return bool(p["bim_base"])
        return None
    if g == "E-member":
        true_set, false_set = _MEMBER_TABLES.get(p.get("kind"), (set(), set()))
        m = p.get("member")
        if m in true_set:
            return True
        if m in false_set:
            return False
        return None  # 封闭域外禁入
    return None


# 禁入 token：绿色建造导则 territory(M8 混淆源)/OCR 存疑(pack §8.4)/跨领域重复
# 判别词(双解)/邻接域/主体规范
_CONTESTED_TOKENS = ("实名制", "智能门禁", "智慧工地", "喷淋", "电子围栏",
                     "自适应力", "变形控制力",
                     "测量放线", "测量放样",
                     "索赔", "进度款", "甲方", "乙方")


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
        "pack_id": "Z01",
        "status": "candidate",  # 双签(teaching+scoring)后经 promote_variant_bank.py 方可签发
        "review_track": "pending_dual_sign(teaching+scoring)·工单=2026-08-06-E06-Z01-双签工单.md",
        "production_basis": "官方《2026教材对比明细》新增《智能建造技术导则(试行)》(建办市〔2025〕14号)·2026 教材块原文锚",
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
