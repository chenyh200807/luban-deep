#!/usr/bin/env python3
"""供给覆盖地图 v0 —— 按 canonical taxonomy 盘点 published 微课/练习/复测供给。

上游权威:
- `docs/plan/学习脑与学员记忆/2026-08-05-luban-ai-learning-plan-system-plan.md` §5(供给覆盖约束)
  与 §10 stop condition(主力薄弱点族课绑定率 <80% → 不上空计划);
- `docs/plan/测评题库与考试模块/2026-08-04-luban-pass-readiness-acquisition-diagnostic-plan.md`
  §6.4(五主题族)/ §6.5(复测供给取自既有编译池)/ §11 Phase 1(排除清单)。

纪律:
- **只读**。脚本不写任何生产状态、不改 manifest、不改 authority、不落库;
  唯一写盘对象是自己的报告 JSON(`--out`),默认 `docs/原始数据/数据盘点/`。
- **零估算**。所有数字来自确定性扫描;扫不到的资产记为 `null` + `missing` 原因,
  由文档侧写"未找到,需人工确认",脚本不猜。
- **幂等**。同一输入重跑产出逐字节相同的 JSON(sorted keys / 固定顺序)。

用法::

    python3 scripts/build_supply_coverage_map.py            # 打印 markdown 表 + 写报告 JSON
    python3 scripts/build_supply_coverage_map.py --stdout   # 只打印,不写盘
    python3 scripts/build_supply_coverage_map.py --json     # 打印完整 JSON
    python3 scripts/build_supply_coverage_map.py --check    # 报告 JSON 有漂移即非 0 退出
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]

PACK_DIR = REPO / "docs" / "原始数据" / "考点原料" / "成品"
MANIFEST_PATH = PACK_DIR / "_pack_manifest.json"
TAXONOMY_REGISTRY_PATH = PACK_DIR / "_pack_taxonomy_registry.v0.json"
COMPILED_TAXONOMY_PATH = (
    REPO / "deeptutor" / "services" / "taxonomy" / "compiled" / "construction_2026_taxonomy.compiled.json"
)
PRACTICE_AUTHORITY_DIR = REPO / "deeptutor" / "services" / "luban_lesson" / "compiled"
CARD_HOST_DIR = REPO / "web" / "public" / "luban-preview"
DEFAULT_OUT = REPO / "docs" / "原始数据" / "数据盘点" / "2026-08-05-供给覆盖地图v0.json"

SCHEMA_NAME = "luban_supply_coverage_map.v0"

# --------------------------------------------------------------------------------------
# 主题族映射(显式声明,不做启发式推断)
#
# 依据:诊断计划 §6.4 的五个 P0 主题族 + pack_id 前缀语义 + 注册表 student_title。
# 该映射复算出的包数/题数与 2026-08-05 初盘数字逐族精确一致(见 EXPECTED_AUDIT_2026_08_05),
# 因此作为 v0 的既定口径固化在此;任何调整必须同时更新对账基线,不得静默改。
#
# 已知歧义(文档侧已标"需人工确认"):`质量验收` 族的 4 个增补包存在两种同和读法——
# G01/G02/G03/G04(地基基础,本表采用)与 D11/D12/D13/D14(装饰),两者恰好都是 4 包/43 题。
# 本表采用 G 组,理由:§6.4 把 decoration 与 waterproofing 并列为第五轮换族,
# 若 D 组并入质量验收则第五族与质量验收重叠计数。
# --------------------------------------------------------------------------------------
FAMILY_MAP: dict[str, list[str]] = {
    "主体结构": ["C01", "C04", "C05", "C06", "C07", "Q01", "Q02"],
    "安全": ["J01", "R01", "S01", "S02", "S05", "S06", "S07"],
    "进度": ["E05", "N01", "N02", "N03"],
    "质量验收": ["A01", "A02", "G01", "G02", "G03", "G04", "Q03"],
    "防水": ["F02", "F03", "F04", "F05", "F16"],
    "装饰": ["D11", "D12", "D13", "D14"],
}
# 第五族在 §6.4 是轮换位(P0 取防水);两半都盘,合并数字单列。
ROTATING_FAMILY = ("防水+装饰", ["防水", "装饰"])
# 诊断计划 §6.4/§11 Phase 1 点名排除的族(不进 P0 表单,但必须盘出证据)。
EXCLUDED_FAMILY = ("合同索赔", ["C02", "E01", "K01"])
# 未归入以上任何族的 published 包(盘点必须自平,防漏包)。
UNASSIGNED_LABEL = "未归族"

# 2026-08-05 初盘(学习计划 §5 / 诊断计划 §6.4 引用)对账基线。
EXPECTED_AUDIT_2026_08_05 = {
    "published_pack_count": 41,
    "registry_slot_count": 60,
    "empty_slot_count": 19,
    "compiled_practice_pack_count": 40,
    "eligible_question_total": 382,
    "families": {
        "主体结构": {"packs": 7, "eligible_questions": 68},
        "安全": {"packs": 7, "eligible_questions": 61},
        "进度": {"packs": 4, "eligible_questions": 32},
        "质量验收": {"packs": 7, "eligible_questions": 75},
        "防水": {"packs": 5, "eligible_questions": 48},
    },
    "excluded_family_packs": {"合同索赔": 3},
}

LESSON_BINDING_THRESHOLD = 0.80  # 学习计划 §10 stop condition


# --------------------------------------------------------------------------------------
# 读取层(全部只读)
# --------------------------------------------------------------------------------------
def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _leaf_codes(nodes: list[dict]) -> set[str]:
    parents = {n["parent_code"] for n in nodes if n.get("parent_code")}
    return {n["code"] for n in nodes if n["code"] not in parents}


def _children_index(nodes: list[dict]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for n in nodes:
        idx.setdefault(n.get("parent_code") or "", []).append(n["code"])
    return idx


def _subtree_leaves(code: str, children: dict[str, list[str]], leaves: set[str]) -> set[str]:
    out: set[str] = set()
    stack = [code]
    while stack:
        cur = stack.pop()
        if cur in leaves:
            out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def _variant_bank_stats(pack_id: str) -> dict:
    """rule-group 确定性复测变体池(`_<PID>_variant_bank.v0.json`)。"""
    path = PACK_DIR / f"_{pack_id}_variant_bank.v0.json"
    if not path.is_file():
        return {"present": False, "variant_count": None, "status": None, "gate_pass_rate": None,
                "rule_group_count": None, "path": None}
    d = _load_json(path)
    gate = d.get("gate") or {}
    return {
        "present": True,
        "variant_count": len(d.get("variants") or []),
        "status": d.get("status"),
        "gate_pass_rate": gate.get("pass_rate"),
        "rule_group_count": len(d.get("per_group_counts") or {}),
        "path": str(path.relative_to(REPO)),
    }


def _practice_authority_stats(pack_id: str) -> dict:
    """编译练习/复测权威(`<pid>.practice.authority.json`)——§6.5 指定的复测取材池。"""
    path = PRACTICE_AUTHORITY_DIR / f"{pack_id.lower()}.practice.authority.json"
    if not path.is_file():
        return {"present": False, "item_count": None, "surface_count": None,
                "eligible_variant_id_count": None, "path": None}
    d = _load_json(path)
    surfaces = d.get("surfaces") or []
    eligible_ids: set[str] = set()
    for s in surfaces:
        eligible_ids.update(s.get("eligible_variant_ids") or [])
    return {
        "present": True,
        "item_count": len(d.get("items") or []),
        "surface_count": len(surfaces),
        "eligible_variant_id_count": len(eligible_ids),
        "path": str(path.relative_to(REPO)),
    }


def _lesson_page(pack_id: str) -> dict:
    """讲解页(讲懂卡)托管实证——与 build_luban_pack_manifest.py 同一判据,独立复扫。"""
    path = CARD_HOST_DIR / pack_id.lower() / "lesson.html"
    return {"hosted": path.is_file(), "path": str(path.relative_to(REPO)) if path.is_file() else None}


# --------------------------------------------------------------------------------------
# 盘点主体
# --------------------------------------------------------------------------------------
def collect() -> dict:
    manifest = _load_json(MANIFEST_PATH)
    registry = _load_json(TAXONOMY_REGISTRY_PATH)
    taxonomy = _load_json(COMPILED_TAXONOMY_PATH)

    nodes = taxonomy["nodes"]
    by_code = {n["code"]: n for n in nodes}
    leaves = _leaf_codes(nodes)
    children = _children_index(nodes)

    reg_packs = registry["packs"]

    packs: list[dict] = []
    for p in sorted(manifest["packs"], key=lambda x: x["pack_id"]):
        pid = p["pack_id"]
        pr = p.get("practice") or {}
        r = reg_packs.get(pid) or {}
        refs = [r.get("primary_taxonomy_ref")] + list(r.get("supporting_taxonomy_refs") or [])
        refs = [x for x in refs if x]
        packs.append(
            {
                "pack_id": pid,
                "title": p.get("title"),
                "student_title": r.get("student_title"),
                "slot": r.get("slot"),
                "published": bool(p.get("published")),
                "lesson": _lesson_page(pid),
                "manifest_card_hosted": bool(p.get("card_hosted")),
                "has_answer_layer": bool(p.get("has_answer_layer")),
                "has_exam_evidence": bool(p.get("has_exam_evidence")),
                "jury_clean": bool(p.get("jury_clean")),
                "alignment_status": r.get("alignment_status"),
                "registry_note": r.get("note"),
                "primary_taxonomy_ref": r.get("primary_taxonomy_ref"),
                "primary_taxonomy_ref_provisional": bool(r.get("primary_taxonomy_ref_provisional")),
                "taxonomy_refs": refs,
                "taxonomy_refs_unresolved": sorted(x for x in refs if x not in by_code),
                "practice_status": pr.get("status"),
                "practice_eligibility_status": pr.get("eligibility_status"),
                "eligible_question_count": pr.get("eligible_question_count"),
                "question_count": pr.get("question_count"),
                "revoked_question_count": pr.get("revoked_question_count"),
                "practice_authority": _practice_authority_stats(pid),
                "variant_bank": _variant_bank_stats(pid),
            }
        )

    by_id = {p["pack_id"]: p for p in packs}
    published_ids = [p["pack_id"] for p in packs if p["published"]]

    # 60 槽注册表空槽 = 注册表有槽位但 manifest 无 published 包
    empty_slots = sorted(
        (
            {"slot": v.get("slot"), "pack_id": pid, "student_title": v.get("student_title"),
             "alignment_status": v.get("alignment_status"), "note": v.get("note")}
            for pid, v in reg_packs.items()
            if pid not in set(published_ids)
        ),
        key=lambda x: int(x["slot"]) if str(x["slot"]).isdigit() else 999,
    )

    def family_block(name: str, pack_ids: list[str]) -> dict:
        members = [by_id[pid] for pid in sorted(pack_ids) if pid in by_id]
        missing = sorted(set(pack_ids) - set(by_id))
        hosted = [m for m in members if m["lesson"]["hosted"]]
        elig = [m["eligible_question_count"] or 0 for m in members]
        vb = [m for m in members if m["variant_bank"]["present"]]
        pa = [m for m in members if m["practice_authority"]["present"]]
        return {
            "family": name,
            "pack_ids": sorted(pack_ids),
            "missing_from_manifest": missing,
            "pack_count": len(members),
            "published_pack_count": sum(1 for m in members if m["published"]),
            "lesson_bound_pack_count": len(hosted),
            "lesson_binding_rate": round(len(hosted) / len(members), 4) if members else None,
            "lesson_unbound_pack_ids": sorted(m["pack_id"] for m in members if not m["lesson"]["hosted"]),
            "eligible_question_total": sum(elig),
            "question_total": sum(m["question_count"] or 0 for m in members),
            "answer_layer_pack_count": sum(1 for m in members if m["has_answer_layer"]),
            "answer_layer_missing_pack_ids": sorted(m["pack_id"] for m in members if not m["has_answer_layer"]),
            "exam_evidence_pack_count": sum(1 for m in members if m["has_exam_evidence"]),
            "exam_evidence_missing_pack_ids": sorted(m["pack_id"] for m in members if not m["has_exam_evidence"]),
            "compiled_practice_pack_count": len(pa),
            "practice_authority_surface_total": sum(m["practice_authority"]["surface_count"] or 0 for m in pa),
            "practice_authority_eligible_variant_total": sum(
                m["practice_authority"]["eligible_variant_id_count"] or 0 for m in pa
            ),
            "retest_variant_bank_pack_count": len(vb),
            "retest_variant_total": sum(m["variant_bank"]["variant_count"] or 0 for m in vb),
            "retest_variant_bank_pack_ids": sorted(m["pack_id"] for m in vb),
            "coarse_review_pack_ids": sorted(
                m["pack_id"] for m in members if m["alignment_status"] == "coarse_review"
            ),
            "taxonomy_leaf_coverage": _family_leaf_coverage(members, children, leaves),
        }

    families = {name: family_block(name, ids) for name, ids in FAMILY_MAP.items()}

    rot_name, rot_parts = ROTATING_FAMILY
    rotating_ids = sorted({pid for part in rot_parts for pid in FAMILY_MAP[part]})
    families[rot_name] = family_block(rot_name, rotating_ids)

    exc_name, exc_ids = EXCLUDED_FAMILY
    excluded = family_block(exc_name, exc_ids)

    assigned = {pid for ids in FAMILY_MAP.values() for pid in ids} | set(exc_ids)
    unassigned_ids = sorted(set(published_ids) - assigned)
    unassigned = family_block(UNASSIGNED_LABEL, unassigned_ids)

    # taxonomy 覆盖(published 包 → canonical leaf)
    published_refs = sorted({x for pid in published_ids for x in by_id[pid]["taxonomy_refs"]})
    all_refs = sorted({x for v in reg_packs.values()
                       for x in ([v.get("primary_taxonomy_ref")] + list(v.get("supporting_taxonomy_refs") or []))
                       if x})
    pub_cov: set[str] = set()
    for x in published_refs:
        pub_cov |= _subtree_leaves(x, children, leaves)
    all_cov: set[str] = set()
    for x in all_refs:
        all_cov |= _subtree_leaves(x, children, leaves)

    report = {
        "schema": SCHEMA_NAME,
        "generated_from": {
            "pack_manifest": str(MANIFEST_PATH.relative_to(REPO)),
            "pack_taxonomy_registry": str(TAXONOMY_REGISTRY_PATH.relative_to(REPO)),
            "compiled_taxonomy": str(COMPILED_TAXONOMY_PATH.relative_to(REPO)),
            "practice_authority_dir": str(PRACTICE_AUTHORITY_DIR.relative_to(REPO)),
            "card_host_dir": str(CARD_HOST_DIR.relative_to(REPO)),
        },
        "taxonomy": {
            "compiled_node_count": len(nodes),
            "compiled_leaf_count": len(leaves),
            "registry_snapshot_node_count": 2116,
            "registry_snapshot_leaf_count": 1976,
            "drift_vs_registry_snapshot": len(nodes) - 2116,
            "distinct_refs_all_slots": len(all_refs),
            "distinct_refs_published": len(published_refs),
            "unresolved_refs": sorted(
                {x for x in all_refs if x not in by_code}
            ),
            "leaves_covered_published": len(pub_cov),
            "leaf_coverage_rate_published": round(len(pub_cov) / len(leaves), 4),
            "leaves_covered_all_slots": len(all_cov),
            "leaf_coverage_rate_all_slots": round(len(all_cov) / len(leaves), 4),
        },
        "totals": {
            "manifest_pack_count": manifest.get("pack_count"),
            "published_pack_count": len(published_ids),
            "registry_slot_count": len(reg_packs),
            "empty_slot_count": len(empty_slots),
            "lesson_hosted_pack_count": sum(1 for p in packs if p["lesson"]["hosted"]),
            "compiled_practice_pack_count": sum(1 for p in packs if p["practice_status"] == "compiled"),
            "practice_unavailable_pack_ids": sorted(
                p["pack_id"] for p in packs if p["practice_status"] != "compiled"
            ),
            "eligible_question_total": sum(p["eligible_question_count"] or 0 for p in packs),
            "question_total": sum(p["question_count"] or 0 for p in packs),
            "retest_variant_bank_pack_count": sum(1 for p in packs if p["variant_bank"]["present"]),
            "retest_variant_total": sum(p["variant_bank"]["variant_count"] or 0 for p in packs),
            "answer_layer_missing_pack_ids": sorted(
                p["pack_id"] for p in packs if p["published"] and not p["has_answer_layer"]
            ),
            "exam_evidence_missing_pack_ids": sorted(
                p["pack_id"] for p in packs if p["published"] and not p["has_exam_evidence"]
            ),
            "lesson_unbound_published_pack_ids": sorted(
                p["pack_id"] for p in packs if p["published"] and not p["lesson"]["hosted"]
            ),
            "coarse_review_published_pack_ids": sorted(
                p["pack_id"] for p in packs if p["published"] and p["alignment_status"] == "coarse_review"
            ),
        },
        "families": families,
        "excluded_family": excluded,
        "unassigned": unassigned,
        "empty_slots": empty_slots,
        "packs": packs,
        "verdict": _verdict(families),
        "reconciliation": _reconcile(families, excluded, packs, reg_packs, empty_slots),
    }
    return report


def _family_leaf_coverage(members: list[dict], children: dict, leaves: set[str]) -> dict:
    refs = sorted({x for m in members for x in m["taxonomy_refs"]})
    cov: set[str] = set()
    for x in refs:
        cov |= _subtree_leaves(x, children, leaves)
    return {
        "distinct_taxonomy_refs": len(refs),
        "leaves_covered": len(cov),
        "leaf_coverage_rate_of_full_tree": round(len(cov) / len(leaves), 4) if leaves else None,
    }


def _verdict(families: dict) -> dict:
    """学习计划 §10 stop condition:五族 lesson 绑定率是否全部 ≥80%。"""
    scope = [n for n in FAMILY_MAP if n != "装饰"] + ["防水+装饰"]
    rows = []
    for name in scope:
        f = families[name]
        rows.append(
            {
                "family": name,
                "lesson_binding_rate": f["lesson_binding_rate"],
                "pass": (f["lesson_binding_rate"] or 0) >= LESSON_BINDING_THRESHOLD,
                "unbound": f["lesson_unbound_pack_ids"],
            }
        )
    return {
        "threshold": LESSON_BINDING_THRESHOLD,
        "scope": scope,
        "rows": rows,
        "all_pass": all(r["pass"] for r in rows),
    }


def _reconcile(families: dict, excluded: dict, packs: list[dict], reg_packs: dict, empty_slots: list) -> dict:
    exp = EXPECTED_AUDIT_2026_08_05
    published = [p for p in packs if p["published"]]
    checks = [
        ("published_pack_count", len(published), exp["published_pack_count"]),
        ("registry_slot_count", len(reg_packs), exp["registry_slot_count"]),
        ("empty_slot_count", len(empty_slots), exp["empty_slot_count"]),
        (
            "compiled_practice_pack_count",
            sum(1 for p in packs if p["practice_status"] == "compiled"),
            exp["compiled_practice_pack_count"],
        ),
        (
            "eligible_question_total",
            sum(p["eligible_question_count"] or 0 for p in packs),
            exp["eligible_question_total"],
        ),
        ("合同索赔_pack_count", excluded["pack_count"], exp["excluded_family_packs"]["合同索赔"]),
    ]
    for fam, want in exp["families"].items():
        checks.append((f"{fam}_pack_count", families[fam]["pack_count"], want["packs"]))
        checks.append((f"{fam}_eligible_questions", families[fam]["eligible_question_total"], want["eligible_questions"]))
    rows = [{"check": c, "actual": a, "expected": e, "match": a == e} for c, a, e in checks]
    return {"baseline": "2026-08-05 初盘(学习计划 §5 / 诊断计划 §6.4)", "rows": rows,
            "all_match": all(r["match"] for r in rows)}


# --------------------------------------------------------------------------------------
# 打印层
# --------------------------------------------------------------------------------------
def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def render_markdown(rep: dict) -> str:
    t = rep["totals"]
    tx = rep["taxonomy"]
    out: list[str] = []
    a = out.append

    a("### 总览")
    a("")
    a("| 指标 | 值 |")
    a("| --- | ---: |")
    a(f"| manifest 登记包数 | {t['manifest_pack_count']} |")
    a(f"| published 微课包 | {t['published_pack_count']} |")
    a(f"| 60 槽注册表槽位 | {t['registry_slot_count']} |")
    a(f"| 空槽(注册但未 published) | {t['empty_slot_count']} |")
    a(f"| 有讲解页(lesson.html 实证) | {t['lesson_hosted_pack_count']} |")
    a(f"| 编译练习包(practice compiled) | {t['compiled_practice_pack_count']} |")
    a(f"| eligible 练习题 | {t['eligible_question_total']} |")
    a(f"| 练习题登记总数(含未 eligible) | {t['question_total']} |")
    a(f"| 复测变体池包数(variant_bank) | {t['retest_variant_bank_pack_count']} |")
    a(f"| 复测变体总数 | {t['retest_variant_total']} |")
    a(f"| canonical taxonomy 节点/叶 | {tx['compiled_node_count']} / {tx['compiled_leaf_count']} |")
    a(f"| published 包锚定 taxonomy code 数 | {tx['distinct_refs_published']} |")
    a(f"| published 覆盖叶数(子树展开) | {tx['leaves_covered_published']} ({_pct(tx['leaf_coverage_rate_published'])}) |")
    a(f"| 60 槽全展开覆盖叶数 | {tx['leaves_covered_all_slots']} ({_pct(tx['leaf_coverage_rate_all_slots'])}) |")
    a("")

    a("### 主题族明细")
    a("")
    a("| 族 | 包数 | 讲解页 | lesson 绑定率 | eligible 题 | 题登记总数 | 作答层缺 | 考试实证缺 | 复测变体池包 | 复测变体数 | 编译 surface | 覆盖叶 |")
    a("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |")
    order = list(FAMILY_MAP) + [ROTATING_FAMILY[0]]
    for name in order:
        f = rep["families"][name]
        a(
            f"| {name} | {f['pack_count']} | {f['lesson_bound_pack_count']} | {_pct(f['lesson_binding_rate'])} | "
            f"{f['eligible_question_total']} | {f['question_total']} | "
            f"{','.join(f['answer_layer_missing_pack_ids']) or '—'} | "
            f"{','.join(f['exam_evidence_missing_pack_ids']) or '—'} | "
            f"{f['retest_variant_bank_pack_count']} | {f['retest_variant_total']} | "
            f"{f['practice_authority_surface_total']} | {f['taxonomy_leaf_coverage']['leaves_covered']} |"
        )
    for f in (rep["excluded_family"], rep["unassigned"]):
        a(
            f"| {f['family']}(参考) | {f['pack_count']} | {f['lesson_bound_pack_count']} | {_pct(f['lesson_binding_rate'])} | "
            f"{f['eligible_question_total']} | {f['question_total']} | "
            f"{','.join(f['answer_layer_missing_pack_ids']) or '—'} | "
            f"{','.join(f['exam_evidence_missing_pack_ids']) or '—'} | "
            f"{f['retest_variant_bank_pack_count']} | {f['retest_variant_total']} | "
            f"{f['practice_authority_surface_total']} | {f['taxonomy_leaf_coverage']['leaves_covered']} |"
        )
    a("")

    v = rep["verdict"]
    a(f"### 判定:五族 lesson 绑定率 ≥{int(v['threshold'] * 100)}%")
    a("")
    a("| 族 | 绑定率 | 判定 | 未绑定包 |")
    a("| --- | ---: | --- | --- |")
    for r in v["rows"]:
        a(f"| {r['family']} | {_pct(r['lesson_binding_rate'])} | {'PASS' if r['pass'] else 'FAIL'} | {','.join(r['unbound']) or '—'} |")
    a("")
    a(f"**结论:{'全部 PASS' if v['all_pass'] else '存在 FAIL'}** —— stop condition "
      f"{'不触发' if v['all_pass'] else '触发'}。")
    a("")

    r = rep["reconciliation"]
    a("### 与 2026-08-05 初盘对账")
    a("")
    a("| 校验项 | 实跑 | 初盘 | 一致 |")
    a("| --- | ---: | ---: | --- |")
    for row in r["rows"]:
        a(f"| {row['check']} | {row['actual']} | {row['expected']} | {'✅' if row['match'] else '❌'} |")
    a("")
    a(f"**{'全部一致' if r['all_match'] else '存在不一致'}**")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="供给覆盖地图 v0(只读盘点)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="报告 JSON 落盘路径")
    ap.add_argument("--stdout", action="store_true", help="只打印,不写盘")
    ap.add_argument("--json", action="store_true", help="打印完整 JSON")
    ap.add_argument("--check", action="store_true", help="报告 JSON 有漂移即非 0 退出(CI 用)")
    args = ap.parse_args(argv)

    rep = collect()
    payload = json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.json:
        print(payload, end="")
    else:
        print(render_markdown(rep))

    if args.check:
        if not args.out.is_file():
            print(f"\n[check] 报告缺失: {args.out}", file=sys.stderr)
            return 1
        if args.out.read_text(encoding="utf-8") != payload:
            print(f"\n[check] 报告漂移: {args.out}(请重跑本脚本刷新)", file=sys.stderr)
            return 1
        print(f"\n[check] ok: {args.out}")
        return 0

    if not args.stdout:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"\n[written] {args.out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
