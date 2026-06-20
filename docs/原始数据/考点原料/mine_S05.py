#!/usr/bin/env python3
"""S05 临时用电:三级配电两级保护 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 S05 真采分点, 产 _S05_compiled_source.json (照 S06 结构).

⚠️ 源库标签污染防御 (C07/S06 踩过):
  - leaf 名义 vs compiled_context 实际常错挂; 必须按 source_ref.chunk_id 去重 + 核 compiled_context 真实内容确属临时用电.
  - 经人工核真 13 个 content-命中 chunk: 仅保留真临电/三级配电/两级保护内容的 chunk;
    名实不符(住宅装修/仓库消防/智慧工地)的污染 chunk 绕开;
    部分 chunk(107_0174)EP是模板支架但有"施工用电检查项目"TC -> 只取该TC不取EP.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_S05_compiled_source.json")

KEYWORDS = "临时用电|临电|施工用电|三级配电|两级保护|总配电箱|分配电箱|开关箱|TN-S|保护接零|接零保护|漏电保护|漏电保护器|PE线|重复接地|工作接地|一机一闸|一闸一漏|配电室|外电防护|安全距离|电缆敷设|照明"

# 经人工核真的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该chunk全部 TC+EP; "tc_only"=只取teaching_cards(EP污染); "tc_filter"=只取title含临电关键词的TC
CHUNK_POLICY = {
    "1A431011_015_0016": ("full",   "本体·临时用电安全技术(三大系统/送停电顺序/安全电压)"),
    "1A431011_014_0015": ("full",   "本体·临时用电管理(电缆埋地/三级配电装置/一机一闸/动力照明分设/电工持证)"),
    "1A436000_107_0174": ("tc_filter", "本体·施工用电检查评定项目(外电防护/接地接零/配电线路/配电箱开关箱) — 该chunk的EP是模板支架,绕开,只取施工用电TC"),
    "1A436000_007_0010": ("tc_filter", "本体外延·临时用电重大隐患(特殊环境未用安全电压照明) — 该chunk主题是重大隐患综合表,只取临时用电TC"),
    "1A436000_130_0209": ("full",   "外延·触电事故预防/特殊场所照明安全电压(手持灯具≤36V/双绕组隔离变压器)"),
    "1A436000_126_0200": ("tc_filter", "邻接·电动冲击夯须漏电保护(漏电保护是临电外延) — 只取含漏电保护TC"),
}
# TC 标题/内容须含这些词才算真临电 (用于 tc_filter)
TC_S05 = re.compile(r"施工用电|临时用电|配电|开关箱|外电防护|接地|接零|漏电|安全电压|36V|24V|12V|电缆|配电箱")

# 明确绕开的污染 chunk (留痕)
SKIPPED = {
    "1A411011_021_0039": "住宅装修禁令 — 临时用电仅旁系关键词命中,主题为室内装修,绕开",
    "1A437000_147_0236": "仓库与堆料场消防 — 开关箱距堆垛≥1.5m属消防间距,非临电采分眼,绕开",
    "1A437000_151_0297": "智慧工地/智能电表 — 信息技术,非临电采分眼,绕开",
    "1A436000_105_0172": "安全检查'测'方法含漏电保护器 — 通用检查方法,非临电采分眼,绕开",
    "1A436000_111_0183": "灌注桩施工安全 — 桩工腹地,漏电保护仅其中一项,绕开",
    "1A436000_111_0184": "人工挖孔桩施工安全 — 桩工腹地,照明≤12V仅其中一项,绕开",
    "1A438000_155_0252": "机械验收七项 — 机械资源管理,接地接零仅其中一项,绕开",
}


def pj(x):
    try:
        return json.loads(x) if isinstance(x, str) else x
    except Exception:
        return None


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
    # 按 chunk_id 去重: 多 leaf 共享同一 chunk, 取第一条 record 的 compiled_context
    seen = {}
    for r in recs:
        ch = r["source_ref"].get("chunk_id", "")
        if ch in CHUNK_POLICY and ch not in seen:
            seen[ch] = r

    units = []
    total_sp = 0
    for ch, (mode, note) in CHUNK_POLICY.items():
        r = seen.get(ch)
        if not r:
            print(f"⚠ chunk {ch} 未在bundle找到, 跳过")
            continue
        cc = r["compiled_context"]
        sps = []
        # teaching_cards -> kc:<chunk>:<idx>
        idx = 0
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") + t.get("content", ""))
            if mode == "tc_filter" and not TC_S05.search(blob):
                continue
            sps.append({
                "statement": (t.get("title", "") + "：" + t.get("content", "")).strip("："),
                "required_terms": t.get("source_refs", []),
                "point_id": f"kc:{ch}:{idx}",
                "quote": t.get("content", ""),
                "chunk": ch,
            })
            idx += 1
        # exam_patterns -> ca:<chunk>  (只在 full 模式取; tc_filter 模式 EP 污染绕开)
        if mode == "full":
            for ep in cc.get("exam_patterns", []):
                e = pj(ep)
                if not e:
                    continue
                sps.append({
                    "statement": e.get("description", ""),
                    "required_terms": e.get("grading_keywords", []),
                    "point_id": f"ca:{ch}",
                    "quote": e.get("description", ""),
                    "chunk": ch,
                })
        if sps:
            units.append({
                "leaf_id": r.get("leaf_id"),
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "临时用电三级配电两级保护",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"S05 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染 chunk: {len(SKIPPED)} 个")
    for u in units:
        print(f"  [{u['leaf_id']}] {u['note'][:40]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
