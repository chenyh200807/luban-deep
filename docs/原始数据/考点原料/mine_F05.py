#!/usr/bin/env python3
"""F05 渗漏治理诊断 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 F05 真采分点, 产 _F05_compiled_source.json (照 F02/S06/D13/G02 结构).

考点身份 (注册表 slot 33, **direct**):
  primary  1A434033 (渗漏治理诊断 canonical 专属判断节点; 编译库 bundle 内**无独立 record**, 直读确认 0 条)
  support  1A434000-B016 屋面与防水工程质量通病防治  (resolve✅, registry 列首 support; chunk 1A434000_074_0116)
           1A434000-B067 防水混凝土施工缝渗漏水      (resolve✅, 同 chunk 同卡, name 与"施工缝渗漏诊断"最贴)
  ⚠️ 注册表/编译库现实(直读核真):
     - canonical 主锚 1A434033(渗漏治理诊断)在 taxonomy 树上是专属判断节点, 但编译库 bundle 内**无独立 record**(0 条)——
       真正承载渗漏治理/诊断教学卡的编译库 chunk 散在 1A434(施工质量管理·质量通病防治)章的若干 chunk:
       · 1A434000_074_0116 (registry support B016/B067 所在 chunk)
       · 1A434000_075_0117 (管道穿墙/防水混凝土裂缝渗漏)
       · 1A434000_076_0118 (卷材屋面流淌治理)
       · 1A434000_076_0119 (屋面卷材起鼓治理)
       · 1A434000_077_0120 (山墙女儿墙漏水治理·诊断+治理)
       (同 F02 的 1A413103 无 record / 锚挂 supporting leaf 模式.)
     - F05 判分核心 = **渗漏诊断(找成因/部位) + 治理方法(对症处置/分级处置)**:
       施工缝渗漏成因(未清理/接槎/钢筋密集浇捣不密实); 管道穿墙渗漏治理(止水环/灌浆堵漏); 防水混凝土裂缝渗漏防治(多道设防/刚柔结合/保湿养护);
       卷材屋面流淌治理(切割法/局部切除重铺/钉钉子法); 卷材起鼓治理(<100mm抽气灌胶法/≥100mm割开重贴); 山墙女儿墙漏水治理(清旧胶结料→重新钉压条→防水油膏封口).
       **逐方法/逐数值核真.**
     - 诊断检验背景: 1A422000_039_0063(外墙体接缝防水检验·现场淋水试验·每批抽查≥10m²)是渗漏检验方法🔵背景(诊断侧).
     - 治理用材通识: 1A412010_065_0127(堵漏灌浆材料分类·颗粒性/化学/环氧/聚氨酯)是材料知识🔵相邻.

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前若干新产都踩过, F05 污染尤重):
  - **chunk 1A434000_074_0116 = 严重 card 污染**: 8 个 leaf(含 registry support B016 屋面与防水工程质量通病防治 / B067 防水混凝土施工缝渗漏水 /
    B004 地下防水工程质量问题防治 / B005 地基不均下沉墙体裂缝 / B013 填充墙砌筑不当 / B042 焊缝夹渣 / B046 砌体质量问题)
    **共用同一组 4 张卡**: ①焊缝夹渣防治 ②地基不均沉降裂缝防治 ③填充墙裂缝防治 ④地下防水施工缝渗漏原因.
    其中**只有第④张'地下防水施工缝渗漏原因'是真渗漏诊断**——①②③(焊缝/地基沉降/填充墙裂缝)是名实不符的污染卡(B016/B067 名为防水渗漏, 卡内容却含焊缝/地基/砌体), 一律 NOISE 剔噪.
    且该 chunk 的 EP'防止填充墙交接处裂缝'与渗漏无关(污染), NOISE 剔. 只取 B016(registry support 列首)作本体锚, B067/B004 同卡不重复收(留痕).
  - **chunk 1A434000_075_0117 = 同卡共用**: B037(混凝土施工缝及接槎部位质量通病防治) / B049(管道穿墙地部位渗漏水) / B068(防水混凝土裂缝渗漏水)
    **共用同卡**: 防水混凝土裂缝渗漏防治(多道设防/刚柔结合/保湿养护) + 管道穿墙渗漏防治(止水环/灌浆堵漏). 只取 B049(管道穿墙渗漏·keyword命中最贴)作本体锚, B037/B068 同卡不重复收(留痕).
  - chunk 1A434000_074_0116 的 B016/B067 卡里'焊缝夹渣/地基沉降/填充墙裂缝'三卡是 A01/Q01/C06 territory(焊缝=钢结构, 地基沉降=地基, 填充墙=砌体), 与 F05 渗漏完全不同采分轴, NOISE 剔噪绕开.
  - 淋水试验卡所在 chunk 1A422000_039_0063 同卡含'预制构件结构性能检验/套筒灌浆连接 40×40×160'=装配式(非渗漏诊断), NOISE 剔, 仅取'外墙体接缝防水检验·现场淋水试验'一张🔵诊断背景卡.
  - 与 F02(卷材防水施工顺序搭接)区分: F02 是正确铺贴搭接(防为主·新做), F05 是渗漏成因诊断+治理(治为主·修缮); 同屋面防水背景但采分轴不同, 严格分界.
  - 与 C01(混凝土施工缝)区分: C01 是施工缝留置处理(新做), F05 取'施工缝渗漏成因诊断'(已渗漏后找原因), 仅'施工缝'撞词, 采分轴不同(诊断侧), 严格分界.
  - 与 Q01/Q03(裂缝/质量通病)区分: Q 系列是混凝土裂缝/质量通病防治本体, F05 取其中'渗漏'子集(防水混凝土裂缝→渗漏)的诊断治理侧, 非渗漏的裂缝防治不进 F05.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_F05_compiled_source.json")

KEYWORDS = ("渗漏|渗漏治理|渗漏诊断|渗漏水|防水通病|堵漏|注浆堵漏|找漏|渗漏点|渗漏部位|屋面渗漏|地下室渗漏|卫生间渗漏|"
            "外墙渗漏|穿墙管|变形缝渗漏|施工缝渗漏|治理方法|快速堵漏|引水|防水修缮|蓄水试验|淋水试验")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 本体判分眼(渗漏诊断/治理) ; "ext"=邻接外延/通识(标🔵, 非 F05 渗漏诊断治理主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (施工缝/地下防水渗漏诊断·成因: registry support B016 列首; 同卡 3 张污染卡 NOISE 剔) ──
    ("1A434000_074_0116", "1A434000-B016"): ("full", "本体·registry support 屋面与防水工程质量通病防治(渗漏诊断·施工缝渗漏成因): 施工缝未清理干净→混凝土粘结不良→渗漏; 未按规范处理施工缝→接槎明显; 钢筋密集→浇捣困难→混凝土不密实. **同卡'焊缝夹渣/地基不均沉降裂缝/填充墙裂缝'三张为名实不符污染卡, NOISE 剔噪**. 逐成因核真"),
    # ── 主轴本体 (管道穿墙/防水混凝土裂缝渗漏治理: 止水环/灌浆堵漏/多道设防刚柔结合/保湿养护) ──
    ("1A434000_075_0117", "1A434000-B049"): ("full", "本体·管道穿墙(地)部位渗漏水治理(对症处置): 清理管道表面→设置止水环→振捣密实→避免振动→灌浆堵漏; 防水混凝土裂缝渗漏防治=混凝土浇筑后及时保湿养护·多道设防刚柔结合·确保防水层保护层质量. **逐措施核真**"),
    # ── 主轴本体 (卷材屋面流淌治理·分级处置: 真题2025案例三明锚) ──
    ("1A434000_076_0118", "1A434000-B001"): ("full", "本体·卷材屋面流淌治理(分级处置判分眼·真题2025案例三): 中等流淌可采用切割法/局部切除重铺/钉钉子法; (严重流淌拆除重铺/轻微流淌如不渗漏可不治理). **逐方法核真**"),
    # ── 主轴本体 (屋面卷材起鼓治理·按直径分档处置) ──
    ("1A434000_076_0119", "1A434000-B017"): ("full", "本体·屋面卷材起鼓治理(按直径分档处置): 直径<100mm用抽气灌胶法; ≥100mm需割开(斜十字形)、清理、吹干、重贴(新贴方形卷材). **逐数值/逐方法核真**"),
    # ── 主轴本体 (山墙女儿墙部位漏水·诊断成因+治理: EP既问原因又问治理=诊断治理一体) ──
    ("1A434000_077_0120", "1A434000-B019"): ("full", "本体·山墙女儿墙部位漏水治理(诊断+治理一体): 成因=卷材收口/压条脱落/滴水线破损/拉结不牢/钝角; 治理=清除旧胶结料→烤干基层→重新钉压条→覆盖新卷材→防水油膏封口; 修复压顶砂浆; 分层压入新卷材并加铺一层. **逐措施核真**"),
    # ── 通识背景 (堵漏灌浆材料分类: 渗漏治理用材, 标🔵相邻材料通识) ──
    ("1A412010_065_0127", "1A412010-B020"): ("ext", "治理用材通识·堵漏灌浆材料分类: 分颗粒性(如水泥)和无颗粒化学两类; 按成分有丙烯酸胶/甲基丙烯酸酯/环氧树脂/聚氨酯. 标🔵相邻(渗漏治理用材选用背景, 非诊断治理方法主判分眼)"),
    # ── 诊断检验背景 (现场淋水试验: 渗漏检验方法, 标🔵诊断背景; 同卡装配式 NOISE 剔) ──
    ("1A422000_039_0063", "1A422000-B013"): ("ext", "诊断检验背景·外墙体接缝防水检验方法(现场淋水试验): 每1000m²外墙面积划为一检验批·不足也划一批; 每批抽查一处·面积≥10m²·进行现场淋水试验. 标🔵诊断背景(渗漏检验/验收方法, 非渗漏治理方法主判分眼). **同卡'预制构件结构性能检验/套筒灌浆40×40×160'=装配式 NOISE 剔噪**"),
}

# ext 模式剔除噪声卡; B016 full 模式也要 NOISE 剔污染卡(焊缝/地基沉降/填充墙裂缝, 非渗漏)
NOISE = re.compile(r"焊缝夹渣|焊件|地基软弱部位|沉降缝|圈梁|反拱|填充墙|2φ6|半砖斜砌|加强网片|"
                   r"预制构件|结构性能检验|套筒灌浆|40×40×160|叠合板底板|梁板类简支")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A434000_074_0116(B067防水混凝土施工缝渗漏水/B004地下防水工程质量问题防治)": "与 B016(屋面与防水工程质量通病防治)同 chunk 同组 4 卡(内容完全相同), B016 已收(registry support 列首), B067/B004 不重复收(留痕). B067 名'防水混凝土施工缝渗漏水'与第④卡'地下防水施工缝渗漏'最贴, 但同卡, 已由 B016 本体收",
    "1A434000_074_0116(焊缝夹渣/地基不均沉降裂缝/填充墙裂缝三张污染卡)": "B016/B067 名为'防水渗漏', 卡内容却含焊缝夹渣(钢结构A01)/地基不均沉降裂缝(地基)/填充墙裂缝(砌体C06)——**名实不符的源库标签污染**, 与 F05 渗漏诊断治理完全不同采分轴, NOISE 全部剔噪绕开; 该 chunk EP'防止填充墙交接处裂缝'同(污染), 剔",
    "1A434000_075_0117(B037混凝土施工缝接槎质量通病/B068防水混凝土裂缝渗漏水)": "与 B049(管道穿墙渗漏水)同 chunk 同卡(防水混凝土裂缝渗漏防治+管道穿墙渗漏防治), B049 已收(keyword 命中最贴), B037/B068 不重复收(留痕)",
    "1A422000_039_0063(预制构件结构性能检验/套筒灌浆连接)": "同卡含'梁板类简支受弯结构性能检验/套筒灌浆 40×40×160 标养28d'=装配式(非渗漏诊断), NOISE 剔噪; 仅取'外墙体接缝防水检验·现场淋水试验'一张🔵诊断背景卡",
    "F02(卷材防水施工顺序搭接)territory": "F02 是正确铺贴搭接(防为主·新做), F05 是渗漏成因诊断+治理(治为主·修缮); 同屋面防水背景但采分轴不同, 严格分界(同案例的正确铺贴部分非 F05 判分眼)",
    "C01(混凝土施工缝)territory": "C01 是施工缝留置处理(新做正确做法), F05 仅取'施工缝渗漏成因诊断'(已渗漏后找原因), 仅'施工缝'撞词, 采分轴不同(诊断侧), 严格分界",
    "Q01/Q03(混凝土裂缝/质量通病)territory": "Q 系列是混凝土裂缝/质量通病防治本体, F05 仅取其中'渗漏'子集(防水混凝土裂缝→渗漏)诊断治理侧; 非渗漏的裂缝防治/质量通病不进 F05",
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
    for (ch, lf), (mode, note) in CHUNK_POLICY.items():
        r = seen.get((ch, lf))
        if not r:
            print(f"⚠ chunk {ch} (leaf {lf}) 未在bundle找到, 跳过")
            continue
        cc = r["compiled_context"]
        sps = []
        idx = 0
        captured = set()
        # 所有单元都开 NOISE 过滤(B016 主轴也要剔污染卡; ext 也剔)
        noise_filter = True
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            content = t.get("content", "") or ""
            title = t.get("title", "") or ""
            if not content.strip():
                continue
            blob = title + content
            if noise_filter and NOISE.search(blob):
                continue
            prefix = "[🔵相邻/诊断背景] " if mode == "ext" else ""
            sps.append({
                "statement": prefix + (title + "：" + content).strip("："),
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
            if noise_filter and NOISE.search(rt):
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
            desc = e.get("content", "") or e.get("description", "") or ""
            gk = e.get("grading_keywords", [])
            if not (desc or gk):
                continue
            if noise_filter and NOISE.search(desc):
                continue
            sps.append({
                "statement": desc,
                "required_terms": gk,
                "point_id": f"ca:{ch}",
                "quote": desc + " | grading_keywords=" + ",".join(gk),
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
        "考点": "F05 渗漏治理诊断",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 33, canonical 专属判断节点 1A434033 渗漏治理诊断; 编译库 bundle 内无独立 record, 锚挂 supporting 1A434000-B016/B067 所在 1A434 质量通病防治章 chunk)",
        "编译库覆盖说明": "registry primary 1A434033(渗漏治理诊断)是 canonical taxonomy 专属判断节点, 但编译库 bundle 内**无独立 record**(直读确认0条)——真正承载渗漏治理/诊断教学卡的编译库 chunk 散在 1A434(施工质量管理·质量通病防治)章: 施工缝渗漏成因诊断 chunk 1A434000_074_0116(registry support B016/B067 所在, **8 leaf 共用同组4卡, 仅'地下防水施工缝渗漏原因'是真渗漏诊断, 焊缝夹渣/地基沉降/填充墙裂缝三卡为名实不符污染已NOISE剔噪**); 管道穿墙/防水混凝土裂缝渗漏治理 chunk 1A434000_075_0117(B049·止水环/灌浆堵漏/多道设防刚柔结合); 卷材屋面流淌治理 chunk 1A434000_076_0118(B001·切割法/局部切除重铺/钉钉子法·真题2025案例三明锚); 屋面卷材起鼓治理 chunk 1A434000_076_0119(B017·<100mm抽气灌胶法/≥100mm割开重贴); 山墙女儿墙漏水治理 chunk 1A434000_077_0120(B019·诊断成因+治理一体). 诊断检验背景(现场淋水试验·每批≥10m²)在 chunk 1A422000_039_0063 标🔵; 堵漏灌浆材料分类(颗粒性/化学/环氧/聚氨酯)在 chunk 1A412010_065_0127 标🔵治理用材. ⚠️源库标签污染严重: B016/B067 名为防水渗漏但卡含焊缝/地基/砌体污染(已剔); 与 F02(正确铺贴新做)/C01(施工缝留置)/Q01-Q03(裂缝质量通病)严格分界, F05 取'渗漏诊断+治理修缮'侧. 真题侧关键补料: 卷材流淌分级治理(2025案例三)/防水水泥砂浆做法(2022第16题)/刚性防水抗裂(2022第3题)/变形缝不穿漏水房间(2024第23题)是判分眼/相邻真题锚, 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"F05 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:48]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
