#!/usr/bin/env python3
"""G01 基坑开挖与降水方法选择 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 G01 真采分点, 产 _G01_compiled_source.json (照 D11/S07/C06 结构).

考点身份 (注册表 slot 25, **direct**):
  primary    1A413037 (任务给定·降水方法选择腹地)
  supporting 1A413036 / 1A413000-B081 (降水施工技术) / 1A413000-B071 (深基坑的土方开挖)
  taxonomy sha 26dbb542b31601d6b3255d53463d0007c0c7eaea5a24ad9c338b3742baa976c8

  ⚠️ 注册表 code 与编译库 leaf_id 命名差异 (诚实标注): 注册表 primary=1A413037 / supporting=1A413036
  是 canonical compiled taxonomy 的 node_code(降水/降水方法腹地)；编译库 rich_leaf bundle 里 G01 弹药本体
  集中在 1A413000_082~085 几个 chunk 的 leaf(1A413000-B011 降水方案选择 / 1A413000-B081 降水施工技术 /
  1A413000-B075 真空降水井管+截水+回灌 / 1A413000-B071 深基坑土方开挖)，作弹药内部引用与 canonical code 并存。
  status=direct/coarse_review 由 §注册表对账块按 compiled taxonomy resolve 结果裁决(resolve 不到老实标 coarse_review)。

⚠️ 与 B02(基坑支护选型/监测) 严格分界 (任务硬约束):
  - G01 = 开挖方法(分层/放坡/盆式/逆作/预留土层/严禁超挖) + 降水方法选择(集水明排/轻型井点/喷射井点/管井/
    真空降水/截水/回灌/降水方案三原则)。
  - B02 = 支护选型(土钉墙/排桩/地下连续墙/锚杆/钢支撑) + 基坑监测/危险报警。
  - 1A413000_076~082 的支护 leaf(B037 基坑支护工程/B068 浅基坑支护/B070 深基坑支护/B073 灌注桩排桩/B029 地下
    连续墙/B023 土钉墙/B080 锚杆)、1A413000_081_0152(基坑监测 B038)、1A413000_082_0153(基坑危险报警 B033)
    全部归 B02 territory → 绕开留痕。
  - 1A422000_033_0055 是混卡 chunk(锚杆/钢支撑/土钉墙=B02 + 地下水控制方法=G01 降水本体)：仅卡级保留
    "地下水控制方法"(管井/真空井点/喷射井点间距/水位坑底0.5m)作 🔵 法规外延, 锚杆/支撑/土钉墙卡剔除归 B02。

⚠️ 源库标签污染 + 名实不符防御 (前 9 个新产 B02/N01/C01/C06/J01/S07/D11/D12/D13 都踩过):
  - 必须核 compiled_context 真实内容确属"基坑开挖方法/降水方法选择"本体, 名实不符卡(同 chunk 的支护/锚杆/测量
    /验槽卡)绕开并留痕。
  - 与 地基处理(1A413031 复合地基/夯实/换填)、测量(1A413000-B0xx 水准仪/全站仪)、验槽(1A413000-B030~084
    天然/桩基验槽)、防水混凝土(1A422000_028 防水混凝土)、岩土物理指标(B021)严格区分。
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_G01_compiled_source.json")

KEYWORDS = ("土方开挖|基坑开挖|深基坑|降水|井点降水|轻型井点|喷射井点|管井|管井降水|集水明排|明排水|放坡|放坡开挖|"
            "分层开挖|开挖顺序|降水方法|土方|边坡稳定|坑底|无支护|有支护|地下水|截水|回灌|流砂|管涌")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型 + 每卡级过滤.
# mode: "full"=取该 chunk 全部 G01 本体 TC/rule/EP ; "ext"=邻接/法规外延(标🔵外延).
# card_keep: 只保留 title/content 命中此正则的卡(剔同 chunk 名实不符/跨考点卡, 如混卡 chunk 的锚杆/支撑卡)
CHUNK_POLICY = {
    # ── 降水方法主轴 (G01 核心) ──
    ("1A413000_082_0154", "1A413000-B011"): (
        "full", "本体·降水方案选择三原则(主锚): 深度≤3m且软土→集水明排; 深度>3m→井点降水; 危及周边→截水/回灌; 承压水→验算突涌封底减压 — G01 降水方法选择最核心判分眼",
        re.compile(r"降水方案|集水明排|井点降水|截水|回灌|承压水|突涌")),
    ("1A413000_082_0155", "1A413000-B081"): (
        "full", "本体·降水施工技术(supporting 注册表辅锚): 轻型井点(渗透系数1e-7~2e-4/降水深度≤6m/多级6~10m) + 喷射井点(降水深度8~20m/碎石土黄土) 技术参数与适用",
        re.compile(r"井点|渗透系数|降水深度|管径|间距|排距|碎石土|黄土")),
    ("1A413000_083_0156", "1A413000-B075"): (
        "full", "本体·真空降水井管+截水帷幕+井点回灌: 真空降水井管(渗透系数>1e-6/降水深度>6m/管径≥200mm/水平间距≤25m) + 截水帷幕(渗透系数<1e-6/插入不透水层) + 回灌(维持地下水位防沉降)",
        re.compile(r"真空降水|截水|回灌|渗透系数|降水深度|不透水层|沉降")),
    # ── 开挖方法主轴 (G01 核心) ──
    ("1A413000_084_0157", "1A413000-B071"): (
        "full", "本体·深基坑土方开挖(supporting 注册表辅锚): 分层厚度≤3m + 预留土层(人工150~300mm/机械200~300mm) + 地下水位以下挖土水位降至坑底以下500mm且持续到基础完成 + 逆作法盆式开挖(先中部再分块对称限时)",
        re.compile(r"分层厚度|预留|土层|地下水位|坑底|逆作|盆式|开挖|挖土")),
    ("1A422000_028_0048", "1A422000-B036"): (
        "full", "本体·基坑开挖与回填法规: 基坑土方开挖必须与设计工况一致严禁超挖; 软土基坑高差≤1m; 土方开挖不得损坏支护结构/降水设施/工程桩 (防水混凝土卡名实不符已剔)",
        re.compile(r"超挖|设计工况|软土|高差|降水设施|工程桩|支护结构")),
    # ── 邻接/法规外延 (标🔵外延) ──
    ("1A422000_033_0055", "1A422000-B028"): (
        "ext", "🔵外延·法规·地下水控制方法(混卡 chunk 仅保留此卡): 基坑降水可用管井/真空井点/喷射井点; 水位应低于坑底0.5m; 真空井点间距0.8~2.0m; 喷射井点间距1.5~3.0m; 深度>6m多级井点高差4~5m (锚杆/钢支撑/土钉墙卡=B02已剔)",
        re.compile(r"地下水控制方法|管井|真空井点|喷射井点|水位.*坑底|降水可")),
    ("1A413000_075_0143", "1A413000-B042"): (
        "ext", "🔵外延·岩土按开挖难易分八类(放坡/开挖方法选择背景): 一类土(松软土)至八类土(特坚石), 每类对应坚实系数与施工方法(影响放坡/机械选择)",
        re.compile(r"八类|开挖难易|松软土|特坚石|坚实系数")),
    ("1A413000_085_0158", "1A413000-B019"): (
        "ext", "🔵外延·土方回填(开挖回填配套): 填方土料禁用(淤泥/有机质>5%/含水量不符) + 填方边坡坡度(<10m为1:1.5; >10m上1:1.5下1:1.75) + 分层压实参数",
        re.compile(r"填方|回填|淤泥|有机质|边坡坡度|压实|分层")),
}

# 卡级噪声剔除 (混卡 chunk 的 B02 territory 卡 / 跨考点卡)
NOISE_BLOCK = re.compile(r"锚杆.*间距|钢筋混凝土支撑|钢结构支撑|土钉墙施工要点|土钉墙应分层|防水混凝土|腰梁|牛腿")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A413000_076_0146~082_0151(支护选型 B037/B068/B070/B073/B029/B023/B080 等)": "基坑支护工程施工/浅基坑支护/深基坑支护/灌注桩排桩/地下连续墙/土钉墙/锚杆 — 全部属【B02 基坑支护选型】territory(支护≠开挖/降水), 命题考支护选型, 绕开归 B02",
    "1A413000_081_0152(基坑监测 B038) + 1A413000_082_0153(基坑危险报警 B033)": "基坑监测/基坑危险报警条件 — 属【B02 基坑监测】territory(监测/报警≠开挖/降水方法), 绕开归 B02",
    "1A422000_033_0055 的锚杆/钢支撑/土钉墙卡(B028/B038/B080 同卡集)": "锚杆布置/钢筋混凝土支撑/钢结构支撑/土钉墙施工要点 — 属【B02 支护】territory, 与同 chunk 的'地下水控制方法'(G01降水本体)混卡; 卡级 NOISE_BLOCK 已剔, 仅保留'地下水控制方法'卡作🔵外延",
    "1A413000_069~072(测量 B049/B065/B077/B012/B051 水准仪/经纬仪/全站仪/定位放线)": "常用工程测量仪器/施工测量 — 属【测量】territory, 命题考测量仪器/放线, 与开挖/降水无关, 绕开归测量考点",
    "1A413000_072_0139~074_0142(变形监测 B026/B050/B057/B067 + 岩土物理指标 B021/B043/B013)": "施工期间变形监测/沉降观测周期 + 岩土物理性质指标(孔隙比/内摩擦角/抗剪强度) — 变形监测属监测territory; 岩土物理指标属土力学基础(非开挖方法选择本体), 绕开",
    "1A413000_086_0159(验槽 B030/B041/B064/B078/B083/B084 天然/桩基验槽/观察法)": "地基处理工程验槽/天然地基验槽/桩基验槽/验槽方法 — 属【验槽/地基验收】territory(验槽≠土方开挖方法), 绕开归验槽考点",
    "1A413030_088~089(地基处理 1A413031-R01~R10 复合地基/夯实/换填/注浆)": "常用地基处理方法与施工(复合地基/夯实/换填/水泥粉煤灰碎石桩/注浆加固) — 属【地基处理】territory(地基处理≠基坑开挖), 绕开归地基处理考点",
    "1A422000_028_0048 的防水混凝土卡 + 1A422000_032_0054(排桩/地下连续墙法规 B083)": "防水混凝土抗压抗渗(属防水/混凝土考点) + 排桩/地下连续墙法规(B02支护) — 卡级/chunk级剔除归各自考点",
}


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
    seen = {}
    for r in recs:
        ch = r["source_ref"].get("chunk_id", "")
        lf = r.get("leaf_id", "")
        if (ch, lf) in CHUNK_POLICY and (ch, lf) not in seen:
            seen[(ch, lf)] = r

    units = []
    total_sp = 0
    for (ch, lf), (mode, note, card_keep) in CHUNK_POLICY.items():
        r = seen.get((ch, lf))
        if not r:
            print(f"⚠ chunk {ch} (leaf {lf}) 未在bundle找到, 跳过")
            continue
        cc = r["compiled_context"]
        sps = []
        idx = 0
        captured = set()
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if NOISE_BLOCK.search(blob):
                continue
            if card_keep and not card_keep.search(blob):
                continue
            content = t.get("content", "") or ""
            if content.strip() in captured:
                continue
            prefix = "[🔵外延] " if mode == "ext" else ""
            sps.append({
                "statement": prefix + (t.get("title", "") + "：" + content).strip("："),
                "required_terms": t.get("source_refs", []),
                "point_id": f"kc:{ch}:{idx}",
                "quote": content,
                "chunk": ch,
                "tier": mode,
            })
            captured.add(content.strip())
            idx += 1
        for rule in cc.get("rules", []):
            ro = pj(rule)
            if isinstance(ro, dict):
                rt = ro.get("description", "") or ro.get("statement", "")
            elif isinstance(rule, str):
                rt = rule
            else:
                rt = ""
            if not rt or rt.strip() in captured:
                continue
            if NOISE_BLOCK.search(rt):
                continue
            if card_keep and not card_keep.search(rt):
                continue
            sps.append({
                "statement": rt,
                "required_terms": [],
                "point_id": f"kc:{ch}:{idx}",
                "quote": rt,
                "chunk": ch,
                "tier": mode,
            })
            captured.add(rt.strip())
            idx += 1
        for ep in cc.get("exam_patterns", []):
            e = pj(ep)
            if not e:
                continue
            desc = e.get("description", "") or ""
            if NOISE_BLOCK.search(desc):
                continue
            if card_keep and not card_keep.search(desc) and not re.search(r"降水|井点|开挖|基坑|超挖|回填|放坡", desc):
                continue
            sps.append({
                "statement": desc,
                "required_terms": e.get("grading_keywords", []),
                "point_id": f"ca:{ch}",
                "quote": desc + " | grading_keywords=" + ",".join(e.get("grading_keywords", [])),
                "chunk": ch,
                "tier": mode,
            })
        if sps:
            units.append({
                "leaf_id": lf,
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "tier": mode,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "G01 基坑开挖与降水方法选择",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "待 compiled taxonomy resolve 裁决 (slot 25; primary 1A413037 / supporting 1A413036 / 1A413000-B081 / 1A413000-B071)",
        "编译库覆盖说明": (
            "G01 弹药本体集中在 1A413000_082~085 几个 chunk(降水方案选择三原则 / 轻型+喷射井点参数 / 真空降水+截水+回灌 / "
            "深基坑土方开挖分层3m+预留土层+水位坑底500mm+盆式逆作 / 基坑开挖严禁超挖软土高差≤1m)，教材锚【厚实】"
            "(降水/开挖方法 RichLeaf 编译库覆盖好，与 D11/S07 的薄覆盖不同)。注册表 primary 1A413037/supporting 1A413036 "
            "为 canonical compiled taxonomy 的降水腹地 node_code，与编译库 1A413000-B0xx leaf 并存(弹药内部引用)。"
            "数值判读锚(井点参数/分层厚度/降水深度)教材+真题双锚，真题侧 _G01_exam_evidence.json 补足。"),
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"G01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:54]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
