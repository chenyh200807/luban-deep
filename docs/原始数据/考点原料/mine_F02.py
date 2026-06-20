#!/usr/bin/env python3
"""F02 卷材防水施工顺序与搭接方向 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 F02 真采分点, 产 _F02_compiled_source.json (照 S06/S07/C06/D13/G02 结构).

考点身份 (注册表 slot 30, **direct**):
  primary  1A413103 屋面卷材防水层施工            (canonical 专属叶子, resolve ✅, name 与 F02 完全相符)
  support  1A413051-R03 屋面卷材防水层施工        (resolve ✅, 真正承载教学卡的编译库 chunk 锚)
           1A413112 卷材防水层施工(地下室防水)     (resolve ✅, 地下防水侧 name-match)
           1A422000-B021 卷材防水层               (resolve ✅, 相关法规章规范锚)
  ⚠️ 注册表/编译库现实(直读核真):
     - canonical 主锚 1A413103(屋面卷材防水层施工)是 taxonomy 树上的专属叶子(name 完全相符), 故 `direct`.
       但 1A413103 与 1A413112 在编译库 bundle 内**均无独立 record**(直读确认 0 条)——真正承载教学卡的
       编译库 chunk 挂在 supporting leaf 1A413051-R03(屋面卷材防水层施工)所在 chunk 1A413030_123_0234.
       (同 G02 的 1A413039 无 record / 锚挂 supporting 1A413000-B020 模式.)
     - 真正的"卷材防水施工顺序与搭接方向判分眼"集中在 chunk 1A413030_123_0234
       (leaf 1A413051-R03/R07/R10/R11/R14 **共用同一张卡** '卷材防水施工要点'):
       施工顺序=先细部后大面积·由低向高铺贴; 搭接缝顺流水方向; 短边搭接错开≥500mm; 长边搭接错开≥1/3幅宽;
       热熔法加热温度180~200℃; 胶结料厚度1.0~1.5mm. **逐数值/逐方向核真.**
     - 法规章规范锚集中在 chunk 1A422000_041_0065(leaf 1A422000-B021卷材防水层/B043复合防水层/B158防水与密封工程·**共用同一张卡**):
       屋面坡度>25%时需满粘+钉压; 上下层不得垂直铺贴; 短边搭接≥500mm; 长边搭接错开≥1/3幅宽;
       厚度<3mm的卷材严禁热熔法施工; 自粘法接缝密封宽度≥10mm; 焊接法先焊长边后焊短边. **逐条核真.**
     - 地下防水卷材搭接 chunk 1A422000_029_0049(leaf 1A422000-B159·防水卷材施工的规定):
       同层相邻两幅卷材短边搭接错缝≥500mm; 双层铺贴上下两层及相邻两幅接缝错开≥1/3幅宽且不应互相垂直铺贴;
       防水涂料接槎≥100mm. **(印证 1A413112 地下卷材防水侧搭接判分眼·该 leaf 卡含防水混凝土通识需剔噪.)**
     - 细部构造 chunk 1A413030_125_0237(leaf 1A413051-R08·檐口/檐沟/天沟/水落口)与 1A422000_042_0066(leaf B131):
       檐口800mm范围满粘+金属压条钉压收头; 附加层伸入≥250mm; 女儿墙泛水附加层平立面均≥250mm.
       是收头/附加层判分眼(搭接方向考点的细部延伸), 取标🟢本体(细部).
     - 找坡找平 chunk 1A413030_123_0232(leaf 1A413051-R05)与构造层次 chunk 0231(R13):
       找坡坡度/构造层次=屋面防水**背景/基层**, 非卷材铺贴顺序搭接判分眼, 标🔵通识/基层背景(流水坡向定方向的依据可取).

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前若干新产都踩过):
  - chunk 1A413030_123_0234: 5 个 leaf(R03屋面卷材防水层施工/R07搭接缝规定/R10热粘法铺贴/R11立面或大坡面铺贴/
    R14铺贴顺序与方向)**共用同一张卡** '卷材防水施工要点'(cards 内容完全相同). 只取 R03(registry support 名实最贴)
    作本体锚, R07/R10/R11/R14 同卡不重复收(留痕).
  - chunk 1A422000_041_0065: B021卷材防水层/B043复合防水层/B158防水与密封工程 **共用同一张卡**(坡度>25%满粘/搭接/热熔).
    只取 B021(registry support 名实最贴)作本体锚, B043/B158 同卡不重复收(留痕). 同卡第2张'涂料多遍涂布/胎体增强材料'
    是涂膜防水(非卷材), 标🔵相邻(涂膜≠卷材); 第3张'卷材与涂料复合'是复合层取🟢(复合卷材侧搭接同律).
  - chunk 1A413030_124_0235 (leaf R04 屋面涂膜防水层施工): 涂膜防水(多遍涂布/薄涂/胎体)是**涂膜防水**采分轴,
    非卷材铺贴顺序搭接判分眼, 与 F03(防水构造层次)/涂膜考点相邻; 全部绕开(归涂膜防水本体, 与卷材不同采分轴).
  - chunk 1A413030_123_0233 (leaf R09 热桥处理/R12 胎体增强材料): 热桥隔断/胎体无纺布是涂膜/保温背景, 非卷材搭接判分眼, 绕开.
  - chunk 1A422000_040_0064 (leaf B017 保温与隔热/B053 屋面工程施工有关规定): EP'隔汽层150mm/卷材搭接≥80mm'
    是**隔汽层**搭接(保温侧, 80mm≠防水卷材500mm/1/3), '块体保护层分格缝/每遍≤15mm'是保护层/涂膜——
    与 F02 卷材防水搭接**同词不同物**(隔汽层卷材搭接 80mm 是保温隔汽采分轴), 全部绕开. 仅留痕防混.
  - chunk 1A422000_021_0029 (leaf B051/B052 屋面工程及施工质量验收): '检验批→分项→分部→单位/竣工验收程序'
    是验收程序(A01考点), '工序保护/先安设后施工/不得凿孔'是成品保护——非卷材铺贴顺序搭接判分眼, 绕开归 A01/成品保护.
  - chunk 1A422000_028_0048 (leaf B029 地下防水工程有关规定): 主体='基坑土方开挖严禁超挖/防水混凝土抗压抗渗抗裂'
    是基坑开挖(G01)+防水混凝土(非卷材), 非 F02 卷材搭接判分眼, 绕开.
  - chunk 1A422000_029_0049 (leaf B159) 卡含'防水混凝土厚度250mm/抗渗P10/养护14d'=防水混凝土通识(非卷材),
    EP'严禁加水/养护14d'同——仅取'同层短边搭接≥500mm/双层错开≥1/3不垂直/涂料接槎100mm'三条卷材搭接 rule, 余剔噪.
  - 与 F03(防水构造层次)区分: F03 是层次组成(保护/隔离/防水/找平/保温/找坡/结构), F02 是卷材铺贴顺序+搭接方向, 严格分界.
  - 与 F05(渗漏治理)区分: F05 是渗漏成因/治理, F02 是正确铺贴搭接(防为主); 同背景案例的渗漏治理部分非 F02 判分眼.
  - 与 C01(施工缝)区分: 完全不同采分轴(混凝土施工缝 vs 卷材搭接缝), 仅'搭接/接缝'泛词撞名, 严格分界.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_F02_compiled_source.json")

KEYWORDS = ("卷材防水|防水卷材|卷材铺贴|铺贴|搭接|搭接宽度|搭接方向|长边搭接|短边搭接|施工顺序|先低后高|先远后近|由远及近|"
            "满粘|空铺|条粘|点粘|高聚物改性沥青|SBS|APP|热熔法|冷粘法|自粘|附加层|收头|泛水|屋面防水|地下防水|流水坡向|大面|节点")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (本体判分眼) ; "ext"=邻接外延/通识(标🔵, 非 F02 卷材顺序搭接主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (卷材防水施工顺序+搭接方向判分眼: 先细部后大面/由低向高/搭接顺流水/短边≥500/长边≥1/3/热熔180~200) ──
    ("1A413030_123_0234", "1A413051-R03"): ("full", "本体·registry support 屋面卷材防水层施工(判分眼·施工顺序+搭接方向): 先细部后大面积·由低向高铺贴; 搭接缝顺流水方向; 短边搭接错开≥500mm; 长边搭接错开≥1/3幅宽; 热熔法加热温度180~200℃; 胶结料厚度1.0~1.5mm. **逐数值/逐方向核真**"),
    # ── 主轴本体 (法规章规范锚: 坡度>25%满粘钉压/上下层不得垂直/厚<3mm严禁热熔/自粘密封≥10/焊接先长后短) ──
    ("1A422000_041_0065", "1A422000-B021"): ("full", "本体·法规章规范锚 卷材防水层(判分眼·搭接+施工法): 屋面坡度>25%时需满粘+钉压; 上下层不得垂直铺贴; 短边搭接≥500mm; 长边搭接错开≥1/3幅宽; 厚度<3mm的卷材严禁热熔法施工; 自粘法接缝密封宽度≥10mm; 焊接法先焊长边后焊短边. **逐条核真**. 同卡第2张'涂料多遍涂布/胎体增强'=涂膜防水标🔵相邻; 第3张'卷材与涂料复合·涂膜在卷材下方'=复合层取🟢"),
    # ── 主轴本体 (地下防水卷材搭接: 印证 1A413112 地下卷材侧, 含防水混凝土通识需剔噪) ──
    ("1A422000_029_0049", "1A422000-B159"): ("full", "本体·地下防水卷材搭接判分眼(印证 canonical 1A413112 地下室卷材防水侧): 同层相邻两幅卷材短边搭接错缝≥500mm; 双层铺贴上下两层及相邻两幅接缝错开≥1/3幅宽且不应互相垂直铺贴; 防水涂料接槎≥100mm. **仅取卷材搭接3条 rule, 同卡防水混凝土厚度250mm/抗渗P10/养护14d=防水混凝土通识剔噪绕开**"),
    # ── 本体·细部 (收头/附加层: 搭接方向考点的细部延伸·泛水节点) ──
    ("1A413030_125_0237", "1A413051-R08"): ("full", "本体·细部判分眼(收头/附加层·搭接方向的节点延伸): 檐口800mm范围内卷材必须满粘·收头金属压条钉压并密封·下端设鹰嘴滴水槽; 檐沟天沟防水层下增设附加层伸入屋面≥250mm; 女儿墙泛水处附加层平面立面均≥250mm; 水落口杯牢固固定·增设涂膜附加层. **逐数值核真**"),
    # ── 通识背景 (找坡找平: 流水坡向=搭接顺流水方向的依据, 取作🔵基层背景) ──
    ("1A413030_123_0232", "1A413051-R05"): ("ext", "基层背景·找坡与找平(流水坡向定搭接方向的依据): 结构找坡≥3%; 材料找坡宜2%; 檐沟天沟纵向找坡≥1%; 找坡层最薄处≥20mm; 找平层分格缝5~20mm·间距≤6m. 标🔵基层背景(非卷材铺贴顺序搭接主判分眼, 但'流水坡向'是搭接顺流水方向的依据)"),
    # ── 通识背景 (屋面构造层次: 防水层在层次中的位置, F03邻接) ──
    ("1A413030_123_0231", "1A413051-R13"): ("ext", "通识背景·屋面基本构造层次(F03防水构造层次邻接): 保护层/隔离层/防水层/找平层/保温层/找坡层/结构层. 标🔵通识(F03本体·非F02卷材顺序搭接判分眼, 卷材防水层在层次中的位置背景)"),
}

# ext 模式剔除噪声卡; B159 full 模式也要剔防水混凝土通识(非卷材搭接)
NOISE = re.compile(r"防水混凝土|抗渗|抗压抗渗抗裂|P10|养护期|结构厚度|裂缝宽度|止水带|绿色施工|环保材料|扬尘|隔汽层|分格缝|强夯|基坑")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A413030_123_0234(R07搭接缝规定/R10热粘法铺贴/R11立面或大坡面铺贴/R14铺贴顺序与方向)": "与 R03(屋面卷材防水层施工)同 chunk 同卡'卷材防水施工要点'(内容完全相同: 先细部后大面/由低向高/搭接顺流水/短边500/长边1/3/热熔180~200), R03已收(registry support 名实最贴), R07/R10/R11/R14 不重复收(留痕)",
    "1A422000_041_0065(B043复合防水层/B158防水与密封工程)": "与 B021(卷材防水层)同 chunk 同卡(坡度>25%满粘/搭接/热熔), B021已收(registry support 名实最贴), B043/B158 不重复收(留痕)",
    "1A413030_124_0235(R04 屋面涂膜防水层施工)": "涂膜防水(多遍涂布/薄涂/胎体增强1.0mm)是**涂膜防水**采分轴, 非卷材铺贴顺序搭接判分眼, 与卷材不同采分轴(涂膜≠卷材), 全部绕开归涂膜防水本体",
    "1A413030_123_0233(R09热桥处理/R12胎体增强材料)": "热桥隔断/胎体无纺布是涂膜防水/保温背景, 非卷材搭接判分眼, 绕开",
    "1A422000_040_0064(B017保温与隔热/B053屋面工程施工)": "EP'隔汽层150mm/卷材搭接≥80mm'是**隔汽层**搭接(保温隔汽侧, 80mm≠防水卷材500mm/1/3)+'块体保护层分格缝/每遍≤15mm'=保护层/涂膜, 与F02卷材防水搭接同词不同物(隔汽层卷材搭接是保温采分轴), 全部绕开",
    "1A422000_021_0029(B051/B052屋面工程及施工质量验收)": "'检验批→分项→分部→单位/竣工验收程序'是验收程序(A01考点)+'工序保护/先安设/不得凿孔'是成品保护, 非卷材铺贴顺序搭接判分眼, 绕开归A01/成品保护",
    "1A422000_028_0048(B029地下防水工程有关规定)": "主体='基坑土方开挖严禁超挖/防水混凝土抗压抗渗抗裂'=基坑开挖(G01)+防水混凝土(非卷材), 非F02卷材搭接判分眼, 绕开",
    "1A422000_029_0049(B159卡内防水混凝土条款)": "B159卡含'防水混凝土厚度250mm/抗渗P10/养护14d/止水带/绿色施工'=防水混凝土通识(非卷材), 仅取'同层短边搭接≥500/双层错开≥1/3不垂直/涂料接槎100mm'三条卷材搭接rule, 防水混凝土条款NOISE剔噪",
    "F03(防水构造层次)territory": "F03是层次组成(保护/隔离/防水/找平/保温/找坡/结构), F02是卷材铺贴顺序+搭接方向, 严格分界(同屋面防水背景的层次部分非F02判分眼)",
    "F05(渗漏治理)territory": "F05是渗漏成因/治理, F02是正确铺贴搭接(防为主), 严格分界(同案例渗漏治理部分非F02判分眼)",
    "C01(施工缝)territory": "混凝土施工缝 vs 卷材搭接缝完全不同采分轴, 仅'搭接/接缝'泛词撞名, 严格分界",
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
        # B159: 卡含防水混凝土通识, full 模式也要 NOISE 剔噪(只留卷材搭接); 其余 full 不剔
        noise_filter = mode == "ext" or lf == "1A422000-B159"
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
            prefix = "[🔵基层/通识背景] " if mode == "ext" else ""
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
        "考点": "F02 卷材防水施工顺序与搭接方向",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 30, canonical 专属叶子 1A413103 屋面卷材防水层施工 resolve✅ name完全相符; 编译库锚挂 supporting 1A413051-R03 同 chunk 1A413030_123_0234)",
        "编译库覆盖说明": "registry primary 1A413103(屋面卷材防水层施工)是 canonical taxonomy 专属判断节点(name 与 F02 完全相符, resolve✅, 故 direct). 1A413103 与 1A413112(地下室卷材防水层施工) 在编译库 bundle 内均无独立 record(直读确认0条)——真正承载教学卡的编译库 chunk 挂在 supporting leaf 1A413051-R03(屋面卷材防水层施工)所在 chunk 1A413030_123_0234(R03/R07/R10/R11/R14 共用同一张卡'卷材防水施工要点'), 作弹药内部引用与 canonical 主锚并存(同 G02 的 1A413039 无record/锚挂 supporting 1A413000-B020 模式). 卷材防水施工顺序+搭接方向判分眼(先细部后大面积/由低向高铺贴/搭接缝顺流水方向/短边搭接错开≥500mm/长边搭接错开≥1/3幅宽/热熔法180~200℃/胶结料1.0~1.5mm)集中在 chunk 1A413030_123_0234(leaf 1A413051-R03). 法规章规范锚(坡度>25%满粘钉压/上下层不得垂直铺贴/厚度<3mm严禁热熔/自粘密封≥10mm/焊接先长后短边)集中在 chunk 1A422000_041_0065(leaf 1A422000-B021卷材防水层). 地下防水卷材搭接(同层短边错缝≥500mm/双层上下层错开≥1/3不垂直)集中在 chunk 1A422000_029_0049(leaf B159·防水卷材施工的规定·印证 1A413112 地下侧, 同卡防水混凝土通识已NOISE剔噪). 细部收头/附加层(檐口800mm满粘/附加层≥250mm/泛水)在 chunk 1A413030_125_0237(leaf R08). 找坡找平/构造层次标🔵基层/F03通识背景. ⚠️隔汽层卷材搭接≥80mm(1A422000-B017/B053)是保温隔汽采分轴(同词不同物)已绕开. 涂膜防水(R04)/防水混凝土/检验批验收程序均剔噪绕开. 真题侧关键补料: 屋面卷材防水施工工艺正误(先细部后大面/由低向高/搭接顺流水)/搭接宽度数值(短边500/长边1/3)/热熔法温度/坡度>25%满粘/上下层不得垂直铺贴 等是判分眼真题锚, 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"F02 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:48]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
