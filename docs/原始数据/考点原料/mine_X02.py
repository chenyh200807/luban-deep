#!/usr/bin/env python3
"""X02 临设、道路、材料堆场布置 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 X02 真采分点, 产 _X02_compiled_source.json (照 X01/F05/S06/D13 结构).

考点身份 (注册表 slot 35, **composite**):
  primary   1A431040 施工平面布置          (canonical resolve✅; 与 X01 共享 primary, X01 取"平面布置原则",
            X02 取"临设/道路/堆场的具体技术规格"——同 primary 不同采分轴)
  support   1A437000-B011 仓库与堆料场的消防安全要求   (resolve✅, name 相符)
            1A437000-B026 存放易燃材料仓库的消防要求     (resolve✅, name 相符)
            1A438000-B060 材料进场的验收与保管           (resolve✅, name 相符)

  ⚠️ 注册表/编译库现实(直读核真):
     - 4 个 registry code 全部在 canonical taxonomy nodes_by_code resolve✅ (sha 26dbb542...):
       1A431040=施工平面布置 / 1A437000-B011=仓库与堆料场的消防安全要求 /
       1A437000-B026=存放易燃材料仓库的消防要求 / 1A438000-B060=材料进场的验收与保管.
     - 3 个 supporting code 在编译库 bundle 内**各有独立 record 且名实相符**(直读确认):
       1A437000-B011→chunk 1A437000_147_0236(仓库防火分区500m²/可燃库30m²/易燃20m²/疏散门10m/电气间距);
       1A437000-B026→chunk 1A437000_146_0235(易燃材料仓库下风向/消防通道6m/防火间距30m);
       1A438000-B060→chunk 1A438000_150_0241(材料进场验收三要素/料具码放≤1.5m/下垫上盖).
     - primary 1A431040(施工平面布置) 在编译库 bundle 内**无独立 record**(直读确认0条; 与 X01 同) ——
       真正承载 X02 临设技术规格教学卡的 chunk 挂在同叶子族 1A431010-C* 下(布置临时房屋:
       临时仓库距15m/临时道路宽4m6m/宿舍净高2.5m), 作弹药内部引用与 canonical primary 并存
       (同 X01/F02/G03 无record·锚挂 primary 子项族/章内 chunk 模式).
     - **composite (非 direct)**: X02 题面"临设、道路、材料堆场布置"横跨 ①临设技术规格(1A431010-C 平面布置族)
       + ②仓库/堆料场消防(1A437000 绿色环境章) + ③材料进场保管(1A438000 资源管理章) 三章三族,
       primary 1A431040 只覆盖"在平面上布置"维度, 具体规格/消防/保管由 supporting 跨章承载 ——
       横跨多叶族, 故 **composite** (照 B02/F05/G03 composite 模式, 非 X01/A01 的 direct).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card JSON 字符串编码用 pj() 解析 + leaf_name_path 可能错挂别章
  (F03/F05 踩过, 逐项核真):
  - teaching_cards/rules/exam_patterns 可能是 JSON 字符串, pj() 统一解析(F03/D13/G03/F05 踩过).
  - **本批 chunk 直读核真 leaf_name_path 真实属本体**: 临设规格挂"布置临时房屋"(施工组织本体)、
    仓库堆料场消防挂"仓库与堆料场的消防安全要求/存放易燃材料仓库的消防要求"(B011/B026 名实相符)、
    材料保管挂"材料进场的验收与保管/不合格材料与半成品退场"(B060 名实相符, 同chunk含"不合格材料退场"
    属相邻保管管理一并收) ——**未见 F05 那种名实不符污染(B016名渗漏卡含焊缝/地基)**; 仍逐 chunk 以
    compiled_context 真实内容为准. ⚠️ 注: chunk 1A437000_146_0233 的 leaf 是 1A437000-B060(消防器材的配备),
    与 registry supporting 1A438000-B060(材料进场验收保管) **同suffix B060 不同parent**, 不是同一 leaf;
    146_0233(灭火器配置)作"临设消防配备"X02本体一并收, 但归属 1A437000-B060 非 registry 的 1A438000-B060, 留痕.
  - 与 X01(平面布置原则)/X03(文明绿色) 区分:
     · X01 = 施工平面布置【原则·步骤·要点·图内容】+各设施在平面上【布置位置/相互关系】(占地少/分区/塔吊布置考虑因素)
       = X01本体判分眼. X01 取"在平面上怎么布置/为什么这么布置".
     · X02 = 临时设施/道路/材料堆场的【具体技术规格数值与消防/保管要求】(仓库距15m/道路宽4m6m/消防车道4m/
       回车场12m/转弯半径15m/宿舍净高2.5m每间16人/仓库防火墙500m²/可燃库30m²/易燃20m²/消防通道6m/防火间距30m/
       料具码放≤1.5m下垫上盖/灭火器配置/材料进场验收三要素) = X02 territory(本 pack 本体).
       与 X01 同字, 但"具体规格数值/消防保管要求"是 X02 territory; X01 取其"在平面上布置/为什么布置".
     · X03 = 文明施工/绿色施工/节材节水节能/职业健康/建筑垃圾/防尘洒水/围挡防尘【管理内容】= X03 territory, 标🔵绕开.
     · 临时用电三级配电/临时用水量管径计算 = S05/临设计算 territory, 标🔵绕开(NOISE剔).
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_X02_compiled_source.json")

KEYWORDS = ("临时设施|临设|临建|施工道路|场内道路|运输道路|环形道路|消防车道|材料堆场|堆场|堆放|料场|仓库|库房|"
            "材料进场|加工棚|搅拌站|办公区|生活区|宿舍|临时用地|场地布置|占地|二次搬运|装卸|料具堆放")

# 经人工核真(直读 compiled_context)的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (X02 临设/道路/堆场 技术规格·消防·保管 本体判分眼)
CHUNK_POLICY = {
    # ── 主轴本体①: 临设/道路/临时房屋 具体技术规格 (primary 1A431040 territory · X01 把规格数值让渡给 X02) ──
    "1A431011_012_0013": ("full", "本体·临设技术规格(1A431010-C11~C15/C23, primary 1A431040 territory·X01让渡规格数值给X02): "
        "临时仓库布置(接近使用地点·危险品仓库远离现场距在建工程≥15m)·临时道路宽度标准(主干道单行≥4m双行≥6m·"
        "消防车道≥4m·木材场通道≥6m·回车场12m×12m·载重车转弯半径≥15m)·临时房屋布置(宿舍床铺≤2层·净高≥2.5m·"
        "通道≥0.9m·人均≥2.5m²·每间≤16人). 这些'具体规格数值'是 X02 territory(X01 取其在平面上布置维度, 规格数值让渡给 X02). **逐项核真**"),
    # ── 主轴本体②: 仓库与堆料场消防安全 (registry support 1A437000-B011 territory) ──
    "1A437000_147_0236": ("full", "本体·registry support 1A437000-B011 仓库与堆料场消防安全(名实相符): "
        "仓库防火分区(易引起火灾仓库每500m²设防火墙·可燃材料库房单间≤30m²·易燃易爆品库房单间≤20m²·房门净宽≥0.8m·"
        "任一点到疏散门≤10m)·电气设备防火间距(架空电力线与易燃堆垛≥电杆高×1.5·照明灯具与堆垛≥1m·开关箱接线盒距堆垛≥1.5m·"
        "严禁碘钨灯). 堆料场/仓库消防=X02材料堆场布置消防要求本体. 逐项核真"),
    # ── 主轴本体③: 存放易燃材料仓库消防 (registry support 1A437000-B026 territory) ──
    "1A437000_146_0235": ("full", "本体·registry support 1A437000-B026 存放易燃材料仓库消防(名实相符): "
        "易燃材料仓库设下风向·水源充足处·消防通道宽≥6m·与明火区间距≥30m·危险品间距≥10m·与易燃易爆品间距≥30m. "
        "易燃材料堆场/仓库布置消防间距=X02本体. 逐项核真"),
    # ── 主轴本体④: 材料进场验收与保管 (registry support 1A438000-B060 territory; 同chunk含不合格材料退场=相邻保管管理一并收) ──
    "1A438000_150_0241": ("full", "本体·registry support 1A438000-B060 材料进场验收与保管(名实相符): "
        "材料进场验收三要素(凭证/数量规格/外观·挂牌标识·建立收料台账)·材料堆放高度限制(料具码放高度≤1.5m·库外材料下垫上盖)·"
        "不合格材料退场流程(申请→审批→通知→见证退场→记录确认→报告提交). 材料进场/堆放保管=X02材料堆场布置本体. 逐项核真"),
    # ── 主轴本体⑤: 临设消防器材配备 (chunk leaf=1A437000-B060 消防器材配备, ≠registry的1A438000-B060; 临设消防配备X02本体) ──
    "1A437000_146_0233": ("full", "本体·临设消防器材配备(chunk leaf 1A437000-B060 消防器材的配备, 与 registry support 1A438000-B060 "
        "同suffix不同parent·留痕): 临时搭设建筑每100㎡配2只10L灭火器·木料间油漆间等每25㎡配1只·大型临时设施超1200㎡设太平桶/积水池/黄砂池. "
        "临设消防配备=X02临设布置消防要素本体. 逐项核真"),
    # ── 主轴本体⑥: 工具式定型化临时设施 (chunk leaf 1A437000-B020/B028; 加工棚/可重复使用临时道路板=临设道路类型本体) ──
    "1A437000_150_0295": ("ext", "本体·工具式定型化临时设施(1A437000-B020/B028): 标准化箱式房·定型化临边洞口防护·加工棚·"
        "构件化PVC绿色围墙·预制装配式马道·可重复使用临时道路板=临设/加工棚/临时道路 类型(X02临设道路布置本体). "
        "注: 同chunk垃圾管道垂直运输系统=X03/垃圾territory邻接, NOISE剔. 逐项核真"),
}

# full/ext 同chunk 剔除噪声卡(文明绿色/节材节水节能/职业健康/建筑垃圾/防尘/临电三级配电/用水计算等非 X02 临设技术规格判分眼)
# 这些是 X03/S05/计算型 territory
NOISE = re.compile(r"节材|节水|节能|可再生能源|太阳能|空气能|光伏|循环用水|回灌|"
                   r"职业病|矽尘肺|尘肺|中毒|中暑|食堂|厕所|医疗急救|"
                   r"建筑垃圾|资源化|再生骨料|级配回填|垃圾管道|分类收集|楼层垃圾入口|减速门|专用垃圾箱|垃圾出口|"
                   r"防尘|洒水|扬尘|硬化|绿化|沉淀池|冲洗池|"
                   r"三级配电|TN-S|剩余电流|安全电压|电缆.*埋|"
                   r"用水量|管径计算|文明施工基本要求|围挡.*1\.8")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 邻接 territory (留痕)
SKIPPED = {
    "1A437000_140_0223(节材节水节能)/142_0227(职业健康)/143_0229(文明施工)/149_0291(建筑垃圾)/149_0292(太阳能)/141_0224(节地绿色创新)/141_0225(防尘围挡)/136_0219(绿色施工方案/环保措施) chunk":
        "节材/节水/节能/可再生能源/职业病/食堂厕所/建筑垃圾资源化/太阳能空气能/防尘洒水/文明施工基本要求/绿色施工方案=【文明施工·绿色施工·职业健康·环保】=X03(文明绿色)territory, 标🔵邻接绕开/NOISE剔(X02只取临设/道路/堆场的技术规格与消防保管, 不取环保管理内容)",
    "1A437000_013_0019(建筑垃圾堆放≤3m)/150_0295同chunk垃圾管道垂直运输":
        "建筑垃圾堆放高度≤3m·垃圾管道垂直运输系统=建筑垃圾管理=X03/垃圾territory, NOISE剔(150_0295仅取'工具式定型化临设/加工棚/临时道路板'X02本体, 垃圾管道剔)",
    "1A431011_011_0012(施工总平面布置图内容/设计原则/塔吊泵升降机布置)/016_0017(临时用水量计算)":
        "施工总平面布置图内容六项·设计原则七条·大门塔吊泵升降机布置考虑因素=【施工平面布置原则·步骤·要点】=X01(平面布置原则)territory本体, X02不取(X02只取临设具体规格); 临时用水量q4公式/管径d公式=临设计算型territory, NOISE剔",
    "临时用电三级配电/安全电压/电缆埋深 (S05 territory)":
        "三级配电/TN-S/二级剩余电流保护/安全电压/电缆埋深=【施工临时用电安全技术】=S05 territory, 非X02临设布置技术规格本体; X02只取'临时用电管网在平面上布置'已含X01让渡, 用电安全技术规格绕开/NOISE剔",
    "1A437000_146_0232(在建工程禁存氧气瓶乙炔瓶)/145_0231(防火基本要求/高压线下禁堆放)":
        "在建工程禁存危险品/严禁吸烟/不得设宿舍/高压线下禁搭临建禁堆可燃物=【施工现场消防安全管理一般要求】=偏消防管理/安全管理, 与X02'临设/堆场布置技术规格'弱相关; '高压线下禁堆可燃物'可作堆场布置🔵邻接背景, 但整卡偏消防管理通则, 不作X02主采分眼绕开(标🔵邻接)",
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
                "leaf_id": lf,
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "tier": mode,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "X02 临设、道路、材料堆场布置",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "composite (slot 35, primary 1A431040 施工平面布置 resolve✅·与X01共享primary但采分轴不同[X01原则/X02规格], 编译库无独立record锚挂同叶族1A431010-C*; supporting 1A437000-B011 仓库与堆料场消防安全/1A437000-B026 存放易燃材料仓库消防/1A438000-B060 材料进场验收保管 resolve✅·各有独立record·名实相符. X02题面横跨临设规格(1A431010-C)+仓库堆料场消防(1A437000)+材料保管(1A438000)三章三族, primary只覆盖'在平面布置'维度·具体规格/消防/保管由supporting跨章承载, 横跨多叶族故 composite 非 direct)",
        "编译库覆盖说明": "X02 本体判分眼(临设技术规格[临时仓库距在建工程≥15m/临时道路主干道单行≥4m双行≥6m消防车道≥4m木材场通道≥6m回车场12m×12m转弯半径≥15m/宿舍床铺≤2层净高≥2.5m通道≥0.9m人均≥2.5m²每间≤16人]·仓库与堆料场消防[防火墙每500m²/可燃库房单间≤30m²/易燃易爆库房≤20m²/疏散门≤10m/电气间距]·易燃材料仓库消防[下风向/消防通道≥6m/防火间距30m/危险品间距10m]·材料进场验收保管[凭证数量规格外观验收/挂牌标识/收料台账/料具码放≤1.5m/下垫上盖/不合格材料退场流程]·临设消防器材配备[每100㎡2只10L灭火器/木料间每25㎡1只/超1200㎡设太平桶积水池黄砂池]·工具式定型化临设[箱式房/加工棚/可重复使用临时道路板]) 集中在 chunk 1A431011_012_0013(布置临时房屋·primary族) / 1A437000_147_0236(B011) / 1A437000_146_0235(B026) / 1A438000_150_0241(B060) / 1A437000_146_0233(临设灭火器·leaf 1A437000-B060非registry的1A438000-B060) / 1A437000_150_0295(工具式定型化临设), 名实相符. 真题侧关键补料见真题取证 _X02_exam_evidence.json. 邻接绕开: 文明施工/绿色施工/节材节水节能/职业健康/建筑垃圾/防尘洒水(X03 territory标🔵)·临时用电三级配电(S05 NOISE剔)·临时用水量计算(临设计算 NOISE剔)·施工总平面布置图内容/设计原则/塔吊布置(X01 territory)·消防安全管理通则(偏消防管理标🔵). 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"X02 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/邻接 territory: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
