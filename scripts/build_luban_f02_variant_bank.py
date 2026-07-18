#!/usr/bin/env python3
"""F02 变体池编译期预生成器（卷材防水施工顺序与搭接方向）。

双轮设计 v3.2 §8 红线：R4 变体在**编译期**按封闭规则预生成、过 gate、签发入池；
runtime 只抽取，**禁运行时 LLM 现编**。本脚本承接 S05/F16 先例
（`scripts/build_luban_s05_variant_bank.py` / `scripts/build_luban_f16_variant_bank.py`）
——纯确定性枚举（零 LLM、零随机），从 F02 Pack §4 R4 五个封闭规则组派生变体，
自带独立一致性检查门（生成器与校验器从同一规则表**分别**推导判定，互证）。

变体形状（只换皮不换判分锚——红线 9：变题不越变量边界）：
- 每个变体 = 情境题面（做法/数值在封闭取值域内代换）+ 期望判定（妥/不妥）
  + 正确做法 + 采分锚（pack 内 point_id / 真题锚，逐字不变）。
- 判分真值仍归 signed scoring artifact / 判分内核；本池只是复测题面弹药，
  期望判定仅供一致性门与教研审核用，不充 runtime 判分权威。

诚实边界（fail-closed，逐条对应 F02 pack 裁决）：
- **R4 封闭性自检明示**：A~C 组取值域来自教材锚，封闭成立；**D~E 组取值域部分
  来自真题侧归纳**——本池 D/E 只枚举带 🟢 真题锚的档
  （`{2018,第14题}`/`{2025,第13题}`/`{2015,案例2}`，经 gate2 确定性核真）与
  教材锚档（`kc:1A413030_125_0237:0/:1`），不外推规范并列情形。
- **jury §9 #8 争议档整档不入**：「长边错开写 1/2 幅宽判 0 分过硬、与规范比对
  不符」（1/2 幅宽 ≥1/3 本身达标）——「1/2幅宽」档禁入池（含作干扰项）；
  长边组只枚举 {错开1/3幅宽=妥, 不错开=不妥} 两个无争议档。
- **§8.2 C2/C3 同词不同物整族禁入**：涂膜防水搭接（胎体 50/70mm）=涂膜≠卷材
  🔵 邻接；隔汽层卷材搭接 80mm=保温隔汽采分轴——token 禁入。
- **§8.2 C4/C8 剔噪留痕**：饰面砖满粘法（2019 第13题·装饰装修）、防水混凝土/
  水泥砂浆防水（B159 剔噪 / {2023,第19题} 🔵邻接）——token 禁入。
- **热熔法参数档不入**（热熔 180~200℃/胶结料 1.0~1.5mm/厚度<3mm 禁热熔）：
  为 R5 #8 采分点但**不在 R4 A~E 任何封闭规则组内**（§6 也把热熔参数误区降 🔵
  移出主清单）——本池严格以 R4 组为变量权威，不外溢。
- **R7 边界档位全 🔴 待裁决**——不作变体判定依据，本池期望判定只有妥/不妥二值。

用法::

    python3 scripts/build_luban_f02_variant_bank.py          # 生成 + 过一致性门 + 写产物
    python3 scripts/build_luban_f02_variant_bank.py --check  # 只跑一致性门(CI 可挂)
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
OUT_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_F02_variant_bank.v0.json"
PACK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "F02_卷材防水施工顺序与搭接方向.md"

SCHEMA_NAME = "luban-f02-variant-bank"  # dash 命名空间 = 一次性脚本产物(T3), 非 runtime schema

# ── 封闭取值域（全部逐字来自 F02 Pack §4 R4 / §5，锚随行）─────────────────
# 规则组 A：施工顺序 + 铺贴方向（封闭流程）
# 锚 kc:1A413030_123_0234:0；真题印证 {2016,第27题} + {2019,第1题第3问}
_ANCHOR_A = "kc:1A413030_123_0234:0 + {2016,第27题} + {2019,第1题第3问}"
_A_RULES: dict[str, dict[str, Any]] = {
    "施工先后": {
        "ok": ("先进行细部构造处理，后大面积铺贴",),
        "bad": ("先大面积铺贴，后进行细部构造处理",),
        "correct": "应先细部构造处理，后大面积铺贴（先大面后细部=不妥）",
    },
    "铺贴起止": {
        "ok": ("从屋面最低标高处开始，由低向高铺贴",),
        "bad": ("从屋面最高处开始，由高向低铺贴",),
        "correct": "应由屋面最低标高处开始、由低向高铺贴（由高向低=不妥）",
    },
    "铺贴方向": {
        "ok": ("卷材平行屋脊铺贴",),
        "bad": (),  # R4 该行判分边界为"—"，不外推反例
        "correct": "卷材宜平行屋脊铺贴",
    },
    "立面大坡面铺贴法": {
        "ok": ("立面及大坡面铺贴卷材采用满粘法",),
        "bad": ("立面及大坡面铺贴卷材采用空铺法", "立面及大坡面铺贴卷材采用点粘法"),
        "correct": "立面/大坡面应采用满粘法（空铺/点粘=不妥）",
    },
    "坡度大于25%固定": {
        "ok": ("屋面坡度大于25%，铺贴卷材采用满粘法并用钉压固定",),
        "bad": ("屋面坡度大于25%，铺贴卷材仅满粘、未做钉压固定",),
        "correct": "屋面坡度>25%时应满粘并加钉压固定（仅满粘不钉压=不妥）",
    },
}

# 规则组 B：搭接方向（封闭，反向陷阱密集）
# 锚 kc:1A413030_123_0234:0 + kc:1A422000_041_0065:0 + kc:1A422000_029_0049:0
_ANCHOR_B = ("kc:1A413030_123_0234:0 + kc:1A422000_041_0065:0 + "
             "kc:1A422000_029_0049:0 + {2016,第27题}")
_B_RULES: dict[str, dict[str, Any]] = {
    "搭接缝方向": {
        "ok": ("搭接缝顺流水方向",),
        "bad": ("搭接缝逆流水方向", "搭接缝形成迎水缝"),
        "correct": "搭接缝应顺流水方向、卷材宜平行屋脊铺贴（逆流水/迎水缝=不妥）",
    },
    "上下层关系": {
        "ok": ("上下两层卷材不相互垂直铺贴",),
        "bad": ("上下两层卷材相互垂直铺贴",),
        "correct": "上下两层卷材不得相互垂直铺贴（2016 D错项/2018 D错项）",
    },
}

# 规则组 C：搭接错缝量（封闭数字）——锚 kc:1A422000_029_0049:0 + kc:1A422000_041_0065:0
# 短边题面值只用 pack 封闭数字 {500(正), 50(R4 点名陷阱)}；
# 「1/2幅宽」档为 jury#8 争议档整档不入（fail-closed）
_ANCHOR_C = "kc:1A422000_029_0049:0 + kc:1A422000_041_0065:0 + {2016,第27题}(E正项)"
_SHORT_EDGE_MIN_MM = 500
_CORRECT_C_SHORT = "同层相邻两幅卷材短边搭接错缝距离不应小于500mm（写50mm/不错缝=不妥）"
_CORRECT_C_LONG = "双层铺贴时上下两层及相邻两幅卷材长边接缝应错开至少1/3幅宽（不错开=不妥）"

# 规则组 D：地下室卷材（封闭·部位迁移；真题侧 🟢，经 gate2 核真）
_D_RULES: dict[str, dict[str, Any]] = {
    "铺贴面": {
        "ok": ("卷材铺设在混凝土结构迎水面",),
        "bad": ("卷材铺设在混凝土结构背水面",),
        "correct": "地下室卷材应铺设在混凝土结构迎水面（铺背水面=不妥）",
        "anchor": "{2018,第14题}(真题侧🟢) + kc:1A422000_029_0049:0(教材屋面侧)",
    },
    "外墙外侧粘贴": {
        "ok": ("外墙外侧卷材采用满贴法",),
        "bad": ("外墙外侧卷材采用空铺法",),
        "correct": "外墙外侧应采用满贴法（空铺法=不妥）",
        "anchor": "{2018,第14题}(真题侧🟢)",
    },
    "外防内贴法顺序": {
        "ok": ("外防内贴法铺贴卷材，先铺立面、后铺平面",),
        "bad": ("外防内贴法铺贴卷材，先铺平面、后铺立面",),
        "correct": "外防内贴法宜先铺立面、后铺平面（先平面后立面=不妥）",
        "anchor": "{2025,第13题}(真题侧🟢)",
    },
    "双层关系": {
        "ok": ("双层卷材铺贴，两层不相互垂直",),
        "bad": ("双层卷材铺贴，两层相互垂直",),
        "correct": "铺贴双层卷材时两层不得相互垂直（双层垂直=不妥）",
        "anchor": "{2018,第14题}(真题侧🟢) + kc:1A422000_029_0049:0",
    },
}

# 规则组 E：细部收头/附加层（封闭数字，案例侧）
# 锚 kc:1A413030_125_0237:0/:1 + {2015,案例2}
_FLASHING_MIN_MM = 250          # 泛水高度 ≥250mm
_FLASHING_SURFACES_MM = (250, 200)  # 200=2015案例2 原题错误做法（pack 封闭数字）
_ANCHOR_E_FLASHING = "{2015,案例2}(真题侧🟢)"
_CORRECT_E_FLASHING = "泛水高度应≥250mm（泛水200mm=不妥，2015案例2）"
_ADD_LAYER_MIN_MM = 250         # 附加层平面立面均 ≥250mm
_ANCHOR_E_ADD = "kc:1A413030_125_0237:1 + {2015,案例2}"
_CORRECT_E_ADD = "女儿墙泛水应增设附加层，平面和立面宽度均≥250mm（漏附加层=不妥）"
_E_DISCRETE_RULES: dict[str, dict[str, Any]] = {
    "阴阳角基层": {
        "ok": ("阴阳角基层做成45°斜面", "阴阳角基层做成圆弧"),
        "bad": ("阴阳角基层做成直角",),
        "correct": "阴阳角基层应做成45°或圆弧（直角=不妥，2015案例2）",
        "anchor": "{2015,案例2}(真题侧🟢)",
    },
    "收头": {
        "ok": ("卷材收头用金属压条钉压固定并用密封材料密封，压顶做鹰嘴和滴水槽",),
        "bad": ("卷材收头未用金属压条钉压固定",
                "压顶檐口下端未做鹰嘴和滴水槽"),
        "correct": "收头应用金属压条钉压固定并密封，压顶檐口下端做鹰嘴和滴水槽"
                   "（不钉压/未密封/无滴水槽=不妥）",
        "anchor": "kc:1A413030_125_0237:0 + {2015,案例2}",
    },
}


def build_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def add(group: str, surface: str, params: dict[str, Any], verdict_ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"F02-{group}-{len(variants):03d}",
            "rule_group": group,
            "surface": surface,
            "params": params,
            "expected_ok": verdict_ok,
            "correct_statement": correct,
            "anchor": anchor,
            "extension": extension,
        })

    # 组 A：施工顺序 + 铺贴方向——逐项 ok/bad 全枚举
    for item, rule in _A_RULES.items():
        for practice in rule["ok"] + rule["bad"]:
            add("A-order", f"屋面卷材防水层施工中，项目部{practice}",
                {"item": item, "practice": practice}, practice in rule["ok"],
                rule["correct"], _ANCHOR_A)

    # 组 B：搭接方向——逐项 ok/bad 全枚举
    for item, rule in _B_RULES.items():
        for practice in rule["ok"] + rule["bad"]:
            add("B-lap-direction", f"屋面卷材防水层施工中，{practice}",
                {"item": item, "practice": practice}, practice in rule["ok"],
                rule["correct"], _ANCHOR_B)

    # 组 C：搭接错缝量——短边封闭数字 + 长边两个无争议档（1/2幅宽档 jury#8 争议不入）
    for mm in (500, 50):
        add("C-lap-amount", f"同层相邻两幅卷材短边搭接错缝距离 {mm}mm",
            {"edge": "short", "offset_mm": mm}, mm >= _SHORT_EDGE_MIN_MM,
            _CORRECT_C_SHORT, _ANCHOR_C)
    add("C-lap-amount", "同层相邻两幅卷材短边搭接未错缝",
        {"edge": "short", "offset_mm": 0}, False, _CORRECT_C_SHORT, _ANCHOR_C)
    add("C-lap-amount", "双层铺贴时，上下两层及相邻两幅卷材长边接缝错开1/3幅宽",
        {"edge": "long", "offset": "错开1/3幅宽"}, True, _CORRECT_C_LONG, _ANCHOR_C)
    add("C-lap-amount", "双层铺贴时，上下两层及相邻两幅卷材长边接缝上下对齐、不错开",
        {"edge": "long", "offset": "不错开"}, False, _CORRECT_C_LONG, _ANCHOR_C)

    # 组 D：地下室卷材——逐项 ok/bad 全枚举（真题侧 🟢）
    for item, rule in _D_RULES.items():
        for practice in rule["ok"] + rule["bad"]:
            add("D-underground", f"地下室防水工程中，{practice}",
                {"item": item, "practice": practice}, practice in rule["ok"],
                rule["correct"], rule["anchor"])

    # 组 E：细部——泛水高度(封闭数字) + 附加层(数字+漏项) + 阴阳角/收头(离散)
    for mm in _FLASHING_SURFACES_MM:
        add("E-detail", f"屋面女儿墙防水节点泛水高度做至 {mm}mm",
            {"kind": "泛水高度", "height_mm": mm}, mm >= _FLASHING_MIN_MM,
            _CORRECT_E_FLASHING, _ANCHOR_E_FLASHING)
    add("E-detail", "女儿墙泛水部位增设附加层，平面和立面宽度均为 250mm",
        {"kind": "附加层", "added": True, "width_mm": 250}, True,
        _CORRECT_E_ADD, _ANCHOR_E_ADD)
    add("E-detail", "女儿墙泛水部位未增设附加层",
        {"kind": "附加层", "added": False}, False, _CORRECT_E_ADD, _ANCHOR_E_ADD)
    for item, rule in _E_DISCRETE_RULES.items():
        for practice in rule["ok"] + rule["bad"]:
            add("E-detail", f"屋面女儿墙防水节点施工中，{practice}",
                {"kind": item, "practice": practice}, practice in rule["ok"],
                rule["correct"], rule["anchor"])

    return variants


# ── 独立一致性检查门（不复用生成时的判定分支，从 params 重新推导）──────────
def _independent_verdict(v: dict[str, Any]) -> bool | None:
    p, g = v["params"], v["rule_group"]
    if g in ("A-order", "B-lap-direction", "D-underground"):
        rules = {"A-order": _A_RULES, "B-lap-direction": _B_RULES,
                 "D-underground": _D_RULES}[g]
        rule = rules.get(p["item"])
        if rule is None:
            return None
        if p["practice"] in rule["ok"]:
            return True
        if p["practice"] in rule["bad"]:
            return False
        return None  # 封闭域外做法不许出现
    if g == "C-lap-amount":
        if p["edge"] == "short":
            return p["offset_mm"] >= _SHORT_EDGE_MIN_MM
        if p["edge"] == "long":
            if p["offset"] not in ("错开1/3幅宽", "不错开"):
                return None  # 1/2幅宽等争议档禁入（jury#8）
            return p["offset"] == "错开1/3幅宽"
        return None
    if g == "E-detail":
        if p["kind"] == "泛水高度":
            return p["height_mm"] >= _FLASHING_MIN_MM
        if p["kind"] == "附加层":
            return bool(p.get("added")) and p.get("width_mm", 0) >= _ADD_LAYER_MIN_MM
        rule = _E_DISCRETE_RULES.get(p["kind"])
        if rule is None:
            return None
        if p["practice"] in rule["ok"]:
            return True
        if p["practice"] in rule["bad"]:
            return False
        return None
    return None


# 争议/🔵邻接/剔噪层 token，禁入题面与正确做法（fail-closed）：
# 涂膜/胎体=§8.2 C2 涂膜≠卷材(50/70mm)；隔汽=§8.2 C3 同词不同物(80mm 保温隔汽轴)；
# 饰面砖=§8.2 C4 剔除的 2019第13题装饰装修；防水混凝土/水泥砂浆=§8.2 C8 剔噪 +
# {2023,第19题} 🔵邻接；1/2幅宽=jury §9 #8 争议档；热熔=不在 R4 组内(见 docstring)
_CONTESTED_TOKENS = ("涂膜", "胎体", "隔汽", "饰面砖", "防水混凝土", "水泥砂浆",
                     "1/2幅宽", "热熔")


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
        "pack_id": "F02",
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
