#!/usr/bin/env python3
"""N01 双代号网络计划:关键线路/总时差 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 N01 真采分点, 产 _N01_compiled_source.json (照 S05/S06 结构).

⚠️ 源库标签污染防御 (C07/S05/S06 踩过) + N01/N02 题型分界:
  - leaf/chunk 名义 vs compiled_context 实际常错挂; 必须核 compiled_context 真实内容确属"网络计划判读"(关键线路/总时差/时间参数判读),
    名实不符的绕开并留痕.
  - N01(关键线路识别+时差计算+判读) vs N02(工期优化/费用优化/赶工压缩) 是两个考点, 别混:
    凡 chunk 主题是"优化/赶工/压缩成本"的 → 归 N02, 本 pack 绕开.
  - chunk 名"时间参数"(052_0075)实为【流水施工】流水节拍/步距(t/K), 非网络计划六时标注/时差 → 名实不符, 绕开.
  - chunk"工期优化"(056_0085)是 N02 腹地, 但其中含一张【关键工作与关键线路判定】卡是 N01 本体判据 → 只取该卡(tc_filter), 优化卡绕开.

  网络计划核心数值(总时差=最迟开始-最早开始、自由时差、六时标注、虚工作)在 RichLeaf 编译库覆盖弱
  (SOP 已记: "计算型考点(网络/索赔)编译库覆盖弱"), 故 N01 的 R5 采分眼数值锚主要落在【真题取证】(_N01_exam_evidence.json),
  本编译源只提供"判据/程序/术语"教材锚, 数值判读锚以真题为准. 此为诚实现状, 非缺陷掩盖.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_N01_compiled_source.json")

KEYWORDS = ("网络计划|双代号|单代号|关键线路|关键工作|总时差|自由时差|时间参数|最早开始|最早完成|最迟开始|最迟完成|"
            "工期|计算工期|计划工期|虚工作|虚箭线|节点|箭线|时标网络|六时标注")

# 经人工核真的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该chunk全部 TC + rules(EP判读题保留) ; "tc_filter"=只取 title/content 含网络计划判读关键词的 TC/rule
CHUNK_POLICY = {
    "1A433000_055_0084": ("full",      "本体·网络计划技术应用程序(GB/T 13400.3,7阶段18步骤:准备/绘图/计算/编制/确定/实施控制/收尾)"),
    "1A433000_056_0085": ("tc_filter", "本体判据·关键工作=总时差最小;关键线路=全部关键工作组成、工期=计算工期 — 该chunk主题为'工期优化'(N02腹地),只取关键线路判定卡,优化/资源/费用卡绕开归N02"),
    "1A433000_061_0091": ("full",      "本体外延·进度监测:观测关键工作进度与关键线路变化、检查非关键工作、核查逻辑关系"),
    "1A433000_061_0092": ("full",      "本体外延·进度调整:关键工作调整(重点)/逻辑关系调整/非关键工作调整/资源调整/重新编制"),
    "LEC_1A433000_P0018_001": ("full",  "本体·双代号网络图绘制规则(母线法):相对唯一性/节点共用/多看一眼;紧前紧后逻辑;虚工作定位"),
}

# tc_filter 模式下, TC/rule 标题或内容须含这些词才算真"网络计划判读" (排除流水/优化/费用)
TC_N01 = re.compile(r"关键线路|关键工作|总时差|自由时差|时间参数|计算工期|计划工期|最早|最迟|双代号|网络图|虚工作|节点|箭线")
# 优化/赶工/费用 = N02, 在 tc_filter 下额外排除
N02_BLOCK = re.compile(r"优化|赶工|压缩|费用|资源.*目标|成本")

# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A433000_052_0075": "chunk名'时间参数'实为【流水施工】流水节拍t/流水步距K/工期T定义, 非网络计划六时标注/时差, 名实不符绕开",
    "1A433000_055_0082": "图8.1-1【流水施工】进度计划(横道图), 非双代号网络计划, 绕开",
    "1A433000_056_0085#opt": "同chunk的'网络计划优化三大类'/'工期优化选择原则'卡 = N02(工期优化)腹地, 本pack只取关键线路判定卡",
    "1A433000_057_0086": "费用优化 = N02 腹地, 绕开",
    "1A433000_057_0087": "图8.1-3'赶工决策逻辑'(优先压缩赶工费率最低关键工作) = N02(工期优化)腹地, 绕开",
    "1A433000_060_0090": "单位工程进度计划编制八步法/三阶段控制/监测方法 = 进度计划编制通识, 非N01关键线路/时差判读采分眼, 绕开",
    "1A433000_059_0089": "单位工程进度计划内容/分类 = 进度计划编制通识, 非N01判读采分眼, 绕开",
    "1A432000_049_0070/048_0068": "工期索赔计算/索赔管理 = K01(索赔)腹地(关键线路仅作索赔前置), 非N01本体, 绕开",
    "keyword_only_cross_chapter": "1A411011抗震/装配式、1A413030模板/钢结构/幕墙、1A422法规、1A436脚手架、1A437/1A438等仅泛词(节点/网络/工期/箭线)命中, 主题非网络计划判读, 全部绕开",
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
        captured_quotes = set()  # 去重: rules 多为 TC content 的凝练副本, 不重复收
        # teaching_cards -> kc:<chunk>:<idx>
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if mode == "tc_filter" and (not TC_N01.search(blob) or N02_BLOCK.search(blob)):
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
        # rules -> 也作采分锚 (rules 是凝练判据, N01 关键线路判定就在 rules 里)
        # rules item 形态: 纯字符串, 或 dict{id,description}, 或 JSON字符串化的 dict
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
            if rt.strip() in captured_quotes:  # 已被 TC 收录的凝练副本, 跳过
                continue
            if mode == "tc_filter" and (not TC_N01.search(rt) or N02_BLOCK.search(rt)):
                continue
            sps.append({
                "statement": rt,
                "required_terms": [],
                "point_id": f"kc:{ch}:{idx}",
                "quote": rt,
                "chunk": ch,
            })
            idx += 1
        # exam_patterns -> ca:<chunk> (full 模式取; tc_filter 不取避免引入优化EP)
        if mode == "full":
            for ep in cc.get("exam_patterns", []):
                e = pj(ep)
                if not e:
                    continue
                desc = e.get("description", "") or ""
                if N02_BLOCK.search(desc):
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
        "考点": "N01 双代号网络计划关键线路/总时差",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "编译库覆盖说明": "网络计划核心数值(总时差公式/自由时差/六时标注/虚工作)在RichLeaf编译库覆盖弱;本源料提供判据/程序/术语教材锚,数值判读采分锚以_N01_exam_evidence.json真题为准(诚实标注,非缺陷掩盖)",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"N01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['source_ref'].get('chunk_id')}] {u['note'][:46]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
