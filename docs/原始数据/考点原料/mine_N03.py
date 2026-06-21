#!/usr/bin/env python3
"""N03 流水施工参数与工期 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 N03 真采分点, 产 _N03_compiled_source.json (照 N01/S06 结构).

⚠️ 源库标签污染防御 (C07/S05/S06/N01 踩过) + N01/N02/N03 题型严格分界:
  - leaf/chunk 名义 vs compiled_context 实际常错挂; 必须核 compiled_context 真实内容确属"流水施工参数/工期计算"
    (节拍 t / 步距 K / 工期 T / 等节奏-异节奏-无节奏 / 大差法累加数列错位相减), 名实不符的绕开并留痕.
  - **N03(流水施工参数:节拍/步距/工期计算) vs N01(网络计划关键线路/总时差) vs N02(网络计划工期优化)** 是三个考点,同章不同考,严禁混:
    凡 chunk 主题是"双代号/关键线路/总时差/自由时差/六时标注/虚工作" → 归 N01, 本 pack 绕开.
    凡 chunk 主题是"网络计划优化/赶工/压缩/费用优化" → 归 N02, 本 pack 绕开.
  - ✅ **角色反转留痕**: chunk 1A433000_052_0075 名"时间参数", N01 把它当【流水施工】噪声绕开;
    对 N03 它恰是【本体核心】(流水节拍 t / 流水步距 K / 工期 T 定义). 名实在 N03 语境下相符, 收为本体.
  - teaching_card 字段可能为 JSON 字符串化, 用 pj() 解析后取 title/content.

  流水施工在 RichLeaf 编译库覆盖【厚实】(与 N01/N02 计算型覆盖弱不同): 节拍/步距/工期定义 + 三大组织方式 +
  施工段划分原则 + 无/等/异节奏特点 + 大差法(累加数列错位相减)计算步骤 + 横道图, 教材锚充足.
  具体【数值算例】(某工程节拍2/2/6/4/4 → 步距 → 总工期) 的判读锚以真题为准 (_N03_exam_evidence.json),
  此为诚实分工(教材给判据/术语/算法步骤, 真题给数值算例核真), 非缺陷掩盖.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_N03_compiled_source.json")

KEYWORDS = ("流水施工|流水节拍|流水步距|流水段|施工段|施工过程|流水强度|工作面|等节奏流水|异节奏流水|无节奏流水|"
            "等步距异节奏|加快成倍节拍|累加数列错位相减|节拍|步距|流水工期|分别流水|全等节拍|间歇时间|平行搭接")

# 经人工核真的 chunk 白名单 (逐 chunk 已直读 compiled_context 确属流水施工参数/工期本体).
# mode: "full"=取该chunk全部 TC + rules + EP ; "tc_filter"=只取流水施工判读关键词命中的 TC/rule (排除网络计划/优化)
CHUNK_POLICY = {
    "1A433000_051_0074": ("full",      "本体·工艺参数:流水施工三大组织方式(依次/平行/流水)+施工段划分原则(劳动量差异≤15%/工作面/界限结构缝吻合/段数合理/分段分层)"),
    "1A433000_052_0075": ("full",      "本体核心·时间参数:流水节拍t(专业队在一施工段的施工时间)/流水步距K(相邻专业队进入流水的时间间隔)/工期T(首队投入到末队退出)定义 — N01绕为噪声,N03收为本体"),
    "1A433000_052_0076": ("full",      "本体·无节奏流水施工特点(节拍不全相等/步距不尽相等/专业队数=施工过程数/连续作业但过程间可能有间隔)"),
    "1A433000_052_0077": ("full",      "本体·等节奏流水施工特点(各段节拍均相等/步距=节拍 K=t/专业队数=过程数/连续无空闲)"),
    "1A433000_053_0078": ("full",      "本体·异节奏流水施工分类(等步距/异步距)+等步距异节奏特点(节拍成倍数/步距=最大公约数/专业队数>过程数/连续无空闲)"),
    "1A433000_054_0081": ("full",      "本体核心·异节奏流水施工大差法计算(累加数列→错位相减取最大值=流水步距;总工期=Σ步距+末工序节拍之和+技术间歇)"),
    "1A433000_055_0083": ("full",      "本体·等步距异节奏流水施工进度计划(节拍不等时增专业队按相同步距推进)"),
    "1A433000_055_0082": ("tc_filter", "本体·流水施工进度计划横道图(横道图表达各施工过程时间安排+合理搭接) — 该chunk EP混入'关键线路'(N01措辞),只取流水施工横道图TC/rule,关键线路EP绕开归N01"),
}

# tc_filter 模式下, TC/rule 标题或内容须含流水施工词才收 (排除网络计划关键线路/优化)
TC_N03 = re.compile(r"流水|节拍|步距|施工段|施工过程|横道图|搭接|专业队|工作面|间歇")
# 网络计划/优化 = N01/N02, tc_filter 下额外排除
N0102_BLOCK = re.compile(r"关键线路|总时差|自由时差|双代号|虚工作|六时标注|网络计划|优化|赶工|压缩")

# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A433000_055_0084": "网络计划技术应用程序(GB/T 13400.3 7阶段18步骤) = N01腹地(网络计划程序), 绕开",
    "1A433000_056_0085": "网络计划编制七阶段/关键工作与关键线路判定/网络计划优化三大类/工期优化选择原则 = N01(关键线路判定)+N02(优化)腹地, 绕开",
    "1A433000_057_0086": "费用优化核心原则 = N02(工期优化)腹地, 绕开",
    "1A433000_057_0087": "赶工决策逻辑(优先压缩赶工费率最低关键工作) = N02腹地, 绕开",
    "1A433000_060_0090": "单位工程进度计划编制八步法/三阶段控制 = 进度计划编制通识(含网络/横道泛词), 非N03流水参数/工期计算采分眼, 绕开",
    "1A433000_059_0089": "单位工程进度计划内容/分类(总进度/单位工程/分部分项) = 进度计划编制通识, 非N03判读采分眼, 绕开",
    "1A433000_061_0091/0092": "网络计划进度监测/调整(观测关键线路/关键工作调整) = N01外延, 非流水施工, 绕开",
    "keyword_only_cross_chapter": "1A411/1A413/1A422/1A436/1A437等仅泛词(施工段/工作面/搭接/间歇/节拍)命中, 主题非流水施工参数(屋面/法规/脚手架等), 全部绕开",
}


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
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
        idx = 0
        captured_quotes = set()  # 去重: rules 多为 TC content 的凝练副本
        # teaching_cards -> kc:<chunk>:<idx>
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if mode == "tc_filter" and (not TC_N03.search(blob) or N0102_BLOCK.search(blob)):
                continue
            content = t.get("content", "") or ""
            sps.append({
                "statement": (t.get("title", "") + "：" + content).strip("："),
                "required_terms": t.get("source_refs", []),
                "point_id": f"kc:{ch}:{idx}",
                "quote": content,
                "chunk": ch,
            })
            captured_quotes.add(content.strip())
            idx += 1
        # rules -> 凝练判据采分锚
        for rule in cc.get("rules", []):
            ro = pj(rule)
            if isinstance(ro, dict):
                rt = ro.get("description", "") or ro.get("statement", "")
            elif isinstance(rule, str):
                rt = rule
            else:
                rt = ""
            if not rt:
                continue
            if rt.strip() in captured_quotes:
                continue
            if mode == "tc_filter" and (not TC_N03.search(rt) or N0102_BLOCK.search(rt)):
                continue
            sps.append({
                "statement": rt,
                "required_terms": [],
                "point_id": f"kc:{ch}:{idx}",
                "quote": rt,
                "chunk": ch,
            })
            idx += 1
        # exam_patterns -> ca:<chunk> (full 模式取; tc_filter 不取避免引入关键线路EP)
        if mode == "full":
            for ep in cc.get("exam_patterns", []):
                e = pj(ep)
                if not e:
                    continue
                desc = e.get("description", "") or ""
                if N0102_BLOCK.search(desc):
                    continue
                sps.append({
                    "statement": desc,
                    "required_terms": e.get("grading_keywords", []),
                    "point_id": f"ca:{ch}",
                    "quote": desc,
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
        "考点": "N03 流水施工参数与工期",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "编译库覆盖说明": "流水施工在RichLeaf编译库覆盖厚实(节拍/步距/工期定义+三大组织方式+施工段划分+无/等/异节奏特点+大差法累加数列错位相减计算步骤+横道图);具体数值算例(某工程节拍序列→步距→总工期)的判读锚以_N03_exam_evidence.json真题为准(诚实分工:教材给判据/术语/算法,真题给数值算例核真)",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"N03 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['source_ref'].get('chunk_id')}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
