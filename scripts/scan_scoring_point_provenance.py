#!/usr/bin/env python3
"""闸-1 MVP — 采分点原子数值溯源扫描器（编译期，离线，确定性）。

目标:对已签发候选采分点库 rich_leaf_context_bundle，逐条抽 rules 描述里的**量化硬事实**
（带单位/百分比/万的数值阈值，即"4000万"类），归一化后核验它是否字面出现在该规则引用的
教材跨度(content_markdown + knowledge_cards)。无源 → 候选编造。

边界(诚实):
  * 只治 (a)错值 / (b)脱书值 的**数值**型;不治 (c)幽灵 criterion(那是闸-2,需结构镜像)、
    也不治纯术语/条号(后续)。
  * 这是**编译期溯源核验**,不是判分;不与"确定性匹配<LLM理解"(判分层负结果)冲突。
  * 归一化保精度:同一(值,单位)在规则与源各自抽取后比对,不做脆弱的整串匹配。
"""
from __future__ import annotations
import json, re, glob, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json"
TEXTBOOK_GLOB = str(ROOT / "docs/原始数据/2026_副本/2026教材/第二次加强/FINAL_CLEANED_BOOK2026-*_fixed.json")

# ---- 量化硬事实抽取 + 归一化 ----------------------------------------------------
# 只抓"阈值型"数值:数字(可带万/亿乘子)+ 紧跟单位(%, mm, m, m², MPa, 万元, 度, 年, 道...)。
# 纯序号/年份/条号(GB 50352—2019)不抓——它们不是阈值,且条号另立 lane。
_MULT = {"万": 10000, "亿": 100000000}
_UNIT_CANON = {
    "%": "%", "％": "%", "‰": "‰",
    "mm": "mm", "cm": "cm", "m²": "m2", "m2": "m2", "平方米": "m2", "㎡": "m2",
    "m": "m", "米": "m", "MPa": "MPa", "mpa": "MPa",
    "万元": "万元", "元": "元", "年": "年", "度": "度", "道": "道", "kn": "kN", "kN": "kN",
}
# 数字（含小数、范围用~/-）+ 可选万/亿 + 单位
_NUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(万|亿)?\s*(%|％|‰|mm|cm|m²|m2|㎡|平方米|MPa|mpa|kN|kn|万元|元|年|度|道|m|米)",
)

def quant_facts(text: str) -> set[tuple]:
    """从文本抽 (归一化数值, 归一化单位) 集合。范围'2~3%'拆成两端各一。"""
    out: set[tuple] = set()
    if not text:
        return out
    for m in _NUM_RE.finditer(text):
        raw_num, mult, unit = m.group(1), m.group(2), m.group(3)
        try:
            val = float(raw_num)
        except ValueError:
            continue
        if mult:
            val *= _MULT[mult]
        u = _UNIT_CANON.get(unit, unit)
        # 归一化数值:整数化掉 .0
        v = int(val) if val == int(val) else round(val, 4)
        out.add((v, u))
    return out

# ---- 教材源索引 ----------------------------------------------------------------
def load_textbook_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for f in glob.glob(TEXTBOOK_GLOB):
        d = json.load(open(f, encoding="utf-8"))
        for b in d.get("content_blocks", []):
            cid = b.get("chunk_id") or b.get("id")
            if not cid:
                continue
            parts = [b.get("content_markdown") or ""]
            for kc in (b.get("knowledge_cards") or []):
                if isinstance(kc, dict):
                    parts.append(str(kc.get("card_content") or ""))
                    parts.append(str(kc.get("card_title") or ""))
            idx[cid] = "\n".join(parts)
    return idx

# ---- 规则解析 ------------------------------------------------------------------
def parse_rules(rules_field) -> list[dict]:
    out = []
    for r in (rules_field or []):
        if isinstance(r, str):
            try: r = json.loads(r)
            except Exception: r = {"description": r, "source_refs": []}
        if isinstance(r, dict):
            out.append(r)
    return out

# ---- 主扫描 --------------------------------------------------------------------
def scan(records, tb_idx):
    findings = []          # 无源量化硬事实
    stats = Counter()
    for rec in records:
        leaf = rec.get("leaf_name_path") or rec.get("leaf_id") or "?"
        rec_chunk = (rec.get("source_ref") or {}).get("chunk_id")
        for rule in parse_rules(rec["compiled_context"].get("rules")):
            desc = str(rule.get("description") or "")
            facts = quant_facts(desc)
            if not facts:
                stats["rules_no_quant"] += 1
                continue
            stats["rules_with_quant"] += 1
            refs = list(rule.get("source_refs") or [])
            if rec_chunk and rec_chunk not in refs:
                refs.append(rec_chunk)
            src_text = "\n".join(tb_idx.get(c, "") for c in refs)
            src_facts = quant_facts(src_text)
            src_resolved = any(tb_idx.get(c) for c in refs)
            unsourced = facts - src_facts
            if unsourced:
                stats["rules_with_unsourced"] += 1
                findings.append({
                    "leaf": leaf, "rule_id": rule.get("id"),
                    "desc": desc[:160],
                    "unsourced_facts": sorted(f"{v}{u}" for v, u in unsourced),
                    "rule_facts": sorted(f"{v}{u}" for v, u in facts),
                    "refs": refs, "src_resolved": src_resolved,
                })
            else:
                stats["rules_all_sourced"] += 1
    return findings, stats

# ---- 自标定 --------------------------------------------------------------------
def calibrate(tb_idx):
    """合成 2 条:已知编造(4000万,源里无)必抓;已知正确(找坡3%,若源里有)必放。"""
    # 找一个真实含"3%"或"找坡"的教材 chunk 作正例源
    pos_chunk = next((c for c, t in tb_idx.items() if "3%" in t and "找坡" in t), None)
    fake_chunk = next(iter(tb_idx))  # 任意源，里面无 4000万
    recs = [
        {"leaf_name_path": "CALIB-编造", "source_ref": {"chunk_id": fake_chunk},
         "compiled_context": {"rules": [json.dumps(
             {"id": "CF", "description": "二级资质企业可承接合同额4000万元以下的工程。",
              "source_refs": [fake_chunk]}, ensure_ascii=False)]}},
    ]
    if pos_chunk:
        recs.append({"leaf_name_path": "CALIB-正确", "source_ref": {"chunk_id": pos_chunk},
            "compiled_context": {"rules": [json.dumps(
                {"id": "CT", "description": "结构找坡坡度不小于3%。", "source_refs": [pos_chunk]},
                ensure_ascii=False)]}})
    f, _ = scan(recs, tb_idx)
    flagged = {x["leaf"] for x in f}
    fab_caught = "CALIB-编造" in flagged
    pos_passed = (pos_chunk is not None) and ("CALIB-正确" not in flagged)
    return fab_caught, pos_passed, pos_chunk is not None

def main():
    tb_idx = load_textbook_index()
    print(f"教材源 chunk 数: {len(tb_idx)}")
    fab_caught, pos_passed, had_pos = calibrate(tb_idx)
    print(f"=== 自标定: 编造必抓={fab_caught} | 正确必放={pos_passed} (正例源存在={had_pos}) ===")
    if not fab_caught or (had_pos and not pos_passed):
        print("!! 标定未过,扫描结果不可信,中止"); sys.exit(1)

    bundle = json.load(open(BUNDLE, encoding="utf-8"))
    recs = bundle["records"]
    findings, stats = scan(recs, tb_idx)
    print(f"\n=== 库规模 ===")
    print(f"records={len(recs)} | manifest.published={bundle['manifest'].get('published')} "
          f"official_score_allowed={bundle['manifest'].get('official_score_allowed')}")
    print(f"\n=== 规则量化覆盖 ===")
    for k in ("rules_with_quant", "rules_no_quant", "rules_all_sourced", "rules_with_unsourced"):
        print(f"  {k} = {stats[k]}")
    wq = stats["rules_with_quant"] or 1
    print(f"  无源率(含量化的规则中) = {stats['rules_with_unsourced']}/{wq} = {stats['rules_with_unsourced']/wq:.1%}")

    # 分桶:源能解析 vs 源缺失(后者是 provenance 断链,另一类病)
    resolved = [f for f in findings if f["src_resolved"]]
    broken = [f for f in findings if not f["src_resolved"]]
    print(f"\n=== 无源发现分桶 ===")
    print(f"  源跨度可解析但数值对不上(真·候选编造) = {len(resolved)}")
    print(f"  源跨度解析不到(provenance 断链) = {len(broken)}")

    print(f"\n=== 真·候选编造 样例(前15,源能解析但数值不在源里) ===")
    for f in resolved[:15]:
        print(f"  [{f['leaf'][:34]}] rule {f['rule_id']}: 无源数值={f['unsourced_facts']}")
        print(f"     desc: {f['desc']}")

    out = ROOT / "artifacts/scoring_point_provenance_scan_2026-06-24.json"
    out.write_text(json.dumps({
        "calibration": {"fab_caught": fab_caught, "pos_passed": pos_passed},
        "library": {"records": len(recs), "published": bundle["manifest"].get("published"),
                    "official_score_allowed": bundle["manifest"].get("official_score_allowed")},
        "stats": dict(stats),
        "unsourced_resolved": resolved, "unsourced_broken_provenance": broken,
    }, ensure_ascii=False, indent=2))
    print(f"\n报告 JSON: {out}")

if __name__ == "__main__":
    main()
