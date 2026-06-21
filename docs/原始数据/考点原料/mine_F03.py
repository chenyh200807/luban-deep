#!/usr/bin/env python3
"""F03 防水构造层次: 屋面/地下 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 F03 真采分点, 产 _F03_compiled_source.json (照 G03/S06/D13 结构).

考点身份 (注册表 slot 31, **composite**):
  primary  1A413100 屋面防水等级和防水做法    (canonical resolve✅, name 与 F03 防水构造层次/做法 相符)
  support  1A413102 屋面防水基本要求          (resolve✅, name 相符)
           1A413050-R20 屋面防水基本要求      (resolve✅, =1A413102 同名叶子, 编译库本体承载叶子之一)
           1A413050-R21 屋面防水等级和防水做法 (resolve✅, =1A413100 同名叶子, 编译库本体承载叶子之一)
           1A413112 卷材防水层施工            (resolve✅, ⚠️名实偏材料施工工艺·非构造层次本体, 标🔵材料施工外延)

  ⚠️ 注册表/编译库现实(直读核真):
     - 5 个 registry code 全部在 canonical taxonomy nodes_by_code resolve✅:
       1A413100=屋面防水等级和防水做法 / 1A413102=屋面防水基本要求 / 1A413050-R20=屋面防水基本要求 /
       1A413050-R21=屋面防水等级和防水做法 / 1A413112=卷材防水层施工.
     - primary 1A413100 与 supporting 1A413102/1A413112 在编译库 bundle 内**无独立 record**(直读确认0条);
       1A413050-R20/R21 各有1条 record. 真正承载 F03 教学卡的 chunk 全部挂在同叶子族 1A413050-R* 下
       (屋面与防水工程施工), 作弹药内部引用与 canonical primary/supporting 并存(同 G03 的 1A413067/068/069
       无record/锚挂 primary 子项 R* 模式, 同 D13 的 1A413134 模式).
     - 故 composite(非 direct): primary 1A413100 是 canonical "屋面防水等级和防水做法"专属叶子(name 与 F03
       防水构造层次/做法相符), 但 F03 学员题面"防水构造层次: 屋面/地下"横跨**屋面防水等级设防 + 地下防水设防 +
       构造层次 + 接缝防水设防 + 结构自防水**多个 1A413050-R* 叶子(R17/R19/R20/R21/R22/R23/R31/R32/R34/R36/R37/
       R38/R39/R40), 由 primary+supporting 多 code 合成覆盖, 故 composite (照 B02/K01 composite 模式).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card JSON 字符串编码用 pj() 解析 (前 20+ 个新产都踩过):
  - teaching_cards/rules/exam_patterns 可能是 JSON 字符串, pj() 统一解析(D13/G03 踩过).
  - **leaf_name_path 标签污染**: chunk 1A413030_122_0230 的代表 record leaf_name_path 写成"地基与基础工程施工 >
    建筑物的类别"(源库标签错挂!), 但 compiled_context 真实内容=平屋面防水等级一二三级/防水材料选择/屋面防水基本
    要求(直读核真属 F03 屋面防水设防本体). 名实不符 leaf 绕开标🔵留痕, 以 compiled_context 真实内容为准.
  - **保温层施工本体非 F03 构造层次判分眼**: 1A413050-R01~R12/R18/R28/R29/R30/R33/R35/R43(保温层分类/设计/施工/
    墙体保温节能体系/外墙内外保温/自保温砌块/夹芯墙)属【保温隔热工程施工】采分轴, 非 F03 防水构造层次本体, 绕开/标🔵
    (隔汽层 R22/构造层次顺序里的保温层位置 是 F03 本体, 但保温层施工工艺本身不是). NOISE 剔.
  - **卷材/涂膜/砂浆具体施工工艺=F02(卷材施工)territory**: 1A413050-R07/1A413112(卷材防水层施工)/R24(水泥砂浆
    防水层施工)/R25(涂膜防水施工要求)属【防水材料施工工艺】(搭接/铺贴/排气/收头), 是 F02 卷材施工 territory,
    非 F03 防水构造层次/设防判分眼; 标🔵材料施工外延(构造层"有几道卷材/砂浆防水层"是 F03 本体, 但"卷材怎么铺/搭接
    多少"是 F02). 与 F02(卷材施工)/F05(渗漏治理)/C01(施工缝留置)严格区分.
  - **防火隔离带 R41 = 防火**(消防 territory)非防水构造, 绕开.
  - 与 C01(施工缝留置与处理)区分: C01 是混凝土施工缝留置位置/接槎处理(结构施工), F03 的"施工缝防水构造"(R23,
    遇水膨胀止水带/止水条防水设防)是防水构造层侧, 取作 F03 本体(地下接缝防水设防), 但不重复 C01 的结构施工缝留置判分.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_F03_compiled_source.json")

KEYWORDS = ("防水等级|防水构造|构造层次|屋面构造|找平层|找坡层|结构层|保温层|隔汽层|隔离层|防水层|保护层|"
            "地下防水|防水设防|设防道数|一道防水|两道防水|卷材层数|刚性防水|柔性防水|排水坡度|分仓缝|"
            "结构自防水|防水混凝土")

# 经人工核真(直读 compiled_context)的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (F03 防水构造层次/设防本体判分眼)
#       "ext" =邻接外延(墙体防水/材料施工/外墙防水, 标🔵, 非 F03 屋面/地下防水构造层次主采分)
CHUNK_POLICY = {
    # ── 主轴本体: 屋面防水等级与做法 + 防水材料选择 + 屋面防水基本要求 (primary 1A413100/1A413102 territory) ──
    "1A413030_122_0230": ("full", "本体·屋面防水等级与做法(1A413050-R19/R20/R21/R36/R39, 即 primary 1A413100/1A413102 territory; ⚠️源库 leaf_name_path 错挂'地基与基础>建筑物类别', 直读 compiled_context 真实=屋面防水设防): 平屋面防水等级一/二/三级; 一级≥3道(卷材≥1道)·二级≥2道(卷材≥1道)·三级≥1道(可任选卷材/涂料); 屋面防水以防为主以排为辅·设计年限≥20年·泛水/天沟/檐沟/变形缝设附加层; 防水材料按部位选择(外露耐紫外/上人耐霉变/潮湿耐穿刺). **逐道数/逐数值核真**"),
    # ── 主轴本体: 隔汽层构造 (隔汽层位置=构造层次本体, 保温层施工工艺=邻接NOISE剔) ──
    "1A413030_125_0238": ("full", "本体·隔汽层构造要求(1A413050-R22): 隔汽层应在结构层上·保温层下; 气密性好; 沿周边墙面向上连续铺设高出保温层≥150mm. (注: 同chunk保温层分类/设计/施工工艺属保温隔热工程非F03构造层次本体, NOISE剔)"),
    # ── 主轴本体: 种植屋面构造层次 + 排水坡度 + 耐根穿刺 ──
    "1A413030_127_0240": ("full", "本体·种植屋面构造层次+排水坡度+耐根穿刺(1A413050-R31/R32/R34): 种植屋面构造层次自下而上=基层→绝热层→找平层→普通防水层→耐根穿刺防水层→保护层→排(蓄)水层→过滤层→种植土层→植被层; 种植平屋面排水坡度≥2%·天沟檐沟≥1%; 耐根穿刺材料改性沥青卷材≥4mm/PVC等≥1.2mm/喷涂聚脲≥2mm. **逐层次顺序/逐数值核真**"),
    # ── 主轴本体: 地下防水·防水混凝土(结构自防水) ──
    "1A413030_130_0249": ("full", "本体·防水混凝土(结构自防水)施工要求(1A413050-R26/R27/R40): 抗渗等级≥P6·试配比设计提高0.2MPa(设计P8则试配P10); 胶凝材料≥320kg/m³·水泥≥260kg/m³·水胶比≤0.50(有侵蚀性≤0.45)·入泵坍落度120~160mm; 分层连续浇筑分层厚≤500mm·机械振捣. **逐数值核真**"),
    # ── 主轴本体: 地下防水·明挖法主体结构防水做法(设防道数+抗渗) ──
    "1A413030_130_0247": ("full", "本体·明挖法地下工程主体结构防水做法(1A413050-R37): 一级防水≥3道·防水混凝土1道(应选)·外设防水层≥2道(卷材或涂料≥1道)·抗渗≥P8; 三级防水≥1道·防水混凝土1道(应选)·外设防水层不作要求·抗渗≥P6. **逐道数/逐抗渗核真**"),
    # ── 主轴本体: 地下防水·接缝防水设防措施(施工缝/后浇带防水设防) ──
    "1A413030_130_0248": ("full", "本体·明挖法地下工程结构接缝防水设防措施(1A413050-R38): 施工缝防水设防≥2种(界面剂/水泥基渗透结晶/遇水膨胀止水条胶/预埋注浆管/中埋式止水带/外贴卷材外涂涂料); 后浇带防水设防≥1种(补偿收缩混凝土/中埋式止水带/遇水膨胀止水条胶/外贴卷材外涂涂料). **逐种数核真**"),
    # ── 主轴本体: 地下防水·施工缝设置及防水构造(止水条/水平垂直缝设置) ──
    "1A413030_131_0250": ("full", "本体·施工缝设置及防水构造(1A413050-R23): 水平施工缝设在高出底板表面≥300mm处·距孔洞边缘≥300mm; 垂直施工缝避开地下水丰富区宜结合变形缝; 遇水膨胀止水条7d净膨胀率≤60%最终膨胀率·最终膨胀率≥220%. (注: 同chunk大体积防水混凝土龄期60d/90d·养护≥14d后浇带≥28d属地下防水混凝土养护亦F03本体). **逐数值核真**"),
    # ── 主轴本体: 室内防水构造要求(翻起高度/管道密封) ──
    "1A413030_133_0256": ("full", "本体·室内防水构造要求(1A413050-R17): 淋浴区墙面防水层翻起高度≥2000mm·盥洗用水处≥1200mm·其他泛水≥250mm; 地漏管道根部必须密封·穿楼板墙体管道套管嵌填防水密封·套管高出装饰面≥20mm. **逐数值核真**"),
    # ── 邻接外延: 外墙防水工程(外墙=外延, 非屋面/地下构造层次本体) ──
    "1A413030_134_0258": ("ext", "外延·外墙防水工程施工(1A413050-R14/R15): 外墙防水设计与施工(防水层/构造). 标🔵外墙外延(F03 题面'屋面/地下'为本体, 外墙防水属邻接外延非屋面/地下构造层次主采分眼)"),
}

# full/ext 同chunk 剔除噪声卡(保温层施工工艺/材料铺贴搭接/防火隔离带/外墙保温等非 F03 防水构造层次判分眼)
NOISE = re.compile(r"保温层分类|保温层设计|保温层施工|板状材料|纤维材料|整体材料|聚苯|岩棉|喷涂聚氨酯|泡沫混凝土|"
                   r"墙体保温|外墙外保温|外墙内保温|节能系统|自保温|夹芯|防火隔离带|搭接宽度|铺贴方法|排气|收头|"
                   r"卷材铺贴|涂膜遍数|底胶")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf / 邻接 territory (留痕)
SKIPPED = {
    "1A413050-R01~R12/R18/R28~R30/R33/R35/R43(保温隔热工程施工)": "保温层分类/设计/施工/墙体保温节能体系/外墙内外保温/自保温砌块/夹芯墙=【保温隔热工程施工】采分轴, 非F03防水构造层次本体(隔汽层位置R22/构造层次里保温层位置是F03本体, 保温层施工工艺本身不是), 绕开/NOISE剔",
    "1A413050-R07/1A413112(卷材防水层施工)/R24(水泥砂浆防水层)/R25(涂膜防水施工要求)": "卷材/砂浆/涂膜具体施工工艺(搭接/铺贴/排气/收头/遍数)=【防水材料施工工艺】(F02卷材施工 territory), 非F03防水构造层次/设防判分眼; 构造层'有几道卷材/砂浆防水层'是F03本体但'卷材怎么铺/搭接多少'是F02; 标🔵材料施工外延绕开. 注: 1A413112 虽为 registry supporting code 但名实=卷材施工工艺(非构造层次), 仅作 supporting 知识锚不取其施工工艺卡作F03本体",
    "1A413050-R41(防火隔离带施工要点)": "防火隔离带=【消防/防火】territory, 非防水构造, 绕开",
    "C01(施工缝留置与处理)territory": "C01是混凝土结构施工缝留置位置/接槎处理(结构施工), F03 的'施工缝防水构造'(R23 遇水膨胀止水带/接缝防水设防)是防水构造层侧, 取作F03本体(地下接缝防水设防)但不重复C01结构施工缝留置判分, 严格分界",
    "F02(卷材施工)/F05(渗漏治理)territory": "F02=卷材防水层施工工艺(搭接/铺贴/排气/收头), F05=渗漏治理(治漏), F03=防水构造层次/设防道数(等级/几道/构造顺序), 严格分界不混",
    "案例题背景噪声(2015案例2/2019案例一/2021案例一/2023案例一/2024案例二等)": "extract_exam_evidence 关键词命中83条但57案例多为背景资料含'地下/防水/保温'泛词命中(劳务队伍/质量检测/桩基/幕墙封堵等别考点案例), 非F03防水构造层次判分问, 不作F03真题锚; 仅2019第12题/2020第12题/2023第22题(单/多选直接考防水等级/构造层次/墙体防水)作🟢真题锚",
}


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
        leaves = sorted(set(x.get("leaf_id") for x in recs if x["source_ref"].get("chunk_id", "") == ch))
        lf = leaves[0] if leaves else r.get("leaf_id", "")
        sps = []
        idx = 0
        captured = set()
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            content = t.get("content", "") or ""
            title = t.get("title", "") or ""
            if not content.strip():
                continue
            blob = title + content
            if NOISE.search(blob):
                continue
            prefix = "[🔵外墙/材料施工外延] " if mode == "ext" else ""
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
            if NOISE.search(rt):
                continue
            sps.append({
                "statement": ("[🔵外墙/材料施工外延] " if mode == "ext" else "") + rt,
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
            if NOISE.search(desc):
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
        "考点": "F03 防水构造层次: 屋面/地下",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "composite (slot 31, primary 1A413100 屋面防水等级和防水做法 resolve✅ name相符; supporting 1A413102/1A413050-R20/1A413050-R21/1A413112 resolve✅; primary 1A413100 与 1A413102/1A413112 在编译库无独立record, 1A413050-R20/R21 各1条; F03题面'屋面/地下'横跨屋面设防+地下设防+构造层次+接缝设防+结构自防水多个1A413050-R*叶子, 由primary+supporting多code合成覆盖, 故 composite)",
        "编译库覆盖说明": "F03 本体判分眼(屋面防水等级一二三级·设防道数·卷材≥1道·屋面防水以防为主以排为辅·设计年限≥20年·泛水附加层 / 隔汽层在结构层上保温层下·高出保温层≥150mm / 种植屋面构造层次10层顺序·排水坡度≥2%·耐根穿刺≥4mm/1.2mm/2mm / 防水混凝土抗渗≥P6·试配提高0.2MPa·胶凝≥320·水胶比≤0.50·分层≤500mm / 地下一级防水≥3道防水混凝土1道外设≥2道抗渗P8·三级≥1道P6 / 接缝设防施工缝≥2种后浇带≥1种 / 施工缝水平≥300mm·止水条7d≤60%最终膨胀率≥220% / 室内防水翻起≥2000mm/1200mm/250mm)全部集中在 1A413050-R* 叶子族 chunk 1A413030_122_0230/125_0238/127_0240/130_0247/130_0248/130_0249/131_0250/133_0256, 名实相符(⚠️0230源库leaf_name_path错挂'地基与基础'但compiled_context真实属屋面防水设防, 直读核真). 真题侧关键补料(genuine F03 anchors, 单/多选直接考): 2019第12题(地下工程防水等级分四级 ans=C)/2020第12题(倒置式屋面构造层次自下而上顺序 ans=B 结构找坡再找平防水保温后保护)/2023第22题(墙体防水防潮规定 ans=ABCD). 2025第23题(防水卷材防水性能不透水性/抗渗透性 ans=BD)标🔵邻接(材料性能偏F02). 案例评据83条命中(57案例)多为背景资料泛词命中(劳务/质量检测/桩基/幕墙封堵等别考点案例), 非F03防水构造层次判分问, 不作F03真题锚. 邻接绕开: 保温层施工工艺(保温隔热工程)·卷材/砂浆/涂膜材料施工工艺(F02 territory)·防火隔离带(消防)·外墙防水(R14/R15标🔵外延). 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"F03 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 leaf/邻接 territory: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
