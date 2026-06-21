#!/usr/bin/env python3
"""R01 现场消防布置、动火、检查、验收流程 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 R01 真采分点, 产 _R01_compiled_source.json (照 X02/X01/S06/D13 结构).

考点身份 (注册表 slot 37, **composite**):
  primary   1A437030 施工现场消防              (canonical resolve✅ "施工现场消防")
  support   1A437031 施工现场防火要求          (resolve✅, name 相符)
            1A437032 施工现场消防管理          (resolve✅, name 相符)
            1A437000-B060 消防器材的配备       (resolve✅, name 相符)
            1A437000-B061 消防安全管理要求     (resolve✅, name 相符)
            1A422026 建设工程消防设计审查验收有关规定 (resolve✅, name 相符·验收/审查 锚)

  ⚠️ 注册表/编译库现实(直读核真, taxonomy sha 26dbb542...):
     - 6 个 registry code 全部在 canonical taxonomy outline_structure resolve✅:
       1A437030=施工现场消防 / 1A437031=施工现场防火要求 / 1A437032=施工现场消防管理 /
       1A437000-B060=消防器材的配备 / 1A437000-B061=消防安全管理要求 /
       1A422026=建设工程消防设计审查验收有关规定.
     - primary 1A437030 与 supporting 1A437031/1A437032/1A422026 在 rich_leaf_context bundle 内
       **均无独立 record**(直读确认 prefix_record=0; 与 X01/X02 primary 同) ——
       真正承载 R01 现场消防布置/动火/检查 教学卡的 chunk 挂在同章 1A437000-B0xx 扁平叶族
       (动火审批/灭火器配置/消防安全管理/油漆料库/木工操作间/十不烧 等), 作弹药内部引用与 canonical primary 并存
       (同 X01/X02/F02/G03 无record·锚挂 primary 章内 1A437000-B0xx chunk 模式).
     - 2 个 supporting code 在 bundle 内**各有独立 record 且名实相符**(直读确认):
       1A437000-B060→chunk 1A437000_146_0233(临设灭火器配置: 临建每100㎡2只10L/木料间每25㎡1只/超1200㎡设太平桶);
       1A437000-B061→chunk 1A437000_146_0232(消防安全管理: 在建禁存氧气瓶乙炔瓶/禁液化气钢瓶/禁易燃材料作安全网).
     - **composite (非 direct)**: R01 题面"现场消防布置、动火、检查、验收流程"横跨
       ①现场消防布置(消防车道/水源/灭火器/重点防火部位/防火间距=1A437030/031 现场消防)
       + ②动火管理(分级审批/动火证/十不烧/气瓶距离=1A437031 防火要求 + 1A436000 焊接安全)
       + ③消防检查/管理(消防安全检查/义务消防队/禁用品=1A437032 消防管理 + 1A437000-B061)
       + ④消防设计审查验收(=1A422026, 独立设计规定章) ——
       横跨多叶族/多章, 故 **composite** (照 X02/B02/G03 composite 模式).

⚠️ 源库标签污染 + 名实不符 supporting leaf + B060 撞名 + teaching_card JSON 编码用 pj() 解析 (X02/F05 踩过, 逐项核真):
  - teaching_cards/rules/exam_patterns 可能是 JSON 字符串, pj() 统一解析.
  - **B060 撞名警惕(X02 踩过)**: chunk 1A437000_146_0233(灭火器配置) leaf=1A437000-B060(消防器材的配备);
    与"材料保管"系的 1A438000-B060(材料进场验收) 同 suffix 不同 parent. 本 pack 的 1A437000-B060
    是 registry 明列 supporting(消防器材配备), 名实相符·非污染; X02 借同一 chunk 作"临设消防配备",
    R01 借作"现场消防布置→灭火器配备"(本体), 两考点共享同一 chunk 不同采分轴, 留痕.
  - **与 X02(临设/堆场布置规格) territory 区分(逐 chunk 核真)**:
     · X02 = 临时设施/道路/材料堆场 的【具体技术规格数值】(临时仓库距15m/道路宽4m6m/宿舍净高2.5m/
       仓库防火分区500m²/可燃库30m²易燃库20m²/材料码放1.5m). 仓库防火分区(147_0236 B011)/
       易燃材料仓库下风向(146_0235 B026)/电气防火间距 = **X02 territory**, R01 标🔵邻接绕开(仓库规格不是R01"现场消防布置流程"本体).
     · R01 = 现场【总体消防布置(消防车道/水源/消火栓/灭火器/重点防火部位)+ 动火作业全流程(分级审批/
       动火证/十不烧/气瓶距离/明火看护)+ 消防检查/管理(义务消防队/禁用品/八项管理)+ 消防设计审查验收】
       = R01 territory(本 pack 本体). 灭火器配置(146_0233)归 R01 现场消防布置本体(亦 X02 借用, 留痕).
     · X03 = 文明施工/绿色施工/节材节水节能/职业健康/建筑垃圾/防尘 = X03 territory, 标🔵/NOISE剔.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_R01_compiled_source.json")

KEYWORDS = ("施工现场消防|现场消防|临时消防|临时消防设施|消防车道|消防通道|消防水源|消防给水|灭火器|"
            "临时室内消火栓|临时室外消火栓|消火栓|动火|动火作业|动火证|明火作业|用火管理|防火检查|"
            "消防安全检查|消防验收|消防审查|易燃易爆|重点防火部位|防火间距|消防安全管理|灭火及应急疏散预案|"
            "十不烧|氧气瓶|乙炔瓶|义务消防|木工操作间|油漆料库")

# 经人工核真(直读 compiled_context)的 chunk 白名单 + 每 chunk 允许采用的内容类型.
CHUNK_POLICY = {
    # ── 主轴本体①: 动火分级审批 + 动火证 + 防火基本要求 (primary 1A437030/031 territory · 真题 {2020,第17题}/{2024,第20题}/{2025}明锚) ──
    "1A437000_145_0231": ("full", "本体·动火分级审批+动火证+防火基本要求(primary 1A437030 施工现场消防 territory): "
        "一级动火(项目负责人编方案→企业安全部门审批)/二级动火(责任工程师→项目安全部门+负责人)/三级动火(班组→责任工程师+安全部门)·"
        "动火证当日有效·地点变化重办·防火基本要求(高压线下禁搭建禁堆可燃物/严禁吸烟/工程内禁设宿舍/禁液化气钢瓶/油漆防水专人看护). "
        "动火审批=R01 动火流程本体. 真题 {2020,第17题}(一级动火=企业安全部门)/{2024,第20题}(登高焊割报企业安全部门)/{2015,第30题}A(动火证当日有效) 明锚. 逐项核真"),
    # ── 主轴本体②: 动火等级划分 + 义务消防队 (1A437031/032 territory) ──
    "1A437000_144_0230": ("full", "本体·动火等级划分+义务消防队(1A437031 防火要求/1A437032 消防管理 territory): "
        "一级动火(禁火区/油罐/受压设备/登高焊/密封空间/大量可燃物)/二级动火(非禁火区临时焊割/小型油箱/登高焊)/三级动火(无明显危险). "
        "施工现场义务消防队人数≥施工总人数10%. 动火等级/义务消防=R01本体. 真题 {2015,第30题}C(义务消防人员) 印证. "
        "注: 成品保护四字法(护包盖封)=成品保护territory邻接 NOISE剔. 逐项核真"),
    # ── 主轴本体③: 电气焊十不烧 + 气瓶安全距离 (1A437031 明火作业 territory) ──
    "1A437000_147_0237": ("full", "本体·电焊十不烧+气瓶安全距离(1A437031 电气焊作业消防 territory): "
        "焊割十不烧(无证/无审批/不了解现场/不了解内部/未清洗容器/未防护/有压力/有易燃物/有冲突工种/外部危险 不烧)·"
        "焊割点与氧气瓶乙炔瓶≥10m·与易燃易爆物≥30m·乙炔瓶与氧气瓶存放≥2m使用≥5m. 明火作业消防=R01动火本体. 逐项核真"),
    # ── 主轴本体④: 临设灭火器配置 (registry support 1A437000-B060 消防器材配备 · X02 共享同chunk不同采分轴·留痕) ──
    "1A437000_146_0233": ("full", "本体·registry support 1A437000-B060 消防器材配备(名实相符·现场消防布置→灭火器配备): "
        "临时搭设建筑每100㎡配2只10L灭火器·木料间油漆间等每25㎡配1只·大型临时设施超1200㎡设太平桶积水池黄砂池. "
        "现场消防布置灭火器配备=R01本体(X02 借同chunk作临设消防配备·留痕共享). 逐项核真"),
    # ── 主轴本体⑤: 灭火器设置高度 (registry support 1A437000-B068 灭火器设置要求·现场消防设施布置) ──
    "1A437000_146_0234": ("full", "本体·灭火器设置要求(1A437000-B068·现场消防设施布置): "
        "手提式灭火器顶部离地≤1.50m·底部≥0.15m·明显位置·铭牌朝外·正面竖直放置. 灭火器设置=R01现场消防布置本体. 逐项核真"),
    # ── 主轴本体⑥: 消防安全管理要求/禁用品 (registry support 1A437000-B061 消防安全管理要求 · 真题 {2015,第30题}印证) ──
    "1A437000_146_0232": ("full", "本体·registry support 1A437000-B061 消防安全管理要求(名实相符): "
        "在建工程内禁存氧气瓶乙炔瓶·禁用液化石油气钢瓶·不得用易燃可燃材料作安全网防尘网保温材料. "
        "消防安全管理禁用品=R01消防管理本体. 真题 {2015,第30题}B(严禁吸烟·同管理通则) 印证. 逐项核真"),
    # ── 主轴本体⑦: 油漆料库与调料间消防 (1A437000-B059 · 真题 {2015,第30题}E 明锚) ──
    "1A437000_147_0238": ("full", "本体·油漆料库与调料间消防(1A437000-B059): "
        "油漆料库与调料间必须分开设置·与散发火星场所保持防火间距. 真题 {2015,第30题}E(油漆料库内应设调料间=错·应分开) 明锚. 逐项核真"),
    # ── 主轴本体⑧: 木工操作间消防 + 扩改建防火措施 (1A437000-B040 · 动火前后清理可燃物=动火管理) ──
    "1A437000_148_0239": ("full", "本体·木工操作间消防+扩改建防火(1A437000-B040·现场消防布置+动火清理): "
        "木工操作间阻燃材料搭建·配消防水箱水桶·严禁吸烟明火·清理刨花锯末·断电离开·"
        "施工区非施工区设防火分隔·外脚手架不妨碍消防通道·动火作业前后清理可燃物·禁易燃材料上动火·禁爆炸性场所明火设备. "
        "木工间消防/动火清理=R01现场消防+动火本体. 逐项核真"),
    # ── 主轴本体⑨: 气焊电石起火灭火方法 (1A436000-B125 焊接消防 · 真题 {2015,第18题}明锚) ──
    "1A436000_127_0203": ("full", "本体·气焊电石起火灭火方法(1A436000-B125 焊接消防): "
        "气焊电石起火必须用干砂或二氧化碳灭火器·严禁用泡沫四氯化碳灭火器或水. 真题 {2015,第18题}(电石起火用干砂A) 明锚. 逐项核真"),
    # ── 主轴本体⑩: 施工现场安全管理八项(含消防管理) + 现场消防布置EP (1A436000-B099 · EP grading_keywords=现场消防布置核心) ──
    "1A436000_101_0166": ("full", "本体·施工现场安全管理八项+现场消防布置EP(1A436000-B099): "
        "安全管理八项(目标/资源/方案/措施/文明/消防/应急/资料); EP grading_keywords=现场消防布置核心(消防通道/消防水源/消防设施/灭火器材/明显标志/消防安全责任人). "
        "现场消防布置(消防通道+水源+设施+灭火器材+标志+责任人)=R01现场消防布置本体EP. 逐项核真"),
}

# 同chunk 剔除噪声卡(文明绿色/节材节水/职业健康/建筑垃圾/成品保护/X02仓库规格 等非R01现场消防/动火判分眼)
NOISE = re.compile(r"节材|节水|节能|可再生能源|太阳能|空气能|光伏|循环用水|回灌|"
                   r"职业病|矽尘肺|尘肺|中毒|中暑|食堂|厕所|医疗急救|"
                   r"建筑垃圾|资源化|再生骨料|垃圾管道|分类收集|"
                   r"扬尘|洒水|绿化|沉淀池|冲洗池|围挡|"
                   r"成品保护|护：提前|包：包裹|盖：表面|封：局部")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 邻接 territory (留痕)
SKIPPED = {
    "1A437000_147_0236(仓库防火分区500m²/可燃库30m²易燃库20m²/电气防火间距电杆×1.5)":
        "仓库防火分区面积/电气防火间距=【临设/堆场仓库具体技术规格】=X02 territory(X02 已收作 B011 仓库与堆料场消防), R01 不取(R01取'现场总体消防布置流程·动火·检查·验收', 不取仓库分区规格数值); 标🔵邻接绕开",
    "1A437000_146_0235(易燃材料仓库下风向/消防通道6m/防火间距30m)":
        "易燃材料仓库下风向/间距=【临设易燃仓库布置规格】=X02 territory(X02 已收作 B026), R01 不取仓库布置规格; 但 {2015,第30题}D(易燃仓库上风向=错) 是 R01 消防管理MCQ判分眼·真题侧引(标🔵邻接·真题归 R01 MCQ, 教材规格归 X02)",
    "1A437000_136_0219(绿色施工方案/场地布置原则/地基环保/灌注桩环保)/140_0223(节材节水节能)/142_0227(职业健康)/143_0229(文明施工)/149_0291~0294(建筑垃圾/太阳能/噪声/扬尘) chunk":
        "绿色施工/场地布置原则/节材节水节能/职业病/文明施工/建筑垃圾/噪声扬尘=【文明施工·绿色施工·职业健康·环保】=X03(文明绿色)territory, 标🔵邻接绕开/NOISE剔",
    "1A436000_126_0200(施工电梯安全距离/桩工机械/电动冲击夯)/127_0203同chunk若含机械":
        "施工电梯5m防护棚/桩工机械/电动冲击夯=机械作业安全=S02/机械安全 territory, R01 不取(127_0203 仅取'气焊电石起火灭火方法'消防卡); 留痕",
    "1A431011_012_0013(临时仓库距15m/临时道路4m6m/宿舍净高2.5m)消防车道":
        "临时仓库间距/道路宽度/宿舍标准=临设具体技术规格=X02 territory; 其中'消防车道≥4m'是R01现场消防布置邻接背景但整卡属X02临设规格本体, R01 不取该chunk(标🔵邻接)",
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
            sps.append({
                "statement": (title + "：" + content).strip("："),
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
            if NOISE.search(desc):
                continue
            sps.append({
                "statement": desc or ("命题点(grading_keywords): " + ",".join(gk)),
                "required_terms": gk,
                "point_id": f"ca:{ch}",
                "quote": (desc + " | grading_keywords=" + ",".join(gk)).strip(" |"),
                "chunk": ch,
                "tier": mode,
            })
        if sps:
            units.append({
                "leaf_id": r.get("leaf_id", ""),
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "tier": mode,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "R01 现场消防布置、动火、检查、验收流程",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "composite (slot 37, primary 1A437030 施工现场消防 resolve✅·编译库无独立record锚挂同章1A437000-B0xx扁平叶族; "
            "supporting 1A437031 施工现场防火要求/1A437032 施工现场消防管理/1A422026 建设工程消防设计审查验收有关规定 resolve✅·bundle内无独立record; "
            "supporting 1A437000-B060 消防器材的配备/1A437000-B061 消防安全管理要求 resolve✅·各有独立record·名实相符. "
            "R01题面横跨现场消防布置(1A437030/031)+动火管理(1A437031+1A436000焊接)+消防检查管理(1A437032+B061)+消防设计审查验收(1A422026独立设计章), "
            "横跨多叶族多章故 composite 非 direct)",
        "编译库覆盖说明": "R01 本体判分眼(动火分级审批[一级企业安全部门/二级项目安全部门+负责人/三级责任工程师+安全部门·动火证当日有效·地点变化重办]·"
            "动火等级划分[一级禁火区油罐受压设备登高焊密封空间大量可燃物]·电焊十不烧·气瓶距离[氧气乙炔≥10m/易燃易爆≥30m/乙炔氧气存放≥2m用≥5m]·"
            "义务消防队≥总人数10%·灭火器配置[临建每100㎡2只10L/木料油漆间每25㎡1只/超1200㎡设太平桶积水池黄砂池]·灭火器设置[顶部≤1.5m底部≥0.15m]·"
            "消防安全管理禁用品[在建禁存氧气乙炔瓶/禁液化气钢瓶/禁易燃材料作安全网]·油漆料库调料间分开设置·木工间消防+动火清理可燃物·"
            "气焊电石起火用干砂二氧化碳禁水·现场消防布置EP[消防通道/水源/设施/灭火器材/标志/责任人]) "
            "集中在 chunk 145_0231(动火审批·primary)/144_0230(动火等级义务消防)/147_0237(十不烧气瓶)/146_0233(灭火器配置B060)/146_0234(灭火器设置)/"
            "146_0232(消防管理禁用品B061)/147_0238(油漆料库)/148_0239(木工间防火)/127_0203(电石起火灭火)/101_0166(安全管理八项+现场消防布置EP), 名实相符. "
            "真题侧关键补料见真题取证 _R01_exam_evidence.json(动火审批/临时消防设施布置改错/电石起火/消防管理MCQ). "
            "邻接绕开: 仓库防火分区500m²/易燃仓库下风向(147_0236/146_0235=X02临设/堆场规格 territory标🔵)·绿色施工/文明施工/职业健康/建筑垃圾(X03 territory标🔵)·"
            "施工电梯桩工机械(S02机械安全)·临时仓库道路宿舍规格(X02). 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"R01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/邻接 territory: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
