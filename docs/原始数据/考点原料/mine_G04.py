#!/usr/bin/env python3
"""G04 地基验槽与地基处理 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 G04 真采分点, 产 _G04_compiled_source.json (照 G01/D11/S07/C06 结构).

考点身份 (注册表 slot 28, **direct**):
  primary    1A413048 (天然地基验槽)
  supporting 1A413000-B041 (天然地基验槽) / 1A413025 (基坑验槽要求)
  taxonomy sha 26dbb542b31601d6b3255d53463d0007c0c7eaea5a24ad9c338b3742baa976c8

  ✅ resolve 核真(去 compiled taxonomy nodes_by_code 直查): 1A413048=天然地基验槽 / 1A413000-B041=天然地基验槽
  / 1A413025=基坑验槽要求 —— 三 code 名实相符, status=direct。

⚠️ 与 G01(基坑开挖与降水) / G03(桩基) 严格分界 (任务硬约束):
  - G04 = 验槽(基坑/基槽/天然地基/桩基/地基处理工程验槽 + 验槽资料条件 + 验槽方法观察法 + 轻型动力触探/钎探 +
    持力层/软弱下卧层判定 + 局部软弱处理 + 槽底标高/超挖局部处理) + 地基处理(换填垫层/夯实/强夯/压实/复合地基/
    注浆加固/灰土挤密/水泥土搅拌/振冲/旋喷 选型+参数+检测)。
  - G01 = 基坑开挖方法(分层/放坡/盆式/逆作/预留土层/超挖) + 降水方法选择(集水明排/井点/真空/截水/回灌)。
  - G03 = 桩基成孔/灌注工艺。
  ⚠️ chunk 1A413000_084_0157 leaf "基坑验槽要求"(1A413000-B039) **名实不符**: 名义是验槽, 内容实为深基坑开挖控制
    (分层≤3m/预留土层/水位坑底500mm/逆作盆式)=G01 开挖本体 → 整 chunk 绕开归 G01, 留痕。

⚠️ 源库标签污染 + 名实不符防御 (前 11 个新产 B02/N01/C01/C06/J01/S07/D11/D12/D13/G01/G02 都踩过):
  - 必须核 compiled_context 真实内容确属"验槽/地基处理"本体, 名实不符卡绕开并留痕。
  - chunk 1A413000_086_0159 的 6 个 leaf(B030 地基处理工程验槽/B041 天然地基验槽/B064 桩基工程验槽/B078 观察法/
    B083 验槽资料条件/B084 验槽方法)共享同一组 3 张验槽 TC(验槽资料/不触探三情况/观察法), 去重后只采一次,
    挂 canonical primary leaf 1A413000-B041。
  - teaching_card 可能 JSON 字符串编码, pj() 解析。
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_G04_compiled_source.json")

KEYWORDS = ("地基验槽|验槽|基坑验槽|基槽|天然地基|地基处理|换填|换填垫层|垫层|夯实地基|强夯|压实地基|注浆加固|钎探|"
            "轻型动力触探|持力层|槽底|槽底标高|基底标高|软弱下卧层|局部处理|局部软弱|超挖|钎探图|验槽方法|无支护")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型 + 每卡级过滤.
# mode: "full"=取该 chunk 全部 G04 本体 TC/rule/EP ; "ext"=邻接/法规外延(标🔵外延).
CHUNK_POLICY = {
    # ── 验槽主轴 (G04 核心 · primary 1A413048/B041 + supporting 1A413025) ──
    ("1A413000_086_0159", "1A413000-B041"): (
        "full", "本体·天然地基验槽(canonical primary 主锚): 验槽必备资料清单(五方到场+设计文件+勘察报告+轻型动力触探记录+地基处理检测报告+基底保护层≤100mm) + 可不触探三情况(承压水头高于坑底/砾石卵石层>1m/均匀密实砂层>1.5m) + 观察法要点(槽壁槽底土质与勘察一致/开挖深度达标/土质结构未被破坏) — G04 验槽最核心判分眼; 同 chunk 另 5 leaf(B030/B064/B078/B083/B084)共享同组 TC 去重",
        re.compile(r"验槽|触探|观察法|持力层|槽壁|槽底|勘察|保护层|承压水|卵石|砂层")),
    ("1A413030_087_0160", "1A413020-R01"): (
        "full", "本体·基槽检验与轻型动力触探(钎探): 轻型动力触探用于检测地基持力层强度/均匀性/浅埋软弱层或硬层/古井/墓穴/空洞 — G04 验槽检测方法判分眼",
        re.compile(r"动力触探|钎探|持力层|软弱|古井|墓穴|空洞|均匀性")),
    # ── 地基处理主轴 (G04 核心) ──
    ("1A413030_087_0162", "1A413030-B106"): (
        "full", "本体·换填地基(垫层)施工要点: 适用浅层软弱土厚0.5~3m; 材料素土/灰土/砂石/粉煤灰; 灰土配合比2:8或3:7; 分层厚度200~300mm; 压实系数灰土粉煤灰≥0.95其他≥0.97; 粉煤灰最上层覆盖300~500mm土层 — G04 换填判分眼",
        re.compile(r"换填|垫层|灰土|配合比|压实系数|分层厚度|粉煤灰|砂石|软弱土")),
    ("1A413030_088_0163", "1A413031-R02"): (
        "full", "本体·夯实/强夯/CFG/换填接缝: 强夯夯锤质量10~60t/锤底静接地压力25~80kPa/排气孔直径300~400mm; CFG桩四工艺适用(长螺旋钻孔/中心压灌/振动沉管/泥浆护壁); 换填接缝不得在柱基墙角承重窗间墙下/上下层缝距≥500mm夯压密实 — G04 地基处理本体",
        re.compile(r"强夯|夯锤|接地压力|排气孔|CFG|长螺旋|振动沉管|换填|接缝|缝距")),
    ("1A413030_089_0164", "1A413031-R09"): (
        "full", "本体·复合地基方法选型(注浆/灰土挤密/振冲/夯实水泥土/搅拌桩/旋喷): 灰土挤密桩(水位以上粉土黏性土素填土湿陷性黄土/厚3~15m/含水量>24%或饱和度>65%需试验); 振冲碎石桩(含泥量≤5%不用风化易碎); 夯实水泥土桩(有机质≤5%/机械成孔≤15m人工≤6m); 水泥土搅拌桩(淤泥软可塑黏性土粉细砂/不适用大孤石密实砂土渗流区); 旋喷桩(水灰比0.8~1.5/单双三管); 注浆加固(砂土粉土黏性土填土/软弱土用双液浆/地下水流动禁单液/既有建筑监测多孔间隔注浆) — G04 地基处理选型判分眼",
        re.compile(r"灰土挤密|振冲|碎石桩|夯实水泥土|水泥土搅拌|旋喷|注浆加固|复合地基|含水量|饱和度|双液浆|含泥量")),
    # ── 地基处理验收 (G04 验收侧) ──
    ("1A434000_064_0095", "1A434000-B007"): (
        "full", "本体·地基与基础工程质量检验: 地基承载力检验数量每300m²≥1点/超3000m²每500m²≥1点/每单位工程≥3点; 强夯地基施工后检验承载力/强度/变形指标; 土方回填检标高及压实系数 — G04 验收检测判分眼",
        re.compile(r"地基承载力|检验数量|压实系数|强夯.*检验|变形指标|标高")),
    # ── 地基处理法规外延 (标🔵外延) ──
    ("1A422000_030_0050", "1A422000-B079"): (
        "ext", "🔵外延·法规·强夯/素土灰土地基: 强夯施工后检测间隔砂土≥7d/粉性土≥14d/黏性土≥28d; 素土灰土施工含水量最优含水量±2%; 强夯先边后中由内而外隔行跳打",
        re.compile(r"强夯|7d|14d|28d|含水量|最优含水量|隔行跳打|分区")),
    ("1A422000_031_0051", "1A422000-B169"): (
        "ext", "🔵外延·法规·高压喷射注浆/搅拌桩/CFG: 高压喷射注浆前工艺试验≥2根/敏感区速凝浆液隔孔喷射/施工期邻近禁抽水; 搅拌桩水灰比单双轴0.55~0.65三轴1.5~2.0停浆面高于桩顶300~500mm; CFG坍落度长螺旋160~200mm褥垫层夯填度≤0.9",
        re.compile(r"高压喷射|工艺试验|水灰比|停浆面|坍落度|褥垫层|速凝")),
}

# 卡级噪声剔除 (混卡 chunk 的跨考点卡 / G01开挖卡)
NOISE_BLOCK = re.compile(r"分层厚度宜控制在3m|逆作法的基坑开挖|预留150|降水工作应持续|土钉墙|排桩|地下连续墙|锚杆")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A413000_084_0157(leaf B039 名为'基坑验槽要求'实为深基坑开挖控制)": "TC 内容=深基坑分层≤3m/预留土层150~300mm/水位降至坑底500mm/逆作盆式开挖 —— 名实不符: 名义验槽, 内容是【G01 基坑开挖与降水】本体, 整 chunk 绕开归 G01",
    "1A413000_078~079(土钉墙/咬合桩/型钢水泥土搅拌墙/基坑支护施工 B023~B032)": "土钉墙/咬合桩围护墙/型钢水泥土搅拌墙/复合土钉墙 —— 属【B02 基坑支护选型】territory(支护≠验槽/地基处理), 绕开归 B02",
    "1A413030_094~095(混凝土基础施工 1A413033-R*)": "基础底板钢筋/基础混凝土施工/条形基础/大体积混凝土 —— 属【混凝土基础施工/Q02 大体积】territory, 绕开",
    "1A413000_072_0138(高程测设 B031/B053/B085)": "地面上点高程测设/细部点高程/高程传递 —— 属【测量】territory, 绕开归测量考点",
    "1A413000_075_0143(岩土按开挖难易分八类 B042)": "岩土分类(按开挖难易) —— 属【G01 开挖方法选择背景/放坡机械选型】, 与验槽/地基处理选型间接相关, 不作 G04 本体采分(若需可作🔵但本 pack 不收, 避免与 G01 重叠)",
    "1A422000_028_0048(基坑开挖与回填法规 B036 + 地下防水 B029)": "基坑开挖与回填施工规定(严禁超挖/软土高差)=G01 法规; 地下防水=防水考点 —— 绕开归 G01/防水",
    "1A434020_082~083(地基与基础工程验收程序/条件 B011/B012)": "地基与基础工程验收所需条件/验收程序 —— 属【A01 检验批/分部分项验收程序】territory(验收程序≠验槽地基处理本体), 绕开归 A01; G04 仅取 1A434000_064 的承载力检验频率/检测内容作验收侧",
    "1A436000_007~008/110(危大基坑情形 B040/B041 + 基坑应急 B042 + 坍塌预防 B038)": "危大基坑工程情形/基坑支护降水危大/基坑应急措施/坍塌事故预防 —— 属【J01 危大论证/S02 安全管理】territory, 绕开",
    "跨章 B041/B042 同后缀码命中(网络计划/招标/成本/项目经理/绿色建造的 -B041/-B042)": "1A433000-B041 网络计划/1A432000-B041 总承包/1A431000-B041 项目经理/1A435000-B041 成本/1A437000-B041 收集存放 —— 仅 leaf_id 后缀 'B041/B042' 撞码, 与验槽/地基处理无关, 绕开",
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
            if card_keep and not card_keep.search(desc) and not re.search(r"验槽|触探|换填|强夯|地基处理|注浆|承载力|压实", desc):
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
        "考点": "G04 地基验槽与地基处理",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 28; primary 1A413048 天然地基验槽 / supporting 1A413000-B041 天然地基验槽 / 1A413025 基坑验槽要求; 三 code resolve 名实相符)",
        "编译库覆盖说明": (
            "G04 弹药本体集中在 验槽轴(1A413000_086_0159 天然地基验槽: 验槽资料/不触探三情况/观察法 + 1A413030_087_0160 "
            "轻型动力触探/钎探) + 地基处理轴(1A413030_087_0162 换填垫层 + 088_0163 强夯CFG接缝 + 089_0164 复合地基六法选型: "
            "灰土挤密/振冲/夯实水泥土/搅拌桩/旋喷/注浆加固) + 验收侧(1A434000_064_0095 地基承载力检验频率) + 法规外延"
            "(1A422000_030/031 强夯检测时间7/14/28d + 高压喷射/搅拌桩/CFG法规)。教材锚【厚实】(验槽+地基处理 RichLeaf 编译库"
            "覆盖好)。⚠️ leaf 1A413000-B039(名'基坑验槽要求')名实不符=G01开挖, 已整 chunk 绕开。"
            "数值判读锚(不触探阈值/换填参数/强夯参数/检测时间)教材+真题双锚, 真题侧 _G04_exam_evidence.json 补足。"),
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"G04 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:54]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
